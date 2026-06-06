"""OIDC JWT Verification helper for securing endpoints."""

import logging
from typing import Optional

from fastapi import Request
from google.oauth2 import id_token
from google.auth.transport import requests

from config import settings

logger = logging.getLogger(__name__)


def verify_oidc_token(request: Request, audience: str, endpoint_name: str) -> bool:
    """
    Verifies the OIDC JWT token attached by Google Cloud Pub/Sub or Scheduler.

    In DEBUG mode, bypasses verification entirely.
    If verification fails, logs a detailed warning with IP, prefix, and timestamp.
    """
    if settings.DEBUG:
        return True

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        _log_intrusion(request, endpoint_name, "Missing or invalid Bearer scheme")
        return False

    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        _log_intrusion(request, endpoint_name, "Empty token")
        return False

    try:
        # Verify the token against Google's certs, check expiry, and verify audience
        claim = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            audience=audience if audience else None
        )

        if claim["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            _log_intrusion(request, endpoint_name, f"Invalid issuer: {claim['iss']}")
            return False

        return True

    except Exception as e:
        # e.g., google.auth.exceptions.GoogleAuthError or ValueError (invalid token/aud)
        _log_intrusion(request, endpoint_name, f"Verification failed: {str(e)}")
        return False


def _log_intrusion(request: Request, endpoint_name: str, reason: str):
    """Loudly log the intrusion attempt with raw header prefix and IP."""
    auth_header = request.headers.get("Authorization", "")
    prefix = auth_header[:20] + "..." if len(auth_header) > 20 else auth_header
    client_ip = request.client.host if request.client else "unknown"

    logger.warning(
        "OIDC Verification Failed | Endpoint: %s | IP: %s | Reason: %s | Header Prefix: '%s'",
        endpoint_name,
        client_ip,
        reason,
        prefix
    )
