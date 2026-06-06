"""ThreadComb Corpus Ingestion Pipeline
=====================================

Reads structured documents from a local folder, extracts signals via Gemini
2.5 Flash, cross-validates, and writes results to MongoDB.

Usage:
    python backend/corpus/ingest.py --folder ./corpus/data/
    python backend/corpus/ingest.py --folder ./corpus/data/ --dry-run
    python backend/corpus/ingest.py --folder ./corpus/data/ --niche beauty

This script is idempotent. Identical input → identical output, regardless
of how many times you run it.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorClient

# ─── Make `backend/` importable when this file is executed directly ──────────
HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parent.parent  # /app/backend
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Accept MONGODB_URI (canonical) or MONGO_URL (legacy fallback).
if not os.environ.get("MONGODB_URI") and os.environ.get("MONGO_URL"):
    os.environ["MONGODB_URI"] = os.environ["MONGO_URL"]
if not os.environ.get("DB_NAME") and os.environ.get("MONGODB_DB_NAME"):
    os.environ["DB_NAME"] = os.environ["MONGODB_DB_NAME"]

from config import settings  # noqa: E402
from models.corpus import PublicDataExtraction  # noqa: E402
from services.gemini_client import gemini_client  # noqa: E402

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("threadcomb.corpus")

# ─── Constants ───────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json"}
EXTRACTION_MODEL = "gemini-2.5-flash"
MAX_CHARS_PER_DOCUMENT = 80_000

SOURCE_TYPE_FOLDER_MAP = {
    "industry_reports": "industry_report",
    "contract_templates": "contract_template",
    "public_media_kits": "public_media_kit",
    "brand_signals": "brand_signal",
    "disclosure_data": "disclosure_data",
}


EXTRACTION_SYSTEM_PROMPT = """\
You are a data extraction specialist for ThreadComb — a creator operations
platform focused on the Indian creator economy.

Your task: Extract structured signals from public documents about the Indian
influencer and creator economy. You are reading industry reports, contract
templates, media kits, and brand activity signals.

IMPORTANT RULES:
1. Only extract what is explicitly stated in the document. Do not infer or estimate.
2. If a rate is given as a range (e.g. ₹30K–₹75K), set rate_min=30000, rate_max=75000,
   rate_typical=52500 (midpoint).
3. If a follower tier is described in words ("nano influencers", "micro-creators"),
   map to: nano=<10K, micro=10K-50K, mid=50K-200K, macro=200K-1M, mega=>1M.
4. Geographic scope defaults to "india" unless explicitly stated otherwise.
5. For source_quote: extract the exact sentence or phrase that supports the
   extraction. This is used for human verification. Keep it under 150 characters.
6. Set extraction_confidence based on how clearly the source states the data:
   - 0.95: explicitly stated with numbers ("Beauty mid-tier creators earn ₹45K per Reel")
   - 0.75: implied or estimated ("creators in this tier typically earn...")
   - 0.50: inferred from context without explicit statement
   - Below 0.50: DO NOT extract — skip this data point entirely.
7. Brands section: only include brands clearly identified as running creator
   campaigns. A brand named in an ASCI complaint has active campaign evidence.
   A brand mentioned in passing does NOT.
8. content_format MUST be one of: instagram_reel | instagram_post | instagram_story
   | youtube_dedicated | youtube_integration | youtube_shorts | multi_platform.
9. niche MUST be one of: beauty | gaming | education | finance | fashion | food
   | tech | sports | asmr | wellness | politics | gifting.
10. follower_tier MUST be one of: nano | micro | mid | macro | mega.

Return a JSON object with these top-level keys ONLY:
{
  "document_date": "YYYY or YYYY-MM or null",
  "geographic_scope": "india",
  "document_summary": "one paragraph summary",
  "rate_benchmarks": [
     {"niche": "...", "follower_tier": "...", "content_format": "...",
      "rate_min": <number|null>, "rate_max": <number|null>, "rate_typical": <number|null>,
      "currency": "INR", "geographic_scope": "india",
      "observation_period": "2024_annual", "source_quote": "...",
      "extraction_confidence": 0.0-1.0}
  ],
  "brand_signals": [
     {"brand_name": "...", "brand_domain": "..."|null, "category": "...",
      "niche_targeted": ["..."], "content_formats_used": ["..."],
      "campaign_activity_signal": true, "geographic_scope": "india",
      "observation_period": "2024_annual", "source_quote": "...",
      "extraction_confidence": 0.0-1.0}
  ],
  "clauses": [
     {"clause_type": "...", "clause_summary": "...",
      "creator_favourable": true|false, "risk_level": 1-5,
      "typical_or_unusual": "typical"|"unusual"|"red_flag",
      "source_quote": "...", "extraction_confidence": 0.0-1.0}
  ]
}

