"""Competitor watch: competitors' own sites, the market and name checks, judged once per run.

Runs only when triggered. Each run searches for pages published since the last
successful run (minus an overlap), skips every link judged before, and asks the
model once per batch which items report something that happened, for whom, and
how much it matters. Code compares only exact links and dates.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
import openpyxl
from pydantic import BaseModel, ConfigDict, Field

from ..config import require
from ..paths import REPO_ROOT
from ..profile import SEARCH_ANGLES, SEARCH_CONSTRAINTS, load_business_profile, profile_section, without_sections
from ..storage import finish_run, start_run
from ..storage.runs import RUNS
from . import workflow as w
from .budget import RunBudget
from .link_resolver import canonicalize_url
from .providers import EXA_TIMEOUT_SECONDS, EXA_URL
from .state import WorkflowRuntime

COMPETITORS_FILE = REPO_ROOT / "docs" / "Competitors.xlsx"
SIGNALS = "competitor_signals"
SEEN = "competitor_seen"
FOCUS = "competitors"

FIRST_RUN_DAYS = 90
OVERLAP_DAYS = 2
RECENT_DAYS = 30
MARKET_QUERIES = 8
RESULTS_PER_SEARCH = 10
TEXT_CHARS = 3_000
JUDGE_TEXT_CHARS = 1_500
JUDGE_BATCH = 20
TOKENS_JUDGE = 20_000
REQUIRED = ("Competitor", "Website", "Watch")


class CompetitorListError(ValueError):
    """The competitor list is missing, or a column or value the pipeline needs is wrong."""


@dataclass(frozen=True)
class Competitor:
    name: str
    website: str
    name_check: str


def load_competitors(path: Path = COMPETITORS_FILE) -> list[Competitor]:
    """The competitors marked Watch = yes; raises CompetitorListError naming the column or row at fault."""
    if not path.exists():
        raise CompetitorListError(f"no competitor list at {path}")
    rows = openpyxl.load_workbook(path, read_only=True).worksheets[0].iter_rows(values_only=True)
    header = [str(c or "").strip() for c in next(rows, ())]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise CompetitorListError(f"{path.name} is missing column(s): {', '.join(missing)}")
    watched = []
    for n, row in enumerate(rows, 2):
        values = {h: str(v or "").strip() for h, v in zip(header, row) if h}
        if not values.get("Competitor"):
            continue
        if values["Watch"] not in ("yes", "no"):
            raise CompetitorListError(f"{path.name} row {n}: Watch must be yes or no, found {values['Watch']!r}")
        if values["Watch"] == "yes":
            site = values["Website"].removeprefix("https://").removeprefix("http://").strip("/")
            watched.append(Competitor(values["Competitor"], site, values.get("Name check") or values["Competitor"]))
    if not watched:
        raise CompetitorListError(f"{path.name} has no competitor with Watch = yes")
    return watched


async def exa_signal_search(
    query: str, *, since: date, include_domains: list[str] | None = None, news: bool = False,
) -> list[dict]:
    """Pages published since `since`, with highlights and capped text; raises on any failure."""
    body: dict = {
        "query": query, "type": "auto", "numResults": RESULTS_PER_SEARCH,
        "startPublishedDate": f"{since.isoformat()}T00:00:00.000Z",
        "contents": {"highlights": True, "text": {"maxCharacters": TEXT_CHARS}},
    }
    if include_domains:
        body["includeDomains"] = include_domains
    if news:
        body["category"] = "news"
    async with httpx.AsyncClient(headers={"x-api-key": require("EXA_API_KEY")}, timeout=EXA_TIMEOUT_SECONDS) as client:
        response = await asyncio.wait_for(client.post(EXA_URL, json=body), timeout=EXA_TIMEOUT_SECONDS)
    response.raise_for_status()
    return [
        {
            "url": canonicalize_url(item["url"]),
            "title": item.get("title") or "",
            "published": (item.get("publishedDate") or "")[:10],
            "highlights": " … ".join(item.get("highlights") or []),
            "text": (item.get("text") or "")[:TEXT_CHARS],
        }
        for item in response.json().get("results", [])
        if item.get("url")
    ]


class _MarketQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(max_length=200)
    news: bool
    rationale: str = Field(max_length=300)


class _MarketPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[_MarketQuery] = Field(min_length=4, max_length=MARKET_QUERIES)


_KINDS = Literal["contract or tender", "product", "expansion", "partnership or funding", "event or award", "other"]
SECTIONS = ("Act on this", "Competitor moves", "Market and policy", "New entrants and other companies", "Own group")
FOLLOWING_UP = "Following up"


class _Judged(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    keep: bool
    competitor: str = Field(max_length=120)
    section: Literal[SECTIONS]
    kind: _KINDS
    headline: str = Field(max_length=200)
    what_happened: str = Field(max_length=600)
    date: str = Field(max_length=10)
    importance: Literal["high", "medium", "low"]
    why_it_matters: str = Field(max_length=400)
    same_story_as: str = Field(max_length=40)
    duplicate_of: int
    reason: str = Field(max_length=300)


class _Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[_Judged] = Field(max_length=JUDGE_BATCH)


async def run_digest(db, run_id: str) -> list[dict]:
    """A run's signals grouped into the judge's sections, most important first, then earlier stories it updated."""
    order = {"high": 0, "medium": 1, "low": 2}
    signals = [d async for d in db[SIGNALS].find({"run_id": run_id}, {"_id": 0})]
    signals.sort(key=lambda s: (order[s["importance"]], s["competitor"]))
    merged = [d["url"] async for d in db[SEEN].find({"run_id": run_id, "verdict": "merged"}, {"url": 1})]
    updated = [d async for d in db[SIGNALS].find(
        {"also_reported_by": {"$in": merged}, "run_id": {"$ne": run_id}}, {"_id": 0})] if merged else []
    sections = [{"title": t, "signals": [s for s in signals if s["section"] == t]} for t in SECTIONS]
    sections.append({"title": FOLLOWING_UP, "signals": updated})
    return [s for s in sections if s["signals"]]


async def _since(db) -> tuple[date, bool]:
    """Search window start: the last successful watch run minus the overlap, or the first-run window."""
    last = await db[RUNS].find_one(
        {"budget.focus": FOCUS, "status": "succeeded"}, {"started_at": 1}, sort=[("started_at", -1)]
    )
    if last:
        return (last["started_at"].date() - timedelta(days=OVERLAP_DAYS)), False
    return date.today() - timedelta(days=FIRST_RUN_DAYS), True


async def _plan_market(runtime: WorkflowRuntime, competitors: list[Competitor], today: date) -> list[_MarketQuery]:
    prompt = f"""## Objective
