#!/usr/bin/env python
"""Standalone executable: migrate, create collections, create indexes.

Usage:
    python backend/database/run_seed.py

This script:
  1. Runs schema migration (deletes invalid Session 1 niche_graph placeholders)
  2. Creates all 10 collections if they don't exist
  3. Creates all indexes defined in create_indexes()
  4. Prints a verification summary

niche_graph is NO LONGER seeded with hardcoded data. Run the corpus pipeline
instead:
    python backend/corpus/ingest.py --folder ./corpus/data/
"""

import asyncio
import os
import sys
from pathlib import Path

# Make `backend/` importable when this file is executed directly.
HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Accept either MONGODB_URI (spec) or MONGO_URL (platform default).
if not os.environ.get("MONGO_URL") and os.environ.get("MONGODB_URI"):
    os.environ["MONGO_URL"] = os.environ["MONGODB_URI"]
if not os.environ.get("DB_NAME") and os.environ.get("MONGODB_DB_NAME"):
    os.environ["DB_NAME"] = os.environ["MONGODB_DB_NAME"]

from database.mongodb import (  # noqa: E402
    MongoDBSingleton,
    ensure_collections,
    create_indexes,
    COLLECTION_NAMES,
)
from database.migrate import migrate_niche_graph_v2  # noqa: E402


EXPECTED_COLLECTIONS = COLLECTION_NAMES


async def main() -> int:
    print("=" * 70)
    print("ThreadComb Database Setup")
    print("=" * 70)

    db = MongoDBSingleton.get_db()
    print(f"\n[1/4] Connected to MongoDB database: {db.name}")
    try:
        await db.command("ping")
        print("       Ping OK.")
    except Exception as exc:
        print(f"       Ping FAILED: {exc}")
        return 1

    # ── Step 1: Migration ──
    print("\n[2/4] Running schema migration (Session 2A — niche_graph v2)...")
    deleted = await migrate_niche_graph_v2(db)
    print(f"       Removed {deleted} invalid placeholder documents.")

    # ── Step 2: Collections + Indexes ──
    print("\n[3/4] Ensuring collections + indexes...")
    await ensure_collections(db)
    await create_indexes(db)
    final_collections = await db.list_collection_names()
    for name in EXPECTED_COLLECTIONS:
        marker = "OK " if name in final_collections else "MISSING"
        print(f"       [{marker}] {name}")

    # ── Step 3: Verification (no seed) ──
    print("\n[4/4] Verification:")
    for name in EXPECTED_COLLECTIONS:
        count = await db[name].count_documents({})
        print(f"       ✓ {name}: {count} documents")

    valid_niche = await db.niche_graph.count_documents(
        {"confidence_weight": {"$gte": 0.40}}
    )
    print(f"\n       niche_graph valid docs (confidence_weight ≥ 0.40): {valid_niche}")
    if valid_niche == 0:
        print(
            "\n   → niche_graph is empty. Populate it by running:\n"
            "       python backend/corpus/ingest.py --folder ./corpus/data/"
        )

    print("\n" + "=" * 70)
    print("ThreadComb DB setup COMPLETE.")
    print("=" * 70)
    MongoDBSingleton.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
