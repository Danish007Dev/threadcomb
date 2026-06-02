"""ThreadComb FastAPI application entry point.

Wires up:
  - MongoDB collections + indexes at startup
  - niche_graph seed (idempotent — only seeds if empty)
    - /api/auth/*       — Google OAuth + creator lifecycle
  - /api/onboarding/* — 4-step creator onboarding
  - /api/health       — liveness + Mongo ping
"""
import logging
print("DEBUG: Loaded logging")

print("DEBUG: Importing FastAPI...")
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

print("DEBUG: Importing config...")
from config import settings

print("DEBUG: Importing MongoDB...")
from database.mongodb import (
    MongoDBSingleton,
    ensure_collections,
    create_indexes,
)

print("DEBUG: Importing seed...")
from database.seed import seed_niche_graph

print("DEBUG: Importing Auth Router...")
from routers import auth as auth_router

print("DEBUG: Importing Onboarding Router...")
from routers import onboarding as onboarding_router

print("DEBUG: Importing Health Router...")
from routers import health as health_router

print("DEBUG: Importing Ingestion Router...")
from routers import ingestion as ingestion_router

print("DEBUG: Importing SSE Router...")
from routers import sse as sse_router

print("DEBUG: Importing Audit Router...")
from routers import audit as audit_router

print("DEBUG: Importing Deals Router...")
from routers import deals as deals_router

print("DEBUG: ALL IMPORTS COMPLETE!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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


# @app.on_event("startup")
# async def on_startup():
#     db = MongoDBSingleton.get_db()
#     logger.info("Connecting to MongoDB database: %s", db.name)
#     await ensure_collections(db)
#     await create_indexes(db)
#     seeded = await seed_niche_graph(db)
#     if seeded:
#         logger.info("Seeded %d niche_graph documents at startup.", seeded)
#     logger.info("ThreadComb backend ready.")
@app.on_event("startup")
async def on_startup():
    print("DEBUG: Startup hook triggered! Attempting to connect to MongoDB...")
    try:
        db = MongoDBSingleton.get_db()
        print(f"DEBUG: Successfully got DB object. Database name: {db.name}")
        
        print("DEBUG: Pinging MongoDB to ensure collections exist...")
        await ensure_collections(db)
        print("DEBUG: Collections verified!")
        
        print("DEBUG: Checking indexes...")
        await create_indexes(db)
        print("DEBUG: Indexes verified!")
        
        print("DEBUG: Running seed function...")
        seeded = await seed_niche_graph(db)
        if seeded:
            logger.info("Seeded %d niche_graph documents at startup.", seeded)
            
        logger.info("ThreadComb backend ready.")
        print("DEBUG: STARTUP COMPLETELY FINISHED!")
        
    except Exception as e:
        print("\n" + "="*50)
        print(f"🚨 MASSIVE DATABASE ERROR 🚨")
        print(f"Details: {str(e)}")
        print("="*50 + "\n")

@app.on_event("shutdown")
async def on_shutdown():
    MongoDBSingleton.close()
