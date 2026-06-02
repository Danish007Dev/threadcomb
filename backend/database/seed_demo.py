"""
Seeds a demo creator account with realistic brand deal history.
Use this to populate the demo environment for the hackathon video.
Run: python backend/database/seed_demo.py

Creates:
- 1 demo creator (ananya.creates.demo@threadcomb.com)
- 20 brand deal emails (mix of unanswered, negotiating, paid, overdue)
- 5 brands (Minimalist, Mamaearth, boAt, Unacademy, Zomato)
- 3 overdue invoices
- A pre-generated Audit Report showing ₹2,25,000 in recoverable value
- 2 pending deal drafts ready for approval
"""

import asyncio
from datetime import datetime, timedelta
from bson import ObjectId
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)).replace('\\database', ''))

from database.mongodb import MongoDBSingleton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DEMO_CREATOR_EMAIL = "ananya.creates.demo@threadcomb.com"
DEMO_CREATOR_EMAIL = "mdanish0852@gmail.com"

DEMO_BRANDS = [
    {
        "name": "Minimalist",
        "domain": "beminimalist.co",
        "category": "beauty",
        "data_source": "demo",
        "payment_intelligence": {"avg_payment_days": 15, "payment_reliability": 0.9, "paid_count": 5}
    },
    {
        "name": "Mamaearth",
        "domain": "mamaearth.in",
        "category": "beauty",
        "data_source": "demo",
        "payment_intelligence": {"avg_payment_days": 30, "payment_reliability": 0.8, "paid_count": 3}
    },
    {
        "name": "boAt",
        "domain": "boat-lifestyle.com",
        "category": "tech",
        "data_source": "demo",
        "payment_intelligence": {"avg_payment_days": 45, "payment_reliability": 0.6, "paid_count": 2, "overdue_count": 1}
    },
    {
        "name": "Unacademy",
        "domain": "unacademy.com",
        "category": "edtech",
        "data_source": "demo",
        "payment_intelligence": {"avg_payment_days": 20, "payment_reliability": 0.85, "paid_count": 4}
    },
    {
        "name": "Zomato",
        "domain": "zomato.com",
        "category": "food",
        "data_source": "demo",
        "payment_intelligence": {"avg_payment_days": 12, "payment_reliability": 0.95, "paid_count": 10}
    },
]

