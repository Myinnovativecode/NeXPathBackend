from sklearn import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
import os
from postgres_models import Base, UserProfile  ,Interview# ✅ Add UserProfile import

# Load .env variables
load_dotenv()

# Fetch PostgreSQL URL securely
POSTGRES_URL = os.getenv("POSTGRES_URL")

# Setup engine and session
engine = create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables in the database (if they don't exist)
Base.metadata.create_all(bind=engine)

# ✅ Utility to fetch name from user_profiles table
def get_user_name_from_db(db: Session, user_id: str) -> str:
    user = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if user and user.name:
        logger.info(f"👉 Looking up user name from database : {user.name}")
        return user.name
    return None



def get_user_email_for_interview(interview_id: int) -> str:
    """Given an interview_id, fetch the associated user's email address."""
    db: Session = SessionLocal()
    try:
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        if interview and interview.user and interview.user.email:
            return interview.user.email
        return None
    except Exception as e:
        print(f"DB error fetching email for interview {interview_id}: {e}")
        return None
    finally:
        db.close()