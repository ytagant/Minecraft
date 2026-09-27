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

# ================= کنفیگریشن =================
SERVICE_ACCOUNT_FILE = 'service_account.json'
MAIN_FOLDER_ID = os.environ.get('MAIN_FOLDER_ID')
TOKENS = ['token1.json', 'token2.json', 'token3.json', 'token4.json']
# ===============================================

def run_with_retry(func, max_retries=3, delay=2, *args, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ ایرر: {e}. {delay} سیکنڈ بعد دوبارہ کوشش (Attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
    print("❌ 3 بار کوشش کرنے کے بعد پروسیس فیل ہو گیا۔")
    return None

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def find_or_create_folder(drive_service, folder_name, parent_id, create_if_missing=False):
    query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = results.get('files', [])
    
    if folders:
        return folders[0]['id']
    
    if create_if_missing:
        print(f"📁 '{folder_name}' نہیں ملا۔ نیا فولڈر کریٹ کیا جا رہا ہے...")
        folder_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        return folder.get('id')
    return None

def download_video_and_tokens(drive_service, main_folder_id):
    print("🔍 ڈرائیو سکین کی جا رہی है...")
    tokens_query = f"'{main_folder_id}' in parents and name contains 'token' and trashed=false"
    token_files = drive_service.files().list(q=tokens_query, fields='files(id, name)').execute().get('files', [])
    for t_file in token_files:
        request = drive_service.files().get_media(fileId=t_file['id'])
        with io.FileIO(t_file['name'], 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: _, done = downloader.next_chunk()

    ready_folder_id = find_or_create_folder(drive_service, 'Ready_To_Upload', main_folder_id, False)
    if not ready_folder_id:
        raise Exception("❌ 'Ready_To_Upload' فولڈر نہیں ملا۔")
        
    video_folders = drive_service.files().list(
        q=f"'{ready_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false", 
        fields='files(id, name)'
    ).execute().get('files', [])
    
    if not video_folders:
        raise Exception("📁 'Ready_To_Upload' میں کوئی نیا ویڈیو فولڈر نہیں ہے۔")
        
    target_folder = video_folders[0]
    folder_id = target_folder['id']
    print(f"⬇️ ڈاؤنلوڈ شروع: فولڈر '{target_folder['name']}'")
    
    files = drive_service.files().list(q=f"'{folder_id}' in parents and trashed=false", fields='files(id, name)').execute().get('files', [])
    
    video_downloaded = False
    for f in files:
        if f['name'].endswith('.mp4') or f['name'].endswith('.json'):
            request = drive_service.files().get_media(fileId=f['id'])
            filename = "input_video.mp4" if f['name'].endswith('.mp4') else "metadata.json"
            with io.FileIO(filename, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done: _, done = downloader.next_chunk()
            if filename == "input_video.mp4": video_downloaded = True
            
    if not video_downloaded:
        raise Exception("❌ اس فولڈر میں کوئی .mp4 ویڈیو فائل نہیں ملی!")
        
    return folder_id

def edit_video_with_ffmpeg():
    print("🎬 FFmpeg ایڈیٹنگ شروع ہو रही ہے (بغیر مرر کے)...")
    
    # اوبنٹو سرور के فونٹ का سیدھا रास्ता
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', 'input_video.mp4',
        '-vf', (
            f"scale=1080:1830,"
            f"pad=1080:1920:0:90:black,"
            f"drawtext=fontfile='{font_path}':text='CraftVibe':fontcolor=white:fontsize=45:x=(w-text_w)/2:y=20,"
            f"drawtext=fontfile='{font_path}':text='CraftVibe':fontcolor=white@0.05:fontsize=90:x=(w-text_w)/2+sin(t)*150:y=(h-text_h)/2"
        ),
        '-c:a', 'copy',
        'final_edit.mp4'
    ]
    
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ FFmpeg का اصل ایرر:\n{result.stderr}")
        raise Exception("FFmpeg کمانڈ کریش हो गई।")
        
    print("✅ ایڈیٹنگ مکمل!")
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
        print(f"🔄 ٹوکن {token} سے اپلوڈ ٹرائی کر رہے ہیں...")
        
        creds = Credentials.from_authorized_user_file(token, ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        
        try:
            media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status: print(f"⏳ اپلوڈ ہو रहा है... {int(status.progress() * 100)}%")
                    
            print(f"✅ ویڈیو لائیو हो गई! ID: {response['id']}")
            return True
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print(f"⛔ {token} का कोटह ختم۔")
            else:
                print(f"❌ یوٹیوب ایرر: {e}")
    return False

def cleanup_and_move(drive_service, main_folder_id, folder_id_to_move):
    success_folder_id = find_or_create_folder(drive_service, 'Uploaded_Success', main_folder_id, create_if_missing=True)
    print("🧹 فولڈر को 'Uploaded_Success' میں شفٹ किया जा रहा है...")
    file_metadata = drive_service.files().get(fileId=folder_id_to_move, fields='parents').execute()
    previous_parents = ",".join(file_metadata.get('parents'))
    
    drive_service.files().update(
        fileId=folder_id_to_move,
        addParents=success_folder_id,
        removeParents=previous_parents
    ).execute()
    print("✨ صفائی مکمل! گٹ ہب اب سو جائے گا۔")

def main():
    if not MAIN_FOLDER_ID:
        print("❌ MAIN_FOLDER_ID سیکرٹ سیٹ नहीं है!")
        return

    print("🚀 CraftVibe آٹومेशन روبوٹ چالو ہو गया है...\n")
    drive_service = run_with_retry(get_drive_service)
    if not drive_service: return
    
    folder_id_to_move = run_with_retry(download_video_and_tokens, max_retries=3, delay=3, drive_service=drive_service, main_folder_id=MAIN_FOLDER_ID)
    if not folder_id_to_move: return
    
    metadata = {}
    if os.path.exists("metadata.json"):
        with open("metadata.json", 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
    final_video = run_with_retry(edit_video_with_ffmpeg)
    if not final_video:
        print("❌ ویڈیو ایڈیٹنگ فیل ہو गई है, اس लिए अपلوड रोक दिया गया है।")
        return
    
    upload_success = run_with_retry(upload_to_youtube, max_retries=3, delay=5, video_file=final_video, metadata=metadata)
    
    if upload_success:
        run_with_retry(cleanup_and_move, max_retries=3, delay=2, drive_service=drive_service, main_folder_id=MAIN_FOLDER_ID, folder_id_to_move=folder_id_to_move)

if __name__ == '__main__':
    main()
        
