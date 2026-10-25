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
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from ..config import MongoConfig
from ..discovery import RunBudget, TraversalLimits, run_discovery
from ..discovery.budget import (
    DEFAULT_MAX_LLM_CALLS,
    DEFAULT_MAX_SCRAPES,
    DEFAULT_MAX_SEARCHES,
    DEFAULT_TOOL_CALLS,
    DEFAULT_WALL_CLOCK_SECONDS,
)
from ..discovery import competitor_watch as cw
from ..discovery import component_watch as cmw
from ..eligibility import evaluate_criteria
from ..paths import REPO_ROOT
from ..profile import load_business_profile
from ..product_profile import ProductProfileError, load_product_profile, machines
from ..reporting import components_email, configured_recipients, opportunities_email, send_mail, signals_email
from ..storage import (
    DEAD_ENDS,
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
        # PyMongo hands back naive datetimes even though Mongo stores UTC, and
        # `new Date("...T12:51:22")` with no offset is parsed as LOCAL time —
        # so an IST viewer saw every run 5h30m early. Mark it as UTC and let
        # the browser convert.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
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
    # Runs live inside this process, so any run still marked running died with the last one.
    await _db[RUNS].update_many(
        {"status": "running"},
        {"$set": {"status": "failed", "summary": "server restarted during the run"}},
    )


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
    latest_counts = runs[0].get("counts", {}) if runs else {}

    verdicts = {"high": 0, "low": 0, "unevaluated": 0}
    statuses = {"met": 0, "not_met": 0, "unclear": 0}
    for opp in opportunities:
        eligibility = opp.get("eligibility")
        if opp.get("fit"):
            continue
        if not eligibility:
            verdicts["unevaluated"] += 1
            continue
        verdicts[eligibility.get("confidence", "low")] += 1
        for result in eligibility.get("criteria_results", []):
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1

    latest_run_id = runs[0].get("run_id") if runs else None
    for opp in opportunities:
        opp["from_latest_run"] = (
            latest_run_id is not None
            and opp.get("discovery_run_id") == latest_run_id
        )

    return {
        "latest_run_id": latest_run_id,
        "metrics": {
            "opportunities": len(opportunities),
            "programs": len(programs),
            "extraction_success": latest_counts.get("extracted", 0),
            "extraction_failed": latest_counts.get("extraction_failed", 0),
            "verdicts": verdicts,
            "criteria": statuses,
        },
        "opportunities": opportunities,
        "programs": programs,
        "failures": failures,
        "runs": runs,
    }


def _read_journey(journey: list[dict]) -> dict[str, list[dict]]:
    """Split one run's journey into what it saved, set aside, and failed on.

    Derived from the journey rather than from `discovery_run_id`, which is a
    single field on an upserted record: when a later run re-finds the same
    opportunity that field is overwritten, and an earlier run's page would
    silently lose the thing it found. A journey is immutable once written.
    """
    saved: list[str] = []
    set_aside: list[dict] = []
    failures: list[dict] = []
    scraped: dict[str, dict] = {}
    unreachable: dict[str, dict] = {}
    reached_extraction: set[str] = set()

    for event in journey:
        url, tool, outcome = event.get("url"), event.get("tool"), event.get("outcome")

        # Skips are decided by `analyze` and carried on its candidate list, not
        # as rows of their own.
        if tool == "analyze":
            reached_extraction.add(url)
            if not event.get("candidates"):
                set_aside.append({
                    "url": url,
                    "title": None,
                    "outcome": "not relevant",
                    "reason": "no opportunity identified on this site",
                })
            for candidate in event.get("candidates") or []:
                if candidate.get("decision") == "skip" and candidate.get("url"):
                    set_aside.append({
                        "url": candidate["url"],
                        "title": candidate.get("title"),
                        "outcome": "not relevant",
                        "reason": candidate.get("reason") or "not taken forward",
                    })
            continue

        if not url:
            continue
        if tool == "save_opportunity" and outcome == "ok":
            saved.append(url)
        elif tool == "scrape" and outcome == "ok":
            # Followed pages are evidence for their site, not candidates.
            if not event.get("depth"):
                scraped[url] = event
            unreachable.pop(url, None)
        elif tool == "scrape":
            # A page that would not load is a gap in the evidence, not a
            # judgement about the programme. It has to stay visible.
            unreachable.setdefault(url, event)
        elif tool == "extract":
            reached_extraction.add(url)
            if outcome == "failed":
                failures.append({
                    "url": url,
                    "title": event.get("title"),
                    "reason": event.get("reason") or "extraction failed",
                    "detail": event.get("detail"),
                })
        elif tool == "expired":
            set_aside.append({
                "url": url,
                "title": event.get("title"),
                "outcome": "already closed",
                "reason": "dates verified on the page have passed: deadline "
                          f"{event.get('entry_deadline') or '-'}, event {event.get('event_date') or '-'}",
            })
        elif tool == "dedupe":
            set_aside.append({
                "url": url,
                "title": event.get("title"),
                "outcome": "duplicate",
                "reason": f"same page as {event.get('duplicate_of')}",
            })
        elif tool in ("skip", "actionability"):
            set_aside.append({
                "url": url,
                "title": event.get("title"),
                "outcome": outcome or "not relevant",
                "reason": event.get("reason") or "not taken forward",
            })

    decided = {row["url"] for row in set_aside} | reached_extraction

    for url, event in unreachable.items():
        if url in decided:
            continue
        set_aside.append({
            "url": url,
            "title": None,
            "outcome": "could not fetch",
            "reason": event.get("detail") or (
                "the page returned too little content to use — usually a bot block, "
                "an error page or a redirect"
                if event.get("outcome") == "insufficient"
                else "the fetch failed"
            ),
        })

    # A page fetched but never analysed into a candidate — no explicit decision
    # was ever recorded for it, so it would otherwise vanish from the account.
    for url, event in scraped.items():
        if url not in decided:
            set_aside.append({
                "url": url,
                "title": None,
                "outcome": "not pursued",
                "reason": (
                    f"fetched ({event.get('chars')} chars) but never became a candidate"
                ),
            })

    unique = {(row["url"], row["title"]): row for row in reversed(set_aside)}
    set_aside = [row for row in set_aside if unique[(row["url"], row["title"])] is row]
    return {"saved": saved, "set_aside": set_aside, "failures": failures}


# Far above any reachable journey length (budget caps at 200 tool calls), so a
# poll never silently truncates.
_EVENT_PAGE = 2_000


@app.get("/api/runs/{run_id}/events")
async def get_run_events(run_id: str, after: int = 0) -> dict:
    """Run metadata plus only the journey rows after `after`.

    The whole-document poll this replaces re-sent every search snippet every
    1.5 seconds — about 6 MB over a 90-second run, growing with journey length.
    Journey rows are append-only and `seq` is their 1-based position, so a
    positional slice is exactly "everything newer than what the client holds".
    """
    doc = await _db[RUNS].find_one(
        {"run_id": run_id},
        {
            "_id": 0,
            "journey": {"$slice": [max(after, 0), _EVENT_PAGE]},
            "run_id": 1, "model": 1, "status": 1, "started_at": 1, "finished_at": 1,
            "budget": 1, "counts": 1, "summary": 1, "trace_url": 1, "thinking": 1,
            "queries": 1, "warnings": 1, "failures": 1,
            "eligibility_done": 1, "eligibility_evaluated": 1, "eligibility_failures": 1,
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")

    events = doc.pop("journey", None) or []
    return {**_jsonable(doc), "events": [_jsonable(e) for e in events]}


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str) -> dict:
    """Remove one run's record and its journey.

    Deliberately does not touch `opportunities` or `programs`: a record is
    upserted on its own identity and may have been confirmed by later runs, so
    deleting a run must not delete findings that outlived it. Component findings
    belong to one run only, so they go with it.
    """
    if run_id in _ACTIVE:
        raise HTTPException(
            status_code=409,
            detail="that run is still in flight — stop it before deleting it",
        )
    result = await _db[RUNS].delete_one({"run_id": run_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    offers = await _db[cmw.OFFERS].delete_many({"run_id": run_id})
    # A competitor run's pages count as seen only while the run exists, so a redo reads them again.
    seen = await _db[cw.SEEN].delete_many({"run_id": run_id})
    signals = await _db[cw.SIGNALS].delete_many({"run_id": run_id})
    return {"run_id": run_id, "deleted": True, "component_findings_deleted": offers.deleted_count,
            "competitor_pages_deleted": seen.deleted_count, "competitor_signals_deleted": signals.deleted_count}


@app.get("/api/runs/{run_id}/results")
async def get_run_results(run_id: str) -> dict:
    """What one run actually produced, scoped to that run alone."""
    run = await _db[RUNS].find_one({"run_id": run_id}, {"journey": 1})
    if not run:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")

    read = _read_journey(run.get("journey") or [])
    ordered = list(dict.fromkeys(read["saved"]))

    # Keyed by identity, not by source_url. One page often carries several
    # award tracks, each its own record on the same URL — keying by URL let
    # siblings overwrite each other, so a run that stored three tracks showed
    # one. Identity is `organizing_body + base_title + cycle_year`.
    saved: list[dict] = []
    seen_urls: set[str] = set()
    if ordered:
        # Only this run's own writes: an older record on the same page is not this run's result.
        async for doc in _db[OPPORTUNITIES].find(
            {"source_url": {"$in": ordered}, "discovery_run_id": run_id}
        ):
            saved.append(_jsonable(doc))
            seen_urls.add(doc["source_url"])

    saved.sort(key=lambda d: (ordered.index(d["source_url"]), d.get("title") or ""))
    # Why extract pursued each record lives in the journey, so older runs show it too.
    reasons = {
        (c.get("url"), (c.get("title") or "").strip().casefold()): c.get("reason")
        for e in run.get("journey") or [] if e.get("tool") == "analyze"
        for c in e.get("candidates") or [] if c.get("decision") == "pursue"
    }
    for doc in saved:
        doc["why_pursued"] = reasons.get(
            (doc.get("source_url"), (doc.get("title") or "").strip().casefold())
        )

    return {
        "run_id": run_id,
        "saved": saved,
        # Saved by this run but no longer in storage — the database was cleared
        # after the run. Reported rather than silently dropped.
        "missing": [url for url in ordered if url not in seen_urls],
        "set_aside": read["set_aside"],
        "failures": read["failures"],
        # The authoritative tallies, so the header and the tabs cannot disagree.
        "totals": {
            "ready": sum(1 for d in saved if d.get("record_state") != "needs_deeper_read"),
            "needs_deeper": sum(
                1 for d in saved if d.get("record_state") == "needs_deeper_read"
            ),
            "set_aside": len(read["set_aside"]) + len(read["failures"]),
        },
    }


@app.get("/api/mail")
async def mail_settings() -> dict:
    """Where a report would go. Recipients come from SMTP_TO only."""
    return {"to": configured_recipients()}


async def _run_email(run_id: str) -> dict:
    """The email for one run: its digest for a competitor run, its opportunities otherwise."""
    run = await _db[RUNS].find_one({"run_id": run_id}, {"run_id": 1, "counts": 1, "budget": 1})
    if not run:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    focus = (run.get("budget") or {}).get("focus")
    if focus == cw.FOCUS:
        return signals_email(await cw.run_digest(_db, run_id), run)
    if focus == cmw.FOCUS:
        try:
            return components_email(await cmw.run_offers(_db, run_id), run)
        except cmw.OutdatedRunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    rows = (await get_run_results(run_id))["saved"]
    if not rows:
        raise HTTPException(status_code=400, detail="this run saved no opportunities")
    return opportunities_email(rows, run_id)


@app.get("/api/runs/{run_id}/email")
async def preview_run_email(run_id: str) -> dict:
    """Exactly what the email for this run would contain, and who it would go to."""
    mail = await _run_email(run_id)
    return {"to": configured_recipients(), "subject": mail["subject"], "html": mail["html"],
            "csv": mail["csv"].decode("utf-8-sig"), "filename": mail["filename"], "count": mail["count"]}


@app.post("/api/runs/{run_id}/email")
async def email_run(run_id: str) -> dict:
    """Mail one run's email (readable body, CSV attached) to the SMTP_TO recipients."""
    to = configured_recipients()
    if not to:
        raise HTTPException(status_code=400, detail="SMTP_TO is not set in .env")
    mail = await _run_email(run_id)
    try:
        await asyncio.to_thread(send_mail, to, mail)
    except Exception as exc:  # noqa: BLE001 — shown to the user as-is
        raise HTTPException(
            status_code=502, detail=f"{type(exc).__name__}: {exc}"[:500]
        ) from exc
    return {"sent_to": to, "count": mail["count"]}


# Budgets of runs currently in flight, so /stop can cancel one. A cancelled
# budget refuses every paid tool but still allows saves.
_ACTIVE: dict[str, RunBudget] = {}


@app.post("/api/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict:
    """Cancel a run in flight. Work already paid for still reaches storage."""
    budget = _ACTIVE.get(run_id)
    if budget is None:
        raise HTTPException(status_code=404, detail=f"no active run {run_id}")
    budget.cancel("stopped from the dashboard")
    return {"run_id": run_id, "status": "stopping"}


_LIMITS = TraversalLimits()


class RunConfig(BaseModel):
    """Everything the configurator sets. Each cap maps to a `RunBudget` field.

    All five were previously fixed at their defaults because only `tool_calls`
    was passed through, so `max_llm_calls` silently capped every run at 16
    however high the headline budget was set.
    """

    # Defaults come from RunBudget, never copies of it. Held separately, the
    # API kept a frontend run on the old caps after they were raised here.
    model: str | None = None
    budget: int = Field(default=DEFAULT_TOOL_CALLS, ge=1, le=200)
    max_searches: int = Field(default=DEFAULT_MAX_SEARCHES, ge=1, le=60)
    max_scrapes: int = Field(default=DEFAULT_MAX_SCRAPES, ge=1, le=60)
    max_llm_calls: int = Field(default=DEFAULT_MAX_LLM_CALLS, ge=1, le=60)
    wall_clock_seconds: int = Field(
        default=DEFAULT_WALL_CLOCK_SECONDS, ge=30, le=3600
    )
    # How far research reaches. `max_depth` was inert until the traversal bug
    # was fixed: link choice never ran below the seed whatever it was set to.
    max_candidates: int = Field(default=_LIMITS.max_candidates, ge=1, le=12)
    max_links_per_page: int = Field(
        default=_LIMITS.max_links_per_page, ge=0, le=6
    )
    max_pages_per_seed: int = Field(
        default=_LIMITS.max_pages_per_seed, ge=1, le=10
    )
    max_depth: int = Field(default=_LIMITS.max_depth, ge=0, le=3)
    # What this run is looking for. Steers the planner and site selection;
    # nothing in code filters on it, so a focused run that meets a great
    # opportunity of another kind still keeps it.
    focus: Literal["any", "award", "event", "research"] = "any"
    search_provider: Literal["exa", "tavily"] = "exa"
    queries: list[str] = Field(default_factory=list)
    dry_run: bool = False

    @field_validator("model")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """An empty model box means "use OPENROUTER_MODEL", not a model named ''."""
        return (value or "").strip() or None

    @field_validator("queries")
    @classmethod
    def _drop_blank_queries(cls, value: list[str]) -> list[str]:
        return [q.strip() for q in value if q and q.strip()]

    def to_limits(self) -> TraversalLimits:
        return TraversalLimits(
            max_candidates=self.max_candidates,
            max_links_per_page=self.max_links_per_page,
            max_pages_per_seed=self.max_pages_per_seed,
            max_depth=self.max_depth,
        )

    def to_budget(self) -> RunBudget:
        return RunBudget(
            tool_calls=self.budget,
            max_searches=self.max_searches,
            max_scrapes=self.max_scrapes,
            max_llm_calls=self.max_llm_calls,
            wall_clock_seconds=self.wall_clock_seconds,
        )


PipelineRequest = RunConfig


@app.post("/api/pipeline")
async def run_pipeline(request: PipelineRequest, background: BackgroundTasks) -> dict:
    """Discovery, then eligibility over whatever it found — one action.

    This is what a demo actually wants: start to finish, unattended, with the
    journey filling in as it goes. Eligibility runs only on records that have
    criteria and no verdict yet, so re-running is cheap and idempotent.
    """
    run_id = uuid4().hex
    budget = request.to_budget()
    limits = request.to_limits()
    profile = load_business_profile()

    async def _go() -> None:
        _ACTIVE[run_id] = budget
        try:
            discovery = await run_discovery(
                _db, queries=request.queries or None,
                model=request.model, budget=budget, limits=limits,
                dry_run=request.dry_run, run_id=run_id, focus=request.focus,
                search_provider=request.search_provider,
            )
        except Exception as exc:  # noqa: BLE001
            await _db[RUNS].update_one(
                {"run_id": run_id},
                {"$set": {"status": "failed", "summary": f"{type(exc).__name__}: {exc}"}},
            )
            _ACTIVE.pop(run_id, None)
            return

        # Feasibility now runs inside the graph, in finalize, per record. It
        # used to run here — after the graph had returned — so a run reported
        # "succeeded" before anything had been judged and a failure never
        # appeared in the journey.
        await _db[RUNS].update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "eligibility_done": True,
                    "eligibility_evaluated": len(discovery.saved),
                    "eligibility_failures": [],
                }
            },
        )
        _ACTIVE.pop(run_id, None)

    background.add_task(_go)
    return {"run_id": run_id, "status": "running"}


@app.get("/api/runs/{run_id}")
async def get_run_detail(run_id: str) -> dict:
    run = await _db[RUNS].find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    return _jsonable(run)


RunRequest = RunConfig


class CompetitorRunRequest(BaseModel):
    """Only the model matters to a competitor run; other sidebar settings are ignored."""

    model: str | None = None


@app.post("/api/competitors/runs")
async def start_competitor_watch(request: CompetitorRunRequest, background: BackgroundTasks) -> dict:
    """Trigger one competitor-watch run; the list is checked first so a bad sheet fails here, not mid-run."""
    try:
        cw.load_competitors()
    except cw.CompetitorListError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_id = uuid4().hex
    budget = RunBudget(tool_calls=80, max_searches=40, max_llm_calls=15)

    async def _go() -> None:
        _ACTIVE[run_id] = budget
        try:
            await cw.run_competitor_watch(_db, model=request.model or None, run_id=run_id, budget=budget)
        finally:
            _ACTIVE.pop(run_id, None)

    background.add_task(_go)
    return {"run_id": run_id, "status": "running"}


class ComponentRunRequest(BaseModel):
    """Which product's parts to check, and with which model."""

    product: str = "ace"
    model: str | None = None
    only: list[str] | None = None
    #: "priority": the parts that make up 80% of off-the-shelf spend (weekly); "all": every part.
    scope: Literal["priority", "all"] = "priority"


@app.post("/api/components/runs")
async def start_component_watch(request: ComponentRunRequest, background: BackgroundTasks) -> dict:
    """Trigger one component-watch run; the workbook is checked first so a bad sheet fails here, not mid-run."""
    try:
        load_product_profile(request.product)
    except ProductProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_id = uuid4().hex
    budget = RunBudget(tool_calls=240, max_searches=150, max_llm_calls=80)

    async def _go() -> None:
        _ACTIVE[run_id] = budget
        try:
            await cmw.run_component_watch(_db, request.product, model=request.model or None, run_id=run_id,
                                          budget=budget, only=request.only or None, scope=request.scope)
        finally:
            _ACTIVE.pop(run_id, None)

    background.add_task(_go)
    return {"run_id": run_id, "status": "running"}


@app.get("/api/components/machines")
async def list_machines() -> dict:
    """The product line, and which machines have a product workbook to run on."""
    try:
        return {"machines": machines()}
    except ProductProfileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class OfferCheck(BaseModel):
    """Procurement's verdict on one finding after asking the seller."""

    check: Literal["holds", "does not hold", ""]
    note: str = ""


@app.patch("/api/components/offers/{offer_id}")
async def check_offer(offer_id: str, body: OfferCheck) -> dict:
    """Record whether a finding held up when procurement asked the seller (same part, that price, in stock)."""
    try:
        return await cmw.record_check(_db, offer_id, body.check, body.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"no finding {offer_id}") from exc


@app.get("/api/runs/{run_id}/components")
async def get_run_components(run_id: str) -> dict:
    """A component run's findings by part, plus custom parts and parts with nothing found."""
    try:
        return _jsonable(await cmw.run_offers(_db, run_id))
    except cmw.OutdatedRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/signals")
async def get_run_signals(run_id: str) -> dict:
    """A competitor run's signals by section, most important first, then earlier stories it updated."""
    return {"sections": _jsonable(await cw.run_digest(_db, run_id))}


@app.post("/api/runs")
async def start_discovery(request: RunRequest, background: BackgroundTasks) -> dict:
    """Kick off a discovery run and return immediately.

    The journey is written to Mongo step by step, so the page polls
    /api/runs/{id} and watches it fill in rather than holding a connection open
    for the ninety seconds a run takes.
    """
    run_id = uuid4().hex
    budget = request.to_budget()
    limits = request.to_limits()

    async def _go() -> None:
        _ACTIVE[run_id] = budget
        try:
            await run_discovery(
                _db,
                queries=request.queries or None,
                model=request.model,
                budget=budget,
                limits=limits,
                dry_run=request.dry_run,
                run_id=run_id,
                focus=request.focus,
                search_provider=request.search_provider,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced through the run record
            await _db[RUNS].update_one(
                {"run_id": run_id},
                {"$set": {"status": "failed", "summary": f"{type(exc).__name__}: {exc}"}},
            )
        finally:
            _ACTIVE.pop(run_id, None)

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
            # shortcut: research venues are judged for fit only during a run; a failed fit is not retried here.
            if not criteria or doc.get("eligibility") or doc.get("category") == "research":
                continue
            try:
                result = await asyncio.to_thread(
                    evaluate_criteria,
                    criteria,
                    profile.text,
                    f"{doc.get('title')} — {doc.get('organizing_body')}",
                    request.model,
                )
                await attach_eligibility(
                    _db,
                    result.model_dump(),
                    organizing_body=doc["organizing_body"],
                    base_title=doc["base_title"],
                    cycle_year=doc["cycle_year"],
                )
            except Exception:  # noqa: BLE001 — one bad record must not stop the rest
                continue

    background.add_task(_go)
    return {"status": "running"}


class ClearRequest(BaseModel):
    # A JSON body, so a form on another site cannot send it without a CORS check this API never passes.
    confirm: Literal["delete everything"]


@app.post("/api/database/clear")
async def clear_database(request: ClearRequest) -> dict:
    """Wipe every collection so a demo can start from nothing.

    Destructive and deliberately explicit — the UI puts a confirmation in front
    of it. It does not touch the business profile or product workbooks, which are files.
    """
    deleted = {}
    for name in (OPPORTUNITIES, PROGRAMS, RUNS, EXTRACTION_FAILURES, DEAD_ENDS,
                 cw.SEEN, cw.SIGNALS, cmw.OFFERS, "run_progress", "run_progress_writes"):
        result = await _db[name].delete_many({})
        deleted[name] = result.deleted_count
    return {"deleted": deleted}


# The built React page, when it exists. Mounted last so /api/* always wins.
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # Client-side routes (/run/<id>) must survive a refresh. Declared last, so
    # every /api route above still wins — FastAPI matches in definition order.
    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"no route /{full_path}")
        return FileResponse(STATIC_DIR / "index.html")
