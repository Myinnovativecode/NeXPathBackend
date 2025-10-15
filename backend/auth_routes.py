# auth_routes.py
import uuid
import os
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import httpx

from postgres_client import SessionLocal
from postgres_models import UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# ✅ Use env vars for production URLs
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://nexpathbackend-1.onrender.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://nexpath.vercel.app")

# ✅ Production redirect URI (must match Google Console)
REDIRECT_URI = f"{BACKEND_BASE_URL}/auth/google/callback"

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
            contact="",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {"user_id": new_user.user_id, "name": new_user.name, "email": new_user.email}
    finally:
        db.close()

@router.post("/login_user")
def login_user(data: LoginRequest):
    db: Session = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.email == data.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {"user_id": user.user_id, "name": user.name, "email": user.email}
    finally:
        db.close()

@router.get("/google/login")
def login_with_google():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    return RedirectResponse(url="https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))

@router.get("/google/callback")
async def google_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    async with httpx.AsyncClient() as client:
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
        raise HTTPException(status_code=400, detail=f"Failed to obtain access token: {token_json}")

    async with httpx.AsyncClient() as client:
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info = userinfo_response.json()

    email = user_info.get("email")
    name = user_info.get("name") or "Google User"
    if not email:
        raise HTTPException(status_code=400, detail="Email not available from Google")

    db: Session = SessionLocal()
    try:
        user = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not user:
            user = UserProfile(
                user_id=str(uuid.uuid4()),
                name=name,
                email=email,
                contact="",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
    finally:
        db.close()

    # ✅ Redirect back to your frontend (not localhost)
    qs = urlencode({"user_id": user.user_id, "name": user.name, "email": user.email})
    return RedirectResponse(url=f"{FRONTEND_URL}/chat?{qs}")


