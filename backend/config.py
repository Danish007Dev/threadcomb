"""ThreadComb backend configuration."""

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
    EMERGENT_LLM_KEY: str = os.environ.get("EMERGENT_LLM_KEY", "")

    # Gmail OAuth (placeholder, used in Session 2)
    GMAIL_CLIENT_ID: str = os.environ.get("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET: str = os.environ.get("GMAIL_CLIENT_SECRET", "")

    # GCS
    GCS_BUCKET_NAME: str = os.environ.get("GCS_BUCKET_NAME", "threadcomb-reports")

    # Google Cloud Tasks
    GOOGLE_CLOUD_PROJECT: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    GOOGLE_CLOUD_LOCATION: str = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-south1")
    CLOUD_TASKS_QUEUE_NAME: str = os.environ.get(
        "CLOUD_TASKS_QUEUE_NAME", "threadcomb-ingestion"
    )

    # Cloud Tasks worker (Session 2B+)
    WORKER_BASE_URL: str = os.environ.get("WORKER_BASE_URL", "")
    WORKER_SECRET: str = os.environ.get("WORKER_SECRET", "")

    # Emergent Auth
    EMERGENT_AUTH_BASE: str = "https://demobackend.emergentagent.com/auth/v1/env/oauth"


settings = Settings()
