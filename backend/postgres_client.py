import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from postgres_models import Base, UserProfile, Interview

load_dotenv()

url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
if not url:
    raise RuntimeError("DATABASE_URL is not set")

# Normalize for SQLAlchemy + psycopg3
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg://", 1)
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def get_user_name_from_db(db: Session, user_id: str) -> str:
    user = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return user.name if user and user.name else None