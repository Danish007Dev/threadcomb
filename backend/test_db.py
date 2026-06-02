import asyncio
import os
import sys

# Ensure imports work from the root dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)).replace('\\backend', ''))

from backend.database.mongodb import MongoDBSingleton

async def test():
    db = MongoDBSingleton.get_db()
    c = await db.creators.find_one({'email': 'mdanish0852@gmail.com'})
    print("CREATOR:", c)
    if c:
        creator_id = c.get('creator_id', str(c['_id']))
        report = await db.audit_reports.find_one({'creator_id': creator_id})
        print("REPORT:", report)
    else:
        print("No creator found")

if __name__ == "__main__":
    asyncio.run(test())
