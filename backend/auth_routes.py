import uuid
import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import httpx

from postgres_client import SessionLocal  # Your DB session
from postgres_models import UserProfile  # Your SQLAlchemy user model

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/google/callback"  # Update for production

# -------------------
# Email Signup/Login
# -------------------

class SignupRequest(BaseModel):
    name: str
    email: str

class LoginRequest(BaseModel):
    email: str

@router.post("/signup_user")
def signup_user(data: SignupRequest):
    db: Session = SessionLocal()
    try:
        existing_user = db.query(UserProfile).filter(UserProfile.email == data.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")

        user_id = str(uuid.uuid4())

        new_user = UserProfile(
            user_id=user_id,
            name=data.name,
            email=data.email,
            contact="",  # contact is optional/not used here
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "user_id": new_user.user_id,
            "name": new_user.name,
            "email": new_user.email
        }
    finally:
        db.close()

@router.post("/login_user")
def login_user(data: LoginRequest):
    db: Session = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.email == data.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email
        }
    finally:
        db.close()

# -------------------
# Google OAuth2 Login
# -------------------

@router.get("/google/login")
def login_with_google():
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=consent"
    )
    return RedirectResponse(url=google_auth_url)

@router.get("/google/callback")
async def google_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    async with httpx.AsyncClient() as client:
        # Exchange code for tokens
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_json = token_response.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to obtain access token")

        # Get user info from Google
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info = userinfo_response.json()

    email = user_info.get("email")
    name = user_info.get("name")
    google_id = user_info.get("id")
    # picture = user_info.get("picture")  # Optional

    if not email:
        raise HTTPException(status_code=400, detail="Email not available from Google")

    # Create or get user from DB
    db: Session = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not user:
            user = UserProfile(
                user_id=str(uuid.uuid4()),
                name=name or "Google User",
                email=email,
                contact="",  # No contact from Google
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    finally:
        db.close()

    # ✅ Redirect to Asha AI Chatbot home (not login/signup)
    frontend_chat_url = f"http://localhost:5173/chat?user_id={user.user_id}&name={user.name}&email={user.email}"
    return RedirectResponse(url=frontend_chat_url)



