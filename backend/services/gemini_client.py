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
    """Process-wide singleton facade around the Gemini REST API."""

    DEFAULT_MODEL = "gemini-2.5-flash-lite"
    DEFAULT_EMBEDDING_MODEL = settings.GEMINI_EMBEDDING_MODEL

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or settings.GEMINI_API_KEY

    def _generate(self, system_message: str, user_message: str, model: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system_message}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        response = requests.post(url, params={"key": self.api_key}, json=payload, timeout=60)
        response.raise_for_status()
        response_json = response.json()
        candidates = response_json.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise ValueError("Gemini returned empty content")
        texts = [part.get("text", "") for part in parts if part.get("text")]
        if not texts:
            raise ValueError("Gemini returned no text payload")
        return "\n".join(texts)

    def _embed(self, text: str, model: str) -> List[float]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        url = f"{GEMINI_API_BASE}/models/{model}:embedContent"
        payload = {
            "content": {"parts": [{"text": text}]},
        }
        response = requests.post(url, params={"key": self.api_key}, json=payload, timeout=60)
        response.raise_for_status()
        response_json = response.json()
        embedding = response_json.get("embedding", {})
        values = embedding.get("values") or []
        if not values:
            raise ValueError("Gemini returned no embedding values")

        expected = settings.GEMINI_EMBEDDING_DIMENSIONS
        if expected and len(values) != expected:
            raise ValueError(
                f"Gemini embedding dimension mismatch: got {len(values)}, expected {expected}"
            )
        return [float(value) for value in values]

    async def send_text(
        self,
        system_message: str,
        user_message: str,
        model: str = DEFAULT_MODEL,
        session_id: Optional[str] = None,
    ) -> str:
        """Send a one-shot request and return the model's response as a string."""
        return await asyncio.to_thread(self._generate, system_message, user_message, model)

    async def embed_text(
        self,
        text: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        normalize: Optional[bool] = None,
    ) -> List[float]:
        """Return an embedding vector for a text input.

        Normalization defaults to the GEMINI_EMBEDDING_NORMALIZE setting.
        """
        vector = await asyncio.to_thread(self._embed, text, model)
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
        """Send a request, parse the response as JSON, raise on failure.

        Strips ``` fences first because Gemini still emits them occasionally
        despite "JSON only" instructions.
        """
        raw = await self.send_text(system_message, user_message, model, session_id)
        payload_text = _strip_code_fences(raw)
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
    """Return a google.genai.Client initialized with GEMINI_API_KEY.

    This is separate from the old GeminiClient singleton — it uses the new
    google-genai SDK which supports response_schema with Pydantic models.
    """
    global _genai_client
    if _genai_client is None:
        try:
            from google import genai
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not configured")
            _genai_client = genai.Client(api_key=api_key)
            logger.info("Initialized google.genai.Client for structured output")
        except ImportError:
            raise ImportError(
                "google-genai package is required. Install with: pip install google-genai"
            )
    return _genai_client
