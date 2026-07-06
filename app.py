import os
import uuid
import hashlib
import mimetypes
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

from src import config
from src import sheets_client
from src import ingest
from src import ai_extractor

# Set up Streamlit Page Configuration
st.set_page_config(
    page_title="Events Dashboard",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium SaaS Custom CSS Injection
st.markdown("""
<style>
    /* Import fonts */
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    /* Standard font overrides */
    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }
    
    /* JetBrains Mono for data numbers & code */
    .mono-text {
        font-family: 'JetBrains Mono', monospace;
    }
    
    /* Metrics display styling */
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        color: #2563eb;
        line-height: 1.2;
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 500;
        color: #71717a;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Custom event cards badge styles */
    .badge {
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 0.5rem;
    }
    .badge-concert { background-color: #dbeafe; color: #1e40af; }
    .badge-conference { background-color: #f3e8ff; color: #6b21a8; }
    .badge-class { background-color: #fef3c7; color: #92400e; }
    .badge-meetup { background-color: #dcfce7; color: #166534; }
    .badge-sports { background-color: #ffedd5; color: #9a3412; }
    .badge-festival { background-color: #fee2e2; color: #991b1b; }
    .badge-play { background-color: #e0f2fe; color: #075985; }
    .badge-dinner { background-color: #e0e7ff; color: #3730a3; }
    .badge-exhibition { background-color: #fae8ff; color: #86198f; }
    .badge-other { background-color: #f4f4f5; color: #18181b; }
    
    /* Source Badge Styles */
    .badge-gmail { background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; }
    .badge-drive { background-color: #dbeafe; color: #2563eb; border: 1px solid #93c5fd; }
    .badge-local { background-color: #f4f4f5; color: #71717a; border: 1px solid #d4d4d8; }
    .badge-web { background-color: #dcfce7; color: #16a34a; border: 1px solid #86efac; }
</style>
""", unsafe_allow_html=True)

# Helper function to assign category classes
def get_category_badge(category: str) -> str:
    cat_lower = category.lower()
    if "concert" in cat_lower:
        return f'<span class="badge badge-concert">🎵 Concert</span>'
    elif "conference" in cat_lower:
        return f'<span class="badge badge-conference">💼 Conference</span>'
    elif "class" in cat_lower or "workshop" in cat_lower:
        return f'<span class="badge badge-class">🎓 Class/Workshop</span>'
    elif "meetup" in cat_lower or "social" in cat_lower:
        return f'<span class="badge badge-meetup">👥 Meetup/Social</span>'
    elif "sports" in cat_lower or "sport" in cat_lower:
        return f'<span class="badge badge-sports">⚽ Sports</span>'
    elif "festival" in cat_lower:
        return f'<span class="badge badge-festival">🎡 Festival</span>'
    elif "play" in cat_lower or "show" in cat_lower:
        return f'<span class="badge badge-play">🎭 Play/Show</span>'
    elif "dinner" in cat_lower or "food" in cat_lower or "restaurant" in cat_lower:
        return f'<span class="badge badge-dinner">🍽️ Dinner/Food</span>'
    elif "exhibition" in cat_lower or "museum" in cat_lower:
        return f'<span class="badge badge-exhibition">🖼️ Exhibition</span>'
    else:
        return f'<span class="badge badge-other">📅 {category}</span>'

def get_source_badge(source_type: str) -> str:
    s_lower = source_type.lower()
    if "gmail" in s_lower:
        return '<span class="badge badge-gmail">📧 Gmail</span>'
    elif "drive" in s_lower:
        return '<span class="badge badge-drive">📁 Drive</span>'
    elif "local" in s_lower:
        return '<span class="badge badge-local">💻 Local File</span>'
    else:
        return '<span class="badge badge-web">🔗 Web Link</span>'

# Initialize session state for events
if "events_df" not in st.session_state:
    st.session_state.events_df = None

# Load events data
def refresh_data(force=False):
    events = sheets_client.read_all_events(force_refresh=force)
    if events:
        df = pd.DataFrame(events)
        # Parse Dates
        df["Date_Parsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Cost_Parsed"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0.0)
        st.session_state.events_df = df
    else:
        st.session_state.events_df = pd.DataFrame()

# Initial data load
if st.session_state.events_df is None:
    refresh_data()

# --- SIDEBAR: Settings & Control Panel ---
with st.sidebar:
    st.title("📅 EventDashBoard")
    st.markdown("Summarize and explore events you want to attend.")
    st.divider()

    # 1. API Status and Setup
    st.subheader("🔑 Authentication & Keys")
    
    # Gemini Key Status
    if config.has_gemini_key():
        st.success("Gemini API Key: **Connected**")
    else:
        st.error("Gemini API Key: **Missing**")
        user_key = st.text_input("Enter Gemini API Key", type="password")
        if user_key:
            os.environ["GEMINI_API_KEY"] = user_key
            config.GEMINI_API_KEY = user_key
            st.rerun()

    # Google OAuth Status
    if config.has_google_credentials():
        if config.is_google_authorized():
            st.success("Google Workspace: **Authorized**")
        else:
            st.warning("Google Workspace: **Not Logged In**")
            if st.button("Authorize Google Account"):
                try:
                    from src.google_client import get_credentials
                    get_credentials()
                    st.success("Authorization successful! Refreshing...")
                    st.rerun()
                except Exception as e:
                    st.error(f"Authorization failed: {e}")
    else:
        st.info("Google Workspace: **Local Only Mode**")
        st.caption("Add `credentials.json` to project folder to connect Gmail/Drive.")

    # Secrets Debug Expansion
    with st.sidebar.expander("🛠️ Secrets Diagnostic Panel"):
        st.write("Credentials file exists:", config.CREDENTIALS_JSON_PATH.exists())
        st.write("Token file exists:", config.TOKEN_JSON_PATH.exists())
        try:
            if hasattr(st, "secrets") and st.secrets:
                st.write("Secrets keys detected:", list(st.secrets.keys()))
                for k in ["GEMINI_API_KEY", "CREDENTIALS_JSON_CONTENT", "TOKEN_JSON_CONTENT"]:
                    st.write(f"- `{k}` present:", k in st.secrets)
            else:
                st.write("st.secrets is empty/unavailable.")
        except Exception as err:
            st.write("Secrets error:", str(err))

    st.divider()

    # 2. Synchronize Trigger
    st.subheader("🔄 Ingestion Controls")
    
    sync_logs = st.empty()
    
    if st.button("Sync New Data", use_container_width=True, type="primary"):
        with st.status("Syncing new events...", expanded=True) as status:
            def log_callback(msg):
                status.write(msg)
                
            try:
                new_evs, logs = ingest.run_ingestion(progress_callback=log_callback)
                status.update(label=f"Sync Complete! Found {len(new_evs)} new event(s).", state="complete")
                # Force refresh from sheets
                refresh_data(force=True)
                st.success(f"Added {len(new_evs)} new events!")
            except Exception as e:
                status.update(label="Sync Failed!", state="error")
                st.error(f"Error details: {e}")
                
    if st.button("Reload Cached Sheet", use_container_width=True):
        refresh_data(force=True)
        st.success("Refreshed cached sheet rows.")

    st.divider()
    
    # Sync settings overview
    st.caption("Settings configured in `.env`:")
    st.caption(f"- Google Drive Folder: `{config.DRIVE_FOLDER_NAME}`")
    st.caption(f"- Gmail Label: `{config.GMAIL_LABEL}`")
    st.caption(f"- Google Sheet DB: `{config.SPREADSHEET_NAME}`")

# --- MAIN PAGE ---

# Handle case with empty dataframe (no events loaded yet)
df = st.session_state.events_df

if df is None or df.empty:
    st.subheader("Welcome to your Event Dashboard! 👋")
    st.info("No events have been processed yet. To populate your dashboard, choose one of these steps:")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        #### Option A: Synced Mode
        1. Place a `credentials.json` in the root folder.
        2. Make sure you have a Google Drive folder named **"Event Dashboard Intake"** containing PDFs/images of events.
        3. Labels some emails in Gmail as **"Events"**.
        4. Click **"Sync New Data"** in the sidebar.
        """)
    with col2:
        st.markdown("""
        #### Option B: Local Mode
        1. Place event flyers, ticket PDFs, or texts inside the local `data/raw_inputs/` folder.
        2. Make sure your **Gemini API Key** is entered in the sidebar.
        3. Click **"Sync New Data"** in the sidebar.
        """)
        
    st.divider()
else:
    # 1. Dashboard KPI summary strips
    total_events = len(df)
    
    # Filter upcoming events (date >= today)
    today = pd.Timestamp.now().normalize()
    upcoming_events = df[df["Date_Parsed"] >= today]
    num_upcoming = len(upcoming_events)
    
    # Next 7 Days
    next_week = today + pd.Timedelta(days=7)
    next_7_days = df[(df["Date_Parsed"] >= today) & (df["Date_Parsed"] <= next_week)]
    num_7_days = len(next_7_days)
    
    # Free Events
    free_events = df[df["Cost_Parsed"] == 0.0]
    num_free = len(free_events)

    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    
    with kpi_col1:
        with st.container(border=True):
            st.markdown('<div class="metric-label">Total Events</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value">{total_events}</div>', unsafe_allow_html=True)
            
    with kpi_col2:
        with st.container(border=True):
            st.markdown('<div class="metric-label">Upcoming Events</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value">{num_upcoming}</div>', unsafe_allow_html=True)
            
    with kpi_col3:
        with st.container(border=True):
            st.markdown('<div class="metric-label">In Next 7 Days</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value" style="color: #ea580c;">{num_7_days}</div>', unsafe_allow_html=True)
            
    with kpi_col4:
        with st.container(border=True):
            st.markdown('<div class="metric-label">Free Events</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value" style="color: #16a34a;">{num_free}</div>', unsafe_allow_html=True)

    st.divider()

    # 2. Main Timeline Graph (Quick overview)
    st.subheader("📅 Event Distribution Timeline")
    timeline_df = upcoming_events.copy()
    if not timeline_df.empty:
        # Group by week or month to visualize
        timeline_df["Week"] = timeline_df["Date_Parsed"].dt.to_period("W").dt.to_timestamp()
        weeks_chart = timeline_df.groupby("Week").size().reset_index(name="Count")
        st.area_chart(weeks_chart.set_index("Week")["Count"], height=160, color="#2563eb")
    else:
        st.info("No upcoming events to display on the timeline. Adjust dates or add new events!")

    st.divider()

    # 3. Interactive Filters and Search
    st.subheader("🔍 Filter & Explore Events")
    
    search_q = st.text_input("Search Events (Matches title, location, or summary)", "")
    
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    
    with f_col1:
        # Filter by Type
        all_types = sorted(df["Type"].unique().tolist())
        selected_types = st.multiselect("Event Type", all_types, default=all_types)
        
    with f_col2:
        # Filter by Cost
        cost_choice = st.radio("Cost Option", ["All Prices", "Free Only", "Paid Only"])
        
    with f_col3:
        # Filter by Date
        date_filter = st.selectbox("Date Range", ["All Dates", "Upcoming Only", "Past Events Only", "Custom Range"])
        
        custom_start = None
        custom_end = None
        if date_filter == "Custom Range":
            custom_range = st.date_input("Select Dates", [datetime.now().date(), (datetime.now() + timedelta(days=30)).date()])
            if len(custom_range) == 2:
                custom_start, custom_end = custom_range
                
    with f_col4:
        # Sort selection
        sort_by = st.selectbox("Sort By", ["Event Date (Chronological)", "Cost (Low to High)", "Cost (High to Low)", "Type", "Location"])

    # Apply Filters in Pandas
    filtered_df = df.copy()
    
    # 1. Search Query Filter
    if search_q:
        search_q = search_q.lower()
        filtered_df = filtered_df[
            filtered_df["Title"].str.lower().str.contains(search_q) |
            filtered_df["Location"].str.lower().str.contains(search_q) |
            filtered_df["Summary"].str.lower().str.contains(search_q) |
            filtered_df["Raw Detail"].str.lower().str.contains(search_q)
        ]
        
    # 2. Type Filter
    if selected_types:
        filtered_df = filtered_df[filtered_df["Type"].isin(selected_types)]
    else:
        filtered_df = filtered_df.iloc[0:0] # empty if nothing selected
        
    # 3. Cost Filter
    if cost_choice == "Free Only":
        filtered_df = filtered_df[filtered_df["Cost_Parsed"] == 0.0]
    elif cost_choice == "Paid Only":
        filtered_df = filtered_df[filtered_df["Cost_Parsed"] > 0.0]
        
    # 4. Date Filter
    if date_filter == "Upcoming Only":
        filtered_df = filtered_df[filtered_df["Date_Parsed"] >= today]
    elif date_filter == "Past Events Only":
        filtered_df = filtered_df[filtered_df["Date_Parsed"] < today]
    elif date_filter == "Custom Range" and custom_start and custom_end:
        filtered_df = filtered_df[
            (filtered_df["Date_Parsed"] >= pd.Timestamp(custom_start)) &
            (filtered_df["Date_Parsed"] <= pd.Timestamp(custom_end))
        ]

    # 5. Sorting
    if sort_by == "Event Date (Chronological)":
        # Keep NaT dates at the end
        filtered_df = filtered_df.sort_values(by="Date_Parsed", ascending=True, na_position="last")
    elif sort_by == "Cost (Low to High)":
        filtered_df = filtered_df.sort_values(by="Cost_Parsed", ascending=True)
    elif sort_by == "Cost (High to Low)":
        filtered_df = filtered_df.sort_values(by="Cost_Parsed", ascending=False)
    elif sort_by == "Type":
        filtered_df = filtered_df.sort_values(by="Type", ascending=True)
    elif sort_by == "Location":
        filtered_df = filtered_df.sort_values(by="Location", ascending=True)

    # 4. Display Events List
    st.subheader(f"✨ Found {len(filtered_df)} Event(s)")
    
    if filtered_df.empty:
        st.info("No events match your filter criteria. Try expanding search or filters!")
    else:
        for idx, row in filtered_df.iterrows():
            # Create a bordered container card for each event
            with st.container(border=True):
                # Layout header columns: Title and Badges
                title_col, badge_col = st.columns([3, 1])
                
                with title_col:
                    st.markdown(f"### {row['Title']}")
                with badge_col:
                    cat_html = get_category_badge(row['Type'])
                    src_html = get_source_badge(row['Source Type'])
                    st.markdown(f"{cat_html} {src_html}", unsafe_allow_html=True)
                
                # Metadata sub-grid
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    # Parse and format date nicely
                    date_val = row["Date"]
                    try:
                        d_obj = datetime.strptime(row["Date"], "%Y-%m-%d")
                        date_val = d_obj.strftime("%b %d, %Y (%a)")
                    except:
                        pass
                    st.markdown(f"📅 **Date:** <span class='mono-text'>{date_val}</span>", unsafe_allow_html=True)
                with m2:
                    st.markdown(f"🕒 **Time:** <span class='mono-text'>{row['Time']}</span>", unsafe_allow_html=True)
                with m3:
                    st.markdown(f"📍 **Location:** {row['Location']}", unsafe_allow_html=True)
                with m4:
                    cost_val = float(row["Cost_Parsed"])
                    cost_text = "Free" if cost_val == 0.0 else f"${cost_val:,.2f}"
                    st.markdown(f"💵 **Cost:** <span class='mono-text'>{cost_text}</span>", unsafe_allow_html=True)
                
                # Brief Summary
                st.write(f"📝 {row['Summary']}")
                
                # Interactive Details Expander
                with st.expander("🔎 View Full Event Details & Origin"):
                    # Quick details
                    st.markdown("#### Extended Details & Descriptions")
                    st.write(row["Raw Detail"] if row["Raw Detail"] else "No further description provided.")
                    
                    # Direct Link/Action Button
                    if row["Link"]:
                        st.markdown(f"[🔗 Go to Event Resource / Source Link]({row['Link']})")
                    
                    # Source metadata
                    st.markdown("---")
                    st.caption(f"Processed on: {row['Processed Date']} | Source ID: {row['Source ID']}")

# --- QUICK ADD MANUALLY SECTION ---
st.divider()
with st.expander("➕ Quick Add Source File / Web URL / Text"):
    st.markdown("You can manually submit a source to Gemini to parse and add directly to your Google Sheet.")
    
    add_method = st.radio("Choose Add Method", ["Paste Text / Copy-Paste Email", "Paste Website URL", "Upload File (PDF/Image)"])
    
    # Status outputs
    status_box = st.empty()
    
    if add_method == "Paste Text / Copy-Paste Email":
        raw_text = st.text_area("Paste event content details here (invitation text, newsletter clipping, etc.):", height=150)
        source_title = st.text_input("Source Identifier (e.g. 'Newsletter Email copy')", "Manual Text Copy")
        
        if st.button("Process & Add Text"):
            if not raw_text.strip():
                st.warning("Please paste some text first.")
            else:
                with st.spinner("Gemini is extracting event details..."):
                    try:
                        extraction = ai_extractor.extract_event_from_source(
                            text_content=raw_text,
                            mime_type="text/plain"
                        )
                        source_id = f"manual_txt_{str(uuid.uuid4())[:8]}"
                        event = ingest.format_event(extraction, "Web Link", source_id)
                        
                        # Add to Google Sheets
                        if config.has_google_credentials():
                            sheets_client.append_events_to_sheet([event])
                        else:
                            # Local only
                            existing = sheets_client.read_all_events()
                            existing.append(event)
                            sheets_client.save_events_to_cache(existing)
                            
                        st.success(f"Successfully added event: {event['Title']}")
                        refresh_data(force=True)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to process text: {e}")
                        
    elif add_method == "Paste Website URL":
        web_url = st.text_input("Paste Event Website Link:")
        if st.button("Process & Add URL"):
            if not web_url.strip():
                st.warning("Please paste a URL first.")
            else:
                with st.spinner("Fetching page details and running Gemini..."):
                    try:
                        # Attempt to fetch page content using requests and BeautifulSoup
                        import requests
                        from bs4 import BeautifulSoup
                        
                        headers = {"User-Agent": "Mozilla/5.0"}
                        response = requests.get(web_url, headers=headers, timeout=10)
                        
                        if response.status_code != 200:
                            st.error(f"Failed to load website. Status code: {response.status_code}")
                        else:
                            soup = BeautifulSoup(response.text, "html.parser")
                            # Strip tags to get clean visible text
                            for script in soup(["script", "style"]):
                                script.decompose()
                            page_text = soup.get_text(separator="\n")
                            # Truncate text if it's too long
                            page_text = page_text[:8000]
                            
                            extraction = ai_extractor.extract_event_from_source(
                                text_content=f"Source URL: {web_url}\n\nWebsite Content:\n{page_text}",
                                mime_type="text/plain"
                            )
                            source_id = f"manual_url_{str(uuid.uuid4())[:8]}"
                            event = ingest.format_event(extraction, "Web Link", source_id, web_url)
                            
                            # Save
                            if config.has_google_credentials():
                                sheets_client.append_events_to_sheet([event])
                            else:
                                existing = sheets_client.read_all_events()
                                existing.append(event)
                                sheets_client.save_events_to_cache(existing)
                                
                            st.success(f"Successfully added event: {event['Title']}")
                            refresh_data(force=True)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to scrape or extract URL: {e}")
                        
    elif add_method == "Upload File (PDF/Image)":
        uploaded_file = st.file_uploader("Upload Event Flyer (PNG, JPG) or Ticket (PDF)", type=["png", "jpg", "jpeg", "pdf"])
        if uploaded_file is not None:
            if st.button("Process & Add Uploaded File"):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                
                with st.spinner("Gemini is analyzing the file..."):
                    try:
                        extraction = ai_extractor.extract_event_from_source(
                            content_bytes=file_bytes,
                            mime_type=mime_type
                        )
                        source_id = f"manual_upload_{hashlib.md5(file_bytes).hexdigest()[:8]}"
                        
                        # Save file to local raw folder for audit records
                        file_ext = mimetypes.guess_extension(mime_type) or ".bin"
                        save_path = os.path.join(config.RAW_INPUTS_DIR, f"{source_id}{file_ext}")
                        with open(save_path, "wb") as f:
                            f.write(file_bytes)
                            
                        event = ingest.format_event(extraction, "Local File", source_id)
                        
                        # Save
                        if config.has_google_credentials():
                            sheets_client.append_events_to_sheet([event])
                        else:
                            existing = sheets_client.read_all_events()
                            existing.append(event)
                            sheets_client.save_events_to_cache(existing)
                            
                        st.success(f"Successfully added event: {event['Title']}")
                        refresh_data(force=True)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to process file: {e}")