Today is {today.isoformat()}. Write {MARKET_QUERIES} web searches that find what is
happening in this business's market: deployments, deposit-return programmes and their
rules, tenders, funding and partnerships, new products, and companies entering new
countries. Cover the whole market, including companies not on the list below.

## Rules
- The market is this business's own: the product category it sells and the programmes its
  buyers run, as SEARCH ANGLES and BUSINESS describe them. Every search names that product
  category or a buyer programme; general waste, recycling or circular-economy news is not it.
- Describe the event you want to find, not a company: the list below is watched separately.
- About half the searches set `news` true (news articles); the rest search the general web.
- One event type per search, about a dozen words. Ground the geography in CONSTRAINTS.
- `rationale` says what kind of event the search is for.

COMPETITORS already watched: {", ".join(c.name for c in competitors)}

CONSTRAINTS:
{profile_section(runtime.profile_text, SEARCH_CONSTRAINTS)}

SEARCH ANGLES:
{profile_section(runtime.profile_text, SEARCH_ANGLES)}

BUSINESS:
{without_sections(runtime.profile_text, SEARCH_CONSTRAINTS, SEARCH_ANGLES)}
"""
    runtime.budget.consume("plan")
    return (await w._structured(runtime, _MarketPlan, "competitor_market_plan", w._PLAN_SYSTEM, prompt,
                                max_tokens=w.TOKENS_PLAN)).queries


async def _judge(runtime: WorkflowRuntime, items: list[dict], competitors: list[Competitor],
                 recent: list[dict], since: date, today: date) -> list[_Judged]:
    listing = "\n\n".join(
        f"[{i}] {it['title']}\n    {it['url']}\n    found by: {it['lane']} search \"{it['query']}\"\n"
        f"    published (hint, often wrong): {it['published'] or 'unknown'}\n"
        f"    highlights: {it['highlights'][:800]}\n    text: {it['text'][:JUDGE_TEXT_CHARS]}"
        for i, it in enumerate(items)
    )
    stories = "\n".join(f"- {s['signal_id']}: {s['competitor']} — {s['headline']} ({s.get('date') or 'undated'})"
                        for s in recent) or "(none yet)"
    prompt = f"""## Objective
Today is {today.isoformat()}. These pages were found while watching this business's competitors and market. Return one
item per page. Keep a page only when it reports something that happened on or after
{since.isoformat()}: a contract or tender, a product, an expansion, a partnership or
funding, or an event or award.

