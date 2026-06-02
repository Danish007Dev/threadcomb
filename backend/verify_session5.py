import asyncio
import os
import sys
import os
sys.path.insert(0, os.path.abspath('..'))

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

from database.mongodb import MongoDBSingleton
from services.revenue_guardian import run_urgency_aggregation
from services.orchestrator import route_deterministic, route_with_llm

async def main():
    db = MongoDBSingleton.get_db()
    creator_id = "ananya.creates.demo@threadcomb.com"  # Using email for lookup
    
    creator = await db.creators.find_one({"email": creator_id})
    if not creator:
        print("FAIL: Demo creator not found. Please run seed_demo.py first.")
        return
        
    c_id = str(creator["_id"])

    print("--- 1. Revenue Guardian Urgency Aggregation ---")
    invoices = await run_urgency_aggregation(db, c_id)
    if len(invoices) >= 2:
        print(f"PASS: Found {len(invoices)} overdue invoices.")
        for inv in invoices:
            score = inv.get("urgency_score")
            tone = inv.get("recommended_tone")
            print(f"  - Invoice: overdue {inv.get('days_overdue')} days, score: {score}, tone: {tone}")
            if score is None or tone is None:
                print("  FAIL: Missing urgency_score or recommended_tone")
    else:
        print(f"FAIL: Expected >= 2 overdue invoices, found {len(invoices)}")

    print("\n--- 5. Orchestrator routes correctly ---")
    agent1, conf1 = route_deterministic("check my invoices")
    if agent1 == "revenue_guardian":
        print("PASS: 'check my invoices' routed to revenue_guardian (deterministic)")
    else:
        print(f"FAIL: 'check my invoices' routed to {agent1}")
        
    agent2, conf2 = await route_with_llm("reply to Myntra email")
    if agent2 == "deal_chief":
        print("PASS: 'reply to Myntra email' routed to deal_chief (LLM)")
    else:
        print(f"FAIL: 'reply to Myntra email' routed to {agent2}")
        
    print("\n--- 9. Data export works ---")
    MongoDBSingleton.close() # Close to reset event loop
    
    from fastapi.testclient import TestClient
    from server import app
    from routers.auth import get_current_creator
    
    # Mock auth for the test client
    app.dependency_overrides[get_current_creator] = lambda: {"_id": c_id}
    client = TestClient(app)
    
    response = client.get("/api/settings/export")
    if response.status_code == 200:
        data = response.json()
        if "deals" in data and "invoices" in data and "skills_map" in data:
            if data["deals"] and "embedding_vector" not in data["deals"][0]:
                print("PASS: Export contains deals, invoices, skills_map, and embedding_vector is excluded.")
            else:
                print("FAIL: Export missing or embedding_vector included")
        else:
            print("FAIL: Export missing key arrays")
    else:
        print(f"FAIL: Export returned {response.status_code}")
    
    print("\n--- 12. No send outside approval endpoints ---")
    # This is a static analysis check, we'll grep it next.

if __name__ == "__main__":
    asyncio.run(main())
