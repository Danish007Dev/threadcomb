import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    # MongoDB
    MONGO_URL: str = os.environ["MONGO_URL"]
    DB_NAME: str = os.environ["DB_NAME"]

    # CORS
    CORS_ORIGINS: list = os.environ.get("CORS_ORIGINS", "*").split(",")

    # Gemini
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_EMBEDDING_MODEL: str = os.environ.get(
        "GEMINI_EMBEDDING_MODEL", "gemini-embedding-2"
    )
    GEMINI_EMBEDDING_DIMENSIONS: int = int(
        os.environ.get("GEMINI_EMBEDDING_DIMENSIONS", "768")
    )
    GEMINI_EMBEDDING_NORMALIZE: bool = os.environ.get(
        "GEMINI_EMBEDDING_NORMALIZE", "true"
    ).lower() in {"1", "true", "yes"}

    # Google OAuth
    GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_OAUTH_REDIRECT_URI: str = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
    )
    FRONTEND_BASE_URL: str = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")

    # Gmail / OAuth scopes used for ingestion
    GMAIL_TOKEN_DIR: str = os.environ.get("GMAIL_TOKEN_DIR", "backend/.secrets/gmail")

    # GCS
    GCS_BUCKET_NAME: str = os.environ.get("GCS_BUCKET_NAME", "threadcomb-reports")

    # Google Cloud Tasks
    GOOGLE_CLOUD_PROJECT: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    GOOGLE_CLOUD_LOCATION: str = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-south1")
    CLOUD_TASKS_QUEUE_NAME: str = os.environ.get(
        "CLOUD_TASKS_QUEUE_NAME", "threadcomb-ingestion"
    )

    # Debug mode — enables dev-only endpoints (trigger-direct, etc.)
    DEBUG: bool = os.environ.get("DEBUG", "true").lower() in {"1", "true", "yes"}

    # Cloud Tasks worker (Session 2B+)
    WORKER_BASE_URL: str = os.environ.get("WORKER_BASE_URL", "")
    WORKER_SECRET: str = os.environ.get("WORKER_SECRET", "")


settings = Settings()
