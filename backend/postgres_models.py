# postgres_models.py

from sqlalchemy import Column, Integer, String, Text ,JSON ,DateTime ,ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

from sqlalchemy.orm import relationship

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    contact = Column(String)  # <-- Added this line


class MentorshipRequest(Base):
    __tablename__ = "mentorship_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    interest_field = Column(String ,nullable=False)



# 🔽 ADD THIS for Resume Builder
class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # Could be chat session ID or user account ID
    resume_data = Column(JSON)  # Stores all resume data in JSON format
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    download_url = Column(String, nullable=True)
    template_used = Column(String, default="professional")
    file_name = Column(String, nullable=True)



class SavedJob(Base):
    __tablename__ = "saved_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False) # Or ForeignKey('users.id') if you have a users table
    job_title = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    apply_link = Column(String, nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    event_date = Column(DateTime, nullable=False)
    join_link = Column(String, nullable=True)

class CareerTip(Base):
    __tablename__ = "career_tips"
    id = Column(Integer, primary_key=True, index=True)
    tip_text = Column(Text, nullable=False)


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # Changed to String to match UserProfile.user_id
    phone_number = Column(String, nullable=False)  # Add this field
    scheduled_time = Column(DateTime, nullable=False)  # Add this field
    status = Column(String, default="scheduled")  # scheduled, completed, cancelled
    recording_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Note: Remove the relationship for now since we're using string user_id