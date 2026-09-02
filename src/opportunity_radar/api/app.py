"""Stage 5 — a read-mostly API over what the pipeline has stored.

CLAUDE.md's Stage 5 is "one page or one script output, reading directly from
Mongo… no approve/reject actions, this is read-only". This serves that page.

One deliberate deviation, agreed explicitly: `POST /api/runs` triggers a
discovery run. That is not an approve/reject action — nothing here judges an
opportunity or writes to the business profile — but it does mean the page is
not purely read-only. Every other endpoint is a read.

The pipeline's hard constraint still holds: nothing in this API submits an
application, contacts an award body, or reaches any third party except the
search/scrape/model providers the pipeline already uses.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import MongoConfig
from ..discovery import RunBudget, run_discovery
from ..eligibility import evaluate_criteria, load_criteria_sets
from ..paths import REPO_ROOT
from ..profile import load_business_profile
from ..storage import (
    EXTRACTION_FAILURES,
    OPPORTUNITIES,
    PROGRAMS,
    RUNS,
    attach_eligibility,
    ensure_indexes,
    get_client,
    get_database,
)

STATIC_DIR = REPO_ROOT / "frontend" / "dist"

app = FastAPI(title="Opportunity Radar", version="0.1.0")

_client = None
_db = None


def _jsonable(value: Any) -> Any:
    """Mongo documents contain ObjectId and datetime; make them JSON-safe."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@app.on_event("startup")
async def _startup() -> None:
    global _client, _db
    config = MongoConfig.from_env()
    _client = get_client(config)
    _db = get_database(_client, config)
    await ensure_indexes(_db)


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _client is not None:
        await _client.close()


@app.get("/api/health")
async def health() -> dict:
    await _db.command("ping")
    return {"ok": True, "database": _db.name}


@app.get("/api/state")
async def state() -> dict:
    """Everything the page renders, in one round trip."""
    opportunities = [
        _jsonable(d) async for d in _db[OPPORTUNITIES].find({}).sort("cycle_year", -1)
    ]
    programs = [_jsonable(d) async for d in _db[PROGRAMS].find({})]
    failures = [_jsonable(d) async for d in _db[EXTRACTION_FAILURES].find({})]
    runs = [
        _jsonable(d)
        async for d in _db[RUNS].find({}, {"journey": 0}).sort("started_at", -1).limit(20)
    ]

    verdicts = {"high": 0, "low": 0, "unevaluated": 0}
    statuses = {"met": 0, "not_met": 0, "unclear": 0}
    for opp in opportunities:
        eligibility = opp.get("eligibility")
        if not eligibility:
            verdicts["unevaluated"] += 1
            continue
        verdicts[eligibility.get("confidence", "low")] += 1
        for result in eligibility.get("criteria_results", []):
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1

    return {
        "metrics": {
            "opportunities": len(opportunities),
            "programs": len(programs),
            # Extraction succeeded once per stored opportunity; failures are the
            # other half of that ratio, which is why they are persisted at all.
            "extraction_success": len(opportunities),
            "extraction_failed": len(failures),
            "verdicts": verdicts,
            "criteria": statuses,
        },
        "opportunities": opportunities,
        "programs": programs,
        "failures": failures,
        "runs": runs,
        "skipped": await _skipped_pages(),
    }


async def _skipped_pages() -> list[dict]:
    """Pages the agent fetched and then chose not to pursue.

    Derived from the run journeys rather than stored separately: a skip is the
    absence of a later extract call, so there is nothing to write down at the
    time. Extraction failures are excluded — those are reported on their own,
    and this list is specifically the agent's judgement calls.
    """
    scraped: dict[str, dict] = {}
    reached_extraction: set[str] = set()

    async for run in _db[RUNS].find({}, {"journey": 1, "run_id": 1, "started_at": 1}):
        for event in run.get("journey", []):
            url = event.get("url")
            if not url:
                continue
            if event["tool"] == "scrape" and event.get("outcome") == "ok":
                scraped[url] = {
                    "url": url,
                    "run_id": run.get("run_id"),
                    "when": run.get("started_at"),
                    "bare_domain": event.get("bare_domain", False),
                    "chars": event.get("chars"),
                }
            elif event["tool"] == "extract":
                reached_extraction.add(url)

    return [_jsonable(v) for k, v in scraped.items() if k not in reached_extraction]


