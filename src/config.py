import os
from pathlib import Path
from dotenv import load_dotenv

# Path Configuration
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_ROOT / "data"
RAW_INPUTS_DIR = DATA_DIR / "raw_inputs"
CACHE_DIR = DATA_DIR / "cache"

# Ensure directories exist
RAW_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Path to Google OAuth credentials/tokens
CREDENTIALS_JSON_PATH = WORKSPACE_ROOT / "credentials.json"
TOKEN_JSON_PATH = WORKSPACE_ROOT / "token.json"
LOCAL_EVENTS_CACHE_PATH = CACHE_DIR / "events_cache.json"

# Load environment variables
load_dotenv(WORKSPACE_ROOT / ".env")

# App Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DRIVE_FOLDER_NAME = os.getenv("DRIVE_FOLDER_NAME", "Event Dashboard Intake")
GMAIL_LABEL = os.getenv("GMAIL_LABEL", "Events")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Event Dashboard DB")

# Load configuration and write credential files from Streamlit Secrets if available
try:
    import streamlit as st
    if hasattr(st, "secrets") and st.secrets:
        if "GEMINI_API_KEY" in st.secrets:
            GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
        if "DRIVE_FOLDER_NAME" in st.secrets:
            DRIVE_FOLDER_NAME = st.secrets["DRIVE_FOLDER_NAME"]
        if "GMAIL_LABEL" in st.secrets:
            GMAIL_LABEL = st.secrets["GMAIL_LABEL"]
        if "SPREADSHEET_NAME" in st.secrets:
            SPREADSHEET_NAME = st.secrets["SPREADSHEET_NAME"]
            
        if "CREDENTIALS_JSON_CONTENT" in st.secrets and not CREDENTIALS_JSON_PATH.exists():
            with open(CREDENTIALS_JSON_PATH, "w") as f:
                f.write(st.secrets["CREDENTIALS_JSON_CONTENT"])
                
        if "TOKEN_JSON_CONTENT" in st.secrets and not TOKEN_JSON_PATH.exists():
            with open(TOKEN_JSON_PATH, "w") as f:
                f.write(st.secrets["TOKEN_JSON_CONTENT"])
except Exception:
    pass

def has_gemini_key() -> bool:
    return bool(GEMINI_API_KEY)

def has_google_credentials() -> bool:
    return CREDENTIALS_JSON_PATH.exists()

def is_google_authorized() -> bool:
    return TOKEN_JSON_PATH.exists()
