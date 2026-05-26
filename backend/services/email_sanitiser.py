"""In-memory email sanitiser.

CRITICAL: returns an in-memory `SanitisedThread`. Nothing in this module
writes to MongoDB. Raw email body text is never persisted — only structured
extracted signals are. The sanitised text passes through the Cloud Tasks
payload as a documented exception (CLOUD_TASKS_SANITISED_TEXT_TRANSIT).
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from typing import Iterator, List

from models.ingestion import SanitisedThread

logger = logging.getLogger(__name__)

# (pattern, replacement[, flags])
STRIP_PATTERNS = [
    (r"https?://\S+", " "),
    (r"--\s*\n.*", "", re.DOTALL),
    (r"Sent from my (iPhone|Android|Galaxy|iPad|MacBook).*", "", re.DOTALL),
    (
        r"[-]+\s*(Forwarded message|Original message|Begin forwarded)\s*[-]+.*?\n\n",
        "\n",
        re.DOTALL | re.IGNORECASE,
    ),
    (r"On .+?wrote:\s*\n", "\n", re.IGNORECASE | re.DOTALL),
    (r"^>.*$", "", re.MULTILINE),
    (r"\n{3,}", "\n\n"),
    (r" {2,}", " "),
]

# Indian phone formats are first (most specific). Negative lookbehinds prevent
# matching parts of email addresses or longer numeric IDs.
PII_REDACT_PATTERNS = [
    (r"(?<!\@)(?<!\d)\+91[-\s]?[6-9]\d{9}(?!\d)", "[PHONE_REDACTED]"),
    (r"(?<!\@)(?<!\d)91[6-9]\d{9}(?!\d)", "[PHONE_REDACTED]"),
    (r"(?<!\@)(?<!\d)[6-9]\d{9}(?!\d)", "[PHONE_REDACTED]"),
    (
        r"\+\d{1,3}[\s-]?\(?\d{1,4}\)?[\s-]?\d{1,4}[\s-]?\d{1,4}",
        "[PHONE_REDACTED]",
    ),
    (
        r"\b\d+[,\s]+(?:flat|floor|plot|sector|block|road|street|lane|nagar|colony|society)\b.*?\n",
        "[ADDRESS_REDACTED]\n",
        re.IGNORECASE,
    ),
]

DETERMINISTIC_SPAM_SIGNALS = [
    "unsubscribe",
    "click here to unsubscribe",
    "you received this email because",
    "view in browser",
    "view this email in your browser",
    "noreply@",
    "no-reply@",
    "donotreply@",
    "newsletter",
    "weekly digest from",
    "your order has been",
    "your package has been",
    "password reset",
    "verify your email",
    "google alert",
    "google notifications",
    "youtube upload",
    "new subscriber",
]

MIN_TOKEN_THRESHOLD = 50


# ----------------------------------------------------------------------------
# MIME parsing
# ----------------------------------------------------------------------------


def _decode_base64url(data: str) -> str:
    try:
        # Gmail uses URL-safe base64; pad before decoding.
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("base64 decode failed: %s", exc)
        return ""


def _strip_html(html: str) -> str:
    """Quick-and-clean HTML → text. Good enough for sanitiser purposes."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    replacements = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"'}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.strip()


def _extract_text_from_payload(payload: dict) -> str:
    """Recursively extract plain text from a Gmail payload.

    Handles multipart/alternative (the most common modern Gmail format).
    Preference order: text/plain > text/html (stripped) > multipart children.
    """
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_base64url(data) if data else ""

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if not data:
            return ""
        html = _decode_base64url(data)
        return _strip_html(html) if html else ""

    parts = payload.get("parts", [])
    if not parts:
        return ""

    if mime_type == "multipart/alternative":
        plain_texts: List[str] = []
        html_texts: List[str] = []
        for part in parts:
            pmime = part.get("mimeType", "")
            extracted = _extract_text_from_payload(part)
            if not extracted:
                continue
            if pmime == "text/plain":
                plain_texts.append(extracted)
            elif pmime == "text/html":
                html_texts.append(extracted)
            else:
                plain_texts.append(extracted)
        return "\n".join(plain_texts) if plain_texts else "\n".join(html_texts)

    # multipart/mixed, multipart/related, etc — recurse all
    texts: List[str] = []
    for part in parts:
        extracted = _extract_text_from_payload(part)
        if extracted:
            texts.append(extracted)
    return "\n".join(texts)


def _iter_parts(payload: dict) -> Iterator[dict]:
    yield payload
    for part in payload.get("parts", []):
        yield from _iter_parts(part)


