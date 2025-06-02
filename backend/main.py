from datetime import datetime
from typing import Optional
import logging
import uuid
import json
from pathlib import Path
import os


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
import httpx
from dotenv import load_dotenv

from user_routes import router as user_router
from redis_client import redis_client
from mongodb_client import save_chat_to_mongodb, get_user_chat_history, get_chat_by_session_id, chat_collection
from postgres_models import MentorshipRequest
from postgres_client import SessionLocal
from auth_routes import router as auth_router
from utils import remove_invalid_characters
import logging


# Basic logging setup
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more verbosity
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)



# Load environment variables
load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# Initialize FastAPI app
app = FastAPI()
app.include_router(user_router)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load mentorship links
mentor_links_path = Path(__file__).parent / "mentor_links.json"
with open(mentor_links_path, "r") as f:
    MENTOR_PLATFORM_LINKS = json.load(f)



# ------------- Models ---------------

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

# ------------- Rasa Communication ---------------

async def talk_to_rasa(message: str, sender_id: str = "default"):
    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                "http://localhost:5005/webhooks/rest/webhook",
                json={"message": message, "sender": sender_id}
            )
            return response.json()
        except httpx.RequestError as e:
            logging.error("Rasa is unavailable: %s", e)
            return [{"text": "Sorry, I'm having trouble reaching my AI brain. Please try again later."}]

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

@app.post("/job_search/")
async def process_job_search(request: JobSearchRequest):
    jobs = await fetch_real_time_jobs(
        request.job_title, request.location,
        page=request.page,
        limit=request.limit
    )

    if jobs:
        job_listings = "\n".join(
            [
                f"🔗 [{remove_invalid_characters(job.get('job_title'))} – "
                f"{remove_invalid_characters(job.get('employer_name'))} "
                f"({remove_invalid_characters(job.get('job_city'))})]({job['job_apply_link']})"
                for job in jobs if 'job_apply_link' in job
            ]
        )

        response_text = (
            f"🌟 **Jobs for {request.job_title} in {request.location}**\n\n"
            f"{job_listings}\n\n"
            "🚀 **Apply now and join our women-in-tech network!**"
        )
    else:
        response_text = (
            f"❌ No jobs found for {request.job_title} in {request.location}.\n"
            "But don’t worry! Try again later or check out our mentorship programs to stay prepared."
        )

    return JSONResponse(
        content={"response": response_text, "source": "real-time"},
        headers={"Content-Type": "application/json; charset=utf-8"}
    )

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
            messages.append(message)

        if not messages:
            raise HTTPException(status_code=404, detail="Session not found")

        return JSONResponse(
            content=jsonable_encoder(messages),
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/chat/")
async def process_chat(message: ChatMessage):
    user_query = message.query
    user_id = message.user_id or "anonymous"

    logger.info(f"Received message from user {user_id}: {user_query}")

    if not user_query:
        logger.warning("No query provided in the message.")
        raise HTTPException(status_code=400, detail="Message query is required.")

    # Generate or fetch session ID
    session_id_key = f"session:{user_id}"
    session_id = redis_client.get(session_id_key)
    if isinstance(session_id, bytes):
        session_id = session_id.decode("utf-8")

    new_session = False
    if not session_id:
        session_id = str(uuid.uuid4())
        new_session = True
        redis_client.set(session_id_key, session_id)
        redis_client.set(f"title:{session_id}", remove_invalid_characters(user_query.strip()[:50]))

    try:
        rasa_responses = await talk_to_rasa(user_query, sender_id=user_id)

        # Combine all text responses if multiple
        bot_reply_text = "\n".join([r["text"] for r in rasa_responses if "text" in r]) or \
                         "Sorry, I didn’t understand that."

        intent = rasa_responses[0].get("intent", {}).get("name") if rasa_responses else None
        entities = rasa_responses[0].get("entities") if rasa_responses else None

    except Exception as e:
        logger.error(f"Error talking to Rasa: {e}")
        bot_reply_text = "Something went wrong while getting a response. Please try again."
        intent = None
        entities = None

    logger.info(f"Bot response to user {user_id} (session {session_id}): {bot_reply_text}")

    # Save chat
    save_chat_to_mongodb(
        session_id=session_id,
        user_id=user_id,
        user_message=user_query,
        bot_response=bot_reply_text,
        intent=intent,
        entities=entities,
    )

    title = redis_client.get(f"title:{session_id}")
    if isinstance(title, bytes):
        title = title.decode("utf-8")

    return JSONResponse(
        content={
            "response": bot_reply_text,
            "session_id": session_id,
            "title": title
        },
        headers={"Content-Type": "application/json; charset=utf-8"}
    )




# Include auth routes
app.include_router(auth_router)



















