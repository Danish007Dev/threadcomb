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
from typing import Optional

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

    async def send_text(
        self,
        system_message: str,
        user_message: str,
        model: str = DEFAULT_MODEL,
        session_id: Optional[str] = None,
    ) -> str:
        """Send a one-shot request and return the model's response as a string."""
        return await asyncio.to_thread(self._generate, system_message, user_message, model)

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
