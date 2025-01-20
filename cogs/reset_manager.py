# cogs/reset_manager.py
from datetime import datetime, timedelta
import pytz
import asyncio
import time
from cogs.constants import (
    DAILY_USAGE_COLLECTION,
    USER_USAGE_SUBCOLLECTION,
    RESET_HOUR,
    RESET_MINUTE
)

async def get_reset_time() -> float:
    """Calculate the next reset time as a UNIX timestamp."""
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    reset_time = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
    if now >= reset_time:
        reset_time += timedelta(days=1)
    return reset_time.timestamp()

async def reset_usage(firestore_cog):
    """Reset guild and user usage counts at the specified reset time."""
    while True:
        current_time = time.time()
        reset_time = await get_reset_time()
        wait_time = reset_time - current_time

        if wait_time > 0:
            print(f"Waiting {wait_time:.2f} seconds for the next reset...")
            await asyncio.sleep(wait_time)

        print("Resetting daily usage counts...")

        try:
            # Convert guild_docs generator to a list for synchronous iteration
            guild_docs = list(firestore_cog.db.collection(DAILY_USAGE_COLLECTION).stream())
            for guild_doc in guild_docs:
                guild_id = guild_doc.id
                await firestore_cog.set_daily_usage(guild_id, usage_count=0)

                # Convert user_docs generator to a list
                user_docs = list(
                    firestore_cog.db.collection(DAILY_USAGE_COLLECTION)
                    .document(guild_id)
                    .collection(USER_USAGE_SUBCOLLECTION)
                    .stream()
                )
                for user_doc in user_docs:
                    user_id = user_doc.id
                    await firestore_cog.set_daily_usage(guild_id, usage_count=0, user_id=int(user_id))

                # Convert session_docs generator to a list
                session_docs = list(
                    firestore_cog.sessions_collection.where('guild_id', '==', guild_id).stream()
                )
                for session_doc in session_docs:
                    await firestore_cog.remove_session(session_doc.id)

                print(f"Reset usage counts and cleaned up sessions for guild {guild_id}.")

            print("Daily usage counts reset successfully.")

        except Exception as e:
            print(f"Error during usage reset: {e}")

        # Calculate the next reset time
        reset_time = await get_reset_time()