Return ONLY the JSON. No markdown fences. No preamble. No commentary.
If the document contains nothing relevant, return arrays with [].
"""


# ============================================================================
# File reading helpers
# ============================================================================


def _read_pdf(file_path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Add it to requirements.txt.")
        return ""
    try:
        with pdfplumber.open(file_path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages)
    except Exception as exc:
        logger.warning("pdfplumber failed for %s: %s. Skipping.", file_path.name, exc)
        return ""


def _read_text(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Failed to read %s: %s", file_path.name, exc)
        return ""


def _load_document_content(file_path: Path) -> str:
    if file_path.suffix.lower() == ".pdf":
        return _read_pdf(file_path)
    return _read_text(file_path)


def _strip_code_fences(text: str) -> str:
    """Some models still emit ```json fences despite instructions; strip them."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


# ============================================================================
# Extraction
# ============================================================================


async def extract_from_document(
    file_path: Path,
    source_type: str,
    api_key: str,
) -> Optional[PublicDataExtraction]:
    """Run Gemini 2.5 Flash extraction on a single document.

    Returns PublicDataExtraction or None on failure.
    """
    content = _load_document_content(file_path)
    if not content.strip():
        logger.warning("Empty content for %s. Skipping.", file_path.name)
        return None

    if file_path.suffix.lower() == ".json":
        try:
            payload = json.loads(content)
            logger.info("Bypassing Gemini for pre-extracted JSON file: %s", file_path.name)
        except json.JSONDecodeError as exc:
            logger.error(
                "Could not parse pre-extracted JSON from %s: %s",
                file_path.name, exc,
            )
            return None
    else:
        if len(content) > MAX_CHARS_PER_DOCUMENT:
            content = content[:MAX_CHARS_PER_DOCUMENT]
            logger.info("Truncated %s to %d chars", file_path.name, MAX_CHARS_PER_DOCUMENT)

        user_prompt = (
            f"Source file: {file_path.name}\n"
            f"Source type: {source_type}\n"
            f"Document date: (extract from document if available)\n\n"
            f"Document content:\n{content}\n\n"
            f"Extract all rate benchmarks, brand signals, and contract clauses. "
            f"Return ONLY the JSON object. No markdown, no prose."
        )

        try:
            response_text = await gemini_client.send_text(
                system_message=EXTRACTION_SYSTEM_PROMPT,
                user_message=user_prompt,
                model=EXTRACTION_MODEL,
            )
        except Exception as exc:
            logger.error("Gemini call failed for %s: %s", file_path.name, exc)
            return None

        payload_text = _strip_code_fences(str(response_text))

        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            logger.error(
                "Could not parse JSON from %s response: %s\nRaw: %s",
                file_path.name, exc, payload_text[:500],
            )
            return None

    # Inject required source identity (model doesn't see source_file/source_type).
    payload["source_file"] = file_path.name
    payload["source_type"] = source_type
    payload.setdefault("rate_benchmarks", [])
    payload.setdefault("brand_signals", [])
    payload.setdefault("clauses", [])
    payload.setdefault("geographic_scope", "india")
    payload.setdefault("document_summary", "")
    payload["total_extractions"] = (
        len(payload.get("rate_benchmarks", []))
        + len(payload.get("brand_signals", []))
        + len(payload.get("clauses", []))
    )

    try:
        result = PublicDataExtraction.model_validate(payload)
    except Exception as exc:
        logger.error(
            "Schema validation failed for %s: %s\nPayload: %s",
            file_path.name, exc, json.dumps(payload)[:500],
        )
        return None

    logger.info(
        "Extracted from %s: %d rates, %d brands, %d clauses",
        file_path.name,
        len(result.rate_benchmarks),
        len(result.brand_signals),
        len(result.clauses),
    )
    return result


# ============================================================================
# Cross-validation (pure Python — no model calls, no numpy/pandas)
# ============================================================================


def compute_confidence_weight(corroboration_score: float) -> float:
    """Deterministic formula. Not a model call.

    corroboration_score = distinct_source_types_confirming / 3

    Range:
        0.33 (1 source type)  → confidence_weight: 0.55
        0.67 (2 source types) → confidence_weight: 0.70
        1.00 (3 source types) → confidence_weight: 0.85
    """
    return round(0.40 + (corroboration_score * 0.45), 2)


def cross_validate_benchmarks(
    all_extractions: List[PublicDataExtraction],
) -> List[dict]:
    """Group rate benchmarks by (niche, follower_tier, content_format).

    For each group:
      - Counts distinct source_type values
      - Computes corroboration_score and confidence_weight
      - Computes rate_p50 as confidence-weighted mean of rate_typicals
      - Falls back to multiplier-derived p25/p75 if explicit min/max absent
      - Detects outliers (>2 std deviations from mean)
      - Returns list of NicheGraphNode dicts ready for upsert
    """
    groups: dict = defaultdict(list)

    for extraction in all_extractions:
        for benchmark in extraction.rate_benchmarks:
            if not all(
                [benchmark.niche, benchmark.follower_tier, benchmark.content_format]
            ):
                continue
            if benchmark.extraction_confidence < 0.50:
                continue
            key = (
                benchmark.niche,
                benchmark.follower_tier,
                benchmark.content_format,
            )
            groups[key].append(
                {
                    "source_type": extraction.source_type,
                    "source_file": extraction.source_file,
                    "observation_period": benchmark.observation_period,
                    "rate_min": benchmark.rate_min,
                    "rate_max": benchmark.rate_max,
                    "rate_typical": benchmark.rate_typical,
                    "extraction_confidence": benchmark.extraction_confidence,
                    "source_quote": benchmark.source_quote,
                }
            )

    validated_nodes: List[dict] = []

    for (niche, follower_tier, content_format), entries in groups.items():
        distinct_source_types = set(e["source_type"] for e in entries)
        corroboration_score = round(min(len(distinct_source_types) / 3, 1.0), 3)
        confidence_weight = compute_confidence_weight(corroboration_score)

        typicals = [e["rate_typical"] for e in entries if e["rate_typical"]]
        mins = [e["rate_min"] for e in entries if e["rate_min"]]
        maxes = [e["rate_max"] for e in entries if e["rate_max"]]

        if not typicals and not mins and not maxes:
            continue

        if typicals:
            weights = [
                e["extraction_confidence"] for e in entries if e["rate_typical"]
            ]
            rate_p50 = round(
                sum(t * w for t, w in zip(typicals, weights)) / sum(weights), 0
            )
        else:
            rate_p50 = None

        if mins:
            rate_p25 = round(min(mins), 0)
        elif rate_p50:
            rate_p25 = round(rate_p50 * 0.68, 0)
        else:
            rate_p25 = None

        if maxes:
            rate_p75 = round(max(maxes), 0)
        elif rate_p50:
            rate_p75 = round(rate_p50 * 1.48, 0)
        else:
            rate_p75 = None

        # Outlier detection
        flagged = False
        outlier_reason: Optional[str] = None
        if len(typicals) > 2 and rate_p50:
            try:
                stddev = statistics.stdev(typicals)
                mean = statistics.mean(typicals)
                outliers = [t for t in typicals if abs(t - mean) > 2 * stddev]
                if outliers:
                    flagged = True
                    outlier_reason = (
                        f"Values {outliers} are >2σ from mean ₹{mean:.0f}"
                    )
            except statistics.StatisticsError:
                pass

        periods = [e["observation_period"] for e in entries if e["observation_period"]]
        observation_period = max(periods) if periods else "2024_annual"

        corroboration_sources = sorted({e["source_file"] for e in entries})

        # Pick a representative source_type and source_file for the node
        if len(distinct_source_types) == 1:
            source_type_value = next(iter(distinct_source_types))
        else:
            source_type_value = "industry_report"
        source_file_value = corroboration_sources[0] if corroboration_sources else "multiple"

        node = {
            "niche": niche,
            "follower_tier": follower_tier,
            "content_format": content_format,
            "geographic_scope": "india",
            "observation_period": observation_period,
            "rate_p25": rate_p25,
            "rate_p50": rate_p50,
            "rate_p75": rate_p75,
            "currency": "INR",
            "sample_size": 0,
            "creator_count_contributing": 0,
            "source_type": source_type_value,
            "source_file": source_file_value,
            "confidence_weight": confidence_weight,
            "corroboration_score": corroboration_score,
            "corroboration_sources": corroboration_sources,
            "data_source": "pre_training",
            "flagged_for_review": flagged,
            "outlier_reason": outlier_reason,
        }
        validated_nodes.append(node)

    return validated_nodes


# ============================================================================
# Writes
# ============================================================================


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _classification_block() -> dict:
    return {
        "tier": "aggregate",
        "deletion_policy": "retain_anonymised",
        "anonymisation_eligible": True,
        "export_eligible": True,
        "classified_at": _now().isoformat(),
    }


async def write_niche_graph_nodes(db, nodes: List[dict], dry_run: bool = False) -> int:
    """Upsert niche_graph documents.

    Upsert key: (niche, follower_tier, content_format, source_file).
    Idempotent — re-running produces identical output.
    """
    written = 0
    for node in nodes:
        if dry_run:
            logger.info(
                "[DRY RUN] niche_graph: %s / %s / %s  p50=₹%s  weight=%s",
                node["niche"],
                node["follower_tier"],
                node["content_format"],
                node["rate_p50"],
                node["confidence_weight"],
            )
            written += 1
            continue

        filter_key = {
            "niche": node["niche"],
            "follower_tier": node["follower_tier"],
            "content_format": node["content_format"],
            "source_file": node["source_file"],
        }
        update_doc = dict(node)
        update_doc["data_classification"] = _classification_block()
        update_doc["last_updated"] = _now().isoformat()
        update_doc["updated_at"] = _now().isoformat()

        await db.niche_graph.update_one(
            filter_key,
            {
                "$set": update_doc,
                "$setOnInsert": {"created_at": _now().isoformat()},
            },
            upsert=True,
        )
        written += 1

    return written


async def write_brand_signals(
    db,
    all_extractions: List[PublicDataExtraction],
    dry_run: bool = False,
) -> int:
    """Write brand signals to the `brands` collection (NOT niche_graph).

    Upsert key: brand_name (normalised to lowercase).
    Aggregates across all source documents.
    """
    brand_map: dict = defaultdict(list)
    for extraction in all_extractions:
        for signal in extraction.brand_signals:
            if signal.extraction_confidence < 0.50:
                continue
            key = signal.brand_name.lower().strip()
            brand_map[key].append(
                {
                    "source_file": extraction.source_file,
                    "source_type": extraction.source_type,
                    "signal": signal,
                }
            )

    written = 0
    for _brand_key, entries in brand_map.items():
        primary = entries[0]["signal"]
        all_niches = sorted(
            {niche for e in entries for niche in e["signal"].niche_targeted}
        )
        all_formats = sorted(
            {fmt for e in entries for fmt in e["signal"].content_formats_used}
        )
        corroboration_sources = sorted({e["source_file"] for e in entries})
        distinct_source_types = {e["source_type"] for e in entries}
        corroboration_score = round(
            min(len(distinct_source_types) / 3, 1.0), 3
        )
        confidence_weight = compute_confidence_weight(corroboration_score)

        brand_doc = {
            "name": primary.brand_name,
            "domain": primary.brand_domain or "",
            "category": primary.category,
            "niche_targeted": all_niches,
            "content_formats_used": all_formats,
            "campaign_activity_signal": True,
            "geographic_scope": primary.geographic_scope,
            "data_source": "pre_training",
            "corroboration_sources": corroboration_sources,
            "corroboration_score": corroboration_score,
            "confidence_weight": confidence_weight,
            "is_indian_brand": (primary.geographic_scope or "india").lower() == "india",
            "data_classification": {
                "tier": "anonymisable",
                "deletion_policy": "retain_anonymised",
                "anonymisation_eligible": True,
                "export_eligible": True,
                "classified_at": _now().isoformat(),
            },
            "updated_at": _now().isoformat(),
        }

        if dry_run:
            logger.info(
                "[DRY RUN] brands: %s / %s  weight=%s",
                primary.brand_name,
                primary.category,
                confidence_weight,
            )
            written += 1
            continue

        # Case-insensitive name match for the upsert key.
        await db.brands.update_one(
            {"name": {"$regex": f"^{re.escape(primary.brand_name)}$", "$options": "i"}},
            {
                "$set": brand_doc,
                "$setOnInsert": {"created_at": _now().isoformat()},
            },
            upsert=True,
        )
        written += 1

    return written


# ============================================================================
# File discovery
# ============================================================================


def _resolve_source_type(file_path: Path, folder_root: Path) -> Optional[str]:
    """Return the spec source_type for this file based on its parent folder."""
    try:
        relative = file_path.relative_to(folder_root)
    except ValueError:
        relative = file_path
    parts = [p.lower() for p in relative.parts]
    for folder_name, source_type in SOURCE_TYPE_FOLDER_MAP.items():
        if folder_name in parts:
            return source_type
    return None


def discover_files(folder_root: Path) -> List[Tuple[Path, str]]:
    """Walk the corpus folder and return (file, source_type) pairs."""
    files = [
        f
        for f in folder_root.rglob("*")
        if f.suffix.lower() in SUPPORTED_EXTENSIONS and f.is_file() and not f.name.startswith(".")
    ]
    result: List[Tuple[Path, str]] = []
    for f in files:
        source_type = _resolve_source_type(f, folder_root)
        if not source_type:
            logger.warning(
                "Cannot determine source_type for %s. "
                "Place it under one of: %s. Skipping.",
                f.name,
                ", ".join(sorted(SOURCE_TYPE_FOLDER_MAP.keys())),
            )
            continue
        result.append((f, source_type))
    return result


# ============================================================================
# Orchestrator
# ============================================================================


async def run_ingestion(
    folder_path: Path, dry_run: bool, niche_filter: Optional[str]
) -> int:
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in backend/.env")
        return 1

    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.DB_NAME]

    try:
        # ── Step 1: Discover files ──
        file_with_types = discover_files(folder_path)
        if not file_with_types:
            logger.error(
                "No supported files with determinable source_type found in %s. "
                "Expected subfolders: %s",
                folder_path,
                ", ".join(sorted(SOURCE_TYPE_FOLDER_MAP.keys())),
            )
            return 1
        logger.info("Found %d file(s) to process", len(file_with_types))

        # ── Step 2: Extract from each file (sequential; respects rate limits) ──
        all_extractions: List[PublicDataExtraction] = []
        for file_path, source_type in file_with_types:
            logger.info("Processing: %s [%s]", file_path.name, source_type)
            extraction = await extract_from_document(file_path, source_type, settings.GEMINI_API_KEY)
            if extraction:
                all_extractions.append(extraction)

        if not all_extractions:
            logger.error(
                "No successful extractions. Check your files and the GEMINI_API_KEY."
            )
            return 1

        total_benchmarks = sum(len(e.rate_benchmarks) for e in all_extractions)
        total_brands = sum(len(e.brand_signals) for e in all_extractions)
        total_clauses = sum(len(e.clauses) for e in all_extractions)
        logger.info(
            "Raw extractions: %d rates, %d brands, %d clauses",
            total_benchmarks, total_brands, total_clauses,
        )

        # ── Step 3: Cross-validate ──
        validated_nodes = cross_validate_benchmarks(all_extractions)
        if niche_filter:
            validated_nodes = [n for n in validated_nodes if n["niche"] == niche_filter]
        logger.info("After cross-validation: %d niche_graph nodes", len(validated_nodes))

        flagged = [n for n in validated_nodes if n["flagged_for_review"]]
        if flagged:
            logger.warning(
                "%d nodes flagged as outliers — review before launch:", len(flagged)
            )
            for n in flagged:
                logger.warning(
                    "  → %s/%s/%s: %s",
                    n["niche"], n["follower_tier"], n["content_format"],
                    n["outlier_reason"],
                )

        # ── Step 4: Write ──
        niche_written = await write_niche_graph_nodes(db, validated_nodes, dry_run)
        brand_written = await write_brand_signals(db, all_extractions, dry_run)

        logger.info("=" * 60)
        logger.info(
            "CORPUS INGESTION COMPLETE %s", "[DRY RUN]" if dry_run else ""
        )
        logger.info("  niche_graph documents written/updated: %d", niche_written)
        logger.info("  brands documents written/updated: %d", brand_written)
        logger.info("  Outlier nodes for review: %d", len(flagged))
        if dry_run:
            logger.info("  DRY RUN — no data was written to MongoDB")
        logger.info("=" * 60)
        return 0
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ThreadComb Corpus Ingestion Pipeline"
    )
    parser.add_argument(
        "--folder", required=True, help="Path to corpus data folder"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and validate but do not write to MongoDB",
    )
    parser.add_argument(
        "--niche",
        help="Filter to specific niche (optional): beauty, gaming, etc.",
    )
    args = parser.parse_args()

    folder_path = Path(args.folder).resolve()
    if not folder_path.exists():
        print(f"ERROR: Folder not found: {folder_path}")
        return 1

    return asyncio.run(run_ingestion(folder_path, args.dry_run, args.niche))


if __name__ == "__main__":
    sys.exit(main())
