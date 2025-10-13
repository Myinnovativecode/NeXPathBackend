import redis
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client = None

try:
    # Render Redis uses TLS (rediss://), local dev uses redis://
    if REDIS_URL.startswith("rediss://"):
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            ssl_cert_reqs=None,  # Required for Render Redis
            socket_connect_timeout=5,
            socket_keepalive=True
        )
    else:
        # Local development
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True
        )

    # Test connection
    redis_client.ping()
    logger.info("✅ Connected to Redis!")
    print("✅ Connected to Redis!")
except redis.ConnectionError as e:
    logger.error(f"❌ Redis connection failed: {e}")
    print(f"❌ Redis connection failed: {e}")
    redis_client = None
except Exception as e:
    logger.error(f"❌ Unexpected Redis error: {e}")
    print(f"❌ Unexpected Redis error: {e}")
    redis_client = None


# Store user conversation
def store_user_conversation(sender_id, message):
    """
    Stores the user's message in Redis for the session (conversation history).

    :param sender_id: Unique ID for the user (session)
    :param message: The user's message to store
    """
    if redis_client:
        try:
            redis_client.rpush(f"user:{sender_id}:messages", message)
        except Exception as e:
            logger.error(f"Error storing conversation: {e}")
    else:
        logger.warning("Redis not available, conversation not stored")


# Get user conversation history
def get_user_conversation(sender_id):
    """
    Retrieves the conversation history for a specific user (sender_id).

    :param sender_id: Unique ID for the user (session)
    :return: List of messages (user's conversation history)
    """
    if redis_client:
        try:
            return redis_client.lrange(f"user:{sender_id}:messages", 0, -1)
        except Exception as e:
            logger.error(f"Error retrieving conversation: {e}")
            return []
    else:
        logger.warning("Redis not available, returning empty conversation")
        return []


# Store the last message
def store_last_message(sender_id, message):
    """
    Stores the last message sent by the user for session management.

    :param sender_id: Unique ID for the user (session)
    :param message: The user's last message to store
    """
    if redis_client:
        try:
            redis_client.set(f"user:{sender_id}:last_message", message)
        except Exception as e:
            logger.error(f"Error storing last message: {e}")
    else:
        logger.warning("Redis not available, last message not stored")


# Get the last message
def get_last_message(sender_id):
    """
    Retrieves the last message sent by the user.

    :param sender_id: Unique ID for the user (session)
    :return: The last message sent by the user
    """
    if redis_client:
        try:
            return redis_client.get(f"user:{sender_id}:last_message")
        except Exception as e:
            logger.error(f"Error retrieving last message: {e}")
            return None
    else:
        logger.warning("Redis not available, returning None")
        return None