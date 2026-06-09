# backend/services/deal_search.py

import asyncio
import logging
from math import sqrt
from typing import List, Optional
from google.genai import types

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIMENSIONS = 768


async def embed_for_search(text: str) -> List[float]:
    """
    Generates a normalized embedding for SEARCH (query-side).
    CRITICAL: use task_type="RETRIEVAL_QUERY" — different from RETRIEVAL_DOCUMENT used during indexing.
    This asymmetric task typing is intentional and improves retrieval accuracy.
    """
    from services.gemini_client import get_gemini_client_genai
    client = get_gemini_client_genai()

    if not text.strip():
        return [0.0] * EMBEDDING_DIMENSIONS

    response = await asyncio.to_thread(
        client.models.embed_content,
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",       # ← query side, not RETRIEVAL_DOCUMENT
            output_dimensionality=EMBEDDING_DIMENSIONS,
        )
    )

    vector = response.embeddings[0].values

    # Normalize — required for 768d (not pre-normalized by API)
    # Using pure Python to match existing codebase convention (no numpy)
    norm = sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


async def find_similar_deals(
    db,
    creator_id: str,
    query_text: str,
    num_results: int = 5,
) -> List[dict]:
    """
    Finds the creator's most similar historical deals using Atlas Vector Search.
    Only searches deals with extraction_confidence >= 0.70.
    Returns empty list gracefully if no deals exist yet.
    """
    query_vector = await embed_for_search(query_text)

    pipeline = [
        {
            "$vectorSearch": {
                "index": "deal_embeddings_index",
                "path": "embedding_vector",
                "queryVector": query_vector,
                "numCandidates": 50,
                "limit": num_results,
                "filter": {
                    "creator_id": {"$eq": creator_id},
                    "extraction_confidence": {"$gte": 0.70},
                    # Only return deals with known outcomes for useful context
                    "status": {"$in": ["accepted", "paid", "delivered", "negotiating"]},
                }
            }
        },
        {
            "$project": {
                "embedding_vector": 0,     # exclude the vector from results
            }
        },
        {
            "$addFields": {
                "score": {"$meta": "vectorSearchScore"},
            }
        }
    ]

    try:
        results = await db.deals.aggregate(pipeline).to_list(num_results)
        return results
    except Exception as e:
        logger.warning(f"Atlas Vector Search error (returning empty): {e}")
        return []


def summarise_similar_deals(similar_deals: List[dict]) -> Optional[str]:
    """
    Produces a one-sentence summary of similar deals for context injection.
    Only includes non-ambiguous amounts. Returns None if no useful data.
    """
    if not similar_deals:
        return None

    amounts = [
        d["financials"]["amount_inr"]
        for d in similar_deals
        if not d.get("financials", {}).get("amount_ambiguity_flag")
        and d.get("financials", {}).get("amount_inr")
    ]

    count = len(similar_deals)
    if amounts:
        avg = sum(amounts) / len(amounts)
        min_a, max_a = min(amounts), max(amounts)
        return f"You've done {count} similar deal{'s' if count > 1 else ''} ranging from ₹{min_a:,.0f} to ₹{max_a:,.0f} (avg ₹{avg:,.0f})."
    else:
        return f"You've done {count} similar deal{'s' if count > 1 else ''} (amounts not on record)."
