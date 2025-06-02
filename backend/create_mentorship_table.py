from postgres_models import MentorshipRequest, Base  # adjust import if needed
from postgres_client import engine  # reuse the existing engine

# Create only the mentorship_requests table
MentorshipRequest.__table__.create(bind=engine, checkfirst=True)

print("✅ mentorship_requests table created (if not already exists)")
