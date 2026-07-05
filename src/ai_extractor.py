import io
import json
from datetime import datetime
from typing import Optional, Dict, Any
from PIL import Image
import google.generativeai as genai
from pydantic import BaseModel, Field

from src.config import GEMINI_API_KEY

class EventExtraction(BaseModel):
    title: str = Field(description="Name/Title of the event")
    date: str = Field(description="Date of the event in YYYY-MM-DD format. If date is a range, parse the start date. If no year is specified, analyze context or default to 2026 (current year is 2026).")
    time: str = Field(description="Start time of the event (e.g. 19:00, 09:30, All Day, TBD, or Evening)")
    location: str = Field(description="Location of the event (e.g., physical address, venue name, Online, Zoom, or TBD)")
    cost: float = Field(description="Price/cost of the event in USD. If it is free, set to 0.0. If there are multiple pricing tiers, parse the standard general admission ticket price or the lowest ticket cost. If cost is unknown or TBD, set to 0.0.")
    type: str = Field(description="Type/category of the event. Must be one of: Concert, Conference, Class/Workshop, Meetup/Social, Sports, Festival, Play/Show, Dinner/Food, Exhibition, Other")
    summary: str = Field(description="A concise 1-2 sentence summary of what the event is about.")
    link: Optional[str] = Field(description="Any URL found in the source related to event details, RSVP, registration, or ticket buying.")
    details: str = Field(description="Additional detailed information, descriptions, schedules, notes, or raw texts.")

def init_gemini():
    """Initializes the Gemini API client."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
    genai.configure(api_key=GEMINI_API_KEY)

def extract_event_from_source(
    content_bytes: Optional[bytes] = None, 
    text_content: Optional[str] = None, 
    mime_type: str = "text/plain"
) -> Dict[str, Any]:
    """Uses Gemini API to extract structured event details from text, images, or PDFs."""
    init_gemini()
    
    # We will use gemini-2.5-flash as the default since it's fast, multimodal, and cheap/free tier
    # Falling back to gemini-1.5-flash if needed
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    # Prepare system prompt with current context
    current_date_str = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
You are an expert event parsing agent. Analyze the provided source document (which could be an email, an image of a ticket/flyer, a PDF document, or website text) and extract the event information.

Current local time is {current_date_str}. Use this as a reference point for relative dates (like "next Tuesday" or "this coming Friday").
If a year is not explicitly specified, assume it is 2026 unless the context strongly suggests otherwise.

Extract the details and populate the JSON schema exactly.
"""

    contents = []
    
    if text_content:
        contents.append(text_content)
    elif content_bytes:
        if mime_type.startswith("image/"):
            try:
                img = Image.open(io.BytesIO(content_bytes))
                contents.append(img)
            except Exception as e:
                raise ValueError(f"Failed to load image: {e}")
        elif mime_type == "application/pdf":
            # Pass PDF bytes directly using part dict
            contents.append({
                "data": content_bytes,
                "mime_type": "application/pdf"
            })
        else:
            # Fallback to reading bytes as text
            try:
                contents.append(content_bytes.decode("utf-8", errors="ignore"))
            except Exception as e:
                raise ValueError(f"Unsupported binary file format: {mime_type}")
    else:
        raise ValueError("Must provide either content_bytes or text_content.")
        
    contents.append(prompt)
    
    # Configure generation config for structured output
    generation_config = {
        "response_mime_type": "application/json",
        "response_schema": EventExtraction,
        "temperature": 0.1
    }
    
    try:
        response = model.generate_content(
            contents,
            generation_config=generation_config
        )
        
        # Parse the JSON response
        data = json.loads(response.text)
        return data
        
    except Exception as e:
        print(f"Gemini generation error: {e}")
        raise e
