"""Convenience launcher for the FastAPI backend (dev only)."""

import os

import uvicorn


def main() -> None:
    host = os.environ.get("TC_BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("TC_BACKEND_PORT", "8000"))
    reload = os.environ.get("TC_BACKEND_RELOAD", "1") == "1"

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=reload,
        app_dir="backend",
        log_level=os.environ.get("TC_BACKEND_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
