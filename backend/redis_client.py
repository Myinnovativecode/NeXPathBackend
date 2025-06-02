import redis

# Connect to Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Optional: test connection
try:
    redis_client.ping()
    print(" Connected to Redis!")
except redis.ConnectionError:
    print(" Redis connection failed.")


# Store user conversation
def store_user_conversation(sender_id, message):
    """
    Stores the user's message in Redis for the session (conversation history).

    :param sender_id: Unique ID for the user (session)
    :param message: The user's message to store
    """
    # Push the message to a list specific to the user
    redis_client.rpush(f"user:{sender_id}:messages", message)


# Get user conversation history
def get_user_conversation(sender_id):
    """
    Retrieves the conversation history for a specific user (sender_id).

    :param sender_id: Unique ID for the user (session)
    :return: List of messages (user's conversation history)
    """
    return redis_client.lrange(f"user:{sender_id}:messages", 0, -1)


# Store the last message
def store_last_message(sender_id, message):
    """
    Stores the last message sent by the user for session management.

    :param sender_id: Unique ID for the user (session)
    :param message: The user's last message to store
    """
    redis_client.set(f"user:{sender_id}:last_message", message)


# Get the last message
def get_last_message(sender_id):
    """
    Retrieves the last message sent by the user.

    :param sender_id: Unique ID for the user (session)
    :return: The last message sent by the user
    """
    return redis_client.get(f"user:{sender_id}:last_message")