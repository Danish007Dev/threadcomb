import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from corpus.ingest import (
    compute_confidence_weight,
    cross_validate_benchmarks,
    write_niche_graph_nodes,
    write_brand_signals,
    run_ingestion,
)
from models.corpus import PublicDataExtraction


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Async mock for updates
    db.niche_graph.update_one = AsyncMock()
    db.brands.update_one = AsyncMock()
    return db


def test_confidence_weight_computation():
    # 1 source type (corroboration_score = 0.33) -> between 0.40 and 0.55
    weight_1 = compute_confidence_weight(0.33)
    assert 0.40 <= weight_1 <= 0.55

    # 3 source types (corroboration_score = 1.0) -> between 0.80 and 0.85
    weight_3 = compute_confidence_weight(1.0)
    assert 0.80 <= weight_3 <= 0.85

    # Should not be below 0.40
    weight_min = compute_confidence_weight(0.0)
    assert weight_min >= 0.40


def test_cross_validation_rejects_low_confidence():
    # An extraction with confidence_weight = 0.3 must be rejected
    extraction = PublicDataExtraction(
        source_file="test.pdf",
        source_type="industry_report",
        document_date=None,
        geographic_scope="india",
        document_summary="",
        rate_benchmarks=[
            {
                "niche": "beauty",
                "follower_tier": "mid",
                "content_format": "instagram_reel",
                "rate_typical": 50000,
                "currency": "INR",
                "extraction_confidence": 0.30,  # Below threshold
                "geographic_scope": "india",
                "source_quote": "test",
            },
            {
                "niche": "beauty",
                "follower_tier": "macro",
                "content_format": "instagram_reel",
                "rate_typical": 100000,
                "currency": "INR",
                "extraction_confidence": 0.80,  # Valid
                "geographic_scope": "india",
                "source_quote": "test",
            }
        ],
        brand_signals=[],
        clauses=[],
        total_extractions=2,
    )
    
    nodes = cross_validate_benchmarks([extraction])
    
    assert len(nodes) == 1
    assert nodes[0]["follower_tier"] == "macro"
    assert all(n["confidence_weight"] >= 0.40 for n in nodes)


def test_invalid_data_rejection():
    # Missing niche must be rejected
    # Note: Pydantic handles some validation, but let's test the cross-validator behaviour
    extraction = PublicDataExtraction(
        source_file="test.pdf",
        source_type="industry_report",
        rate_benchmarks=[
            {
                "niche": "",
                "follower_tier": "mid",
                "content_format": "instagram_reel",
                "rate_typical": 50000,
                "extraction_confidence": 0.8,
            },
        ],
        brand_signals=[],
        clauses=[],
    )
    nodes = cross_validate_benchmarks([extraction])
    assert len(nodes) == 0


@pytest.mark.asyncio
async def test_idempotency(mock_db):
    nodes = [
        {
            "niche": "beauty",
            "follower_tier": "mid",
            "content_format": "instagram_reel",
            "source_file": "report.pdf",
            "rate_p50": 50000,
            "confidence_weight": 0.8,
        }
    ]
    
    # Run once
    written_1 = await write_niche_graph_nodes(mock_db, nodes)
    assert written_1 == 1
    assert mock_db.niche_graph.update_one.call_count == 1
    
    # Run twice
    written_2 = await write_niche_graph_nodes(mock_db, nodes)
    assert written_2 == 1
    assert mock_db.niche_graph.update_one.call_count == 2
    
    # The upsert logic in update_one enforces idempotency on MongoDB side
    call_args_list = mock_db.niche_graph.update_one.call_args_list
    assert call_args_list[0][0][0] == call_args_list[1][0][0]  # Filter key is same


@pytest.mark.asyncio
async def test_routing_brand_signals_and_clauses(mock_db):
    # Brand signal extractions must write to brands collection NOT niche_graph
    extraction = PublicDataExtraction(
        source_file="test.pdf",
        source_type="brand_signal",
        rate_benchmarks=[],
        brand_signals=[
            {
                "brand_name": "Minimalist",
                "category": "Beauty",
                "niche_targeted": ["beauty"],
                "content_formats_used": ["instagram_reel"],
                "campaign_activity_signal": True,
                "extraction_confidence": 0.9,
            }
        ],
        clauses=[],
    )
    
    written_brands = await write_brand_signals(mock_db, [extraction])
    assert written_brands == 1
    assert mock_db.brands.update_one.call_count == 1
    
    nodes = cross_validate_benchmarks([extraction])
    written_niche = await write_niche_graph_nodes(mock_db, nodes)
    assert written_niche == 0
    assert mock_db.niche_graph.update_one.call_count == 0


@pytest.mark.asyncio
async def test_empty_extraction_handling(mock_db):
    extraction = PublicDataExtraction(
        source_file="empty.pdf",
        source_type="industry_report",
        rate_benchmarks=[],
        brand_signals=[],
        clauses=[],
    )
    
    nodes = cross_validate_benchmarks([extraction])
    assert len(nodes) == 0
    
    written_niche = await write_niche_graph_nodes(mock_db, nodes)
    assert written_niche == 0
    
    written_brands = await write_brand_signals(mock_db, [extraction])
    assert written_brands == 0
    
    assert mock_db.niche_graph.update_one.call_count == 0
    assert mock_db.brands.update_one.call_count == 0
