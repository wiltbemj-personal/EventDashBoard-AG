# EventDashBoard-AG

A SaaS-grade intelligent dashboard designed to summarize events from Gmail (emails with the `Events` label), Google Drive (a folder of event documents), and local file uploads (images and PDFs) into a single, unified database managed via Google Sheets. Built with Streamlit, Python, and the Gemini API.

---

## Architecture Overview

1. **Source Ingestion**: Pulls from Google Drive, Gmail (via Google APIs), or local folder drop `data/raw_inputs/`.
2. **AI Multimodal Parsing**: Passes text, images, or PDFs to the Gemini model to extract structured data (Date, Cost, Location, Category, Summary, links).
3. **Database Layer**: Writes to a Google Sheet (acting as a cloud database) and uses a fast local cache to keep dashboard loads instant.
4. **Streamlit UI**: Allows you to explore, search, filter, and sort your events dynamically.

---

## Step-by-Step Setup Guide

### 1. Requirements & Environment
The code is built to run on your local Python environment.
Activate your conda environment and run the app:
```bash
# Verify packages are installed
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
DRIVE_FOLDER_NAME=Event Dashboard Intake
GMAIL_LABEL=Events
SPREADSHEET_NAME=Event Dashboard DB
```
*Get a free Gemini API Key from [Google AI Studio](https://aistudio.google.com/).*

### 3. Setup Google Workspace APIs (OAuth2 Client)
To fetch from Gmail/Drive and write to Google Sheets, you need to create Google Cloud credentials:
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Event Dashboard`).
3. Enable the following APIs:
   * **Google Sheets API**
   * **Google Drive API**
   * **Gmail API**
4. Configure the **OAuth Consent Screen**:
   * Set user type to **External**.
   * Add your email under Test Users (critical, since the app is in test mode).
5. Create Credentials:
   * Go to the **Credentials** tab.
   * Click **Create Credentials** -> **OAuth client ID**.
   * Select **Desktop application** as the application type.
   * Download the JSON credentials file and rename it to **`credentials.json`** in your project root directory.

### 4. Running the Dashboard
Run the Streamlit application:
```bash
streamlit run app.py
```
* **First Run Login**: The app will detect `credentials.json` and prompt you to authorize. A browser window will open for you to log in with your Google account. It will save `token.json` locally so you never have to log in again.
* **Fallback (Local-Only)**: If no `credentials.json` is present, the app works in **Local-Only Drop Mode**. Drop files into `data/raw_inputs/` and sync.

---

## Keeping the Dashboard Updated (Mac Cron Job)
To sync your events automatically in the background, you can add a simple macOS cron job:
1. Open terminal and run `crontab -e`.
2. Add a line to run the sync script every day at 8 AM (change path to match your local project):
```cron
0 8 * * * /Users/wiltbemj/opt/anaconda3/envs/event-dashboard/bin/python -m src.ingest >> /Users/wiltbemj/src/AntiGravity/EventDashBoard/data/cache/cron_sync.log 2>&1
```
This will silently run the sync, update the Google Sheet database, and update the local cache so your dashboard is instantly fresh.