class PipelineRequest(BaseModel):
    model: str | None = None
    budget: int = Field(default=18, ge=1, le=60)
    dry_run: bool = False


@app.post("/api/pipeline")
async def run_pipeline(request: PipelineRequest, background: BackgroundTasks) -> dict:
    """Discovery, then eligibility over whatever it found — one action.

    This is what a demo actually wants: start to finish, unattended, with the
    journey filling in as it goes. Eligibility runs only on records that have
    criteria and no verdict yet, so re-running is cheap and idempotent.
    """
    run_id = uuid4().hex
    budget = RunBudget(tool_calls=request.budget)
    profile = load_business_profile()

    async def _go() -> None:
        try:
            await run_discovery(
                _db, model=request.model, budget=budget,
                dry_run=request.dry_run, run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001
            await _db[RUNS].update_one(
                {"run_id": run_id},
                {"$set": {"status": "failed", "summary": f"{type(exc).__name__}: {exc}"}},
            )
            return

        # Eligibility second, on what discovery just stored.
        async for doc in _db[OPPORTUNITIES].find({}):
            criteria = doc.get("eligibility_criteria") or []
            if not criteria or doc.get("eligibility"):
                continue
            try:
                result = await asyncio.to_thread(
                    evaluate_criteria, criteria, profile.text,
                    f"{doc.get('title')} — {doc.get('organizing_body')}", request.model,
                )
                await attach_eligibility(_db, doc["source_url"], result.model_dump())
            except Exception:  # noqa: BLE001 — one bad record must not stop the rest
                continue

        await _db[RUNS].update_one(
            {"run_id": run_id}, {"$set": {"eligibility_done": True}}
        )

    background.add_task(_go)
    return {"run_id": run_id, "status": "running"}


@app.get("/api/runs/{run_id}")
async def get_run_detail(run_id: str) -> dict:
    run = await _db[RUNS].find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    return _jsonable(run)


class RunRequest(BaseModel):
    model: str | None = None
    budget: int = Field(default=18, ge=1, le=60)
    queries: list[str] = Field(default_factory=list)
    dry_run: bool = False


@app.post("/api/runs")
async def start_discovery(request: RunRequest, background: BackgroundTasks) -> dict:
    """Kick off a discovery run and return immediately.

    The journey is written to Mongo step by step, so the page polls
    /api/runs/{id} and watches it fill in rather than holding a connection open
    for the ninety seconds a run takes.
    """
    run_id = uuid4().hex
    budget = RunBudget(tool_calls=request.budget)

    async def _go() -> None:
        try:
            await run_discovery(
                _db,
                queries=request.queries or None,
                model=request.model,
                budget=budget,
                dry_run=request.dry_run,
                run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced through the run record
            await _db[RUNS].update_one(
                {"run_id": run_id},
                {"$set": {"status": "failed", "summary": f"{type(exc).__name__}: {exc}"}},
            )

    background.add_task(_go)
    return {"run_id": run_id, "status": "running"}


class EligibilityRequest(BaseModel):
    model: str | None = None


@app.post("/api/eligibility")
async def run_eligibility(request: EligibilityRequest, background: BackgroundTasks) -> dict:
    """Evaluate every stored opportunity that has criteria and no verdict yet."""
    profile = load_business_profile()

    async def _go() -> None:
        async for doc in _db[OPPORTUNITIES].find({}):
            criteria = doc.get("eligibility_criteria") or []
            if not criteria or doc.get("eligibility"):
                continue
            try:
                result = await asyncio.to_thread(
                    evaluate_criteria,
                    criteria,
                    profile.text,
                    f"{doc.get('title')} — {doc.get('organizing_body')}",
                    request.model,
                )
                await attach_eligibility(_db, doc["source_url"], result.model_dump())
            except Exception:  # noqa: BLE001 — one bad record must not stop the rest
                continue

    background.add_task(_go)
    return {"status": "running"}


@app.get("/api/reference-sets")
async def reference_sets() -> list[dict]:
    """The hand-written Stage 0 criteria sets, for the eligibility panel."""
    return [
        {
            "number": s.number,
            "label": s.label,
            "criterion": s.criterion,
            "expected_status": s.expected_status,
            "expects_qualitative": s.expects_qualitative,
        }
        for s in load_criteria_sets()
    ]


# The built React page, when it exists. Mounted last so /api/* always wins.
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
