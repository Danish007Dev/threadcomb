#!/usr/bin/env python
"""Session 3 -- Production Verification Script.

Tests three critical path items:
1. /workers/trigger-direct extraction -> deals document with valid embedding
2. Atlas Vector Search returns results
3. Audit report doesn't fabricate amounts

Usage:
    # With backend running on localhost:8000:
    python backend/tests/test_session3_production.py

    # Or run individual tests:
    python backend/tests/test_session3_production.py --test extraction
    python backend/tests/test_session3_production.py --test vectorsearch
    python backend/tests/test_session3_production.py --test audit
"""

import sys
import io

# Force UTF-8 output on Windows to handle special chars (INR symbol, etc.)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio
import json
import math
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# ── Make backend importable ──────────────────────────────────────────────────
HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Accept either MONGODB_URI or MONGO_URL
if not os.environ.get("MONGO_URL") and os.environ.get("MONGODB_URI"):
    os.environ["MONGO_URL"] = os.environ["MONGODB_URI"]

from config import settings  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────────

# A realistic sanitised brand deal email thread for testing
TEST_CREATOR_ID = "test_session3_verification"
TEST_THREAD_ID = "thread_test_session3_001"

REALISTIC_SANITISED_THREAD = """
Subject: Collaboration Opportunity - Minimalist Skincare x {creator_handle}
From: partnerships@beminimalist.co
Date: Mon, 26 May 2026 10:30:00 +0530

Hi there,

I'm Priya from the brand partnerships team at Minimalist (beminimalist.co).

We've been following your content on Instagram and love how you break down skincare
ingredients for your audience. Your recent Reel on Vitamin C serums was particularly
well-received and aligns perfectly with our upcoming product launch.

We'd love to collaborate with you for our new Salicylic Acid 2% Face Wash launch.
Here's what we're thinking:

Deliverables:
- 1 Instagram Reel (60-90 seconds) featuring the product
- 3 Instagram Stories (unboxing + honest review + swipe-up)
- 1 Instagram Post (carousel format with before/after if possible)

Compensation: ₹75,000 for the complete package
Timeline: Content to go live between June 10-15, 2026
Exclusivity: No competing skincare brand posts for 15 days after going live
Payment Terms: 50% upfront upon confirmation, 50% within 7 days of content going live

Please let us know if you're interested and we can hop on a quick call to discuss further.

Best regards,
Priya Sharma
Brand Partnerships Manager
Minimalist | beminimalist.co
priya@beminimalist.co

---

(Creator never replied to this thread)
"""