## Decide
- `competitor`: the company the page is about, exactly as named in COMPETITORS; or
  "own group: <company>" for this business itself or a company BUSINESS names as its
  group; or "new entrant: <company>" for a company newly offering products like this
  business's; or "other company: <company>" for any other company; or "market" when no
  single company is the subject. An own-group item is never a competitor move.
- `section`: "Act on this" for something this business can still act on: a tender it could
  bid for or a decision coming up, with any deadline after today; otherwise "Competitor moves" for a company in
  COMPETITORS, "Own group" for the own group, "New entrants and other companies" for any
  other company, and "Market and policy" for programme rules, launches, delays and figures.
- Drop pages that report nothing new (home pages, catalogues, careers, general
  explainers) and events before {since.isoformat()} by the page's own text; `reason` says why.
- `duplicate_of`: when pages in this list report the same event, choose one to stand for
  it (-1 here) and give each of the others its number; keep them all. -1 for every other page.
- `date`: when it happened, "YYYY-MM-DD" or "YYYY-MM", read from the text; the published
  date is a hint only. Empty when the text gives none.
- `same_story_as`: the id from RECENT SIGNALS when the page reports the same event;
  otherwise empty.
- `importance`: "high" for a competitor's or new entrant's move in this business's product
  category, or a change in a market where this business operates; "medium" for related
  policy or market change; "low" for adjacent sectors. `why_it_matters` names the link
  (same product, same buyers, same technology, a tender it could bid for).
- Write `headline` and `what_happened` in English, whatever the page's language.
For a dropped page, fill the other fields as best you can; they are not stored.

COMPETITORS: {", ".join(c.name for c in competitors)}

RECENT SIGNALS:
{stories}

BUSINESS:
{without_sections(runtime.profile_text, SEARCH_CONSTRAINTS, SEARCH_ANGLES)}

