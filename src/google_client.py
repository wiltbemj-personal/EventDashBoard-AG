import io
import os
import mimetypes
from typing import List, Dict, Any, Tuple, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config import CREDENTIALS_JSON_PATH, TOKEN_JSON_PATH

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

def get_credentials() -> Optional[Credentials]:
    """Retrieves and refreshes Google OAuth2 credentials."""
    creds = None
    if TOKEN_JSON_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_JSON_PATH), SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_JSON_PATH, "w") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                print(f"Failed to refresh credentials: {e}")
                creds = None
        
        if not creds:
            if not CREDENTIALS_JSON_PATH.exists():
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_JSON_PATH), SCOPES
            )
            # Use local server for desktop authentication
            creds = flow.run_local_server(port=0)
            with open(TOKEN_JSON_PATH, "w") as token_file:
                token_file.write(creds.to_json())
                
    return creds

def get_drive_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google Credentials not found or unauthorized.")
    return build("drive", "v3", credentials=creds)

def get_gmail_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google Credentials not found or unauthorized.")
    return build("gmail", "v1", credentials=creds)

def get_sheets_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google Credentials not found or unauthorized.")
    return build("sheets", "v4", credentials=creds)

# --- Google Drive Helpers ---

def find_drive_folder_id(folder_name: str) -> Optional[str]:
    """Finds the ID of a Google Drive folder by name."""
    try:
        service = get_drive_service()
        query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_name}' and trashed = False"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        return None
    except Exception as e:
        print(f"Error searching for Drive folder '{folder_name}': {e}")
        return None

def list_files_in_folder(folder_id: str) -> List[Dict[str, Any]]:
    """Lists all files in a specific Google Drive folder."""
    try:
        service = get_drive_service()
        query = f"'{folder_id}' in parents and trashed = False"
        results = service.files().list(
            q=query, fields="files(id, name, mimeType, createdTime)"
        ).execute()
        return results.get("files", [])
    except Exception as e:
        print(f"Error listing files in folder {folder_id}: {e}")
        return []

def download_drive_file(file_id: str) -> Tuple[bytes, str]:
    """Downloads a file from Google Drive and returns its bytes and mime type."""
    service = get_drive_service()
    
    # First, get file metadata to know the mime type
    metadata = service.files().get(fileId=file_id, fields="mimeType, name").execute()
    mime_type = metadata.get("mimeType", "application/octet-stream")
    
    # Handle Google Docs formats if needed (export them), otherwise download directly
    if mime_type.startswith("application/vnd.google-apps."):
        # e.g., export Google Docs to PDF
        if "document" in mime_type:
            export_mime = "application/pdf"
            request = service.files().export_media(fileId=file_id, mimeType=export_mime)
            mime_type = export_mime
        elif "spreadsheet" in mime_type:
            export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            request = service.files().export_media(fileId=file_id, mimeType=export_mime)
            mime_type = export_mime
        else:
            raise ValueError(f"Cannot download Google Workspace shortcut file: {metadata.get('name')}")
    else:
        request = service.files().get_media(fileId=file_id)
        
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    return fh.getvalue(), mime_type

# --- Gmail Helpers ---

def list_emails_with_label(label_name: str) -> List[Dict[str, Any]]:
    """Lists recent email messages matching a specific label name."""
    try:
        service = get_gmail_service()
        
        # 1. Resolve label name to Label ID
        labels_results = service.users().labels().list(userId="me").execute()
        labels = labels_results.get("labels", [])
        
        label_id = None
        for label in labels:
            if label["name"].lower() == label_name.lower():
                label_id = label["id"]
                break
                
        if not label_id:
            # If the label doesn't exist, we can't find emails
            print(f"Gmail label '{label_name}' not found.")
            return []
            
        # 2. Get list of messages
        results = service.users().messages().list(
            userId="me", labelIds=[label_id], maxResults=100
        ).execute()
        return results.get("messages", [])
    except Exception as e:
        print(f"Error fetching Gmail messages for label '{label_name}': {e}")
        return []

def get_email_details(message_id: str) -> Dict[str, Any]:
    """Retrieves full body and attachments for an email message."""
    service = get_gmail_service()
    message = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    
    headers = message.get("payload", {}).get("headers", [])
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
    date_str = next((h["value"] for h in headers if h["name"].lower() == "date"), "")
    
    body = ""
    attachments = []
    
    def parse_parts(parts):
        nonlocal body
        for part in parts:
            mime_type = part.get("mimeType", "")
            body_data = part.get("body", {}).get("data", "")
            
            # Text body
            if mime_type == "text/plain" and body_data:
                import base64
                body += base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
            elif mime_type == "text/html" and not body and body_data:
                # If we don't have text/plain yet, store HTML as fallback
                import base64
                from bs4 import BeautifulSoup
                html_content = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                body += BeautifulSoup(html_content, "html.parser").get_text(separator="\n")
                
            # Nested parts (e.g. multipart/alternative)
            if "parts" in part:
                parse_parts(part["parts"])
                
            # Attachment info
            if part.get("filename") and part.get("body", {}).get("attachmentId"):
                attachments.append({
                    "filename": part["filename"],
                    "mimeType": mime_type,
                    "attachmentId": part["body"]["attachmentId"],
                    "size": part["body"].get("size", 0)
                })

    payload = message.get("payload", {})
    if "parts" in payload:
        parse_parts(payload["parts"])
    else:
        # Single-part email
        body_data = payload.get("body", {}).get("data", "")
        if body_data:
            import base64
            body = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
            
    return {
        "id": message_id,
        "subject": subject,
        "from": sender,
        "date": date_str,
        "body": body.strip(),
        "attachments": attachments
    }

def download_gmail_attachment(message_id: str, attachment_id: str) -> bytes:
    """Downloads an attachment from a specific Gmail message."""
    service = get_gmail_service()
    attachment = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    import base64
    return base64.urlsafe_b64decode(attachment.get("data", ""))
