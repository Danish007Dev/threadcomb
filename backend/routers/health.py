"""Health check endpoint."""

from fastapi import APIRouter
from database.mongodb import get_db

router = APIRouter()


@router.get("/health")
async def health():
    db = get_db()
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return {
        "status": "ok" if mongo_ok else "degraded",
        "mongo": mongo_ok,
        "service": "threadcomb-backend",
    }
