"""Discovery runs and their journey, persisted.

Stage 5 has to show "the actual agent journey" — what was searched, which
results were shortlisted, what got extracted, what was saved — to people who
will not be reading a Langfuse trace. That story currently exists only in a
run's memory and in terminal output, so it has to be written down.

Deliberately NOT a duplicate of Langfuse. This stores the decisions and their
outcomes, at one row per tool call; Langfuse keeps the full prompts, responses,
token counts and timings. Each run and each failure carries its Langfuse trace
URL, so the UI can hand off to the trace for the detail rather than restating it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

RUNS = "runs"


async def ensure_run_indexes(db: AsyncDatabase) -> None:
    await db[RUNS].create_index([("run_id", 1)], unique=True, name="run_id")
    await db[RUNS].create_index([("started_at", -1)], name="run_started_at")


async def start_run(
    db: AsyncDatabase, run_id: str, model: str, budget: dict, queries: list[str] | None
) -> dict:
    """Record a run as in-progress so the UI can show it live."""
    return await db[RUNS].find_one_and_update(
        {"run_id": run_id},
        {
            "$set": {
                "run_id": run_id,
                "model": model,
                "status": "running",
                "started_at": datetime.now(timezone.utc),
                "finished_at": None,
                "budget": budget,
                "queries": queries or [],
                "journey": [],
                "thinking": [],
                "summary": "",
                "trace_url": None,
                "counts": {"searched": 0, "scraped": 0, "extracted": 0,
                           "saved": 0, "failed": 0},
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


async def append_event(db: AsyncDatabase, run_id: str, event: dict[str, Any]) -> None:
    """Append one tool call to the journey, as it happens.

    Written during the run rather than at the end so a run that crashes still
    leaves a readable trail of how far it got.
    """
    await db[RUNS].update_one({"run_id": run_id}, {"$push": {"journey": event}})


async def finish_run(
    db: AsyncDatabase,
    run_id: str,
    status: str,
    summary: str,
    trace_url: str | None,
    budget: dict,
    counts: dict,
    thinking: list[str],
) -> dict | None:
    return await db[RUNS].find_one_and_update(
        {"run_id": run_id},
        {
            "$set": {
                "status": status,
                "finished_at": datetime.now(timezone.utc),
                "summary": summary,
                "trace_url": trace_url,
                "budget": budget,
                "counts": counts,
                "thinking": thinking,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


async def get_run(db: AsyncDatabase, run_id: str) -> dict | None:
    return await db[RUNS].find_one({"run_id": run_id}, {"_id": 0})


async def list_runs(db: AsyncDatabase, limit: int = 20) -> list[dict]:
    cursor = db[RUNS].find({}, {"_id": 0, "journey": 0}).sort("started_at", -1).limit(limit)
    return [doc async for doc in cursor]
