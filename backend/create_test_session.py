import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.mongodb import MongoDBSingleton
from datetime import datetime, timedelta, timezone
import secrets

async def create_session():
    db = MongoDBSingleton.get_db()
    c = await db.creators.find_one({'email': 'mdanish0852@gmail.com'})
    if not c:
        print("No creator found")
        return None
        
    creator_id = c.get('creator_id')
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    
    await db.creator_sessions.insert_one({
        "creator_id": creator_id,
        "session_token": session_token,
        "expires_at": expires_at
    })
    
    print("SESSION_TOKEN:", session_token)
    print("CREATOR_ID:", creator_id)

if __name__ == "__main__":
    asyncio.run(create_session())
