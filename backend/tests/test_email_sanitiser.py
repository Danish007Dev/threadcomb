import pytest
import copy

from services.email_sanitiser import sanitise_thread
from models.ingestion import SanitisedThread

def test_indian_phone_numbers_redacted():
    raw = {
        "combined_text": (
            "Call me on +919876543210.\n"
            "Or use 919876543210.\n"
            "Just 9876543210 is fine too.\n"
            "call me on 9876543210\n"
        )
    }
    result = sanitise_thread("t1", "c1", raw)
    assert "+919876543210" not in result.sanitised_text
    assert "919876543210" not in result.sanitised_text
    assert "9876543210" not in result.sanitised_text
    assert "[PHONE_REDACTED]" in result.sanitised_text


def test_email_signatures_stripped():
    raw = {
        "combined_text": (
            "Here is the proposal.\n\n"
            "Best,\nJohn\n\n"
            "Regards,\nJane\n\n"
            "Sent from my iPhone\n\n"
            "-- \n"
            "Company Signature"
        )
    }
    result = sanitise_thread("t1", "c1", raw)
    text = result.sanitised_text.lower()
    
    assert "best," not in text
    assert "regards," not in text
    assert "sent from my iphone" not in text
    assert "--" not in text


def test_word_count_reduced():
    body = "word " * 500
    signature = "-- \n" + ("sigword " * 100)
    raw = {"combined_text": body + signature}
    
    result = sanitise_thread("t1", "c1", raw)
    
    # After sanitisation, the word count must be less than the original.
    original_word_count = len(raw["combined_text"].split())
    sanitised_word_count = len(result.sanitised_text.split())
    
    assert sanitised_word_count < original_word_count
    assert sanitised_word_count < 400


def test_zero_urls():
    raw = {
        "combined_text": (
            "Check out https://example.com/deal\n"
            "Also visit minimalist.in for details.\n"
            "<img src=\"https://tracker.com/pixel.gif\" />\n"
        )
    }
    result = sanitise_thread("t1", "c1", raw)
    text = result.sanitised_text
    
    assert "https://" not in text
    assert "minimalist.in" not in text
    assert "tracker.com" not in text


def test_deterministic_output():
    raw = {"combined_text": "This is a test email with +919876543210 and https://link.com"}
    result1 = sanitise_thread("t1", "c1", raw)
    result2 = sanitise_thread("t1", "c1", raw)
    result3 = sanitise_thread("t1", "c1", raw)
    
    assert result1.sanitised_text == result2.sanitised_text == result3.sanitised_text
    assert result1.sanitised_token_count == result2.sanitised_token_count


def test_original_input_not_mutated():
    original_text = "Do not mutate me! +919876543210"
    raw = {"combined_text": original_text, "sender_email": "test@test.com"}
    raw_copy = copy.deepcopy(raw)
    
    sanitise_thread("t1", "c1", raw)
    
    # Assert original raw_text is unchanged
    assert raw == raw_copy
    assert raw["combined_text"] == original_text


def test_edge_case_hindi_only_text():
    hindi_text = "नमस्ते, यह एक परीक्षण ईमेल है। कृपया 9876543210 पर कॉल करें।"
    raw = {"combined_text": hindi_text}
    result = sanitise_thread("t1", "c1", raw)
    
    # Should redact phone number but preserve text
    assert "9876543210" not in result.sanitised_text
    assert "[PHONE_REDACTED]" in result.sanitised_text
    assert "नमस्ते" in result.sanitised_text


def test_edge_case_mixed_hindi_english():
    mixed = "yaar this deal is 50k chahiye, please contact +919876543210 or minimalist.in"
    raw = {"combined_text": mixed}
    result = sanitise_thread("t1", "c1", raw)
    
    assert "yaar this deal is 50k chahiye" in result.sanitised_text
    assert "+919876543210" not in result.sanitised_text
    assert "minimalist.in" not in result.sanitised_text


def test_edge_case_ambiguous_amount():
    ambiguous = "let's do 50, please call 9876543210"
    raw = {"combined_text": ambiguous}
    result = sanitise_thread("t1", "c1", raw)
    
    assert "let's do 50" in result.sanitised_text
    assert "9876543210" not in result.sanitised_text


def test_edge_case_47_message_thread():
    # Construct a 47-message thread
    messages = [f"Message {i} text here.\n\n" for i in range(1, 39)]
    messages.append("Message 39: Agreed on 50k.\n\n")
    messages.extend([f"Message {i} text here.\n\n" for i in range(40, 48)])
    
    raw = {"combined_text": "".join(messages)}
    result = sanitise_thread("t1", "c1", raw, max_chars=160000)
    
    assert "Agreed on 50k" in result.sanitised_text


def test_edge_case_empty_thread():
    raw = {"combined_text": "", "message_count": 0}
    result = sanitise_thread("t1", "c1", raw)
    
    assert result.sanitised_text == ""
    assert result.sanitised_token_count == 0
