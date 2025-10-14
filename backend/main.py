import os
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://nexpathbackend-1.onrender.com")

from datetime import datetime , timedelta
from typing import Optional, List, Dict, Any
import random
import uuid
import json
import re
from pathlib import Path

from tasks import analyze_interview ,initiate_interview_call
from fastapi import Request
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from fastapi import FastAPI, HTTPException, Depends, Form
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
import httpx
import requests
from dotenv import load_dotenv
from user_routes import router as user_router
from redis_client import redis_client
from mongodb_client import save_chat_to_mongodb, chat_collection
from postgres_models import MentorshipRequest, Resume, UserProfile, SavedJob, Event, CareerTip
from auth_routes import router as auth_router
from utils import remove_invalid_characters
import logging
from fastapi.staticfiles import StaticFiles
from postgres_client import get_user_name_from_db, SessionLocal
from resume_service import resume_router  # Assuming this is a module you have
from tasks import initiate_interview_call
from twilio.twiml.voice_response import VoiceResponse, Gather



logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more verbosity
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Initialize FastAPI app
app = FastAPI()
app.include_router(resume_router)
app.include_router(user_router)
app.mount("/static", StaticFiles(directory="static"), name="static")

# main.py (near the top, right after app = FastAPI())
from fastapi.middleware.cors import CORSMiddleware
import os

# Set your production frontend domain (or via Render env var FRONTEND_URL)
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://nexpath.vercel.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],                 # exact prod domain
    allow_origin_regex=r"^https://.*\.vercel\.app$",  # preview deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# origins = [
#     "https://nexpathbackend.vercel.app",     # ✅ Your production Vercel domain
#     "https://*.vercel.app",                   # ✅ All Vercel preview deployments
#     "http://localhost:3000",                  # Local dev (React default)
#     "http://localhost:5173",                  # Local dev (Vite default)
#     "http://localhost:8080",                  # Local dev (alternative)
# ]
#
# # CORS Configuration
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Load mentorship links
mentor_links_path = Path(__file__).parent / "mentor_links.json"
with open(mentor_links_path, "r") as f:
    MENTOR_PLATFORM_LINKS = json.load(f)


# ------------- Models ---------------

class SavedJobBase(BaseModel):
    job_title: str
    company_name: str
    apply_link: Optional[str] = None


# No user_id here - it comes from the path parameter
class SavedJobCreate(SavedJobBase):
    pass


class SavedJobResponse(SavedJobBase):
    id: int
    saved_at: datetime

    class Config:
        orm_mode = True


class DocumentResponse(BaseModel):
    id: int
    file_name: str  # e.g., "Resume - JohnDoe_v1.pdf"
    download_url: str
    created_at: datetime

    class Config:
        orm_mode = True


class EventResponse(BaseModel):
    id: int
    title: str
    event_date: datetime
    join_link: Optional[str] = None

    class Config:
        orm_mode = True


class CareerTipResponse(BaseModel):
    tip_text: str

    class Config:
        orm_mode = True


class ScheduleRequest(BaseModel):
    phone_number: str
    scheduled_time: datetime
    user_id: str


# This will be the main response model for the dashboard
class DashboardResponse(BaseModel):
    saved_jobs: List[SavedJobResponse]
    documents: List[Dict[str, Any]]
    upcoming_events: List[EventResponse]
    career_tip: Optional[CareerTipResponse] = None
    metadata: Optional[Dict[str, Any]] = None  # Add this line


class ChatMessage(BaseModel):
    query: str
    user_id: Optional[str] = None


class JobSearchRequest(BaseModel):
    job_title: str = "Web Developer"
    location: str = "Kolkata"
    page: int = 1
    limit: int = 5


class ConnectMentorshipRequest(BaseModel):
    user_id: Optional[int] = None
    interest_field: str


# ------------- Database Dependencies ---------------

def get_resume_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------- Gemini API Communication ---------------

