import re
import httpx
from typing import Any, Dict, List, Text
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.forms import FormValidationAction   #
from rasa_sdk.events import SlotSet, EventType    #
import requests


# Validation for mentorship form
class ValidateGetMentorshipForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_get_mentorship_form"

    def validate_mentorship_area(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        allowed_fields = ["ai", "ml", "web development", "data science", "cybersecurity", "cloud", "blockchain"]

        normalized_value = slot_value.lower()
        if normalized_value in allowed_fields:
            return {"mentorship_area": slot_value}
        else:
            dispatcher.utter_message(text="⚠️ Sorry, we don't have mentors for that field. Please enter a valid area like AI, ML, or Web Development.")
            return {"mentorship_area": None}


# Form Validation Class for Job Search
class ValidateJobSearchForm(FormValidationAction):

    def name(self) -> Text:
        return "validate_job_search_form"

    def validate_job_role(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        """Validate the job role input."""
        if slot_value and len(slot_value) > 2:  # Example validation condition
            return {"job_role": slot_value}
        dispatcher.utter_message(text="Please enter a valid job role.")
        return {"job_role": None}

    def validate_location(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        """Validate the location input."""
        if slot_value and len(slot_value) > 1:  # Example validation condition
            return {"location": slot_value}
        dispatcher.utter_message(text="Please enter a valid location.")
        return {"location": None}


# Action to Search Jobs from FastAPI Backend
class ActionSearchJobs(Action):

    def name(self) -> Text:
        return "action_search_jobs"

    async def run(self,
                  dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: DomainDict) -> List[Dict[Text, Any]]:

        job_role = tracker.get_slot("job_role")
        location = tracker.get_slot("location")

        # Prepare payload for FastAPI backend
        payload = {
            "job_title": job_role,
            "location": location
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/job_search/",  # Replace with actual FastAPI URL
                    json=payload,
                    timeout=60.0
                )

            if response.status_code == 200:
                data = response.json()
                dispatcher.utter_message(text=data.get("response"))
            else:
                dispatcher.utter_message(
                    text="⚠️ Sorry, I couldn’t fetch jobs right now. Please try again later."
                )
        except Exception as e:
            print(f"Error calling job search API: {e}")
            dispatcher.utter_message(
                text="❌ Something went wrong while searching for jobs."
            )

        return []



# Custom Action to connect mentorship


class ActionConnectMentorship(Action):
    def name(self) -> Text:
        return "action_connect_mentorship"

    async def run(self,
                  dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: DomainDict) -> List[Dict[Text, Any]]:

        user_id = tracker.get_slot("user_id") or 0
        interest_field = tracker.get_slot("mentorship_area")

        payload = {
            "user_id": int(user_id),
            "interest_field": interest_field
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://127.0.0.1:8000/connect_mentorship/",
                    json=payload,
                    timeout=120.0
                )

            if response.status_code == 200:
                data = response.json()
                dispatcher.utter_message(text=data.get("response", "Mentorship details sent!"))
            else:
                dispatcher.utter_message(text="❌ Sorry, we couldn't connect you to a mentor at the moment.")
        except Exception as e:
            dispatcher.utter_message(text=f"Error connecting mentorship: {str(e)}")

        return []





class ActionTriggerResumeForm(Action):
    def name(self) -> str:
        return "action_trigger_resume_form"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[str, Any]) -> List[Dict[str, Any]]:

        dispatcher.utter_message(json_message={
            "trigger": "resume_form",  # ← Frontend will catch this and show form
            "message": "Opening resume form for you..."
        })
        return []








