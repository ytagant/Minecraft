import os
import io
import json
import time
import subprocess
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

# ================= कॉन्फ़िगरेशन =================
SERVICE_ACCOUNT_FILE = 'service_account.json'
# गिटहब सीक्रेट्स से मेन फोल्डर की ID
MAIN_FOLDER_ID = os.environ.get('MAIN_FOLDER_ID')
TOKENS = ['token1.json', 'token2.json', 'token3.json', 'token4.json']
# ===============================================

def run_with_retry(func, max_retries=3, delay=2, *args, **kwargs):
    """नेटवर्क क्रैश से बचाने के लिए 3-स्टेप रीट्राइ सिस्टम"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ एरर: {e}. {delay} सेकंड बाद दोबारा कोशिश (Attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
    print("❌ 3 बार कोशिश करने के बाद नेटवर्क फेल हो गया। सिस्टम सुरक्षित रूप से बंद हो रहा है।")
    return None

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def find_or_create_folder(drive_service, folder_name, parent_id, create_if_missing=False):
    """ड्राइव में फोल्डर ढूंढेगा, न मिलने पर (अगर कहा गया हो) तो नया बना देगा"""
    query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = results.get('files', [])
    
    if folders:
        return folders[0]['id']
    
    if create_if_missing:
        print(f"📁 '{folder_name}' नहीं मिला। नया फोल्डर क्रिएट किया जा रहा है...")
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        return folder.get('id')
    return None

def download_video_and_tokens(drive_service, main_folder_id):
    """मेन फोल्डर से टोकन और Ready_To_Upload से वीडियो डाउनलोड करेगा"""
    print("🔍 ड्राइव स्कैन की जा रही है...")
    
    # 1. मेन फोल्डर से सारे token.json डाउनलोड करना
    tokens_query = f"'{main_folder_id}' in parents and name contains 'token' and trashed=false"
    token_files = drive_service.files().list(q=tokens_query, fields='files(id, name)').execute().get('files', [])
    for t_file in token_files:
        request = drive_service.files().get_media(fileId=t_file['id'])
        with io.FileIO(t_file['name'], 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: _, done = downloader.next_chunk()
    print("✅ टोकन फाइलें डाउनलोड हो गईं।")

    # 2. Ready_To_Upload फोल्डर ढूंढना
    ready_folder_id = find_or_create_folder(drive_service, 'Ready_To_Upload', main_folder_id, False)
    if not ready_folder_id:
        print("❌ 'Ready_To_Upload' फोल्डर नहीं मिला।")
        return None
        
    # 3. उसके अंदर वीडियो का फोल्डर ढूंढना
    video_folders = drive_service.files().list(
        q=f"'{ready_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false", 
        fields='files(id, name)'
    ).execute().get('files', [])
    
    if not video_folders:
        print("📁 'Ready_To_Upload' में कोई नया वीडियो फोल्डर नहीं है।")
        return None
        
    target_folder = video_folders[0]
    folder_id = target_folder['id']
    print(f"⬇️ डाउनलोड शुरू: फोल्डर '{target_folder['name']}'")
    
    files = drive_service.files().list(q=f"'{folder_id}' in parents and trashed=false", fields='files(id, name)').execute().get('files', [])
    
    for f in files:
        if f['name'].endswith('.mp4') or f['name'].endswith('.json'):
            request = drive_service.files().get_media(fileId=f['id'])
            filename = "input_video.mp4" if f['name'].endswith('.mp4') else "metadata.json"
            with io.FileIO(filename, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done: _, done = downloader.next_chunk()
                
    return folder_id

def edit_video_with_ffmpeg():
    """मिररिंग, 90px पतला बैनर और 5% ओपेसिटी वाला पारदर्शी वॉटरमार्क"""
    print("🎬 FFmpeg एडिटिंग शुरू हो रही है...")
    
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', 'input_video.mp4',
        '-vf', (
            "hflip," # मिरर
            "scale=1080:1830," # हाइट सिकुड़ी
            "pad=1080:1920:0:90:black," # 90 पिक्सल का पतला टॉप बैनर
            "drawtext=text='CraftVibe':fontcolor=white:fontsize=45:x=(w-text_w)/2:y=20:fontw=bold," # बैनर टेक्स्ट
            "drawtext=text='CraftVibe':fontcolor=white@0.05:fontsize=90:x='(w-text_w)/2+sin(t)*150':y=(h-text_h)/2:fontw=bold" # 5% पारदर्शी फ्लोटिंग वॉटरमार्क
        ),
        '-c:a', 'copy',
        'final_edit.mp4'
    ]
    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("✅ एडिटिंग मुकम्मल!")
    return 'final_edit.mp4'

def upload_to_youtube(video_file, metadata):
    original_title = metadata.get('title', 'Minecraft Shorts')[:80]
    final_title = f"{original_title} #shorts"
    final_description = f"{original_title}\n\n🔥 Subscribe to CraftVibe for daily Minecraft Shorts!\n#minecraft #minecraftshorts #mcpe #craftvibe"
    
    body = {
        'snippet': {'title': final_title, 'description': final_description, 'tags': ["minecraft", "mcpe", "craftvibe"], 'categoryId': '20'},
        'status': {'privacyStatus': 'public', 'madeForKids': False}
    }
    
    for token in TOKENS:
        if not os.path.exists(token): continue
        print(f"🔄 टोकन {token} से अपलोड ट्राई कर रहे हैं...")
        
        creds = Credentials.from_authorized_user_file(token, ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        
        try:
            media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status: print(f"⏳ अपलोड हो रहा है... {int(status.progress() * 100)}%")
                    
            print(f"✅ वीडियो लाइव हो गई! ID: {response['id']}")
            return True
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print(f"⛔ {token} का कोटा खत्म।")
            else:
                print(f"❌ यूट्यूब एरर: {e}")
    return False

def cleanup_and_move(drive_service, main_folder_id, folder_id_to_move):
    """Uploaded_Success ढूंढेगा (नहीं होगा तो बनाएगा) और वीडियो फोल्डर वहां शिफ्ट करेगा"""
    success_folder_id = find_or_create_folder(drive_service, 'Uploaded_Success', main_folder_id, create_if_missing=True)
    
    print("🧹 फोल्डर को 'Uploaded_Success' में शिफ्ट किया जा रहा है...")
    file_metadata = drive_service.files().get(fileId=folder_id_to_move, fields='parents').execute()
    previous_parents = ",".join(file_metadata.get('parents'))
    
    drive_service.files().update(
        fileId=folder_id_to_move,
        addParents=success_folder_id,
        removeParents=previous_parents
    ).execute()
    print("✨ सफाई मुकम्मल! गिटहब अब सो जाएगा।")

def main():
    if not MAIN_FOLDER_ID:
        print("❌ MAIN_FOLDER_ID सीक्रेट सेट नहीं है!")
        return

    print("🚀 CraftVibe आटोमेशन रोबोट चालू हो गया है...\n")
    drive_service = run_with_retry(get_drive_service)
    if not drive_service: return
    
    folder_id_to_move = run_with_retry(download_video_and_tokens, max_retries=3, delay=3, drive_service=drive_service, main_folder_id=MAIN_FOLDER_ID)
    if not folder_id_to_move: return
    
    with open("metadata.json", 'r', encoding='utf-8') as f:
        metadata = json.load(f)
        
    final_video = run_with_retry(edit_video_with_ffmpeg)
    
    upload_success = run_with_retry(upload_to_youtube, max_retries=3, delay=5, video_file=final_video, metadata=metadata)
    
    if upload_success:
        run_with_retry(cleanup_and_move, max_retries=3, delay=2, drive_service=drive_service, main_folder_id=MAIN_FOLDER_ID, folder_id_to_move=folder_id_to_move)

if __name__ == '__main__':
    main()
    
