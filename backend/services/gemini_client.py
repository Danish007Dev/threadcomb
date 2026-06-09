"""Singleton Gemini client wrapper using the Google Gemini REST API.

Import `gemini_client` from here in every service that calls Gemini.
This wrapper keeps the model access centralized and avoids hard-coding
HTTP details across the codebase.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from math import sqrt
from typing import Optional, List

import requests

from config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class GeminiClient:
    """Process-wide singleton facade around the Gemini API."""

    DEFAULT_MODEL = "gemini-2.5-flash" if settings.USE_VERTEX_AI else "gemini-2.5-flash-lite"
    DEFAULT_EMBEDDING_MODEL = settings.GEMINI_EMBEDDING_MODEL

    def __init__(self, api_key: str = ""):
        # Compatibility signature, no longer needed
        pass

    async def send_text(
        self,
        system_message: str,
        user_message: str,
        model: str = DEFAULT_MODEL,
        session_id: Optional[str] = None,
    ) -> str:
        """Send a one-shot request and return the model's response as a string."""
        from google.genai import types
        client = get_gemini_client_genai()
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_message,
                temperature=0,
            )
        )
        if not response.text:
            raise ValueError("Gemini returned no text payload")
        return response.text

    async def embed_text(
        self,
        text: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        normalize: Optional[bool] = None,
    ) -> List[float]:
        """Return an embedding vector for a text input."""
        client = get_gemini_client_genai()
        response = await client.aio.models.embed_content(
            model=model,
            contents=text,
        )
        if not response.embeddings or not response.embeddings[0].values:
            raise ValueError("Gemini returned no embedding values")
            
        vector = response.embeddings[0].values
        should_normalize = (
            settings.GEMINI_EMBEDDING_NORMALIZE if normalize is None else normalize
        )
        if should_normalize:
            return _l2_normalize(vector)
        return vector

    async def send_json(
        self,
        system_message: str,
        user_message: str,
        model: str = DEFAULT_MODEL,
        session_id: Optional[str] = None,
    ) -> dict:
        """Send a request, parse the response as JSON, raise on failure."""
        from google.genai import types
        client = get_gemini_client_genai()
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_message,
                temperature=0,
                response_mime_type="application/json",
            )
        )
        if not response.text:
            raise ValueError("Gemini returned no text payload")
        payload_text = _strip_code_fences(response.text)
        return json.loads(payload_text)


# Module-level singleton — import this directly.
gemini_client = GeminiClient()


def get_gemini_client() -> GeminiClient:
    """Return the application-scoped Gemini client singleton."""
    return gemini_client


def _l2_normalize(values: List[float]) -> List[float]:
    norm = sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


# ── Google GenAI SDK client (Session 3) ────────────────────────────────────
# The new google.genai.Client supports structured output with Pydantic schemas,
# which is required for DealExtraction / SynthesisReport calls.
# This coexists with the REST-based GeminiClient above.

_genai_client = None


def get_gemini_client_genai():
    """Return a google.genai.Client initialized for Vertex AI or AI Studio."""
    global _genai_client
    if _genai_client is None:
        try:
            from google import genai
            from google.genai import types
            
            retry_policy = types.HttpRetryOptions(
                attempts=4,
                initial_delay=1.5,
                exp_base=2.0,
                max_delay=30.0,
                http_status_codes=[408, 429, 500, 502, 503, 504]
            )
            http_config = types.HttpOptions(
                retry_options=retry_policy,
                timeout=60 * 1000
            )

            if settings.USE_VERTEX_AI:
                _genai_client = genai.Client(
                    vertexai=True,
                    project=settings.GOOGLE_CLOUD_PROJECT,
                    location="us-central1",
                    http_options=http_config
                )
                logger.info("Initialized google.genai.Client for Vertex AI (us-central1)")
            else:
                api_key = settings.GEMINI_API_KEY
                if not api_key:
                    raise ValueError("GEMINI_API_KEY is not configured")
                _genai_client = genai.Client(api_key=api_key)
                logger.info("Initialized google.genai.Client for AI Studio")
        except ImportError:
            raise ImportError(
                "google-genai package is required. Install with: pip install google-genai"
            )
    return _genai_client
