from fastapi import FastAPI
from typing import List
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

mock_jobs = [
    {"title": "Data Scientist - Remote", "company": "TechCorp", "location": "Remote"},
    {"title": "ML Engineer - Bangalore", "company": "AI Innovators", "location": "Bangalore"},
    {"title": "AI Intern - Mumbai", "company": "FutureAI", "location": "Mumbai"}
]

@app.get("/jobs")
def get_jobs(role: str = "", location: str = ""):
    filtered = [
        job for job in mock_jobs
        if (role.lower() in job["title"].lower()) and (location.lower() in job["location"].lower())
    ]
    return {"jobs": filtered or mock_jobs}
