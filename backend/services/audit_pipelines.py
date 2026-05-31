"""3 MongoDB aggregation pipelines for the Audit Report (Session 3).

These run AFTER extraction is complete. They power the Audit Report.
All three run in MongoDB — not Python.
"""

import logging
from typing import Optional

from bson import ObjectId

logger = logging.getLogger(__name__)


async def pipeline_revenue_leakage(db, creator_id: str) -> dict:
    """
    Finds deals the creator never responded to and estimates the lost revenue.
    Only uses deals where extraction_confidence >= 0.70.
    """
    pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "thread_unanswered": True,
            "extraction_confidence": {"$gte": 0.70},
        }},
        {"$group": {
            "_id": "$financials.currency",
            "unanswered_count": {"$sum": 1},
            "estimated_value_min": {"$sum": {"$ifNull": ["$financials.amount_min", 0]}},
            "estimated_value_max": {"$sum": {"$ifNull": ["$financials.amount_max", 0]}},
            "estimated_value_typical": {"$sum": {"$ifNull": ["$financials.amount_inr", 0]}},
            "brands": {"$push": "$raw_signals.brand_contact_email"},
        }},
        {"$project": {
            "unanswered_count": 1,
            "estimated_value_min": 1,
            "estimated_value_max": 1,
            "estimated_value_typical": 1,
            # Only show range if non-zero
            "has_estimates": {"$gt": ["$estimated_value_max", 0]},
        }}
    ]

    results = await db.deals.aggregate(pipeline).to_list(None)
    return {
        "unanswered_deals": results[0].get("unanswered_count", 0) if results else 0,
        "estimated_value_typical": results[0].get("estimated_value_typical", 0) if results else 0,
        "estimated_value_min": results[0].get("estimated_value_min", 0) if results else 0,
        "estimated_value_max": results[0].get("estimated_value_max", 0) if results else 0,
        "has_estimates": results[0].get("has_estimates", False) if results else False,
        # NOTE: If has_estimates=False, show "value unknown — amount not stated in emails"
        # NEVER show a rate we cannot cite. Show deal count instead.
    }


async def pipeline_payment_reliability(db, creator_id: str) -> list:
    """
    Ranks brands by payment reliability based on known deal outcomes.
    Only includes brands with at least 1 deal in a terminal status.
    """
    pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "status": {"$in": ["paid", "overdue", "invoiced", "delivered"]},
            "extraction_confidence": {"$gte": 0.70},
        }},
        {"$lookup": {
            "from": "brands",
            "localField": "brand_id",
            "foreignField": "_id",
            "as": "brand"
        }},
        {"$unwind": {"path": "$brand", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$brand_id",
            "brand_name": {"$first": "$brand.name"},
            "total_deals": {"$sum": 1},
            "paid_count": {"$sum": {"$cond": [{"$eq": ["$status", "paid"]}, 1, 0]}},
            "overdue_count": {"$sum": {"$cond": [{"$eq": ["$status", "overdue"]}, 1, 0]}},
            "avg_payment_days": {"$avg": "$financials.payment_days"},
        }},
        {"$addFields": {
            "payment_reliability": {
                "$cond": [
                    {"$eq": ["$total_deals", 0]},
                    0.5,
                    {"$divide": ["$paid_count", "$total_deals"]}
                ]
            }
        }},
        {"$sort": {"payment_reliability": 1}},  # worst payers first
        {"$limit": 10}
    ]

    return await db.deals.aggregate(pipeline).to_list(None)


async def pipeline_rate_gap(db, creator_id: str) -> dict:
    """
    Compares creator's accepted deal rates against niche_graph benchmarks.
    Only runs if creator has accepted deals with non-ambiguous amounts.
    """
    creator = await db.creators.find_one({"_id": ObjectId(creator_id)})
    if not creator:
        return {}

    niche = creator.get("niche")
    follower_tier = creator.get("follower_tier")
    if not niche or not follower_tier:
        return {}

    # Get creator's actual accepted rates (non-ambiguous only)
    deal_pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "status": {"$in": ["accepted", "paid", "delivered"]},
            "financials.amount_ambiguity_flag": False,
            "financials.amount_inr": {"$gt": 0},
            "extraction_confidence": {"$gte": 0.70},
        }},
        {"$group": {
            "_id": "$deal_type",
            "avg_rate": {"$avg": "$financials.amount_inr"},
            "deal_count": {"$sum": 1},
        }}
    ]

    creator_rates = await db.deals.aggregate(deal_pipeline).to_list(None)

    # Get market benchmarks from niche_graph
    benchmarks = {}
    for rate_entry in creator_rates:
        deal_type = rate_entry.get("_id")
        if not deal_type:
            continue

        benchmark = await db.niche_graph.find_one({
            "niche": niche,
            "follower_tier": follower_tier,
            "content_format": deal_type,
            "confidence_weight": {"$gte": 0.40},
        })

        if benchmark and benchmark.get("rate_p50") and rate_entry.get("avg_rate"):
            gap_pct = round(
                (rate_entry["avg_rate"] - benchmark["rate_p50"]) / benchmark["rate_p50"] * 100, 1
            )
            benchmarks[deal_type] = {
                "creator_avg": round(rate_entry["avg_rate"], 0),
                "market_p50": benchmark["rate_p50"],
                "gap_percentage": gap_pct,
                "gap_label": "below_market" if gap_pct < -10 else ("above_market" if gap_pct > 10 else "at_market"),
                "deal_count": rate_entry["deal_count"],
                "benchmark_confidence": benchmark.get("confidence_weight", 0.40),
                # If benchmark_confidence < 0.55: show transparency note
            }

    return benchmarks