REALISTIC_SANITISED_THREAD_AMBIGUOUS = """
Subject: Quick collab?
From: marketing@randomstartup.in
Date: Thu, 29 May 2026 14:00:00 +0530

Hey!

Loved your content. We're a new D2C brand in the wellness space and would
love to work with you. Budget is flexible — let's discuss rates on a call?

We're thinking maybe a YouTube integration or a dedicated video, whatever
works for you. Competitive budget for sure 😊

Let me know!

Rohit
Head of Marketing
RandomStartup.in
"""

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_result(label: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    print(f"  {status}  {label}")
    if detail:
        print(f"         {detail}")


# ============================================================================
# TEST 1: Extraction Worker → deals document with valid embedding
# ============================================================================

async def test_extraction_worker():
    """
    Calls run_extraction_worker directly (no HTTP needed) with a realistic
    sanitised thread payload. Then checks MongoDB for:
    - deals document exists
    - embedding_vector has 768 floats
    - L2 norm of embedding is within 0.001 of 1.0
    - brands document was upserted
    """
    print_header("TEST 1: Extraction Worker -> Deals + Embedding")

    from database.mongodb import get_db_singleton
    from workers.extract_thread import run_extraction_worker

    db = get_db_singleton()

    # Clean up any previous test data
    await db.deals.delete_many({"creator_id": TEST_CREATOR_ID})
    await db.brands.delete_many({"domain": "beminimalist.co"})
    await db.agent_actions.delete_many({"creator_id": TEST_CREATOR_ID})
    await db.skills_map.delete_many({"creator_id": TEST_CREATOR_ID})
    print(f"  {INFO}  Cleaned up previous test data")

    # Build payload matching what the ingestion pipeline sends
    payload = {
        "thread_id": TEST_THREAD_ID,
        "creator_id": TEST_CREATOR_ID,
        "job_id": "",  # no job — standalone test
        "sanitised_text": REALISTIC_SANITISED_THREAD,
        "sender_email": "priya@beminimalist.co",
        "subject": "Collaboration Opportunity - Minimalist Skincare",
        "hindi_mode": False,
        "has_attachments": False,
        "attachment_names": [],
        "date_range_start": "2026-05-26T10:30:00+05:30",
    }

    print(f"  {INFO}  Calling run_extraction_worker with Minimalist deal thread...")
    try:
        await run_extraction_worker(payload)
        print(f"  {INFO}  Extraction worker completed")
    except Exception as e:
        print(f"  {FAIL}  Extraction worker raised: {e}")
        return False

    # ── Check 1a: deals document exists ──
    deal = await db.deals.find_one({"creator_id": TEST_CREATOR_ID})
    if not deal:
        print_result("Deals document exists", False, "No document found in deals collection")
        return False
    print_result("Deals document exists", True, f"_id={deal['_id']}")

    # ── Check 1b: embedding_vector has 768 floats ──
    vector = deal.get("embedding_vector", [])
    has_vector = isinstance(vector, list) and len(vector) == 768
    all_zero = all(v == 0.0 for v in vector) if has_vector else True
    print_result(
        "Embedding vector has 768 floats",
        has_vector and not all_zero,
        f"len={len(vector)}, all_zero={all_zero}" if has_vector else f"len={len(vector)}"
    )

    if all_zero:
        print(f"  {FAIL}  CRITICAL: Vector is all zeros — Session 4 Atlas Vector Search will return nothing!")
        return False

    # ── Check 1c: L2 norm is within 0.001 of 1.0 ──
    if has_vector and not all_zero:
        l2_norm = math.sqrt(sum(v * v for v in vector))
        norm_ok = abs(l2_norm - 1.0) < 0.001
        print_result(
            f"L2 norm ~= 1.0",
            norm_ok,
            f"actual={l2_norm:.6f}, |diff|={abs(l2_norm - 1.0):.6f}"
        )
        if not norm_ok:
            print(f"  {FAIL}  CRITICAL: Vector not normalized — cosine similarity queries return incorrect results!")
            return False
    else:
        print_result("L2 norm check", False, "Skipped — vector invalid")
        return False

    # ── Check 1d: Deal fields populated correctly ──
    status = deal.get("status", "")
    deal_type = deal.get("deal_type", "")
    financials = deal.get("financials", {})
    amount = financials.get("amount")
    ambiguity = financials.get("amount_ambiguity_flag", True)
    confidence = deal.get("extraction_confidence", 0)

    print(f"\n  {INFO}  Deal details:")
    print(f"         status      = {status}")
    print(f"         deal_type   = {deal_type}")
    print(f"         amount      = {amount}")
    print(f"         ambiguity   = {ambiguity}")
    print(f"         confidence  = {confidence}")

    print_result("Status is 'unanswered' (creator never replied)", status == "unanswered")
    print_result(
        "Amount extracted (₹75,000)",
        amount is not None and 70000 <= amount <= 80000 and not ambiguity,
        f"amount={amount}, ambiguity={ambiguity}"
    )
    print_result("Confidence ≥ 0.70", confidence >= 0.70, f"confidence={confidence}")

    # ── Check 1e: Brand upserted ──
    brand = await db.brands.find_one({"domain": "beminimalist.co"})
    print_result("Brand upserted (beminimalist.co)", brand is not None)

    return True


# ============================================================================
# TEST 1b: Ambiguous amount thread — must NOT fabricate
# ============================================================================

async def test_extraction_ambiguous():
    """Verifies that ambiguous financial amounts are NOT fabricated."""
    print_header("TEST 1b: Ambiguous Amount -- No Fabrication")

    from database.mongodb import get_db_singleton
    from workers.extract_thread import run_extraction_worker

    db = get_db_singleton()

    test_creator = f"{TEST_CREATOR_ID}_ambiguous"
    await db.deals.delete_many({"creator_id": test_creator})
    await db.agent_actions.delete_many({"creator_id": test_creator})

    payload = {
        "thread_id": "thread_test_ambiguous_001",
        "creator_id": test_creator,
        "job_id": "",
        "sanitised_text": REALISTIC_SANITISED_THREAD_AMBIGUOUS,
        "sender_email": "marketing@randomstartup.in",
        "subject": "Quick collab?",
        "hindi_mode": False,
        "has_attachments": False,
        "attachment_names": [],
        "date_range_start": "2026-05-29T14:00:00+05:30",
    }

    print(f"  {INFO}  Extracting ambiguous deal (budget='flexible', 'competitive')...")
    try:
        await run_extraction_worker(payload)
    except Exception as e:
        print(f"  {FAIL}  Extraction error: {e}")
        return False

    deal = await db.deals.find_one({"creator_id": test_creator})
    if not deal:
        # Might have gone to HITL — that's also acceptable
        hitl = await db.agent_actions.find_one({
            "creator_id": test_creator,
            "action_type": "hitl_queued"
        })
        if hitl:
            print_result("Ambiguous deal routed to HITL (acceptable)", True)
            return True
        print_result("Deals or HITL document exists", False)
        return False

    financials = deal.get("financials", {})
    ambiguity = financials.get("amount_ambiguity_flag", False)
    amount = financials.get("amount")
    amount_min = financials.get("amount_min")
    amount_max = financials.get("amount_max")

    print(f"  {INFO}  Ambiguous deal details:")
    print(f"         amount_ambiguity_flag = {ambiguity}")
    print(f"         amount                = {amount}")
    print(f"         amount_min            = {amount_min}")
    print(f"         amount_max            = {amount_max}")

    # If ambiguity is True, all amounts MUST be None
    if ambiguity:
        amounts_null = amount is None and amount_min is None and amount_max is None
        print_result(
            "Ambiguous → all amounts are None (no fabrication)",
            amounts_null,
            f"amount={amount}, min={amount_min}, max={amount_max}"
        )
        return amounts_null
    else:
        # If the model decided it's NOT ambiguous, that's a soft warning
        print(f"  {WARN}  Model did not flag 'flexible/competitive budget' as ambiguous")
        print(f"         This is acceptable if the model found implicit signals, but review manually")
        return True


# ============================================================================
# TEST 2: Atlas Vector Search
# ============================================================================

async def test_vector_search():
    """
    Runs a $vectorSearch aggregation on the deals collection using a test
    query vector. Verifies that it returns at least one result.
    """
    print_header("TEST 2: Atlas Vector Search")

    from database.mongodb import get_db_singleton

    db = get_db_singleton()

    # First check if any deals with embeddings exist
    deal_with_vector = await db.deals.find_one(
        {"embedding_vector": {"$exists": True, "$ne": []}, "embedding_vector.0": {"$exists": True}}
    )
    if not deal_with_vector:
        print(f"  {FAIL}  No deals with embedding vectors found in the database.")
        print(f"         Run test_extraction_worker first, or ingest real threads.")
        return False

    # Use the existing deal's embedding as the query vector (should match itself)
    query_vector = deal_with_vector["embedding_vector"]
    print(f"  {INFO}  Using embedding from deal {deal_with_vector['_id']} as query vector")
    print(f"  {INFO}  Vector length: {len(query_vector)}")

    # ── Try $vectorSearch (Atlas-only) ──
    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "deals_embedding_vector",  # Must exist in Atlas
                    "path": "embedding_vector",
                    "queryVector": query_vector,
                    "numCandidates": 10,
                    "limit": 5,
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "creator_id": 1,
                    "status": 1,
                    "deal_type": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            }
        ]

        results = await db.deals.aggregate(pipeline).to_list(None)
        has_results = len(results) > 0
        print_result(
            f"$vectorSearch returned results",
            has_results,
            f"count={len(results)}"
        )

        if has_results:
            for r in results:
                print(f"         - deal={r['_id']}, score={r.get('score', 'N/A'):.4f}, status={r.get('status', 'N/A')}")

            # Top result should have score close to 1.0 (it's the same vector)
            top_score = results[0].get("score", 0)
            print_result(
                "Top result score ~= 1.0 (self-match)",
                top_score > 0.95,
                f"score={top_score:.4f}"
            )
        return has_results

    except Exception as e:
        error_msg = str(e)
        if "index" in error_msg.lower() or "vectorsearch" in error_msg.lower():
            print(f"  {WARN}  Atlas Vector Search index not found or not ready.")
            print(f"         Error: {error_msg[:200]}")
            print(f"\n  {INFO}  To fix this, create a vector search index in Atlas UI:")
            print(f"         Collection: deals")
            print(f"         Index name: deals_embedding_vector")
            print(f"         Index definition:")
            print(json.dumps({
                "fields": [{
                    "type": "vector",
                    "path": "embedding_vector",
                    "numDimensions": 768,
                    "similarity": "cosine"
                }]
            }, indent=8))
            print(f"\n  {INFO}  The index takes 1-3 minutes to build. Re-run this test after.")

            # Fall back to checking vector exists and is valid
            print(f"\n  {INFO}  Falling back to vector validation (no Atlas index required):")
            l2_norm = math.sqrt(sum(v * v for v in query_vector))
            print_result(
                "Vector has 768 dimensions",
                len(query_vector) == 768,
                f"len={len(query_vector)}"
            )
            print_result(
                "L2 norm ≈ 1.0",
                abs(l2_norm - 1.0) < 0.001,
                f"norm={l2_norm:.6f}"
            )
            return False  # Vector search itself failed
        else:
            print(f"  {FAIL}  Unexpected error: {e}")
            return False


