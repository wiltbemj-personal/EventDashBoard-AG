import json
import os
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
import pandas as pd

from src.config import SPREADSHEET_NAME, LOCAL_EVENTS_CACHE_PATH
from src.google_client import get_sheets_service, get_drive_service

HEADERS = [
    "ID", "Title", "Date", "Time", "Location", "Cost", 
    "Type", "Summary", "Link", "Source Type", "Source ID", 
    "Processed Date", "Raw Detail"
]

def find_or_create_spreadsheet() -> str:
    """Finds the spreadsheet by name, or creates a new one if not found. Returns spreadsheetId."""
    drive_service = get_drive_service()
    sheets_service = get_sheets_service()
    
    # 1. Search for existing spreadsheet
    query = f"mimeType = 'application/vnd.google-apps.spreadsheet' and name = '{SPREADSHEET_NAME}' and trashed = False"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    
    if files:
        return files[0]["id"]
        
    # 2. Create a new one if not found
    spreadsheet_body = {
        "properties": {
            "title": SPREADSHEET_NAME
        }
    }
    spreadsheet = sheets_service.spreadsheets().create(
        body=spreadsheet_body, fields="spreadsheetId"
    ).execute()
    spreadsheet_id = spreadsheet.get("spreadsheetId")
    
    # Write the headers
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1:M1",
        valueInputOption="RAW",
        body={"values": [HEADERS]}
    ).execute()
    
    print(f"Created new Google Sheet '{SPREADSHEET_NAME}' with ID: {spreadsheet_id}")
    return spreadsheet_id

def read_all_events(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Reads all events from the Google Sheet (or from local cache if cache is fresh)."""
    if not force_refresh and LOCAL_EVENTS_CACHE_PATH.exists():
        try:
            with open(LOCAL_EVENTS_CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to read local cache, falling back to Google Sheets: {e}")
            
    # Read from Sheets API
    try:
        spreadsheet_id = find_or_create_spreadsheet()
        sheets_service = get_sheets_service()
        
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range="Sheet1!A:M"
        ).execute()
        
        rows = result.get("values", [])
        if not rows or len(rows) <= 1:
            return []
            
        headers = rows[0]
        events = []
        
        for r_idx, row in enumerate(rows[1:], start=2): # keep sheet row indices
            event = {}
            for h_idx, header in enumerate(HEADERS):
                event[header] = row[h_idx] if h_idx < len(row) else ""
            event["_sheet_row"] = r_idx # tracking row index for any update/delete operations if needed
            events.append(event)
            
        # Update cache
        save_events_to_cache(events)
        return events
        
    except Exception as e:
        print(f"Error reading Google Sheets database: {e}")
        # If network/API error, return cached data if available as fallback
        if LOCAL_EVENTS_CACHE_PATH.exists():
            with open(LOCAL_EVENTS_CACHE_PATH, "r") as f:
                return json.load(f)
        return []

def save_events_to_cache(events: List[Dict[str, Any]]) -> None:
    """Saves the event list to local json cache."""
    try:
        LOCAL_EVENTS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Strip internal keys like _sheet_row from cache
        cleaned_events = []
        for ev in events:
            cleaned = {k: v for k, v in ev.items() if k != "_sheet_row"}
            cleaned_events.append(cleaned)
            
        with open(LOCAL_EVENTS_CACHE_PATH, "w") as f:
            json.dump(cleaned_events, f, indent=2)
    except Exception as e:
        print(f"Failed to save local cache: {e}")

def append_events_to_sheet(events: List[Dict[str, Any]]) -> None:
    """Appends multiple events to the Google Sheet database."""
    if not events:
        return
        
    try:
        spreadsheet_id = find_or_create_spreadsheet()
        sheets_service = get_sheets_service()
        
        values_to_append = []
        for event in events:
            # Reorder according to HEADERS
            row = [
                event.get("ID", ""),
                event.get("Title", ""),
                event.get("Date", ""),
                event.get("Time", ""),
                event.get("Location", ""),
                event.get("Cost", ""),
                event.get("Type", ""),
                event.get("Summary", ""),
                event.get("Link", ""),
                event.get("Source Type", ""),
                event.get("Source ID", ""),
                event.get("Processed Date", ""),
                event.get("Raw Detail", "")
            ]
            values_to_append.append(row)
            
        body = {
            "values": values_to_append
        }
        
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A:M",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        
        # Invalidate cache by forcing a reread
        read_all_events(force_refresh=True)
        
    except Exception as e:
        print(f"Error appending rows to Google Sheet: {e}")
        raise e

def get_processed_source_ids() -> set:
    """Gets a set of already processed Source IDs to prevent duplicates."""
    events = read_all_events()
    return {event["Source ID"] for event in events if event.get("Source ID")}
