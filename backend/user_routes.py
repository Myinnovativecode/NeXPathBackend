from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from postgres_models import UserProfile  # your SQLAlchemy model
from postgres_client import SessionLocal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/user/{user_id}")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "contact_number": user.contact_number,
    }
