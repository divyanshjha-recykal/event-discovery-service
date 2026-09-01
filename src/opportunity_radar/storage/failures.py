"""Extraction failures, persisted.

A third collection, which CLAUDE.md's data schemas do not define. It exists
because Stage 5 requires "extraction success/failure counts, reading directly
from Mongo" — and failures previously lived only in a run's memory, so the
metrics view had no way to see them. Successes are the `opportunities`
collection; this is the other half of that ratio.

Keyed on `source_url`, so a page that fails repeatedly stays one document with
an attempt count rather than growing without bound.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

EXTRACTION_FAILURES = "extraction_failures"


async def ensure_failure_indexes(db: AsyncDatabase) -> None:
    await db[EXTRACTION_FAILURES].create_index(
        [("source_url", 1)], unique=True, name="failure_source_url"
    )


async def record_extraction_failure(
    db: AsyncDatabase,
    source_url: str,
    reason: str,
    detail: str,
    model: str | None = None,
    trace_url: str | None = None,
) -> dict:
    """Upsert one failed extraction. Repeat failures increment `attempts`."""
    now = datetime.now(timezone.utc)
    return await db[EXTRACTION_FAILURES].find_one_and_update(
        {"source_url": source_url},
        {
            "$set": {
                "reason": reason,
                "detail": detail,
                "model": model,
                "trace_url": trace_url,
                "last_seen": now,
            },
            "$setOnInsert": {"source_url": source_url, "first_seen": now},
            "$inc": {"attempts": 1},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


async def clear_extraction_failure(db: AsyncDatabase, source_url: str) -> None:
    """Drop a failure record once that URL later extracts successfully.

    Without this a URL that failed then succeeded would count as both, making
    Stage 5's success/failure ratio wrong — the same bug already fixed for the
    in-run failure list.
    """
    await db[EXTRACTION_FAILURES].delete_many({"source_url": source_url})


async def failure_counts(db: AsyncDatabase) -> dict[str, int]:
    """Failures grouped by typed reason, for the metrics view."""
    counts: dict[str, int] = {}
    async for doc in db[EXTRACTION_FAILURES].find({}, {"reason": 1, "_id": 0}):
        reason = doc.get("reason", "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts
