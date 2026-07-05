import os
import sys
import hashlib
import mimetypes
import uuid
from datetime import datetime
from typing import List, Dict, Any, Tuple

from src import config
from src import google_client
from src import sheets_client
from src import ai_extractor

def generate_local_file_id(file_path: str) -> str:
    """Generates a stable ID for a local file based on its path and modification time."""
    stat = os.stat(file_path)
    hash_input = f"{file_path}_{stat.st_mtime}_{stat.st_size}"
    return f"local_{hashlib.md5(hash_input.encode()).hexdigest()}"

def format_event(raw_extraction: Dict[str, Any], source_type: str, source_id: str, default_link: str = "") -> Dict[str, Any]:
    """Formats raw Gemini extraction dictionary into the official schema."""
    return {
        "ID": str(uuid.uuid4())[:8],
        "Title": raw_extraction.get("title", "Untitled Event").strip(),
        "Date": raw_extraction.get("date", datetime.now().strftime("%Y-%m-%d")).strip(),
        "Time": raw_extraction.get("time", "TBD").strip(),
        "Location": raw_extraction.get("location", "TBD").strip(),
        "Cost": str(raw_extraction.get("cost", 0.0)),
        "Type": raw_extraction.get("type", "Other").strip(),
        "Summary": raw_extraction.get("summary", "").strip(),
        "Link": raw_extraction.get("link") or default_link or "",
        "Source Type": source_type,
        "Source ID": source_id,
        "Processed Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Raw Detail": raw_extraction.get("details", "").strip()
    }

