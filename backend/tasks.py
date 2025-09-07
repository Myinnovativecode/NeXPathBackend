# tasks.py

from celery import Celery
import os
import json
import requests
from twilio.rest import Client
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Celery Configuration ---
celery_app = Celery('tasks', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))

# --- Service Clients ---
# Twilio Client
twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(twilio_account_sid, twilio_auth_token)

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# SendGrid Configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")


# --- Helper Functions ---

def get_interview_state(interview_id: int):
    """Fetches interview state from Redis."""
    # This function needs access to your redis_client.
    # For simplicity, we assume a redis_client is available here.
    # In a larger app, you might import it from a shared redis_client.py
    from redis_client import redis_client
    state = redis_client.get(f"interview_state:{interview_id}")
    return json.loads(state) if state else {"history": []}


def call_gemini_for_feedback(transcript: list) -> str:
    """Calls Gemini API to get feedback on the interview transcript."""
    if not GEMINI_API_KEY:
        return "Feedback could not be generated due to a configuration error."

    analysis_prompt = (
            "You are an expert HR interviewer. Based on the following mock interview transcript, "
            "provide constructive, specific, and encouraging feedback for the 'user'. "
            "Focus on these areas:\n"
            "1. Clarity and conciseness of answers.\n"
            "2. Use of the STAR (Situation, Task, Action, Result) method for behavioral questions.\n"
            "3. Overall professionalism and communication style.\n"
            "4. Provide at least two concrete examples of what they did well and two areas for improvement.\n"
            "Structure the feedback in clear sections. Start with 'Overall Feedback:'"
            "\n\nTranscript:\n" + json.dumps(transcript)
    )

    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    data = {"contents": [{"parts": [{"text": analysis_prompt}]}]}

    try:
        response = requests.post(GEMINI_URL, headers=headers, json=data)
        response_json = response.json()
        if 'candidates' in response_json:
            return response_json['candidates'][0]['content']['parts'][0]['text']
        else:
            return "Could not parse feedback from AI service."
    except Exception as e:
        return f"An error occurred while generating feedback: {e}"


def send_feedback_email(user_email: str, recording_url: str, feedback: str):
    """Sends the feedback email using SendGrid."""
    if not SENDGRID_API_KEY or not SENDER_EMAIL:
        print("SendGrid API Key or Sender Email not configured. Cannot send email.")
        return

    # Fix the f-string issue here
    safe_feedback = feedback.replace("\n", "<br>")

    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=user_email,
        subject='Your Asha AI Mock Interview Feedback is Ready!',
        html_content=f"""
        <h3>Hello!</h3>
        <p>Thank you for completing your mock interview with Asha. Here is your feedback and a link to the recording.</p>
        <h4>AI-Generated Feedback:</h4>
        <div style="background-color:#f4f4f4; border-left: 5px solid #ccc; padding: 15px;">
            <p>{safe_feedback}</p>
        </div>
        <h4>Call Recording:</h4>
        <p>You can listen to your interview here: <a href="{recording_url}">{recording_url}</a></p>
        <br>
        <p>Keep practicing, you're on the right track!</p>
        <p>Best regards,</p>
        <p>The Asha AI Team</p>
        """
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Feedback email sent to {user_email}, Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email with SendGrid: {e}")


# --- Celery Tasks ---

@celery_app.task
def initiate_interview_call(user_phone_number: str, interview_id: int):
    try:
        # Replace with your actual ngrok or public URL
        PUBLIC_URL = os.getenv("PUBLIC_URL", "http://your-public-url.ngrok.io")

        call = twilio_client.calls.create(
            to=user_phone_number,
            from_=twilio_phone_number,
            url=f"{PUBLIC_URL}/interview/start/{interview_id}",
            record=True,
            status_callback=f"{PUBLIC_URL}/interview/status/{interview_id}",
            status_callback_event=['completed']
        )
        print(f"Call initiated for interview {interview_id} with SID: {call.sid}")
    except Exception as e:
        print(f"Error initiating call: {e}")


@celery_app.task
def analyze_interview(interview_id: int, recording_url: str):
    """
    Fetches the transcript, sends it to Gemini for feedback, and emails the user.
    """
    from postgres_client import get_user_email_for_interview  # You need to create this function

    # 1. Fetch transcript from Redis state
    state = get_interview_state(interview_id)
    transcript = state.get("history", [])

    if not transcript:
        print(f"No transcript found for interview {interview_id}. Aborting analysis.")
        return

    # 2. Get feedback from Gemini
    feedback = call_gemini_for_feedback(transcript)

    # 3. Get user email from your PostgreSQL database
    #    You need to implement this function in `postgres_client.py`
    user_email = get_user_email_for_interview(interview_id)  # e.g., "user@example.com"

    if not user_email:
        print(f"No user email found for interview {interview_id}. Cannot send feedback.")
        return

    # 4. Send email with SendGrid
    send_feedback_email(user_email, recording_url, feedback)