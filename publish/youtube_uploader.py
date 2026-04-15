"""
youtube_uploader.py
Uploads a rendered MP4 to YouTube as a Short.
First run opens a browser for OAuth — saves token to token.json for subsequent runs.
"""

import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = os.environ.get(
    "YOUTUBE_CLIENT_SECRET",
    str(Path(__file__).resolve().parent.parent / "client_secret.json")
)
TOKEN_FILE = str(Path(__file__).resolve().parent.parent / "token.json")


def _get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def _sanitize_title(title: str) -> str:
    title = title.replace("<", "").replace(">", "").strip()
    if not title:
        title = "Reddit AITA Story"
    return title[:100]


def upload(video_path: str, title: str, description: str = "", tags: list = None) -> str:
    """Upload a video to YouTube. Returns the video ID."""
    title = _sanitize_title(title)
    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22",  # People & Blogs
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
            "embeddable": True,
            "publicStatsViewable": True,
            "license": "youtube",
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"[youtube] Uploading: {Path(video_path).name}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[youtube] {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"[youtube] Done — https://youtube.com/shorts/{video_id}")
    return video_id
