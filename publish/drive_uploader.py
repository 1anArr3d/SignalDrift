import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET = os.environ.get(
    "YOUTUBE_CLIENT_SECRET",
    str(Path(__file__).resolve().parent.parent / "client_secret.json")
)
TOKEN_FILE = str(Path(__file__).resolve().parent.parent / "drive_token.json")


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


def upload(video_path: str, filename: str, folder_id: str = None) -> str:
    """Upload a video to Google Drive. Returns the file ID."""
    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds)

    metadata = {"name": filename}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    file = service.files().create(body=metadata, media_body=media, fields="id").execute()

    file_id = file["id"]
    print(f"[drive] Uploaded: {filename} → https://drive.google.com/file/d/{file_id}")
    return file_id
