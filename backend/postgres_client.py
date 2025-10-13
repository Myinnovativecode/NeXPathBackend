import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from postgres_models import Base, UserProfile, Interview

load_dotenv()

# Prefer Render-provided DATABASE_URL, fall back to POSTGRES_URL if present
url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
if not url:
    raise RuntimeError("DATABASE_URL (or POSTGRES_URL) is not set")

# Normalize scheme: Render often uses 'postgres://', but SQLAlchemy prefers 'postgresql://'
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

# If you stay on psycopg2, you can leave it as postgresql://
# If you move to psycopg v3, use 'postgresql+psycopg://'
# For Python 3.11 + psycopg2-binary 2.9.9, this is fine:
engine = create_engine(url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def get_user_name_from_db(db: Session, user_id: str) -> str:
    user = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return user.name if user and user.name else None