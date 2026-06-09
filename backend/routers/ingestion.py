"""Gmail ingestion endpoints and background orchestrator (Sessions 2B + 3)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from services.gemini_client import GeminiClient
from config import settings

from database.ingestion_jobs import increment_job_counter, update_job_status
from database.mongodb import get_db_singleton
from models.common import ActionResult, AgentActionType, DataClassificationTier
from models.ingestion import GateDecision, IngestionJob, IngestionStatus, IngestionTrigger
from routers.auth import get_current_creator
from services.gemini_client import gemini_client
from services.mongodb_writer import write_with_classification
from services.sse_manager import publish_sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/start")
async def start_ingestion(
    background_tasks: BackgroundTasks,
    current_creator=Depends(get_current_creator),
):
    """Start a full ingestion job or resume an existing one and return the job id."""
    creator_id = current_creator["creator_id"]
    db = get_db_singleton()

    # Check for an existing incomplete job
    existing_job = await db.ingestion_jobs.find_one(
        {
            "creator_id": creator_id,
            "status": {"$in": [
                IngestionStatus.PENDING.value,
                IngestionStatus.FETCHING.value,
                IngestionStatus.SANITISING.value,
                IngestionStatus.QUEUED_FOR_EXTRACTION.value,
            ]}
        },
        sort=[("created_at", -1)]
    )

    if existing_job:
        job_id = str(existing_job["_id"])
        sse_channel = existing_job.get("sse_channel", f"ingestion:{creator_id}")
        
        # If it's queued for extraction and we are in DEBUG mode, trigger extraction
        if existing_job["status"] == IngestionStatus.QUEUED_FOR_EXTRACTION.value and settings.DEBUG:
            from routers.ingestion import trigger_dev_extraction_internal
            # Simulate the trigger dev extraction request
            asyncio.create_task(trigger_dev_extraction_internal(job_id, creator_id))
        elif existing_job["status"] != IngestionStatus.QUEUED_FOR_EXTRACTION.value:
            # Maybe the background task died? We could restart it, but for now just return the job_id
            # so the frontend connects and we can see where it's stuck.
            pass

        return {"job_id": job_id, "sse_channel": sse_channel, "status": "resumed"}

    job = IngestionJob(
        creator_id=creator_id,
        trigger=IngestionTrigger.MANUAL,
        status=IngestionStatus.PENDING,
        sse_channel=f"ingestion:{creator_id}",
    )

    job_doc = job.model_dump(mode="json")
    job_id = await write_with_classification(
        db.ingestion_jobs,
        job_doc,
        classification_tier=DataClassificationTier.AGGREGATE,
        anonymisation_eligible=False,
        export_eligible=True,
    )

    background_tasks.add_task(
        run_full_ingestion,
        creator_id=creator_id,
        job_id=job_id,
    )

    return {"job_id": job_id, "sse_channel": job.sse_channel, "status": "started"}

async def trigger_dev_extraction_internal(job_id: str, creator_id: str):
    """Internal helper to trigger dev extraction automatically."""
    db = get_db_singleton()
    try:
        oid = ObjectId(job_id)
    except Exception:
        return
    job = await db.ingestion_jobs.find_one({"_id": oid, "creator_id": creator_id})
    if not job:
        return
    
    from workers.extract_thread import run_extraction_worker
    from services.gmail_auth import get_gmail_credentials
    from services.gmail_fetcher import fetch_thread_content
    from services.email_sanitiser import extract_text_from_gmail_thread, sanitise_thread

    credentials = await get_gmail_credentials(creator_id)

    triggered = 0
    for ts in job.get("thread_statuses", []):
        if ts.get("gate_decision") in ("deal_signal", "hindi_mixed") and not ts.get("extraction_complete"):
            thread_id = ts.get("thread_id", "")
            if not thread_id:
                continue

            raw_thread = await fetch_thread_content(credentials, thread_id)
            if not raw_thread:
                continue
                
            raw_extracted = extract_text_from_gmail_thread(raw_thread)
            if not raw_extracted.get("combined_text"):
                continue

            sanitised = sanitise_thread(
                thread_id=thread_id,
                creator_id=creator_id,
                raw_extracted=raw_extracted,
            )

            payload = {
                "thread_id": thread_id,
                "creator_id": creator_id,
                "job_id": job_id,
                "sanitised_text": sanitised.sanitised_text,
                "sender_email": sanitised.sender_email,
                "subject": sanitised.subject,
                "hindi_mode": ts.get("hindi_mode", False),
            }
            asyncio.create_task(run_extraction_worker(payload))
            triggered += 1

    if triggered == 0:
        # All threads are already processed (or none passed the gate). We must trigger the audit if it hasn't been.
        queued = job.get("threads_queued_for_extraction", 1)
        processed = (
            job.get("threads_extraction_complete", 0) +
            job.get("threads_low_confidence", 0) +
            job.get("threads_errored", 0)
        )
        if processed >= queued and not job.get("audit_generation_triggered"):
            await db.ingestion_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"audit_generation_triggered": True, "updated_at": datetime.now(timezone.utc)}}
            )
            from routers.audit import run_audit_generation
            asyncio.create_task(run_audit_generation(creator_id=creator_id))


@router.post("/trigger-dev-extraction/{job_id}")
async def trigger_dev_extraction(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_creator=Depends(get_current_creator),
):
    """
    DEV ONLY — pulls queued threads from ingestion_jobs and sends them
    directly to run_extraction_worker, bypassing Cloud Tasks.
    Use when running locally without a public WORKER_BASE_URL.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Only available in DEBUG mode")

    db = get_db_singleton()
    creator_id = current_creator["creator_id"]
    try:
        oid = ObjectId(job_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Job not found")

    job = await db.ingestion_jobs.find_one({"_id": oid, "creator_id": creator_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Directly call extraction on each queued thread_id
    from workers.extract_thread import run_extraction_worker
    from services.gmail_auth import get_gmail_credentials
    from services.gmail_fetcher import fetch_thread_content
    from services.email_sanitiser import extract_text_from_gmail_thread, sanitise_thread

    credentials = await get_gmail_credentials(creator_id)
    
    triggered = 0
    for ts in job.get("thread_statuses", []):
        if ts.get("gate_decision") in ("deal_signal", "hindi_mixed") and not ts.get("extraction_complete"):
            thread_id = ts.get("thread_id", "")
            if not thread_id:
                continue

            raw_thread = await fetch_thread_content(credentials, thread_id)
            if not raw_thread:
                continue
                
            raw_extracted = extract_text_from_gmail_thread(raw_thread)
            if not raw_extracted.get("combined_text"):
                continue

            sanitised = sanitise_thread(
                thread_id=thread_id,
                creator_id=creator_id,
                raw_extracted=raw_extracted,
            )

            payload = {
                "thread_id": thread_id,
                "creator_id": creator_id,
                "job_id": job_id,
                "sanitised_text": sanitised.sanitised_text,
                "sender_email": sanitised.sender_email,
                "subject": sanitised.subject,
                "hindi_mode": ts.get("hindi_mode", False),
            }
            background_tasks.add_task(run_extraction_worker, payload=payload)
            triggered += 1

    return {"status": "ok", "threads_triggered": triggered, "mode": "dev_direct"}


@router.get("/status/{job_id}")
async def get_ingestion_status(
    job_id: str,
    current_creator=Depends(get_current_creator),
):
    """Return the current state of an ingestion job."""
    creator_id = current_creator["creator_id"]
    db = get_db_singleton()

    try:
        oid = ObjectId(job_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Job not found")

    job = await db.ingestion_jobs.find_one({"_id": oid, "creator_id": creator_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def _to_iso(value):
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "total_threads_found": job.get("total_threads_found", 0),
        "threads_passed_gate": job.get("threads_passed_gate", 0),
        "threads_queued_for_extraction": job.get("threads_queued_for_extraction", 0),
        "threads_extraction_complete": job.get("threads_extraction_complete", 0),
        "error_message": job.get("error_message"),
        "started_at": _to_iso(job.get("started_at")),
        "duration_seconds": job.get("duration_seconds"),
    }


@router.post("/gmail/webhook")
async def gmail_push_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive Gmail Pub/Sub push notifications."""
    try:
        body = await request.json()
        message = body.get("message", {})
        data_encoded = message.get("data", "")
        if not data_encoded:
            return {"status": "ok"}

        data = json.loads(base64.b64decode(data_encoded).decode("utf-8"))
        email_address = data.get("emailAddress")
        new_history_id = data.get("historyId")

        if not email_address or not new_history_id:
            return {"status": "ok"}

        db = get_db_singleton()
        creator = await db.creators.find_one({"email": email_address})
        if not creator:
            return {"status": "ok"}

        creator_id = creator.get("creator_id")
        last_history_id = (creator.get("gmail_watch") or {}).get("history_id")
        if not creator_id or not last_history_id:
            return {"status": "ok"}

        background_tasks.add_task(
            run_incremental_ingestion,
            creator_id=creator_id,
            start_history_id=last_history_id,
            new_history_id=new_history_id,
        )

        await db.creators.update_one(
            {"creator_id": creator_id},
            {
                "$set": {
                    "gmail_watch.history_id": new_history_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("Gmail webhook error: %s", exc)

    return {"status": "ok"}


async def generate_first_signal(creator_id: str, thread_statuses: list):
    """
    Generates immediate value for the creator within 60 seconds of audit start.
    Uses gate classification results only — no Gemini extraction yet.
    Runs BEFORE the extraction worker processes threads.
    """
    deal_signal_threads = [
        t for t in thread_statuses
        if t.get("gate_decision") in ("deal_signal", "hindi_mixed")
    ]
    unanswered_count = len(deal_signal_threads)

    if unanswered_count == 0:
        return  # No deal signals found — don't show a first signal

    # Pull sender emails from thread statuses for display
    # These are already available from the gate pass
    brand_emails = list(set(
        t.get("sender_email", "").split("@")[-1]
        for t in deal_signal_threads
        if t.get("sender_email")
    ))[:3]

    brand_domains_display = ", ".join(brand_emails) if brand_emails else "several brands"

    await publish_sse_event(creator_id, {
        "event": "first_signal",
        "title": "First finding — before your full audit runs",
        "message": f"We found {unanswered_count} brand deal {'email' if unanswered_count == 1 else 'emails'} in your inbox.",
        "detail": f"Brands involved: {brand_domains_display}",
        "sub_detail": "We're now extracting the details from each one. Your full audit will be ready soon.",
        "deal_count": unanswered_count,
    })


async def run_full_ingestion(creator_id: str, job_id: str) -> None:
    """Background ingestion orchestrator."""
    from services.email_sanitiser import extract_text_from_gmail_thread, sanitise_thread
    from services.gmail_auth import get_gmail_credentials
    from services.gmail_fetcher import fetch_thread_content, fetch_thread_ids
    from services.ingestion_gate import classify_thread_gate
    from services.ingestion_queue import enqueue_thread_for_extraction

    db = get_db_singleton()

    try:
        creator = await db.creators.find_one({"creator_id": creator_id})
        if not creator:
            raise ValueError(f"Creator {creator_id} not found")

        credentials = await get_gmail_credentials(creator_id)

        await update_job_status(db, job_id, IngestionStatus.FETCHING)
        await publish_sse_event(
            creator_id,
            {
                "event": "ingestion_started",
                "message": "Reading your email history...",
                "job_id": job_id,
            },
        )

        thread_ids, _ = await fetch_thread_ids(credentials)

        await db.ingestion_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$set": {
                    "total_threads_found": len(thread_ids),
                    "status": IngestionStatus.SANITISING.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        await publish_sse_event(
            creator_id,
            {
                "event": "threads_found",
                "message": f"Found {len(thread_ids)} emails to analyse...",
                "count": len(thread_ids),
            },
        )

        passed_gate = 0
        failed_gate = 0
        hitl_count = 0
        rate_limited_count = 0
        consecutive_rate_limits = 0
        enqueue_delay = 0
        max_enqueue_delay = 60

        # Use configurable sleep for rate limiting
        gate_sleep = settings.GATE_SLEEP_SECONDS

        for index, thread_id in enumerate(thread_ids):
            # Circuit breaker: if too many consecutive rate limits, stop early
            if consecutive_rate_limits >= 5:
                logger.error(
                    "Stopping ingestion for %s: %d consecutive rate limits.",
                    creator_id, consecutive_rate_limits,
                )
                await publish_sse_event(
                    creator_id,
                    {
                        "event": "ingestion_rate_limited",
                        "message": (
                            f"The AI service is overloaded. "
                            f"Processed {index} of {len(thread_ids)} emails before hitting rate limits. "
                            f"{passed_gate} brand deal threads found so far."
                        ),
                        "processed": index,
                        "total": len(thread_ids),
                        "passed": passed_gate,
                        "rate_limited": rate_limited_count,
                        "can_retry": True,
                    },
                )
                break

            raw_thread = await fetch_thread_content(credentials, thread_id)
            if not raw_thread:
                await increment_job_counter(db, job_id, "threads_errored")
                continue

            await increment_job_counter(db, job_id, "threads_fetched")

            raw_extracted = extract_text_from_gmail_thread(raw_thread)
            if not raw_extracted.get("combined_text"):
                await increment_job_counter(db, job_id, "threads_errored")
                continue

            sanitised = sanitise_thread(
                thread_id=thread_id,
                creator_id=creator_id,
                raw_extracted=raw_extracted,
            )

            gate_result = await classify_thread_gate(sanitised, gemini_client)

            await db.ingestion_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$push": {
                        "thread_statuses": {
                            "thread_id": thread_id,
                            "gate_decision": gate_result.gate_decision.value,
                            "gate_confidence": gate_result.confidence,
                            "language_detected": gate_result.language,
                            "hindi_mode": gate_result.hindi_mode,
                            "sanitised_token_count": sanitised.sanitised_token_count,
                            "queued_for_extraction": False,
                            "extraction_complete": False,
                        }
                    }
                },
            )

            if gate_result.gate_decision == GateDecision.RATE_LIMITED:
                rate_limited_count += 1
                consecutive_rate_limits += 1
                await increment_job_counter(db, job_id, "threads_rate_limited")

            elif gate_result.gate_decision in (GateDecision.DEAL_SIGNAL, GateDecision.HINDI_MIXED):
                consecutive_rate_limits = 0  # reset on success
                delay = min(enqueue_delay, max_enqueue_delay)
                await enqueue_thread_for_extraction(
                    thread_id=thread_id,
                    creator_id=creator_id,
                    job_id=job_id,
                    sanitised_text=sanitised.sanitised_text,
                    sender_email=sanitised.sender_email,
                    subject=sanitised.subject,
                    date_range_start=sanitised.date_range_start.isoformat()
                    if sanitised.date_range_start
                    else "",
                    date_range_end=sanitised.date_range_end.isoformat()
                    if sanitised.date_range_end
                    else "",
                    has_attachments=sanitised.has_attachments,
                    attachment_names=sanitised.attachment_names,
                    hindi_mode=gate_result.hindi_mode,
                    language=gate_result.language,
                    delay_seconds=delay,
                )
                enqueue_delay += 1
                passed_gate += 1
                await increment_job_counter(db, job_id, "threads_passed_gate")
                await increment_job_counter(db, job_id, "threads_queued_for_extraction")

            elif gate_result.gate_decision == GateDecision.LOW_CONFIDENCE:
                consecutive_rate_limits = 0
                await write_with_classification(
                    db.agent_actions,
                    {
                        "creator_id": creator_id,
                        "agent": "dna_reader",
                        "action_type": AgentActionType.HITL_QUEUED.value,
                        "execution": {
                            "model_used": GeminiClient.DEFAULT_MODEL,
                            "tokens": gate_result.tokens_used,
                        },
                        "decision": {
                            "reasoning_summary": gate_result.reasoning_brief,
                            "gate_confidence": gate_result.confidence,
                            "thread_id": thread_id,
                            "subject": sanitised.subject,
                            "sender_email": sanitised.sender_email,
                        },
                        "outcome": {"result": ActionResult.PENDING_HITL.value},
                    },
                    classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
                )
                hitl_count += 1
                await increment_job_counter(db, job_id, "threads_low_confidence")
            else:
                consecutive_rate_limits = 0
                failed_gate += 1
                await increment_job_counter(db, job_id, "threads_failed_gate")

            if index % 5 == 0:
                await publish_sse_event(
                    creator_id,
                    {
                        "event": "ingestion_progress",
                        "message": f"Analysed {index + 1} of {len(thread_ids)} emails...",
                        "passed": passed_gate,
                        "failed": failed_gate,
                        "rate_limited": rate_limited_count,
                        "total": len(thread_ids),
                    },
                )

            await asyncio.sleep(gate_sleep)

        # Determine final status
        if rate_limited_count > 0 and passed_gate == 0:
            final_status = IngestionStatus.FAILED
            failure_reason = "rate_limited"
        elif passed_gate > 0:
            final_status = IngestionStatus.QUEUED_FOR_EXTRACTION
            failure_reason = None
        else:
            final_status = IngestionStatus.FAILED
            failure_reason = "no_deals_found"

        await update_job_status(db, job_id, final_status)

        if failure_reason == "rate_limited":
            await publish_sse_event(
                creator_id,
                {
                    "event": "ingestion_failed",
                    "reason": "rate_limited",
                    "message": (
                        "The AI service hit its rate limit. "
                        f"Only {len(thread_ids) - rate_limited_count} of {len(thread_ids)} "
                        "emails could be analysed. Try again in a few minutes."
                    ),
                    "can_retry": True,
                    "passed_gate": passed_gate,
                    "rate_limited": rate_limited_count,
                },
            )
        elif failure_reason == "no_deals_found":
            await publish_sse_event(
                creator_id,
                {
                    "event": "ingestion_failed",
                    "reason": "no_deals_found",
                    "message": (
                        f"Analysed {len(thread_ids)} emails but found no brand deal threads. "
                        "This might mean your inbox doesn't have deal-related emails in the last 6 months, "
                        "or the filter needs adjusting."
                    ),
                    "can_retry": True,
                    "passed_gate": 0,
                    "total_analysed": len(thread_ids),
                },
            )
        else:
            eta_minutes = max(1, round(passed_gate / 5))
            await publish_sse_event(
                creator_id,
                {
                    "event": "gate_complete",
                    "message": (
                        f"Found {passed_gate} brand deal threads. "
                        f"Your audit will be ready in approximately {eta_minutes} minutes."
                    ),
                    "passed_gate": passed_gate,
                    "failed_gate": failed_gate,
                    "hitl_queue": hitl_count,
                    "rate_limited": rate_limited_count,
                },
            )

        # ── First Signal — immediate value before full audit ────────────
        job_doc = await db.ingestion_jobs.find_one({"_id": ObjectId(job_id)})
        if job_doc:
            await generate_first_signal(
                creator_id,
                job_doc.get("thread_statuses", []),
            )
            
        # ── Auto-trigger extraction in DEV mode ─────────────────────────
        if settings.DEBUG and passed_gate > 0:
            # Import here to avoid circular dependency
            from routers.ingestion import trigger_dev_extraction_internal
            asyncio.create_task(trigger_dev_extraction_internal(job_id, creator_id))

        # ── Voice profiling — runs async, not needed for audit ──────────
        if passed_gate > 0:
            await publish_sse_event(creator_id, {
                "event": "voice_profiling",
                "message": "Learning your communication style...",
            })
            from services.voice_profiler import run_voice_profiling
            # Fire and forget — voice profile not needed for the Audit Report
            asyncio.create_task(run_voice_profiling(creator_id=creator_id))

    except Exception as exc:  # noqa: BLE001
        logger.error("Ingestion error for creator %s: %s", creator_id, exc, exc_info=True)
        await update_job_status(db, job_id, IngestionStatus.FAILED, error_message=str(exc))
        await publish_sse_event(
            creator_id,
            {
                "event": "ingestion_failed",
                "reason": "error",
                "message": f"Something went wrong during the audit: {str(exc)[:200]}",
                "can_retry": True,
            },
        )


async def run_incremental_ingestion(
    creator_id: str,
    start_history_id: str,
    new_history_id: str,
) -> None:
    """Incremental ingestion triggered by Gmail push webhook."""
    from services.email_sanitiser import extract_text_from_gmail_thread, sanitise_thread
    from services.gmail_auth import get_gmail_credentials
    from services.gmail_fetcher import fetch_history_delta, fetch_thread_content
    from services.ingestion_gate import classify_thread_gate
    from services.ingestion_queue import enqueue_thread_for_extraction

    db = get_db_singleton()

    try:
        credentials = await get_gmail_credentials(creator_id)
        new_thread_ids, _ = await fetch_history_delta(credentials, start_history_id)

        for thread_id in new_thread_ids:
            raw_thread = await fetch_thread_content(credentials, thread_id)
            if not raw_thread:
                continue
            raw_extracted = extract_text_from_gmail_thread(raw_thread)
            if not raw_extracted.get("combined_text"):
                continue
            sanitised = sanitise_thread(thread_id, creator_id, raw_extracted)
            gate_result = await classify_thread_gate(sanitised, gemini_client)

            if gate_result.gate_decision in (GateDecision.DEAL_SIGNAL, GateDecision.HINDI_MIXED):
                await enqueue_thread_for_extraction(
                    thread_id=thread_id,
                    creator_id=creator_id,
                    job_id=f"incremental_{creator_id}",
                    sanitised_text=sanitised.sanitised_text,
                    sender_email=sanitised.sender_email,
                    subject=sanitised.subject,
                    date_range_start=sanitised.date_range_start.isoformat()
                    if sanitised.date_range_start
                    else "",
                    date_range_end=sanitised.date_range_end.isoformat()
                    if sanitised.date_range_end
                    else "",
                    has_attachments=sanitised.has_attachments,
                    attachment_names=sanitised.attachment_names,
                    hindi_mode=gate_result.hindi_mode,
                    language=gate_result.language,
                    delay_seconds=0,
                )

                # Session 4: Immediately notify creator of new brand deal detection
                await publish_sse_event(creator_id, {
                    "event": "new_deal_detected",
                    "message": f"New brand deal email from {sanitised.sender_email.split('@')[-1]}",
                    "brand_domain": sanitised.sender_email.split("@")[-1],
                    "subject": sanitised.subject,
                    "action": "Extraction in progress — draft will be ready in ~30 seconds",
                })

    except ValueError as exc:
        if "HISTORY_ID_EXPIRED" in str(exc):
            logger.warning(
                "History ID expired for creator %s. Triggering full re-ingest.",
                creator_id,
            )
        else:
            logger.error("Incremental ingestion error for %s: %s", creator_id, exc)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Incremental ingestion error for %s: %s", creator_id, exc, exc_info=True
        )
