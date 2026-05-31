import pytest
from pydantic import ValidationError

from models.deal import DealExtraction
from models.corpus import PublicDataExtraction, RateBenchmarkExtraction


def test_deal_extraction_ambiguity_flag():
    # amount_ambiguity_flag=True with amount set must raise ValidationError
    with pytest.raises(ValidationError):
        DealExtraction(
            amount_ambiguity_flag=True,
            # Testing against existing fields in DealExtraction
            amount_typical=50000.0,
            amount_min=40000.0,
            amount_max=60000.0,
        )

    # Additionally, if 'deal_amount' was the intended field:
    with pytest.raises(ValidationError):
        DealExtraction(
            amount_ambiguity_flag=True,
            deal_amount=50000.0,
        )


def test_extraction_confidence_bounds():
    # extraction_confidence must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        DealExtraction(extraction_confidence=-0.1)
    
    with pytest.raises(ValidationError):
        DealExtraction(extraction_confidence=1.1)
    
    with pytest.raises(ValidationError):
        DealExtraction(extraction_confidence=None)

    # Valid value
    valid = DealExtraction(extraction_confidence=0.85)
    assert valid.extraction_confidence == 0.85


def test_intent_classification_literal_values():
    # intent_classification must only accept defined Literal values
    invalid_values = ["unknown", "maybe_deal", ""]
    
    for invalid in invalid_values:
        with pytest.raises(ValidationError):
            DealExtraction(intent_classification=invalid)


def test_public_data_extraction_corroboration_score_bounds():
    # corroboration_score in PublicDataExtraction must be between 0.0 and 1.0
    invalid_values = [-0.1, 1.1]
    for invalid in invalid_values:
        with pytest.raises(ValidationError):
            PublicDataExtraction(
                source_file="test.pdf",
                source_type="industry_report",
                corroboration_score=invalid,
            )
            
    valid_values = [0.0, 0.33, 0.67, 1.0]
    for valid in valid_values:
        # Assuming we need to satisfy basic required fields as well
        instance = PublicDataExtraction(
            source_file="test.pdf",
            source_type="industry_report",
            corroboration_score=valid,
        )
        assert instance.corroboration_score == valid


def test_rate_benchmark_bounds():
    # rate_p25 must be less than rate_p50, and rate_p50 less than rate_p75
    # Testing inversion: rate_p25 > rate_p50 must be rejected
    
    # Testing with rate_p25, rate_p50, rate_p75 fields if they exist
    with pytest.raises(ValidationError):
        RateBenchmarkExtraction(
            observation_period="2024_annual",
            source_quote="test",
            extraction_confidence=0.9,
            rate_p25=60000,
            rate_p50=50000,
        )
    
    with pytest.raises(ValidationError):
        RateBenchmarkExtraction(
            observation_period="2024_annual",
            source_quote="test",
            extraction_confidence=0.9,
            rate_p50=60000,
            rate_p75=50000,
        )


def test_currency_validation():
    # currency must be one of "INR", "USD", "EUR"
    invalid_currencies = ["inr", "rupees", ""]
    
    for invalid in invalid_currencies:
        with pytest.raises(ValidationError):
            DealExtraction(currency=invalid)
        
        with pytest.raises(ValidationError):
            RateBenchmarkExtraction(
                observation_period="2024_annual",
                source_quote="test",
                extraction_confidence=0.9,
                currency=invalid,
            )