async def talk_to_gemini(
        message: str,
        sender_id: str = "default",
        conversation_history: Optional[List[Dict[str, Any]]] = None
):
    """
    Send message to Google Gemini API and get response
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY environment variable not set")
        return [{"text": "Sorry, I'm not configured correctly. Please contact support."}]

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    # Create system instruction for career-focused assistant
    system_instruction = """
    You are Asha, an AI career assistant specializing in helping users with their professional growth.

    Focus areas:
    1. Career advice and guidance for job seekers
    2. Resume building and improvement tips
    3. Mentorship connections and opportunities
    4. Professional development resources
    5. Upcoming career events, hackathons, and challenges

    Guidelines:
    - Provide concise, professional, and actionable advice
    - Be encouraging and supportive
    - Only answer questions related to careers, professional development, and education
    - For personal questions, politely redirect to career-related topics
    - For resume help, collect necessary information and suggest improvements
    - For job searches, ask for details like role, location, and experience level
    - If user asks about resume building, suggest using the resume building form by saying "Would you like to use our resume builder to create a professional resume?"

    Remember, you're designed to empower users in your professional journey!
    """

    # If conversation history is provided, use it to maintain context
    if conversation_history:
        # Format conversation history for Gemini
        formatted_history = []
        for entry in conversation_history:
            role = "user" if entry["role"] == "user" else "model"
            formatted_history.append({
                "role": role,
                "parts": [{"text": entry["message"]}]
            })

        # Add the system instruction as the first message
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": system_instruction}]},
                *formatted_history,
                {"role": "user", "parts": [{"text": message}]}
            ],
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
    else:
        # First message in conversation
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {"text": message}
                    ]
                }
            ],
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }

    try:
        # Call Gemini API
        response = requests.post(GEMINI_URL, headers=headers, json=data)

        if response.status_code != 200:
            logger.error(f"Gemini API error: {response.status_code}, {response.text}")
            return [{"text": "I'm having trouble processing your request right now. Please try again later."}]

        # Parse response
        response_json = response.json()

        if 'candidates' in response_json and len(response_json['candidates']) > 0:
            bot_reply = response_json['candidates'][0]['content']['parts'][0]['text']

            # Check if this response contains action triggers
            action_trigger = None
            job_results = []

            # Check for specific action triggers in the response
            if "resume builder" in bot_reply.lower() or "build your resume" in bot_reply.lower() or "create a resume" in bot_reply.lower():
                action_trigger = "open_resume_form"

            # Return in Rasa-compatible format for backward compatibility
            return [{"text": bot_reply, "custom": {"action": action_trigger, "job_results": job_results}}]
        else:
            return [{"text": "I couldn't generate a response. Please try rephrasing your question."}]

    except Exception as e:
        logger.error(f"Error connecting to Gemini API: {e}")
        return [{"text": "I'm having technical difficulties. Please try again later."}]


# Intent detection helper function
def detect_user_intent(user_query: str) -> str:
    """
    Detect the user's intent from their query to help with analytics.
    """
    user_query = user_query.lower()

    # Job search intent
    job_keywords = ["job", "jobs", "hiring", "position", "work", "vacancy", "opening"]
    if any(keyword in user_query for keyword in job_keywords):
        return "job_search"

    # Resume intent
    resume_keywords = ["resume", "cv", "curriculum vitae", "build my resume", "create resume"]
    if any(keyword in user_query for keyword in resume_keywords):
        return "resume_help"


    # Mock interview intent
    interview_keywords = ["interview", "mock call", "practice call", "phone screen", "telephonic interview"]
    if any(keyword in user_query for keyword in interview_keywords):
        return "interview_booking"

    # Mentorship intent
    mentorship_keywords = ["mentor", "mentorship", "guidance", "guide me", "coach"]
    if any(keyword in user_query for keyword in mentorship_keywords):
        return "mentorship"

    # Career advice intent
    advice_keywords = ["advice", "suggest", "help me with", "tips", "guidance"]
    if any(keyword in user_query for keyword in advice_keywords):
        return "career_advice"

    # Events intent
    events_keywords = ["event", "hackathon", "workshop", "webinar", "conference"]
    if any(keyword in user_query for keyword in events_keywords):
        return "events_info"

    # Chatbot information intent
    bot_keywords = ["who are you", "what can you do", "your name", "about you"]
    if any(keyword in user_query for keyword in bot_keywords):
        return "bot_info"

    # Default intent
    return "general_query"


# ------------- Job Search API ---------------

async def fetch_real_time_jobs(job_title: str, location: str, page: int = 1, limit: int = 10):
    cache_key = f"jobs:{job_title}:{location}"
    cached_jobs = redis_client.get(cache_key)

    if cached_jobs:
        job_data = json.loads(cached_jobs)
    else:
        querystring = {"query": f"{job_title} in {location}", "num_pages": "1"}
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get("https://jsearch.p.rapidapi.com/search", headers=headers, params=querystring)

        if response.status_code != 200:
            return []

        raw_data = response.json()
        job_data = raw_data.get("data", [])

        for job in job_data:
            job['job_title'] = remove_invalid_characters(job.get('job_title', ''))
            job['employer_name'] = remove_invalid_characters(job.get('employer_name', ''))
            job['job_city'] = remove_invalid_characters(job.get('job_city', ''))

        redis_client.setex(cache_key, 3600, json.dumps(job_data))

    start = (page - 1) * limit
    end = start + limit
    return job_data[start:end]



# ------------- Mentorship API ---------------

@app.post("/connect_mentorship/")
async def process_mentorship(request: ConnectMentorshipRequest):
    db: Session = SessionLocal()
    try:
        mentorship = MentorshipRequest(
            user_id=request.user_id,
            interest_field=request.interest_field
        )
        db.add(mentorship)
        db.commit()
        db.refresh(mentorship)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

    field = request.interest_field.lower()
    mentor_links = MENTOR_PLATFORM_LINKS.get(field, MENTOR_PLATFORM_LINKS["default"])

    if isinstance(mentor_links, list):
        selected_links = mentor_links[:2]
    else:
        selected_links = [mentor_links, MENTOR_PLATFORM_LINKS["default"][0]]

    formatted_links = "\n".join([f"👉 {link}" for link in selected_links])

    return JSONResponse(
        content={
            "response": (
                f"🌱 **Mentorship Opportunity in {request.interest_field}**\n\n"
                f"{formatted_links}\n"
                "Grow your network and get guidance from leaders in the field!"
            ),
            "source": "mentorship"
        },
        headers={"Content-Type": "application/json; charset=utf-8"}
    )


# ------------- Fallback ---------------

@app.post("/fallback/")
async def process_fallback(user_query: dict):
    return JSONResponse(
        content={
            "response": "I'm not sure what you're looking for. Try asking about jobs or mentorship!\n"
                        "You can also ask about AI, Data Science, or career tips.",
            "intent": "fallback"
        },
        headers={"Content-Type": "application/json; charset=utf-8"}
    )


# ------------- Chat History by Session ID ---------------

@app.get("/chat/session/{session_id}")
async def get_session_messages(session_id: str):
    try:
        messages_cursor = chat_collection.find({"session_id": session_id}).sort("timestamp", 1)
        messages = []
        for message in messages_cursor:
            message["_id"] = str(message["_id"])
            if "timestamp" in message and isinstance(message["timestamp"], datetime):
                message["timestamp"] = message["timestamp"].isoformat()

            # Add a sender field based on role
            message["sender"] = "bot" if message.get("role") == "bot" else "user"

            messages.append(message)

        if not messages:
            raise HTTPException(status_code=404, detail="Session not found")

        # Wrap in a messages property as the frontend expects
        return JSONResponse(
            content={"messages": jsonable_encoder(messages)},
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Add this helper function somewhere before your /chat/ endpoint in main.py

def extract_interest_field(query: str) -> str:
    """
    Extracts the field of interest from a mentorship query.
    Uses regex to find the field after keywords like 'in', 'for', or 'on'.
    """
    query = query.lower()

    # Look for patterns like "mentorship in data science" or "mentor for product management"
    match = re.search(r'(?:in|for|on)\s+([a-zA-Z\s\-]+(?:\s+[a-zA-Z\s\-]+)*)', query)

    if match:
        return match.group(1).strip()

    # Fallback: remove common mentorship keywords
    mentorship_keywords = ["mentor", "mentorship", "guidance", "guide me", "coach", "i want to connect", "i want",
                           "connect me with"]
    for keyword in mentorship_keywords:
        query = re.sub(r'\b' + re.escape(keyword) + r'\b', '', query, flags=re.IGNORECASE)

    # Return the cleaned query or a default
    return query.strip() or "Technology"



@app.post("/chat/")
async def process_chat(message: ChatMessage):
    user_query = message.query
    user_id = message.user_id or "anonymous"
    logger.info(f"Received message from user {user_id}: {user_query}")

    if not user_query:
        raise HTTPException(status_code=400, detail="Message query is required.")

    # --- Session and User Handling (No changes here) ---
    session_id_key = f"session:{user_id}"
    session_id = redis_client.get(session_id_key)
    if isinstance(session_id, bytes):
        session_id = session_id.decode("utf-8")

    new_session = False
    if not session_id:
        session_id = str(uuid.uuid4())
        new_session = True
        redis_client.set(session_id_key, session_id)

        # Check if user is in interview booking flow
        booking_state_key = f"interview_booking:{user_id}"
        is_booking = redis_client.get(booking_state_key)

        # Intent Detection
        user_intent = detect_user_intent(user_query)
        logger.info(f"Detected intent: {user_intent}")

        # Check if this message contains scheduling info
        phone_number, scheduled_time = extract_scheduling_info(user_query)

        # Handle Interview Booking Flow
        if user_intent == "interview_booking" or is_booking:
            logger.info(f"Processing interview booking flow")

            if user_intent == "interview_booking" and not phone_number:
                # Start the booking flow
                redis_client.setex(booking_state_key, 300, "active")  # 5 min expiry
                response_text = "Great! I'll help you schedule a mock interview. Please provide your phone number (10 digits) and preferred time (e.g., '15:30' or '3:30 PM')."

                save_chat_to_mongodb(session_id, user_id, "user", user_query, "interview_booking")
                save_chat_to_mongodb(session_id, user_id, "bot", response_text, "interview_booking_response")

                return JSONResponse(content={
                    "response": response_text,
                    "action": "collect_interview_details",
                    "session_id": session_id
                })

            elif phone_number and scheduled_time:
                # We have both phone and time - schedule the interview!
                logger.info(f"Scheduling interview for {phone_number} at {scheduled_time}")

                try:
                    # Clear the booking state
                    redis_client.delete(booking_state_key)

                    # Create interview record in database (you'll need to implement this)
                    db = SessionLocal()
                    try:
                        # First, get or create the interview record
                        # You might want to add an Interview model to your postgres_models.py
                        interview_id = create_interview_record(db, user_id, phone_number, scheduled_time)
                    finally:
                        db.close()

                    # Schedule the Celery task
                    initiate_interview_call.apply_async(
                        args=[f"+91{phone_number}", interview_id],  # Add country code
                        eta=scheduled_time
                    )

                    response_text = f"✅ Perfect! Your mock interview is scheduled for {scheduled_time.strftime('%B %d at %I:%M %p')}. You'll receive a call at {phone_number}. Please make sure you're in a quiet place and ready for the interview!"

                    save_chat_to_mongodb(session_id, user_id, "user", user_query, "interview_scheduled")
                    save_chat_to_mongodb(session_id, user_id, "bot", response_text, "interview_confirmation")

                    return JSONResponse(content={
                        "response": response_text,
                        "action": "interview_scheduled",
                        "session_id": session_id
                    })

                except Exception as e:
                    logger.error(f"Error scheduling interview: {e}")
                    response_text = "Sorry, I couldn't schedule your interview. Please try again or contact support."
                    return JSONResponse(content={
                        "response": response_text,
                        "session_id": session_id
                    })

            elif phone_number or scheduled_time:
                # We have partial info
                missing = []
                if not phone_number:
                    missing.append("phone number")
                if not scheduled_time:
                    missing.append("preferred time")

                response_text = f"I got that! I still need your {' and '.join(missing)} to schedule the interview."

                return JSONResponse(content={
                    "response": response_text,
                    "action": "collect_interview_details",
                    "session_id": session_id
                })

            else:
                # User is in booking flow but didn't provide required info
                response_text = "To schedule your mock interview, please provide your 10-digit phone number and preferred time (e.g., 'phone number is 9876543210 and time 3:30 PM')."

                return JSONResponse(content={
                    "response": response_text,
                    "action": "collect_interview_details",
                    "session_id": session_id
                })

    # --- Intent Detection ---
    user_intent = detect_user_intent(user_query)
    logger.info(f"Detected intent: {user_intent}")

    # --- ROUTING LOGIC ---

    # 1. Handle Job Search Intent
    if user_intent == "job_search":
        logger.info(f"Routing to Job Search logic: {user_query}")

        # Improved extraction logic
        location_match = re.search(r'in\s+([a-zA-Z\s,]+)', user_query, re.IGNORECASE)
        location = location_match.group(1).strip() if location_match else "India"

        job_title = re.sub(r'in\s+' + re.escape(location), '', user_query, flags=re.IGNORECASE)
        job_keywords = ["job", "jobs", "hiring", "career", "position", "work", "vacancy", "opening", "i am looking for",
                        "i am searching for"]
        for keyword in job_keywords:
            job_title = re.sub(r'\b' + re.escape(keyword) + r'\b', '', job_title, flags=re.IGNORECASE)

        job_title = job_title.strip() or "developer"
        logger.info(f"Extracted job title: '{job_title}', location: '{location}'")

        try:
            # Call the job fetching function directly
            jobs = await fetch_real_time_jobs(job_title, location)

            if not jobs:
                return JSONResponse(content={
                    "response": f"❌ No jobs found for '{job_title}' in '{location}'.",
                    "job_results": [],
                    "session_id": session_id,
                })

            # Format the jobs for the frontend
            job_summaries = []
            for job in jobs:
                if 'job_apply_link' not in job:
                    continue
                job_summaries.append({
                    "title": remove_invalid_characters(job.get("job_title", "")),
                    "company": remove_invalid_characters(job.get("employer_name", "")),
                    "city": remove_invalid_characters(job.get("job_city", "")),
                    "description": remove_invalid_characters(job.get("job_description", ""))[:300] + "...",
                    "apply_link": job.get("job_apply_link", ""),
                    "employer_website": job.get("employer_website", ""),
                    "employer_logo": job.get("employer_logo", ""),
                    "employment_type": job.get("job_employment_type", ""),
                    "posted_at": job.get("job_posted_at_datetime_utc", ""),
                })

            response_text = f"🌟 Here are some jobs for '{job_title}' in '{location}':"

            # Save chat to MongoDB
            save_chat_to_mongodb(session_id, user_id, "user", user_query, "job_search")
            save_chat_to_mongodb(session_id, user_id, "bot", response_text, "job_search_results")

            return JSONResponse(content={
                "response": response_text,
                "job_results": job_summaries,
                "session_id": session_id,
            })

        except Exception as e:
            logger.error(f"Error during job fetch: {e}")
            return JSONResponse(
                content={"response": f"Sorry, an error occurred while searching for jobs."},
                status_code=500
            )

        # Inside your @app.post("/chat/") function

        # ... (after intent detection)

        # 3. Handle Interview Booking Intent
    elif user_intent == "interview_booking":
        # Here, Gemini will manage the conversation to get details.
        # Your prompt to Gemini should instruct it to ask for phone number and preferred time.
        # For simplicity, we'll assume Gemini's response asks the user to confirm.

        # In a real scenario, you'd extract phone/time from the conversation.
        # For now, let's assume Gemini guides the user and we trigger a confirmation.

        # A more advanced flow would be a state machine managed here.
        # Let's create a simple trigger.

        logger.info(f"Routing to Interview Booking: {user_query}")

        # For this example, let's hardcode a response that leads to booking.
        # In a real app, Gemini would generate this.
        response_text = "Great! We can set up a mock interview. To schedule, please provide your phone number and a preferred time (e.g., 'tomorrow at 3 PM')."

        # This part is simplified. A full implementation would use a state machine
        # or multiple API calls to collect info before scheduling.
        # Once info is collected, you would then call the scheduling logic.

        return JSONResponse(content={"response": response_text, "action": "collect_interview_details"})



    # 2. Handle Mentorship Intent
    elif user_intent == "mentorship":
        logger.info(f"Routing to Mentorship logic: {user_query}")
        interest_field = extract_interest_field(user_query)
        logger.info(f"Extracted interest field: '{interest_field}'")

        try:
            # Call the mentorship link generation logic directly
            mentorship_request = ConnectMentorshipRequest(user_id=None, interest_field=interest_field)
            mentorship_response = await process_mentorship(mentorship_request)

            # Save chat to MongoDB
            mentorship_data = json.loads(mentorship_response.body)
            save_chat_to_mongodb(session_id, user_id, "user", user_query, "mentorship")
            save_chat_to_mongodb(session_id, user_id, "bot", mentorship_data.get("response"), "mentorship_response")

            return mentorship_response

        except Exception as e:
            logger.error(f"Error processing mentorship request: {e}")
            return JSONResponse(
                content={"response": "Sorry, I had trouble finding mentorship links."},
                status_code=500
            )

    # 3. Handle all other queries with Gemini
    else:
        logger.info(f"Routing to Gemini for general conversation.")
        # Fetch conversation history for context
        try:
            messages_cursor = chat_collection.find({"session_id": session_id}).sort("timestamp", -1).limit(10)
            conversation_history = [{"role": msg.get("role"), "message": msg.get("message")} for msg in messages_cursor]
            conversation_history.reverse()
        except Exception as e:
            logger.error(f"Error fetching conversation history: {e}")
            conversation_history = []

        try:
            gemini_responses = await talk_to_gemini(
                user_query,
                sender_id=user_id,
                conversation_history=conversation_history
            )

            bot_reply_text = gemini_responses[0].get("text", "Sorry, I didn't understand that.").strip()
            action_trigger = gemini_responses[0].get("custom", {}).get("action")

            save_chat_to_mongodb(session_id, user_id, "user", user_query, user_intent)
            save_chat_to_mongodb(session_id, user_id, "bot", bot_reply_text, f"{user_intent}_response")

            return JSONResponse(content={
                "response": bot_reply_text,
                "action": action_trigger,
                "session_id": session_id,
            })
        except Exception as e:
            logger.error(f"Error connecting to Gemini API: {e}")
            return JSONResponse(
                content={"response": "Sorry, I'm having technical difficulties."},
                status_code=500
            )



@app.get("/headings", response_model=List[Dict[str, str]])
async def get_headings():
    # In a real application, fetch this data from a database or CMS
    headings = [
        {"text": "Resume Building Help", "link": "/resume-building"},
        {"text": "Upcoming Events", "link": "/upcoming-events"},
        {"text": "Live Job Updates", "link": "/live-job-updates"},
    ]
    return headings


@app.get("/user/profile/{user_id}")
async def get_user_profile(user_id: str, db: Session = Depends(get_resume_db)):
    """Get user profile data by user_id"""
    try:
        # Query user profile from database
        user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        if not user_profile:
            # Return a default response if user not found in database
            return JSONResponse(
                content=jsonable_encoder({
                    "name": "User",
                    "email": "user@example.com",
                    "contact": None
                }),
                headers={"Content-Type": "application/json; charset=utf-8"}
            )

        # Return user profile data
        return JSONResponse(
            content=jsonable_encoder({
                "name": user_profile.name,
                "email": user_profile.email,
                "contact": user_profile.contact
            }),
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users/{user_id}/jobs", response_model=SavedJobResponse)
def save_job_for_user(user_id: str, job: SavedJobBase, db: Session = Depends(get_resume_db)):
    logger.info(f"Attempting to save job for user {user_id}: {job.dict()}")

    try:
        # Create SavedJob object
        db_job = SavedJob(
            user_id=user_id,
            job_title=job.job_title,
            company_name=job.company_name,
            apply_link=job.apply_link,
            saved_at=datetime.utcnow()  # Explicitly set timestamp
        )

        # Add to database
        db.add(db_job)
        db.commit()
        db.refresh(db_job)

        logger.info(f"Successfully saved job ID {db_job.id} for user {user_id}")
        return db_job
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving job for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save job: {str(e)}")


# THE MAIN DASHBOARD ENDPOINT
@app.get("/users/{user_id}/dashboard", response_model=DashboardResponse)
def get_user_dashboard(
        user_id: str,
        db: Session = Depends(get_resume_db),
        jobs_limit: int = 5,
        resumes_limit: int = None,  # No default limit
        events_limit: int = 5
):
    try:
        # 1. Fetch Saved Jobs
        saved_jobs = (
            db.query(SavedJob)
            .filter(SavedJob.user_id == user_id)
            .order_by(SavedJob.saved_at.desc())
            .limit(jobs_limit)
            .all()
        )

        # 2. Fetch Documents (Resumes)
        if resumes_limit is None:
            resumes = (
                db.query(Resume)
                .filter(Resume.user_id == user_id)
                .order_by(Resume.id.desc())
                .all()
            )
        else:
            resumes = (
                db.query(Resume)
                .filter(Resume.user_id == user_id)
                .order_by(Resume.id.desc())
                .limit(resumes_limit)
                .all()
            )

        documents = []
        for r in resumes:
            # Ensure resume_data is a dictionary
            resume_data = r.resume_data if isinstance(r.resume_data, dict) else {}

            document = {
                "id": r.id,
                "file_name": r.file_name or f"Resume_{r.id}.pdf",
                "download_url": r.download_url or generate_default_download_url(r.id),
                "created_at": r.created_at,  # Use created_at instead of timestamp
                "personal_info": resume_data.get('personal_info', {})
            }
            documents.append(document)

        # 3. Fetch Upcoming Events
        upcoming_events = (
            db.query(Event)
            .filter(Event.event_date >= datetime.utcnow())
            .order_by(Event.event_date.asc())
            .limit(events_limit)
            .all()
        )

        # 4. Fetch a Random Career Tip
        career_tips = db.query(CareerTip).all()
        random_tip = random.choice(career_tips) if career_tips else None

        # Additional: Check total number of resumes
        total_resumes_count = db.query(Resume).filter(Resume.user_id == user_id).count()

        return DashboardResponse(
            saved_jobs=saved_jobs,
            documents=documents,
            upcoming_events=upcoming_events,
            career_tip=random_tip,
            metadata={
                "total_resumes_count": total_resumes_count
            }
        )

    except Exception as e:
        logger.error(f"Error in dashboard retrieval for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not retrieve dashboard information")


def generate_default_download_url(resume_id: int) -> str:
    os.makedirs("static/resumes", exist_ok=True)
    default_filepath = f"static/resumes/resume_{resume_id}_default.pdf"
    if not os.path.exists(default_filepath):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        c = canvas.Canvas(default_filepath, pagesize=letter)
        c.setFont("Helvetica", 12)
        c.drawString(100, 750, f"Resume {resume_id} - Placeholder")
        c.save()

    return f"{BACKEND_BASE_URL}/static/resumes/resume_{resume_id}_default.pdf"


@app.get("/debug/saved-jobs/{user_id}")
def debug_saved_jobs(user_id: str, db: Session = Depends(get_resume_db)):
    try:
        saved_jobs = db.query(SavedJob).filter(SavedJob.user_id == user_id).all()
        return {
            "count": len(saved_jobs),
            "jobs": [
                {
                    "id": job.id,
                    "job_title": job.job_title,
                    "company_name": job.company_name,
                    "saved_at": str(job.saved_at)
                }
                for job in saved_jobs
            ]
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/test/save-job")
def test_save_job(
        user_id: str = Form(...),
        job_title: str = Form(...),
        company_name: str = Form(...),
        apply_link: str = Form(None)
):
    db = SessionLocal()
    try:
        db_job = SavedJob(
            user_id=user_id,
            job_title=job_title,
            company_name=company_name,
            apply_link=apply_link,
            saved_at=datetime.utcnow()
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)

        # Verify by fetching
        saved_jobs = db.query(SavedJob).filter(SavedJob.user_id == user_id).all()

        return {
            "success": True,
            "job_id": db_job.id,
            "total_saved_jobs": len(saved_jobs)
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


@app.delete("/users/{user_id}/jobs/{job_id}")
def delete_saved_job(user_id: str, job_id: int, db: Session = Depends(get_resume_db)):
    try:
        logger.info(f"Attempting to delete job {job_id} for user {user_id}")

        # Find the job that matches both user_id and job_id
        job = db.query(SavedJob).filter(
            SavedJob.id == job_id,
            SavedJob.user_id == user_id
        ).first()

        # Check if job exists and belongs to the user
        if not job:
            logger.warning(f"Job {job_id} not found for user {user_id}")
            raise HTTPException(
                status_code=404,
                detail="Job not found or does not belong to this user"
            )

        # Delete the job
        db.delete(job)
        db.commit()

        logger.info(f"Successfully deleted job {job_id} for user {user_id}")
        return {"success": True, "message": "Job deleted successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting job {job_id} for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")


@app.get("/users/{user_id}/check-saved-job")
def check_saved_job(
        user_id: str,
        title: str,
        company: str,
        db: Session = Depends(get_resume_db)
):
    """Check if a job with matching title and company is already saved by this user"""
    try:
        job = db.query(SavedJob).filter(
            SavedJob.user_id == user_id,
            SavedJob.job_title == title,
            SavedJob.company_name == company
        ).first()

        if job:
            return {"is_saved": True, "job_id": job.id}
        else:
            return {"is_saved": False, "job_id": None}
    except Exception as e:
        logger.error(f"Error checking saved job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to check saved job: {str(e)}")


def extract_scheduling_info(query: str):
    """Extract phone number and time from user query"""
    # Phone number pattern (Indian format)
    phone_pattern = r'\b[6-9]\d{9}\b'
    phone_match = re.search(phone_pattern, query)
    phone_number = phone_match.group() if phone_match else None

    # Time pattern (various formats)
    time_patterns = [
        r'\b(\d{1,2}):(\d{2})\b',  # 13:47, 3:30
        r'\b(\d{1,2})\s*(?:am|pm|AM|PM)\b',  # 3pm, 3 PM
        r'at\s+(\d{1,2})',  # at 3
    ]

    scheduled_time = None
    for pattern in time_patterns:
        time_match = re.search(pattern, query)
        if time_match:
            # Parse the time and create a datetime for today
            if ':' in query:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
            else:
                hour = int(time_match.group(1))
                minute = 0

            # Create datetime for today at that time
            now = datetime.now()
            scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If the time has already passed today, schedule for tomorrow
            if scheduled_time < now:
                scheduled_time += timedelta(days=1)
            break

    return phone_number, scheduled_time


from postgres_models import Interview


def create_interview_record(db: Session, user_id: str, phone_number: str, scheduled_time: datetime) -> int:
    """Create an interview record in the database"""
    try:
        interview = Interview(
            user_id=user_id,
            phone_number=phone_number,
            scheduled_time=scheduled_time,
            status="scheduled"
        )
        db.add(interview)
        db.commit()
        db.refresh(interview)

        logger.info(f"Created interview record {interview.id} for user {user_id}")
        return interview.id
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating interview record: {e}")
        raise



@app.post("/schedule_interview")
async def schedule_interview(request: ScheduleRequest):
    # 1. Save interview details to your database (PostgreSQL)
    #    Create a new `MockInterview` record with a status of 'SCHEDULED'.
    #    interview_id = db_interview.id
    interview_id = 1  # Placeholder

    # 2. Schedule the Celery task
    initiate_interview_call.apply_async(
        args=[request.phone_number, interview_id],
        eta=request.scheduled_time  # 'eta' schedules it for a specific time
    )

    return {"status": "success", "message": "Interview scheduled successfully!"}





# Store conversation state in Redis
def get_interview_state(interview_id):
    state = redis_client.get(f"interview_state:{interview_id}")
    return json.loads(state) if state else {"history": []}


def set_interview_state(interview_id, state):
    redis_client.set(f"interview_state:{interview_id}", json.dumps(state))


@app.post("/interview/start/{interview_id}")
async def start_interview(interview_id: int):
    """
    Twilio calls this webhook when the user answers the phone.
    """
    response = VoiceResponse()

    # Initial greeting and first question
    first_question = "Hello, this is Asha, your AI-powered career coach. Welcome to your mock interview. Let's start with a classic question: Tell me about yourself."

    # Save the first question to state
    state = {"history": [{"role": "model", "parts": [{"text": first_question}]}]}
    set_interview_state(interview_id, state)

    gather = Gather(input='speech', action=f'/interview/continue/{interview_id}', speechTimeout='auto')
    gather.say(first_question, voice='Polly.Joanna')
    response.append(gather)

    return str(response), {"Content-Type": "text/xml"}


@app.post("/interview/continue/{interview_id}")
async def continue_interview(interview_id: int, request: Request):
    """
    Twilio calls this after the user speaks.
    """
    twiml_response = VoiceResponse()
    form_data = await request.form()
    user_answer = form_data.get('SpeechResult', '')

    # Get current conversation state
    state = get_interview_state(interview_id)
    state["history"].append({"role": "user", "parts": [{"text": user_answer}]})

    # Get next question from Gemini
    # You would pass state["history"] to Gemini to get a follow-up question
    # next_question_text = call_gemini_for_next_question(state["history"])
    next_question_text = "Thank you for sharing. My next question is: What is your biggest weakness?"  # Placeholder

    # Update and save state
    state["history"].append({"role": "model", "parts": [{"text": next_question_text}]})
    set_interview_state(interview_id, state)

    # Ask the next question
    gather = Gather(input='speech', action=f'/interview/continue/{interview_id}', speechTimeout='auto')
    gather.say(next_question_text, voice='Polly.Joanna')
    twiml_response.append(gather)

    # If no speech is detected, end the call
    twiml_response.say("I didn't hear a response. Thank you for your time. Goodbye.")

    return str(twiml_response), {"Content-Type": "text/xml"}



@app.post("/interview/status/{interview_id}")
async def interview_status(interview_id: int, request: Request):
    """
    Twilio calls this webhook when the interview call is completed.
    This triggers the background task for analysis and feedback.
    """
    form_data = await request.form()
    recording_url = form_data.get('RecordingUrl')

    if recording_url:
        logger.info(f"Interview {interview_id} completed. Recording available at: {recording_url}")
        # Trigger the background task for analysis
        analyze_interview.delay(interview_id, recording_url)
    else:
        logger.warning(f"Interview {interview_id} completed, but no recording URL was provided.")

    return "OK", 200

# Include auth routes
app.include_router(auth_router)