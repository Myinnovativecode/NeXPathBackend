# mongodb_client.py
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)

# Access DB and collection
db = client["asha_ai_chatbot_db"]
chat_collection = db["chat_sessions"]

# Create indexes for performance and TTL
chat_collection.create_index([("user_id", 1), ("timestamp", -1)])
chat_collection.create_index("timestamp", expireAfterSeconds=2592000)  # 30 days
chat_collection.create_index("session_id")  # Index for efficient session grouping

# Store chat in MongoDB with separate session_id
# mongodb_client.py

# ... (imports and client setup) ...

# Store chat in MongoDB with a more flexible schema
def save_chat_to_mongodb(session_id: str, user_id: str, role: str, message: str, intent: str = None,
                         entities: dict = None):
    """
    Saves a single message to the chat history.
    role: can be 'user' or 'bot'
    """
    from datetime import datetime
    chat_document = {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "message": message,
        "timestamp": datetime.utcnow(),
        "intent": intent,
        "entities": entities or {}
    }

    # This print statement is excellent for debugging.
    print("Attempting to save document to MongoDB:", chat_document)

    # The insert operation itself
    result = chat_collection.insert_one(chat_document)

    # Optional: Confirm the insert was successful
    if not result.inserted_id:
        raise Exception("MongoDB insert_one failed to return an inserted_id.")


# Retrieve chat history for a user (grouped by session_id optionally)
def get_user_chat_history(user_id: str):
    return list(chat_collection.find({"user_id": user_id}).sort("timestamp", -1))

# Optional: expose collection object
def get_chat_collection():
    return chat_collection

def get_chat_by_session_id(session_id: str):
    from pymongo import MongoClient
    from bson import ObjectId
    import os

    client = MongoClient(os.getenv("MONGO_URI"))
    db = client.asha_ai_chatbot_db
    collection = db.chat_sessions

    chat = list(collection.find({"session_id": session_id}))
    return chat if chat else None

