"""ACTION_POLICY — Python code, NOT a prompt.

This module is imported by every agent. Agents call requires_creator_approval(),
requires_hitl_review(), or get_action_policy() to make policy decisions.
They never prompt the model to decide whether approval is needed.
"""

from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    # Email actions
    SEND_BRAND_DEAL_EMAIL = "send_brand_deal_email"
    SEND_INVOICE_FOLLOWUP = "send_invoice_followup"
    SEND_FAN_REPLY = "send_fan_reply"
    DRAFT_BRAND_DEAL_EMAIL = "draft_brand_deal_email"
    DRAFT_INVOICE_FOLLOWUP = "draft_invoice_followup"
    DRAFT_FAN_REPLY = "draft_fan_reply"
    # MongoDB updates
    UPDATE_DEAL_STATUS = "update_deal_status"
    UPDATE_INVOICE_STATUS = "update_invoice_status"
    UPDATE_SKILLS_MAP_PREFERENCE = "update_skills_map_preference"
    UPDATE_BRAND_INTELLIGENCE = "update_brand_intelligence"
    # Calendar actions
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    # Reports
    GENERATE_AUDIT_REPORT = "generate_audit_report"


# ALWAYS requires creator approval before execution.
ALWAYS_REQUIRE_CREATOR_APPROVAL = {
    ActionType.SEND_BRAND_DEAL_EMAIL,
    ActionType.SEND_INVOICE_FOLLOWUP,
    ActionType.SEND_FAN_REPLY,
}

# Requires creator approval by default; can be pre-approved by creator in settings.
DEFAULT_REQUIRE_CREATOR_APPROVAL = {
    ActionType.CREATE_CALENDAR_EVENT,
}

# Requires HITL review if confidence below threshold.
REQUIRE_HITL_IF_LOW_CONFIDENCE = {
    ActionType.DRAFT_BRAND_DEAL_EMAIL: 0.80,
    ActionType.DRAFT_INVOICE_FOLLOWUP: 0.75,
    ActionType.DRAFT_FAN_REPLY: 0.75,
    ActionType.UPDATE_SKILLS_MAP_PREFERENCE: 0.70,
}

# Never requires approval (internal updates only).
NO_APPROVAL_REQUIRED = {
    ActionType.UPDATE_DEAL_STATUS,
    ActionType.UPDATE_INVOICE_STATUS,
    ActionType.UPDATE_BRAND_INTELLIGENCE,
    ActionType.GENERATE_AUDIT_REPORT,
}


def requires_creator_approval(
    action_type: ActionType, creator_settings: Optional[dict] = None
) -> bool:
    """Return True if this action must wait for creator approval before executing."""
    if action_type in ALWAYS_REQUIRE_CREATOR_APPROVAL:
        return True
    if action_type in DEFAULT_REQUIRE_CREATOR_APPROVAL:
        if creator_settings and creator_settings.get(
            f"auto_approve_{action_type.value}", False
        ):
            return False
        return True
    return False


def requires_hitl_review(action_type: ActionType, confidence: float) -> bool:
    """Return True if this action requires human reviewer inspection due to low confidence."""
    threshold = REQUIRE_HITL_IF_LOW_CONFIDENCE.get(action_type)
    if threshold is None:
        return False
    return confidence < threshold


def get_action_policy(
    action_type: ActionType,
    confidence: float = 1.0,
    creator_settings: Optional[dict] = None,
) -> dict:
    """Return the complete policy decision for an action.

    All agents call this before taking any action.
    """
    needs_approval = requires_creator_approval(action_type, creator_settings)
    needs_hitl = requires_hitl_review(action_type, confidence)
    return {
        "action_type": action_type.value,
        "requires_creator_approval": needs_approval,
        "requires_hitl_review": needs_hitl,
        "can_execute": not needs_approval and not needs_hitl,
        "confidence": confidence,
    }


# ============================================================================
# Named architectural exceptions
# ============================================================================
# When a documented exception to a non-negotiable principle is required, it
# lives here — not buried in a code comment. Future reviewers find it by
# grep'ing NAMED_EXCEPTIONS.
NAMED_EXCEPTIONS = {
    "CLOUD_TASKS_SANITISED_TEXT_TRANSIT": {
        "description": (
            "Sanitised email text passes through the Cloud Tasks payload as a "
            "temporary transit medium. This is an explicit exception to "
            "Principle 3 (no email text in persistent storage). "
            "Justification: Cloud Tasks encrypts payloads at rest and in transit. "
            "Tasks execute immediately — they are not long-term storage. "
            "Text is sanitised (PII redacted, signatures stripped), not raw email. "
            "The HITL reviewer never sees this text — only subject and sender_email "
            "are stored in agent_actions for low-confidence threads."
        ),
        "approved_by": "architecture_review",
        "date": "2026-05",
    },
}
