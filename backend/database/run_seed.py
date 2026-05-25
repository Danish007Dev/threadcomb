#!/usr/bin/env python
"""Standalone executable: create all ThreadComb collections, indexes, and seed data.

Usage:
    python backend/database/run_seed.py

This script:
  1. Connects to MongoDB Atlas using MONGODB_URI / MONGO_URL env var
  2. Creates all 10 collections if they don't exist
  3. Creates all indexes defined in create_indexes()
  4. Inserts the niche_graph seed data from seed_niche_graph()
  5. Prints a confirmation for each step

Run once after Session 1.
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
from database.seed import seed_niche_graph  # noqa: E402


async def main() -> int:
    print("=" * 70)
    print("ThreadComb — Database Setup")
    print("=" * 70)

    db = MongoDBSingleton.get_db()
    print(f"\n[1/4] Connected to MongoDB database: {db.name}")

    # Ping
    try:
        await db.command("ping")
        print("       Ping OK.")
    except Exception as exc:
        print(f"       Ping FAILED: {exc}")
        return 1

    print("\n[2/4] Ensuring collections exist...")
    await ensure_collections(db)
    final_collections = await db.list_collection_names()
    for name in COLLECTION_NAMES:
        present = "OK " if name in final_collections else "MISSING"
        print(f"       [{present}] {name}")

    print("\n[3/4] Creating indexes...")
    await create_indexes(db)
    print("       All indexes ensured.")

    print("\n[4/4] Seeding niche_graph...")
    inserted = await seed_niche_graph(db)
    if inserted > 0:
        print(f"       Inserted {inserted} pre-training niche_graph documents.")
    else:
        existing = await db.niche_graph.count_documents({})
        print(f"       niche_graph already has {existing} documents — skipped.")

    print("\n" + "=" * 70)
    print("ThreadComb DB setup COMPLETE.")
    print("=" * 70)
    MongoDBSingleton.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
