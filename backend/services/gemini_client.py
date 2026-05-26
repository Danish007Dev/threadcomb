"""Singleton Gemini client wrapper.

Import `gemini_client` from here in every service that calls Gemini.
Never instantiate `LlmChat` directly in other files — that breaks tracing,
makes mocking harder, and accumulates session history accidentally.

The underlying `emergentintegrations.llm.chat.LlmChat` holds per-session
state and is one-shot. So our singleton is a thin wrapper that creates a
fresh stateless `LlmChat` per call, using the same API key for all of them.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class GeminiClient:
    """Process-wide singleton facade around emergentintegrations LlmChat."""

    DEFAULT_PROVIDER = "gemini"
    DEFAULT_MODEL = "gemini-2.5-flash-lite"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("EMERGENT_LLM_KEY", "")

    def _new_chat(
        self,
        system_message: str,
        model: str,
        session_id: Optional[str] = None,
    ) -> LlmChat:
        return LlmChat(
            api_key=self.api_key,
            session_id=session_id or f"tc-{uuid.uuid4().hex[:8]}",
            system_message=system_message,
        ).with_model(self.DEFAULT_PROVIDER, model)

    async def send_text(
        self,
        system_message: str,
        user_message: str,
        model: str = DEFAULT_MODEL,
        session_id: Optional[str] = None,
    ) -> str:
        """Send a one-shot request and return the model's response as a string."""
        chat = self._new_chat(system_message, model, session_id)
        result = await chat.send_message(UserMessage(text=user_message))
        return str(result)

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
