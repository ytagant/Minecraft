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
TOKENS = ['token1.json', 'token2.json', 'token3.json', 'token4.json']

# यहां अपनी गूगल ड्राइव के दोनों फोल्डर्स की ID डालें
READY_TO_UPLOAD_ID = 'आपकी_READY_TO_UPLOAD_फोल्डर_की_ID_यहाँ_डालें'
UPLOADED_SUCCESS_ID = 'आपकी_UPLOADED_SUCCESS_फोल्डर_की_ID_यहाँ_डालें'
# ===============================================

def run_with_retry(func, max_retries=3, delay=2, *args, **kwargs):
    """नेटवर्क क्रैश से बचाने के लिए 3-स्टेप रीट्राइ सिस्टम"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ एरर: {e}. {delay} सेकंड बाद दोबारा कोशिश कर रहे हैं (Attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
    print("❌ 3 बार कोशिश करने के बाद भी नेटवर्क फेल हो गया। सिस्टम सुरक्षित रूप से बंद हो रहा है।")
    return False

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_youtube_service(token_file):
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, ['https://www.googleapis.com/auth/youtube.upload'])
        return build('youtube', 'v3', credentials=creds)
    return None

def download_video_data(drive_service):
    """ड्राइव से सिर्फ 1 वीडियो का फोल्डर ढूंढेगा और फाइलें डाउनलोड करेगा"""
    print("🔍 ड्राइव स्कैन की जा रही है...")
    results = drive_service.files().list(
        q=f"'{READY_TO_UPLOAD_ID}' in parents and mimeType='application/vnd.google-apps.folder'",
        spaces='drive', fields='files(id, name)'
    ).execute()
    
    folders = results.get('files', [])
    if not folders:
        print("📁 'Ready_To_Upload' फोल्डर खाली है। कोई नई वीडियो नहीं मिली।")
        return None
        
    target_folder = folders[0] # पहला फोल्डर उठाया
    folder_id = target_folder['id']
    
    print(f"⬇️ डाउनलोड शुरू: {target_folder['name']}")
    files = drive_service.files().list(
        q=f"'{folder_id}' in parents", fields='files(id, name)'
    ).execute().get('files', [])
    
    video_file = "input_video.mp4"
    metadata_file = "metadata.json"
    
    for f in files:
        request = drive_service.files().get_media(fileId=f['id'])
        filename = video_file if f['name'].endswith('.mp4') else metadata_file
        
        with io.FileIO(filename, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
    return folder_id

def edit_video_with_ffmpeg():
    """प्रोफेशनल एडिटिंग: मिररिंग, पतला बैनर और 7% पारदर्शी तैरता वॉटरमार्क"""
    print("🎬 FFmpeg एडिटिंग शुरू हो रही है...")
    input_video = "input_video.mp4"
    output_video = "final_edit.mp4"
    
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', input_video,
        '-vf', (
            "hflip," # वीडियो मिरर की गई
            "scale=1080:1830," # ऊपर बैनर के लिए जगह बनाई
            "pad=1080:1920:0:90:black," # 90 पिक्सल का पतला ब्लैक बैनर
            "drawtext=text='CraftVibe':fontcolor=white:fontsize=45:x=(w-text_w)/2:y=20:fontw=bold," # बैनर में टेक्स्ट
            "drawtext=text='CraftVibe':fontcolor=white@0.07:fontsize=90:x='(w-text_w)/2+sin(t)*150':y=(h-text_h)/2:fontw=bold" # तैरता हल्का वॉटरमार्क
        ),
        '-c:a', 'copy', # ऑडियो बिना छेड़े कॉपी
        output_video
    ]
    
    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("✅ एडिटिंग शानदार तरीके से पूरी हुई!")
    return output_video

def upload_video(youtube, video_file, metadata):
    original_title = metadata.get('title', 'Minecraft Shorts')
    if len(original_title) > 85:
        original_title = original_title[:80] + "..."
        
    final_title = f"{original_title} #shorts"
    final_description = f"{original_title}\n\n🔥 Subscribe to CraftVibe for daily Minecraft Shorts!\n#minecraft #minecraftshorts #mcpe #craftvibe"
    
    body = {
        'snippet': {'title': final_title, 'description': final_description, 'tags': ["minecraft", "mcpe", "craftvibe"], 'categoryId': '20'},
        'status': {'privacyStatus': 'public', 'madeForKids': False}
    }
    
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"⏳ अपलोड हो रहा है... {int(status.progress() * 100)}%")
            
    print(f"✅ वीडियो लाइव हो गई! ID: {response['id']}")
    return True

def move_folder_to_success(drive_service, folder_id):
    """सफाई: फोल्डर को Uploaded_Success में मूव करना"""
    print("🧹 फोल्डर को 'Uploaded_Success' में शिफ्ट किया जा रहा है...")
    file_metadata = drive_service.files().get(fileId=folder_id, fields='parents').execute()
    previous_parents = ",".join(file_metadata.get('parents'))
    
    drive_service.files().update(
        fileId=folder_id,
        addParents=UPLOADED_SUCCESS_ID,
        removeParents=previous_parents
    ).execute()
    print("✨ सफाई मुकम्मल! गिटहब अब सो जाएगा।")

def main():
    print("🚀 CraftVibe आटोमेशन रोबोट चालू हो गया है...\n")
    
    drive_service = run_with_retry(get_drive_service)
    if not drive_service: return
    
    # 1. ड्राइव से डेटा डाउनलोड (रीट्राइ के साथ)
    folder_id = run_with_retry(download_video_data, max_retries=3, delay=3, drive_service=drive_service)
    if not folder_id: return
    
    with open("metadata.json", 'r', encoding='utf-8') as f:
        metadata = json.load(f)
        
    # 2. वीडियो एडिटिंग
    final_video = edit_video_with_ffmpeg()
    
    # 3. यूट्यूब पर अपलोड (4-टोकन रोटेशन + रीट्राइ के साथ)
    upload_success = False
    for token in TOKENS:
        print(f"🔄 टोकन {token} ट्राई कर रहे हैं...")
        youtube_service = get_youtube_service(token)
        if not youtube_service: continue
        
        try:
            # अपलोड को भी रीट्राइ लूप में डाला है
            success = run_with_retry(upload_video, max_retries=3, delay=5, youtube=youtube_service, video_file=final_video, metadata=metadata)
            if success:
                upload_success = True
                break
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print(f"⛔ {token} का कोटा खत्म। अगले टोकन पर जा रहे हैं...")
            else:
                print(f"❌ यूट्यूब API एरर: {e}")
                
    # 4. ड्राइव क्लीनअप
    if upload_success:
        run_with_retry(move_folder_to_success, max_retries=3, delay=2, drive_service=drive_service, folder_id=folder_id)
        
    # लोकल गिटहब सर्वर से टेम्पररी फाइलें डिलीट करना
    for temp_file in ["input_video.mp4", "final_edit.mp4", "metadata.json"]:
        if os.path.exists(temp_file): os.remove(temp_file)

if __name__ == '__main__':
    main()
    
