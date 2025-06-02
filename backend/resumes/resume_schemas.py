# resume_schemas.py
from pydantic import BaseModel

class ResumeCreate(BaseModel):
    user_id: str
    name: str
    email: str
    phone: str
    education: str
    experience: str
    skills: str
