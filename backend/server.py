"""ThreadComb FastAPI application entry point.

Wires up:
  - MongoDB collections + indexes at startup
  - niche_graph seed (idempotent — only seeds if empty)
    - /api/auth/*       — Google OAuth + creator lifecycle
  - /api/onboarding/* — 4-step creator onboarding
  - /api/health       — liveness + Mongo ping
"""

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
import logging

from config import settings
from database.mongodb import (
    MongoDBSingleton,
    ensure_collections,
    create_indexes,
)
from database.seed import seed_niche_graph
from routers import auth as auth_router
from routers import onboarding as onboarding_router
from routers import health as health_router
from routers import ingestion as ingestion_router
from routers import sse as sse_router
from routers import audit as audit_router
from routers import deals as deals_router
from workers import process_thread as process_thread_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(title="ThreadComb API", version="0.1.0")

# All ThreadComb routes are prefixed with /api so the Kubernetes ingress can
# route them to the backend pod.
api_router = APIRouter(prefix="/api")
api_router.include_router(health_router.router)
api_router.include_router(auth_router.router)
api_router.include_router(onboarding_router.router)
api_router.include_router(ingestion_router.router)
api_router.include_router(sse_router.router)
api_router.include_router(audit_router.router)
api_router.include_router(deals_router.router)


@api_router.get("/")
async def root():
    return {
        "service": "threadcomb-backend",
        "version": "0.1.0",
        "tagline": "Every brand deal lives in a thread. ThreadComb reads them all.",
    }


app.include_router(api_router)
app.include_router(process_thread_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    db = MongoDBSingleton.get_db()
    logger.info("Connecting to MongoDB database: %s", db.name)
    await ensure_collections(db)
    await create_indexes(db)
    seeded = await seed_niche_graph(db)
    if seeded:
        logger.info("Seeded %d niche_graph documents at startup.", seeded)
    logger.info("ThreadComb backend ready.")


@app.on_event("shutdown")
async def on_shutdown():
    MongoDBSingleton.close()
