import os
import json
import time
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# گوگل ڈرائیو سروس اکاؤنٹ فائل (جو گٹ ہب سیکرٹس سے بنے گی)
SERVICE_ACCOUNT_FILE = 'service_account.json'

# یوٹیوب API ٹوکنز کی لسٹ (4 پروجیکٹس کے لیے)
TOKENS = ['token1.json', 'token2.json', 'token3.json', 'token4.json']

def get_drive_service():
    """گوگل ڈرائیو سے کنیکٹ کرنے کے لیے سروس اکاؤنٹ کا استعمال"""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_youtube_service(token_file):
    """یوٹیوب API سے کنیکٹ کرنے کے لیے ٹوکن کا استعمال"""
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, ['https://www.googleapis.com/auth/youtube.upload'])
        return build('youtube', 'v3', credentials=creds)
    return None

def upload_video(youtube, video_file, metadata):
    """CraftVibe کی برانڈنگ اور SEO کے ساتھ ویڈیو اپلوڈ کرنا"""
    original_title = metadata.get('title', 'Minecraft Shorts')
    if len(original_title) > 85:
        original_title = original_title[:80] + "..."
        
    final_title = f"{original_title} #shorts"
    final_description = (
        f"{original_title}\n\n"
        f"🔥 Subscribe to CraftVibe for daily Minecraft Shorts!\n"
        f"👍 Drop a like if you enjoyed this video!\n\n"
        f"#minecraft #minecraftshorts #mcpe #gaming #minecraftmemes #craftvibe"
    )
    tags = ["minecraft", "minecraft shorts", "mcpe", "viral minecraft", "minecraft funny", "gaming shorts", "minecraft hacks", "craftvibe"]

    body = {
        'snippet': {
            'title': final_title,
            'description': final_description,
            'tags': tags,
            'categoryId': '20'
        },
        'status': {
            'privacyStatus': 'public',
            'madeForKids': False,
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"⏳ Uploading... {int(status.progress() * 100)}%")
            
    print(f"✅ ویڈیو کامیابی سے اپلوڈ ہو گئی! ID: {response['id']}")
    return response['id']

def main():
    print("🚀 CraftVibe آٹو اپلوڈر شروع ہو رہا ہے...")
    
    # نوٹ: اصل سکرپٹ میں یہاں ڈرائیو سے فولڈر ڈاؤن لوڈ کرنے کا کوڈ آئے گا
    # فرض کریں کہ ہم نے ڈرائیو سے ویڈیو اور میٹا ڈیٹا ڈاؤن لوڈ کر لیا ہے:
    video_file = "downloaded_video.mp4"
    metadata_file = "metadata.json"
    
    if not os.path.exists(metadata_file) or not os.path.exists(video_file):
        print("❌ اپلوڈ کرنے کے لیے کوئی نئی ویڈیو نہیں ملی۔")
        return

    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    # 🔄 API روٹیشن کا جادو (Token Rotation Logic)
    upload_success = False
    
    for token in TOKENS:
        print(f"🔍 ٹوکن چیک ہو رہا ہے: {token}")
        youtube_service = get_youtube_service(token)
        
        if not youtube_service:
            print(f"⚠️ {token} نہیں ملا۔ اگلا ٹوکن ٹرائی کر رہے ہیں...")
            continue
            
        try:
            upload_video(youtube_service, video_file, metadata)
            upload_success = True
            print(f"🎉 اپلوڈ مکمل! ({token} استعمال کیا گیا)")
            break # اپلوڈ ہو گیا، تو لوپ سے باہر نکل آئیں
            
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print(f"⛔ {token} کی روزانہ کی لمٹ (Quota) ختم ہو گئی ہے۔ اگلا ٹوکن استعمال کر رہے ہیں...")
            else:
                print(f"❌ اپلوڈ کے دوران ایرر: {e}")
                break

    if upload_success:
        print("🧹 ڈرائیو سے فولڈر کو 'Uploaded_Success' میں منتقل کیا جا رہا ہے...")
        # (ڈرائیو API کے ذریعے فولڈر موو کرنے کی کمانڈ)
        print("✨ کام مکمل ہو گیا! گٹ ہب اب سو جائے گا۔")
    else:
        print("❌ تمام ٹوکنز فیل ہو گئے یا کوٹہ ختم ہو گیا ہے۔")

if __name__ == '__main__':
    main()
  