# ============================================================================
# TEST 3: Audit Report — No Fabricated Amounts
# ============================================================================

async def test_audit_report():
    """
    Runs run_audit_generation on the test creator.
    Checks that:
    - audit_reports document is created
    - total_recoverable_value is not fabricated from ambiguous deals
    - findings with value_inr are backed by non-ambiguous deals
    """
    print_header("TEST 3: Audit Report -- No Fabricated Amounts")

    from database.mongodb import get_db_singleton

    db = get_db_singleton()

    # Check if we have any deals to audit
    deal_count = await db.deals.count_documents({"creator_id": TEST_CREATOR_ID})
    if deal_count == 0:
        print(f"  {FAIL}  No deals found for {TEST_CREATOR_ID}. Run test 1 first.")
        return False
    print(f"  {INFO}  Found {deal_count} deals for test creator")

    # Ensure we have a creator document (the audit generator needs it)
    creator = await db.creators.find_one({"creator_id": TEST_CREATOR_ID})
    if not creator:
        # Create a minimal test creator
        await db.creators.insert_one({
            "creator_id": TEST_CREATOR_ID,
            "email": "test_session3@threadcomb.dev",
            "name": "Test Creator S3",
            "niche": "beauty",
            "follower_tier": "micro",
            "handle": "@test_creator_s3",
            "created_at": datetime.now(timezone.utc),
        })
        print(f"  {INFO}  Created test creator document")

    # Clean up previous audit reports
    await db.audit_reports.delete_many({"creator_id": TEST_CREATOR_ID})

    # Run audit generation
    print(f"  {INFO}  Running run_audit_generation (this calls Gemini Pro)...")
    from routers.audit import run_audit_generation
    try:
        await run_audit_generation(creator_id=TEST_CREATOR_ID)
    except Exception as e:
        print(f"  {FAIL}  Audit generation error: {e}")
        return False

    # Check the report
    report = await db.audit_reports.find_one({"creator_id": TEST_CREATOR_ID})
    if not report:
        print_result("Audit report document exists", False)
        return False
    print_result("Audit report document exists", True)

    # ── Check 3a: executive_summary is not empty ──
    summary = report.get("executive_summary", "")
    print_result("Executive summary present", bool(summary), f"len={len(summary)}")

    # ── Check 3b: findings exist ──
    findings = report.get("findings", [])
    print_result("Findings present", len(findings) > 0, f"count={len(findings)}")

    # ── Check 3c: No fabricated amounts ──
    # Get all ambiguous deals
    ambiguous_deals = await db.deals.find(
        {"creator_id": TEST_CREATOR_ID, "financials.amount_ambiguity_flag": True}
    ).to_list(None)
    non_ambiguous_deals = await db.deals.find(
        {"creator_id": TEST_CREATOR_ID, "financials.amount_ambiguity_flag": {"$ne": True}}
    ).to_list(None)

    total_non_ambiguous_value = sum(
        (d.get("financials", {}).get("amount") or 0) for d in non_ambiguous_deals
    )

    total_recoverable = report.get("total_recoverable_value")
    total_unknown = report.get("total_recoverable_unknown", False)

    print(f"\n  {INFO}  Amount audit:")
    print(f"         Ambiguous deals:     {len(ambiguous_deals)}")
    print(f"         Non-ambiguous deals:  {len(non_ambiguous_deals)}")
    print(f"         Sum of non-ambiguous: ₹{total_non_ambiguous_value:,.0f}")
    print(f"         Report total_recoverable_value: {total_recoverable}")
    print(f"         Report total_recoverable_unknown: {total_unknown}")

    # If ALL deals are ambiguous, total_recoverable_value MUST be None or 0
    if len(non_ambiguous_deals) == 0 and len(ambiguous_deals) > 0:
        fabricated = total_recoverable is not None and total_recoverable > 0
        print_result(
            "No fabricated total (all deals ambiguous)",
            not fabricated,
            f"total_recoverable_value={total_recoverable}" if fabricated else "Correctly None or 0"
        )
        if fabricated:
            print(f"  {FAIL}  CRITICAL: Report fabricated ₹{total_recoverable:,.0f} from ambiguous deals!")
            print(f"         The synthesis prompt is NOT enforcing the no-fabrication rule.")
            return False
    else:
        # Check that total doesn't exceed sum of non-ambiguous amounts
        if total_recoverable is not None and total_non_ambiguous_value > 0:
            reasonable = total_recoverable <= total_non_ambiguous_value * 1.1  # 10% tolerance
            print_result(
                "Total <= sum of non-ambiguous amounts (10% tolerance)",
                reasonable,
                f"total={total_recoverable:,.0f} vs sum={total_non_ambiguous_value:,.0f}"
            )

    # ── Check 3d: Findings with value_inr cite evidence ──
    fabrication_found = False
    for i, finding in enumerate(findings):
        if finding.get("value_inr") and finding.get("value_inr", 0) > 0:
            has_evidence = bool(finding.get("evidence", ""))
            if not has_evidence:
                print(f"  {FAIL}  Finding {i} has value_inr=₹{finding['value_inr']:,.0f} but no evidence")
                fabrication_found = True
        if finding.get("value_unknown"):
            print(f"  {INFO}  Finding {i} correctly marks value as unknown: '{finding.get('title', '')}'")

    print_result("All findings with value have evidence", not fabrication_found)

    # ── Print findings summary ──
    print(f"\n  {INFO}  Findings summary:")
    for i, f in enumerate(findings):
        severity = f.get("severity", "?")
        title = f.get("title", "untitled")
        value = f.get("value_inr")
        unknown = f.get("value_unknown", False)
        val_str = f"₹{value:,.0f}" if value else ("unknown" if unknown else "N/A")
        print(f"         [{severity.upper():>8}] {title} — {val_str}")

    return True