def run_ingestion(progress_callback=None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Runs the full ingestion pipeline from local, Drive, and Gmail.
    
    Returns:
        A tuple of (list of newly added event dicts, list of log messages).
    """
    logs = []
    new_events = []
    
    def log(msg: str):
        logs.append(msg)
        print(msg)
        if progress_callback:
            progress_callback(msg)

    log("Starting event ingestion pipeline...")
    
    # Verify Gemini key
    if not config.has_gemini_key():
        log("ERROR: GEMINI_API_KEY is not set in environment or .env. Aborting.")
        return [], logs

    # 1. Fetch already processed source IDs to avoid duplicates
    try:
        if config.has_google_credentials():
            processed_ids = sheets_client.get_processed_source_ids()
            log(f"Connected to Google Sheet database. Found {len(processed_ids)} already processed source items.")
        else:
            processed_ids = set()
            log("No Google credentials found; running in Local-Only mode. Duplicate tracking limited.")
    except Exception as e:
        processed_ids = set()
        log(f"Warning: Could not fetch processed source history from Google Sheet: {e}. Duplicate processing check skipped.")

    # 2. Ingest Local files
    local_files = [
        f for f in os.listdir(config.RAW_INPUTS_DIR) 
        if os.path.isfile(os.path.join(config.RAW_INPUTS_DIR, f)) and f != ".gitkeep"
    ]
    
    if local_files:
        log(f"Found {len(local_files)} file(s) in local raw inputs directory.")
        for filename in local_files:
            file_path = os.path.join(config.RAW_INPUTS_DIR, filename)
            source_id = generate_local_file_id(file_path)
            
            if source_id in processed_ids:
                log(f"  [Skip] Local file already processed: {filename}")
                continue
                
            log(f"  [Process] Local file: {filename}")
            try:
                mime_type, _ = mimetypes.guess_type(file_path)
                mime_type = mime_type or "application/octet-stream"
                
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
                    
                extraction = ai_extractor.extract_event_from_source(
                    content_bytes=content_bytes,
                    mime_type=mime_type
                )
                
                event = format_event(extraction, "Local File", source_id)
                new_events.append(event)
                log(f"    Extracted: {event['Title']} ({event['Date']})")
                
            except Exception as e:
                log(f"    Failed to process {filename}: {e}")
    else:
        log("No local files found in data/raw_inputs.")

    # 3. Ingest Google Drive files
    if config.has_google_credentials() and config.is_google_authorized():
        log("Checking Google Drive...")
        folder_id = google_client.find_drive_folder_id(config.DRIVE_FOLDER_NAME)
        if folder_id:
            log(f"Found Google Drive folder '{config.DRIVE_FOLDER_NAME}' (ID: {folder_id})")
            drive_files = google_client.list_files_in_folder(folder_id)
            log(f"Found {len(drive_files)} file(s) in Drive folder.")
            
            for d_file in drive_files:
                file_id = d_file["id"]
                filename = d_file["name"]
                source_id = f"drive_{file_id}"
                
                if source_id in processed_ids:
                    continue
                    
                log(f"  [Process] Google Drive file: {filename}")
                try:
                    content_bytes, mime_type = google_client.download_drive_file(file_id)
                    extraction = ai_extractor.extract_event_from_source(
                        content_bytes=content_bytes,
                        mime_type=mime_type
                    )
                    # We can construct a direct Drive file view link
                    link = f"https://drive.google.com/file/d/{file_id}/view"
                    event = format_event(extraction, "Google Drive", source_id, link)
                    new_events.append(event)
                    log(f"    Extracted: {event['Title']} ({event['Date']})")
                except Exception as e:
                    log(f"    Failed to process GDrive file {filename}: {e}")
        else:
            log(f"Warning: Google Drive folder '{config.DRIVE_FOLDER_NAME}' not found.")
            
        # 4. Ingest Gmail emails
        log("Checking Gmail...")
        emails = google_client.list_emails_with_label(config.GMAIL_LABEL)
        log(f"Found {len(emails)} thread(s) in Gmail matching label '{config.GMAIL_LABEL}'.")
        
        for email_item in emails:
            message_id = email_item["id"]
            source_id = f"gmail_{message_id}"
            
            if source_id in processed_ids:
                continue
                
            log(f"  [Process] Email message ID: {message_id}")
            try:
                email_details = google_client.get_email_details(message_id)
                
                # Format text content
                text_content = f"Subject: {email_details['subject']}\n"
                text_content += f"From: {email_details['from']}\n"
                text_content += f"Date: {email_details['date']}\n\n"
                text_content += email_details["body"]
                
                # Check for attachments first. If it has attachments like pdf or images, we process them.
                # In this simple implementation, we run Gemini on the email text. If there is a flyer image,
                # the email body text usually contains the summary/links anyway.
                # Let's extract from the email text first.
                extraction = ai_extractor.extract_event_from_source(
                    text_content=text_content,
                    mime_type="text/plain"
                )
                
                # Build direct Gmail web link
                thread_link = f"https://mail.google.com/mail/u/0/#all/{message_id}"
                
                event = format_event(extraction, "Gmail", source_id, thread_link)
                new_events.append(event)
                log(f"    Extracted email: {event['Title']} ({event['Date']})")
                
            except Exception as e:
                log(f"    Failed to process email {message_id}: {e}")
    else:
        log("Google OAuth credentials missing or not authorized. Skipping Google Drive and Gmail ingestion.")

    # 5. Save new events to Google Sheet
    if new_events:
        if config.has_google_credentials():
            log(f"Saving {len(new_events)} new event(s) to Google Sheet...")
            try:
                sheets_client.append_events_to_sheet(new_events)
                log("Successfully updated Google Sheet database.")
            except Exception as e:
                log(f"ERROR: Failed to write to Google Sheet: {e}")
        else:
            log("No Google Sheet database configured. Saving new events to local cache only.")
            # Local-only cache update
            try:
                import json
                existing_events = []
                if config.LOCAL_EVENTS_CACHE_PATH.exists():
                    with open(config.LOCAL_EVENTS_CACHE_PATH, "r") as f:
                        existing_events = json.load(f)
                combined = existing_events + new_events
                sheets_client.save_events_to_cache(combined)
                log("Successfully updated local event cache.")
            except Exception as e:
                log(f"ERROR: Failed to save to local cache: {e}")
    else:
        log("No new events found to process.")
        
    log("Ingestion completed successfully.")
    return new_events, logs

if __name__ == "__main__":
    # Check if run as CLI script
    if not config.has_gemini_key():
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)
        
    events, logs = run_ingestion()
    print(f"\nDone! Processed and added {len(events)} new events.")