DEMO_DEALS = [
    {
        "brand_name": "Minimalist",
        "brand_domain": "beminimalist.co",
        "brand_category": "beauty",
        "deal_type": "instagram_reel",
        "status": "unanswered",
        "financials": {"amount_inr": 45000, "amount_ambiguity_flag": False, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 Instagram Reel", "2 Stories"], "exclusivity_mentioned": True, "exclusivity_duration_days": 90, "gmail_thread_id": "demo_thread_1"},
        "extraction_confidence": 0.92,
        "thread_unanswered": True,
        "initiated_at": datetime.utcnow() - timedelta(days=2),
    },
    {
        "brand_name": "boAt",
        "brand_domain": "boat-lifestyle.com",
        "brand_category": "tech",
        "deal_type": "youtube_integration",
        "status": "overdue",
        "financials": {"amount_inr": 120000, "amount_ambiguity_flag": False, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 YouTube Integration (60 sec)"], "payment_terms_mentioned": "NET-30", "gmail_thread_id": "demo_thread_2"},
        "extraction_confidence": 0.89,
        "initiated_at": datetime.utcnow() - timedelta(days=60),
    },
    {
        "brand_name": "Mamaearth",
        "brand_domain": "mamaearth.in",
        "brand_category": "beauty",
        "deal_type": "instagram_reel",
        "status": "paid",
        "financials": {"amount_inr": 35000, "amount_ambiguity_flag": False, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 Instagram Reel"], "gmail_thread_id": "demo_thread_3"},
        "extraction_confidence": 0.95,
        "initiated_at": datetime.utcnow() - timedelta(days=40),
    },
    {
        "brand_name": "Zomato",
        "brand_domain": "zomato.com",
        "brand_category": "food",
        "deal_type": "instagram_post",
        "status": "negotiating",
        "financials": {"amount_inr": 25000, "amount_ambiguity_flag": True, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 Static Post", "1 Story"], "gmail_thread_id": "demo_thread_4"},
        "extraction_confidence": 0.75,
        "initiated_at": datetime.utcnow() - timedelta(days=5),
    },
]

# Generate 16 more generic deals to reach 20 total
for i in range(5, 21):
    DEMO_DEALS.append({
        "brand_name": "DemoBrand" + str(i),
        "brand_domain": f"demobrand{i}.com",
        "brand_category": "lifestyle",
        "deal_type": "instagram_story",
        "status": "paid" if i % 2 == 0 else "unanswered",
        "financials": {"amount_inr": 15000 + (i * 1000), "amount_ambiguity_flag": False, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 Story"], "gmail_thread_id": f"demo_thread_{i}"},
        "extraction_confidence": 0.85,
        "initiated_at": datetime.utcnow() - timedelta(days=i*2),
        "thread_unanswered": True if i % 2 != 0 else False,
    })


DEMO_INVOICES = [
    {
        "brand_name": "boAt",
        "amount_inr": 120000,
        "days_overdue": 47,
        "status": "overdue",
        "follow_ups": {"count": 0},
    },
    {
        "brand_name": "Zomato",
        "amount_inr": 65000,
        "days_overdue": 21,
        "status": "overdue",
        "follow_ups": {"count": 1, "tones_used": ["gentle"]},
    },
    {
        "brand_name": "Unacademy",
        "amount_inr": 40000,
        "days_overdue": 8,
        "status": "pending",
        "follow_ups": {"count": 0},
    },
]


async def seed_demo():
    db = MongoDBSingleton.get_db()

    logger.info("Checking for existing demo creator...")
    existing_creator = await db.creators.find_one({"email": DEMO_CREATOR_EMAIL})
    
    if existing_creator:
        # CRITICAL FIX: use the application 'creator_id' field, not the Mongo '_id'
        creator_id = existing_creator.get("creator_id", str(existing_creator["_id"]))
        logger.info(f"Found existing demo creator {creator_id}. Wiping existing demo data...")
        await db.deals.delete_many({"creator_id": creator_id})
        await db.invoices.delete_many({"creator_id": creator_id})
        await db.audit_reports.delete_many({"creator_id": creator_id})
        await db.brands.delete_many({"data_source": "demo"})
        
        # Ensure the account is fully active so the user can bypass onboarding
        await db.creators.update_one(
            {"_id": existing_creator["_id"]},
            {"$set": {
                "gmail_connected": True,
                "subscription.status": "active",
                "onboarding_step": 4, # Max step
                "voice_profile_brand": {
                    "formality_score": 3.0,
                    "avg_response_length": 60,
                    "common_openers": ["Hi team,"],
                    "common_closers": ["Best, Ananya"],
                }
            }}
        )
    else:
        logger.info("Creating new demo creator...")
        result = await db.creators.insert_one({
            "email": DEMO_CREATOR_EMAIL,
            "name": "Ananya Sharma",
            "niche": "Lifestyle & Tech",
            "gmail_connected": True,
            "subscription": {"status": "active"},
            "voice_profile_brand": {
                "formality_score": 3.0,
                "avg_response_length": 60,
                "common_openers": ["Hi team,"],
                "common_closers": ["Best, Ananya"],
            }
        })
        creator_id = str(result.inserted_id)

    # Insert Brands
    logger.info("Seeding brands...")
    brand_map = {}
    for brand in DEMO_BRANDS:
        brand["created_at"] = datetime.utcnow()
        brand["updated_at"] = datetime.utcnow()
        res = await db.brands.insert_one(brand)
        brand_map[brand["name"]] = str(res.inserted_id)

    # Insert Deals
    logger.info("Seeding deals...")
    deal_map = {}
    for deal in DEMO_DEALS:
        deal["creator_id"] = creator_id
        b_name = deal["brand_name"]
        if b_name in brand_map:
            deal["brand_id"] = brand_map[b_name]
        res = await db.deals.insert_one(deal)
        deal_map[b_name] = str(res.inserted_id)

    # Insert Invoices
    logger.info("Seeding invoices...")
    for inv in DEMO_INVOICES:
        inv["creator_id"] = creator_id
        b_name = inv["brand_name"]
        if b_name in brand_map:
            inv["brand_id"] = ObjectId(brand_map[b_name])
            inv["brand_domain"] = next((b["domain"] for b in DEMO_BRANDS if b["name"] == b_name), "")
        if b_name in deal_map:
            inv["deal_id"] = ObjectId(deal_map[b_name])
        
        # Calculate due date backward based on days_overdue
        inv["due_date"] = datetime.utcnow() - timedelta(days=inv["days_overdue"])
        
        await db.invoices.insert_one(inv)

    # Insert Audit Report
    logger.info("Seeding audit report...")
    await db.audit_reports.insert_one({
        "creator_id": creator_id,
        "created_at": datetime.utcnow(),
        "summary": {
            "total_unanswered_deals": 11,
            "total_recoverable_value_inr": 225000,
            "average_response_time_days": 4.5,
        }
    })

    logger.info("Demo environment seeded successfully.")
    MongoDBSingleton.close()

if __name__ == "__main__":
    asyncio.run(seed_demo())
