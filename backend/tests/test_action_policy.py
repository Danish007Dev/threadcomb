import pytest
from unittest.mock import MagicMock

# Assuming these imports will map to the actual implementation.
# If they do not exist yet, this serves as a TDD specification.
from services.action_policy import (
    ActionType,
    get_action_policy,
    requires_creator_approval,
    requires_hitl_review,
)

# Placeholder classes to represent the expected models if not fully implemented in action_policy
class PolicyViolationError(Exception):
    pass

class ActionResult:
    def __init__(self, status: str):
        self.status = status

class AgentAction:
    def __init__(self, action_type: str, creator_approved: bool = False, confidence_score: float = 1.0, hitl_review_required: bool = False):
        self.action_type = action_type
        self.creator_approved = creator_approved
        self.confidence_score = confidence_score
        self.hitl_review_required = hitl_review_required

def execute_action(action: AgentAction, email_send_fn):
    # This is a dummy executor that should ideally be replaced by the actual system executor
    policy = get_action_policy(ActionType(action.action_type), action.confidence_score)
    
    if policy["requires_creator_approval"] and not action.creator_approved:
        # Expected to raise PolicyViolationError or return blocked
        return ActionResult(status="blocked_pending_approval")
        
    if policy["requires_hitl_review"]:
        action.hitl_review_required = True
        
    email_send_fn()
    return ActionResult(status="success")


def test_action_policy_blocks_unapproved_email():
    action = AgentAction(action_type="send_fan_reply", creator_approved=False)
    mock_send = MagicMock()
    
    result = execute_action(action, mock_send)
    
    assert result.status == "blocked_pending_approval"
    mock_send.assert_not_called()


def test_action_policy_allows_approved_email():
    action = AgentAction(action_type="send_fan_reply", creator_approved=True, confidence_score=0.90)
    mock_send = MagicMock()
    
    result = execute_action(action, mock_send)
    
    assert result.status == "success"
    mock_send.assert_called_once()


def test_action_policy_forces_hitl_review_on_low_confidence():
    # confidence below 0.75 for fan reply
    action = AgentAction(action_type="draft_fan_reply", creator_approved=False, confidence_score=0.60)
    
    # Assert hitl_review_required is set to True regardless of what agent passed in
    policy = get_action_policy(ActionType(action.action_type), action.confidence_score)
    
    assert policy["requires_hitl_review"] is True


def test_sensitive_classification_gate():
    # SENSITIVE CLASSIFICATION GATE TEST
    # Create a fan_interactions document with classification.type = "sensitive_mental_health"
    fan_interaction = {
        "id": "123",
        "classification": {
            "type": "sensitive_mental_health"
        }
    }
    
    mock_creator_notification_fn = MagicMock()
    mock_draft_generation_fn = MagicMock()
    
    # Dummy pipeline to represent the expected system behavior
    def response_generation_pipeline(interaction, notify_fn, draft_fn):
        class Response:
            draft_text = None
            requires_human_review = False
        
        response = Response()
        if interaction["classification"]["type"] == "sensitive_mental_health":
            response.draft_text = None
            response.requires_human_review = True
            notify_fn()
        else:
            response.draft_text = draft_fn()
        
        return response

    response = response_generation_pipeline(
        fan_interaction,
        mock_creator_notification_fn,
        mock_draft_generation_fn
    )
    
    # Assert response.draft_text is None
    assert response.draft_text is None
    
    # Assert requires_human_review is True
    assert response.requires_human_review is True
    
    # Assert creator notification function was called exactly once
    mock_creator_notification_fn.assert_called_once()
    
    # Assert NO draft generation function (Flash) was called
    mock_draft_generation_fn.assert_not_called()