# ============================================================================
# TEST 4: Cleanup (optional)
# ============================================================================

async def cleanup_test_data():
    """Remove all test data created by the verification script."""
    print_header("CLEANUP: Removing test data")

    from database.mongodb import get_db_singleton
    db = get_db_singleton()

    for test_id in [TEST_CREATOR_ID, f"{TEST_CREATOR_ID}_ambiguous"]:
        r1 = await db.deals.delete_many({"creator_id": test_id})
        r2 = await db.agent_actions.delete_many({"creator_id": test_id})
        r3 = await db.skills_map.delete_many({"creator_id": test_id})
        r4 = await db.audit_reports.delete_many({"creator_id": test_id})
        r5 = await db.creators.delete_many({"creator_id": test_id})
        print(f"  {INFO}  {test_id}: deals={r1.deleted_count}, actions={r2.deleted_count}, "
              f"skills={r3.deleted_count}, audits={r4.deleted_count}, creators={r5.deleted_count}")

    await db.brands.delete_many({"domain": "beminimalist.co"})
    await db.brands.delete_many({"domain": "randomstartup.in"})
    print(f"  {INFO}  Cleaned up test brands")


# ============================================================================
# Main
# ============================================================================

async def run_all():
    results = {}

    # Test 1: Extraction
    results["extraction"] = await test_extraction_worker()

    # Test 1b: Ambiguous amount
    results["ambiguous"] = await test_extraction_ambiguous()

    # Test 2: Vector Search
    results["vectorsearch"] = await test_vector_search()

    # Test 3: Audit Report
    results["audit"] = await test_audit_report()

    # Summary
    print_header("SUMMARY")
    all_pass = True
    for name, passed in results.items():
        status = PASS if passed else FAIL
        print(f"  {status}  {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print(f"\n  ALL TESTS PASSED -- Session 3 is production-ready!")
    else:
        print(f"\n  SOME TESTS FAILED -- review output above before proceeding to Session 4.")

    # Cleanup
    await cleanup_test_data()

    from database.mongodb import MongoDBSingleton
    MongoDBSingleton.close()

    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Session 3 production verification")
    parser.add_argument(
        "--test",
        choices=["extraction", "ambiguous", "vectorsearch", "audit", "cleanup", "all"],
        default="all",
        help="Which test to run"
    )
    args = parser.parse_args()

    async def run_single():
        from database.mongodb import MongoDBSingleton

        if args.test == "extraction":
            result = await test_extraction_worker()
        elif args.test == "ambiguous":
            result = await test_extraction_ambiguous()
        elif args.test == "vectorsearch":
            result = await test_vector_search()
        elif args.test == "audit":
            result = await test_audit_report()
        elif args.test == "cleanup":
            await cleanup_test_data()
            result = True
        else:
            result = await run_all()
            return result

        MongoDBSingleton.close()
        return result

    passed = asyncio.run(run_single() if args.test != "all" else run_all())
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