PAGES:
{listing}
"""
    runtime.budget.consume("analyze")
    parsed = await w._structured(
        runtime, _Judgement, "competitor_judge",
        "Judge competitor and market pages. Return JSON matching the supplied schema.",
        prompt, max_tokens=TOKENS_JUDGE,
    )
    return [j for j in parsed.items if 0 <= j.index < len(items)]


async def run_competitor_watch(
    db, model: str | None = None, run_id: str | None = None, budget: RunBudget | None = None,
    only: list[str] | None = None, since: date | None = None,
) -> dict:
    """One triggered run; returns its counts. Stops with an error rather than skipping a failed step."""
    run_id = run_id or uuid4().hex
    budget = budget or RunBudget(tool_calls=80, max_searches=40, max_llm_calls=15)
    competitors = load_competitors()
    if only:
        competitors = [c for c in competitors if c.name in only]
        if not competitors:
            raise CompetitorListError(f"none of {only} is a watched competitor")
    runtime = WorkflowRuntime(db=db, budget=budget, model=model, dry_run=False, run_id=run_id,
                              focus="any", profile_text=load_business_profile().text)
    await db[SEEN].create_index("url", unique=True)
    await db[SIGNALS].create_index("signal_id", unique=True)
    await db[SIGNALS].create_index("first_seen_at")
    # An explicit start date widens or narrows this run's window; seen pages are still skipped.
    since, first = (since, False) if since else await _since(db)
    today = date.today()
    meta = {**budget.caps(), "focus": FOCUS, "workflow": "competitor-watch", "since": since.isoformat(),
            "competitors": [c.name for c in competitors]}
    await start_run(db, run_id, model or "(OPENROUTER_MODEL)", meta, [])
    counts = {"searched": 0, "results": 0, "new": 0, "signals": 0, "merged": 0, "context": 0, "dropped": 0}
    status, summary = "succeeded", ""
    try:
        market = await _plan_market(runtime, competitors, today)
        await w._record(runtime, "plan", node="plan", outcome="ok", asked=len(market),
                        detail=f"window from {since.isoformat()}" + (" (first run)" if first else ""),
                        queries=[{"query": q.query, "intent": "news" if q.news else "web", "rationale": q.rationale}
                                 for q in market])
        searches = (
            [("site", f"news, announcements and new products from {c.name}", [c.website], False)
             for c in competitors if c.website]
            + [("market", q.query, None, q.news) for q in market]
            + [("name", c.name_check, None, False) for c in competitors]
        )
        found: dict[str, dict] = {}
        for lane, query, domains, news in searches:
            budget.consume("search")
            results = await exa_signal_search(query, since=since, include_domains=domains, news=news)
            counts["searched"] += 1
            counts["results"] += len(results)
            for r in results:
                found.setdefault(r["url"], {**r, "lane": lane, "query": query})
            await w._record(runtime, "search", node="search", query=query, outcome="ok", lane=lane,
                            count=len(results), results=[{"title": r["title"], "url": r["url"],
                                                          "published_date": r["published"]} for r in results])
        seen = {d["url"] async for d in db[SEEN].find({"url": {"$in": list(found)}}, {"url": 1})}
        fresh = [it for url, it in found.items() if url not in seen]
        counts["new"] = len(fresh)
        await w._record(runtime, "seen", node="search", outcome="ok",
                        detail=f"{len(found)} distinct pages, {len(seen)} judged in earlier runs, {len(fresh)} new")

        cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
        recent = [d async for d in db[SIGNALS].find({"first_seen_at": {"$gte": cutoff}},
                                                     {"_id": 0, "signal_id": 1, "competitor": 1, "headline": 1, "date": 1})]
        for start in range(0, len(fresh), JUDGE_BATCH):
            batch = fresh[start:start + JUDGE_BATCH]
            verdicts = await _judge(runtime, batch, competitors, recent, since, today)
            now = datetime.now(timezone.utc)
            # Pages standing for an event first, so each repeat joins the story its page landed in.
            landed: dict[int, str] = {}
            merges: dict[int, str] = {}
            for j in sorted(verdicts, key=lambda j: j.duplicate_of >= 0):
                item = batch[j.index]
                known = {s["signal_id"] for s in recent}
                target = j.same_story_as if j.same_story_as in known else landed.get(j.duplicate_of)
                if j.keep and target:
                    await db[SIGNALS].update_one({"signal_id": target},
                                                 {"$addToSet": {"also_reported_by": item["url"]}, "$set": {"last_seen_at": now}})
                    landed[j.index] = merges[j.index] = target
                    verdict = "merged"
                    counts["merged"] += 1
                elif j.keep and j.importance == "low":
                    # Adjacent sectors are recorded so they are not judged again, but are not signals.
                    verdict = "context"
                    counts["context"] += 1
                elif j.keep:
                    signal = {
                        "signal_id": uuid4().hex[:10], "competitor": j.competitor, "section": j.section, "kind": j.kind,
                        "headline": j.headline, "what_happened": j.what_happened, "date": j.date,
                        "importance": j.importance, "why_it_matters": j.why_it_matters,
                        "url": item["url"], "title": item["title"], "lane": item["lane"], "query": item["query"],
                        "first_seen_at": now, "last_seen_at": now, "run_id": run_id, "also_reported_by": [],
                    }
                    await db[SIGNALS].insert_one(dict(signal))
                    recent.append(signal)
                    landed[j.index] = signal["signal_id"]
                    verdict = "kept"
                    counts["signals"] += 1
                    if j.duplicate_of >= 0:
                        runtime.warnings.append(f"{item['url']} was marked a repeat of page {j.duplicate_of}, "
                                                "which did not become a signal; stored as its own signal")
                else:
                    verdict = "dropped"
                    counts["dropped"] += 1
                await db[SEEN].update_one({"url": item["url"]}, {"$setOnInsert": {
                    "url": item["url"], "verdict": verdict, "reason": j.reason, "run_id": run_id, "first_seen_at": now}},
                    upsert=True)
            await w._record(runtime, "judge", node="evaluate", outcome="ok", considered=len(batch),
                            kept=[{"competitor": j.competitor, "headline": j.headline, "importance": j.importance,
                                   "url": batch[j.index]["url"], "merged_into": merges.get(j.index)}
                                  for j in verdicts if j.keep],
                            excluded=[{"title": batch[j.index]["title"], "url": batch[j.index]["url"], "reason": j.reason}
                                      for j in verdicts if not j.keep])
        summary = (f"{counts['signals']} new signal(s), {counts['merged']} added to known stories, "
                   f"{counts['context']} kept as low-relevance context, {counts['dropped']} dropped, from {counts['new']} new page(s) across {counts['searched']} searches.")
    except Exception as exc:
        status = "stopped" if budget.cancelled else "failed"
        summary = f"RUN ENDED EARLY: {type(exc).__name__}: {exc}"[:500]
        runtime.failures.append(summary)
    await finish_run(db, run_id, status, summary, None, {**meta, **budget.live()}, counts, [],
                     list(runtime.warnings), list(runtime.failures))
    return {"run_id": run_id, "status": status, "summary": summary, **counts}