def extract_text_from_gmail_thread(gmail_thread: dict) -> dict:
    """Extract clean text and metadata from a Gmail thread API response.

    Returns a dict with combined_text, sender_email/name, subject, date range,
    message_count, and attachment info. Returns {} on empty input.
    """
    messages = gmail_thread.get("messages", []) if gmail_thread else []
    if not messages:
        return {}

    combined_text_parts: List[str] = []
    sender_email = ""
    sender_name = None
    subject = ""
    date_start = None
    date_end = None
    attachment_names: List[str] = []
    has_attachments = False

    for i, message in enumerate(messages):
        if i == 0:
            headers = {
                h.get("name", "").lower(): h.get("value", "")
                for h in message.get("payload", {}).get("headers", [])
            }
            sender_raw = headers.get("from", "")
            subject = headers.get("subject", "")
            if "<" in sender_raw and ">" in sender_raw:
                sender_name = sender_raw.split("<")[0].strip().strip('"').strip()
                sender_email = sender_raw.split("<")[1].rstrip(">").strip()
            else:
                sender_email = sender_raw.strip()

            try:
                ts = int(message.get("internalDate", 0)) / 1000
                if ts:
                    date_start = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError):
                pass

        try:
            ts = int(message.get("internalDate", 0)) / 1000
            if ts:
                date_end = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError):
            pass

        text = _extract_text_from_payload(message.get("payload", {}))
        if text:
            combined_text_parts.append(text)

        for part in _iter_parts(message.get("payload", {})):
            fname = part.get("filename") or ""
            if fname:
                has_attachments = True
                attachment_names.append(fname)

    return {
        "combined_text": "\n\n---\n\n".join(combined_text_parts),
        "sender_email": sender_email or "",
        "sender_name": sender_name,
        "subject": subject or "",
        "message_count": len(messages),
        "date_range_start": date_start,
        "date_range_end": date_end,
        "has_attachments": has_attachments,
        "attachment_names": attachment_names[:10],
    }


# ----------------------------------------------------------------------------
# Sanitisation
# ----------------------------------------------------------------------------


def sanitise_thread(
    thread_id: str,
    creator_id: str,
    raw_extracted: dict,
    max_chars: int = 16000,
) -> SanitisedThread:
    """Sanitise extracted email text into an in-memory SanitisedThread.

    NEVER persisted to MongoDB. The only persistent transit for sanitised_text
    is the Cloud Tasks payload (named exception CLOUD_TASKS_SANITISED_TEXT_TRANSIT).
    """
    text = raw_extracted.get("combined_text", "") or ""
    original_length = len(text)

    for pattern_args in STRIP_PATTERNS:
        pattern, replacement = pattern_args[0], pattern_args[1]
        flags = pattern_args[2] if len(pattern_args) == 3 else 0
        try:
            text = re.sub(pattern, replacement, text, flags=flags)
        except re.error as exc:
            logger.warning("Strip regex error: %s", exc)

    for pattern_args in PII_REDACT_PATTERNS:
        pattern, replacement = pattern_args[0], pattern_args[1]
        flags = pattern_args[2] if len(pattern_args) == 3 else 0
        text = re.sub(pattern, replacement, text, flags=flags)

    # Keep only the most recent `max_chars` (back-of-thread is what matters
    # most for newest deal context).
    if len(text) > max_chars:
        text = text[-max_chars:]
        newline_pos = text.find("\n")
        if newline_pos > 0:
            text = text[newline_pos:].strip()

    token_estimate = len(text) // 3

    return SanitisedThread(
        thread_id=thread_id,
        creator_id=creator_id,
        sanitised_text=text,
        original_token_count=original_length // 3,
        sanitised_token_count=token_estimate,
        sender_email=raw_extracted.get("sender_email", ""),
        sender_name=raw_extracted.get("sender_name"),
        subject=raw_extracted.get("subject", ""),
        message_count=raw_extracted.get("message_count", 1),
        date_range_start=raw_extracted.get("date_range_start"),
        date_range_end=raw_extracted.get("date_range_end"),
        has_attachments=raw_extracted.get("has_attachments", False),
        attachment_names=raw_extracted.get("attachment_names", []),
    )


def is_deterministic_spam(subject: str, text_preview: str) -> bool:
    """Pre-LLM spam check. Returns True if a deterministic signal is found."""
    subject_lower = (subject or "").lower()
    text_lower = (text_preview or "").lower()[:500]
    return any(s in subject_lower or s in text_lower for s in DETERMINISTIC_SPAM_SIGNALS)
