# postgres_client.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
from postgres_models import Base

# Load .env variables
load_dotenv()

# Fetch PostgreSQL URL securely
POSTGRES_URL = os.getenv("POSTGRES_URL")

# Setup engine and session
engine = create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables in the database (if they don't exist)
Base.metadata.create_all(bind=engine)
