"""Bounded Plan -> Research -> Analyze -> Finalize Discovery graph."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from functools import partial
from itertools import zip_longest
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from ..config import discovery_temperature
from ..eligibility import evaluate_criteria
from ..extraction import (
    ExtractionFailure,
    FailureReason,
    build_record,
    record_warnings,
)
from ..storage import (
    append_event,
    attach_eligibility,
    clear_dead_end,
    clear_extraction_failure,
    dead_end_urls,
    due_soon,
    known_orgs,
    record_dead_end,
    record_edition,
    record_extraction_failure,
    save_opportunity,
)
from ..tracing import chat_model, stage_span, trace_handler
from .actionability import assess_actionability, assess_completeness
from .link_resolver import canonicalize_url, resolve_evidence_bundle
from .profile_seed import ProfileSectionMissing, discovery_seed, profile_facts
from .providers import tavily_search
from .state import (
    CandidateVerdict,
    DiscoveryState,
    EvidenceBundle,
    PlannedQuery,
    WorkflowRuntime,
)

# Per call, sized from that call's own schema. One global ceiling meant a call
# that returns four integers was allowed 16,000 tokens, so when gemma looped it
# generated 16,000 tokens of garbage and burned 300 seconds doing it — three
# such calls cost one run 612 seconds. The ceiling must leave room for hidden
# reasoning tokens too (glm-4.7-flash spends them before emitting anything), so
# each is several times its schema's maximum rather than exactly it.
TOKENS_PICK_LINKS = 1_024      # <=4 ints + one sentence
TOKENS_SHORTLIST = 3_000       # <=8 picks, each an int + 300 chars
TOKENS_PLAN = 3_000            # 10 queries with rationales
TOKENS_ANALYZE = 16_000        # full condition lists; schema maxes near 10,400

# Traversal sizes now live on `runtime.limits`, set per run from the
# configurator. These remain only as the fallback for callers without a runtime.
MAX_RESEARCH_CANDIDATES = 4

# Sized to hold every hit a run can produce (10 searches x 7 results), so
# nothing is cut before the model sees it.
SHORTLIST_POOL = 80
MAX_LINKS_PER_PAGE = 2

# Per page, not per bundle. A single positional slice across the whole bundle
# meant a long seed page consumed the entire window and the L1 pages we paid to
# fetch were never read.
ANALYSIS_PAGE_CHARS = 40_000

# Below this a "page" is a bot-block stub, error page or redirect — not worth
# a model call.
MIN_BUNDLE_CHARS = 400

MIN_CALLS_AFTER_RESEARCH = 3


class _PlannedQueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    # No "grant": this business wants recognition, not funding.
    intent: Literal["award", "event", "conference", "mixed"]
    geography: str
    target_year: int
    rationale: str


class _QueryPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[_PlannedQueryModel] = Field(min_length=8, max_length=10)


# Bounded so a MAXIMAL conforming answer still fits under TOKENS_ANALYZE.
# The old limits permitted ~41,000 tokens against a 16,000 cap, so a legal reply
# could truncate — and under strict json_schema a truncated reply is unparseable,
# losing the whole analysis. Two bundles died that way in one run.
class _CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_url: str = Field(max_length=500)
    source_url: str = Field(max_length=500)
    target_title: str = Field(max_length=200)
    category: Literal["award", "grant", "event", "conference"]
    # The record's own values. Analyze reads the evidence once and produces the
    # whole listing; a second model call re-reading the same pages to fill these
    # in is what put six conditions and zero conditions on the same programme.
    organizing_body: str = Field(max_length=200)
    base_title: str = Field(max_length=200)
    cycle_year: int
    status: Literal["open", "closed", "unclear"]
    submission_deadline: str | None = Field(default=None, max_length=32)
    deadline_note: str | None = Field(default=None, max_length=200)
    event_date: str | None = Field(default=None, max_length=32)
    confidence_note: str = Field(default="", max_length=300)
    supporting_urls: list[Annotated[str, Field(max_length=500)]] = Field(
        max_length=3
    )
    decision: Literal["pursue", "skip"]
    reason: str = Field(max_length=400)
    entry_eligibility: list[Annotated[str, Field(max_length=300)]] = Field(
        max_length=12
    )
    judging_criteria: list[Annotated[str, Field(max_length=300)]] = Field(
        max_length=12
    )
    application_requirements: list[
        Annotated[str, Field(max_length=300)]
    ] = Field(max_length=12)


class _AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[_CandidateModel] = Field(max_length=3)


class _ShortlistPickModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Index into the numbered list, not a URL — a model cannot hallucinate an
    # index that resolves to a page that was never offered.
    index: int
    # It can still cite the wrong index. Observed live: a pick resolved to
    # "SME Innovation Awards" while its reason described the Recommerce Expo,
    # so a page nobody chose was fetched. Echoing the title back makes the
    # mismatch detectable instead of silent.
    title: str = Field(max_length=120)
    reason: str = Field(max_length=300)


class _ShortlistModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    picks: list[_ShortlistPickModel] = Field(max_length=8)


class _LinkChoiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indexes: list[int] = Field(max_length=4)
    reason: str = Field(max_length=300)


def _response_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        )
    return str(content)


def _parse_json(content: object) -> dict:
    text = _response_text(content).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("structured response was not a JSON object")
    return value


def _llm(runtime: WorkflowRuntime, *, max_tokens: int, light: bool = False):
    # The wall clock is only checked between calls, so one stalled request could
    # sit for 120s x 3 retries. One retry at 90s keeps a stall survivable.
    kwargs: dict = {
        "max_tokens": max_tokens,
        "timeout": 90,
        "max_retries": 1,
    }
    # Selection calls return a few indices and a sentence; extended reasoning on
    # them is what exhausted the output budget, so ask for the least available.
    if light:
        kwargs["extra_body"] = {"reasoning": {"effort": "low", "exclude": True}}
    temperature = discovery_temperature()
    if temperature is not None:
        kwargs["temperature"] = temperature
    return chat_model(runtime.model, **kwargs)


async def _structured(runtime: WorkflowRuntime, model_cls, name: str,
                      system: str, user: str, *, max_tokens: int,
                      light: bool = False):
    """One strict-JSON model call, validated into `model_cls`."""
    response = await asyncio.to_thread(
        _llm(runtime, max_tokens=max_tokens, light=light).invoke,
        [SystemMessage(system), HumanMessage(user)],
        config={"callbacks": [trace_handler()]},
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": model_cls.model_json_schema(),
            },
        },
    )
    return model_cls.model_validate(_parse_json(response.content))


async def _record(
    runtime: WorkflowRuntime, tool: str, *, node: str, **fields: object
) -> None:
    event = {
        "seq": len(runtime.journey) + 1,
        "t": round(runtime.budget.elapsed, 1),
        "tool": tool,
        "node": node,
        **fields,
    }
    runtime.journey.append(event)
    subject = fields.get("query") or fields.get("url") or fields.get("title") or ""
    with stage_span(
        f"stage3.{node}.{tool}: {str(subject)[:70]}",
        outcome=fields.get("outcome"),
        reason=fields.get("reason"),
        budget_remaining=runtime.budget.remaining,
    ) as span:
        _ = span
    try:
        await append_event(runtime.db, runtime.run_id, event, runtime.budget.live())
    except Exception:  # noqa: BLE001
        pass


async def _memory(runtime: WorkflowRuntime) -> str:
    """The whole business profile, plus what earlier runs already found.

    The whole document, deliberately. This used to be a five-section
    distillation — Identity, sector, geography, recognition history,
    exclusions — which left out Technology, Certifications, Scale and both
    impact sections. The stage that decides what to search for was therefore
    told nothing about edge inference, the patent, the training set, the
    altitude testing or the language support, and could not have written a
    query about any of them.

    Measured, the distillation saved about 1,500 tokens per read, roughly two
    US cents a run. That is what it cost to make the planner unable to describe
    the company it is searching on behalf of.
    """
    orgs = await known_orgs(runtime.db)
    upcoming = await due_soon(runtime.db, lookahead_months=2)
    programs = "\n".join(
        f"- {item['organizing_body']} — {item['base_title']}"
        for item in upcoming
    ) or "(none due soon)"
    # Deliberately NOT the full recorded list. Feeding every stored programme
    # back into the prompt was meant to keep naming consistent; in practice it
    # put the same programmes in front of the model run after run, and one it
    # should have dropped kept reappearing because it was being shown.
    return (
        f"{runtime.profile_text or discovery_seed()}\n\nKnown organizing bodies: "
        f"{', '.join(orgs) if orgs else '(none)'}\n"
        f"Programs due soon:\n{programs}"
    )


def _fallback_queries(today: date) -> list[PlannedQuery]:
    """A minimal plan built from the profile, used only when planning fails.

    Every term here comes from BusinessProfile.md. An earlier version hardcoded
    four queries naming India, the Middle East and the Gulf, plus a rationale
    referring to a different company entirely — so a single planner exception
    silently redirected a whole run at regions this business does not operate
    in. A fallback that searches for the wrong company is worse than no
    fallback, so this raises when the profile yields nothing to search on.
    """
    facts = profile_facts()
    geographies = facts["geographies"]
    sectors = facts["sectors"]
    if not geographies or not sectors:
        raise ProfileSectionMissing(
            "cannot build a fallback query plan: BusinessProfile.md yielded "
            f"{len(geographies)} market(s) and {len(sectors)} sector(s). "
            "Planning must not fall back to invented geography or sector."
        )

    # One query per stated sector, always in the primary market, never grants
    # and never a secondary market — this ran once and spent a whole run on
    # Bhutan, Mauritius and funding, none of which the LLM plan would have done.
    primary = geographies[0]
    years = (today.year, today.year + 1)
    return [
        PlannedQuery(
            f"{sector} awards {years[index % 2]} call for entries {primary}",
            "award",
            primary,
            years[index % 2],
            f"Fallback plan: {sector} is a sector the profile states, "
            f"searched in {primary}",
        )
        for index, sector in enumerate(sectors[:4])
    ]


async def plan_queries_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services
    today = date.fromisoformat(state["as_of_date"])
    memory = state.get("memory") or await _memory(runtime)
    fallback_detail = ""

    if state["supplied_queries"]:
        planned = [
            PlannedQuery(
                query=query,
                intent="mixed",
                geography="unspecified",
                target_year=today.year,
                rationale="Caller-supplied line of enquiry",
            )
            for query in state["supplied_queries"]
        ]
    elif runtime.dry_run:
        planned = _fallback_queries(today)[:3]
    else:
        facts = profile_facts()
        geographies = ", ".join(facts["geographies"]) or "(profile states none)"
        sectors = ", ".join(facts["sectors"]) or "(profile states none)"

        primary = facts["geographies"][0] if facts["geographies"] else "global"
        prompt = f"""Today is {today.isoformat()}. Find awards, prizes,
rankings, summits, conferences and forums this business could enter or take
part in. Recognition and visibility, not funding — never search for grants,
funding or fellowships.

Do not search only for awards. A summit that invites speakers, a conference
with a call for papers, and an industry forum with a showcase are all worth
finding. Spread the ten queries across these kinds, not just award programmes.

Sectors from the profile: {sectors}
Primary market: {primary}

Write 10 searches. Seven or eight must name {primary}; the rest name no country.

KEEP EACH QUERY SHORT — three or four content words. This is the most important
rule here. A search engine returns only pages matching every word you give it,
so each extra word narrows the results. A short query returns a wide, varied
set; a long one returns the same small set of heavily marketed pages every run.

  good:       sustainability awards {primary} {today.year}
  good:       {primary} circular economy awards
  good:       waste management industry awards {primary}
  too narrow: circular economy waste management awards {primary} {today.year} call for entries

Do not add entry phrases — call for entries, nominations open, entry deadline.
Those words sit in page body text, not titles, and they cut recall for no gain.

COVER DIFFERENT GROUND WITH EACH ONE. Ten wordings of a single idea is a wasted
plan. Vary deliberately:
- the field named: the profile's sectors, and also the broader fields they sit
  inside — sustainability, environment, climate, ESG, innovation, technology
- the technical ground the profile describes. Read its Technology section and
  search on what the engineering actually is, not only on the market it serves.
  Capabilities, methods and research areas are named by a different set of
  programmes than sectors are, and those programmes are invisible to a query
  about the market. Name the discipline, never the product.
- whether a year appears at all. Use {today.year} or {today.year + 1} in only
  some of them, never a past year. Most queries should name no year: award
  bodies publish next year's pages late, so a query naming a future year
  mostly returns academic conference listings that advertise years ahead
- the kind of recognition: awards, prize, honours, summits, conferences,
  forums and expos
- the kind of body that runs it: industry association, chamber of commerce,
  government, business publication. These run most awards in any market
- technical and academic venues, one or two of the ten. Professional
  engineering and computing bodies run conferences and workshops that take
  submissions from industry, not only universities, and the Technology section
  says whether this business has work they would accept — granted patents, a
  labelled dataset, deployed models, measured results. Name the research field
  the profile's own technology sits in and the venue type. Do not name a body:
  which societies matter depends on the field, and the field is in the profile
- the company stage: startup, emerging company, SME

Rules:
- No quotation marks.
- No unexplained acronyms; they match company names instead.
- Never name a product or hardware category. Awards are named after fields,
  never after the equipment a company sells.
- Do not copy a programme name out of the profile below. Searching for an award
  we already know about discovers nothing.

BUSINESS:
{memory}
"""
        try:
            refusal = runtime.budget.refusal("plan")
            if refusal:
                raise RuntimeError(refusal)
            runtime.budget.consume("plan")
            parsed = await _structured(
                runtime,
                _QueryPlanModel,
                "opportunity_query_plan",
                "Return a precise search plan as JSON matching the supplied schema.",
                prompt,
                max_tokens=TOKENS_PLAN,
            )
            planned = [
                PlannedQuery(
                    item.query,
                    item.intent,
                    item.geography,
                    item.target_year,
                    item.rationale,
                )
                for item in parsed.queries
            ]
        except Exception as exc:  # noqa: BLE001
            planned = _fallback_queries(today)
            fallback_detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.warnings.append(
                f"query planning fell back to deterministic plan: {fallback_detail}"
            )

    await _record(
        runtime,
        "plan",
        node="plan",
        outcome="fallback" if fallback_detail else "ok",
        detail=fallback_detail,
        queries=[
            {
                "query": item.query,
                "intent": item.intent,
                "geography": item.geography,
                "target_year": item.target_year,
                "rationale": item.rationale,
            }
            for item in planned
        ],
    )
    return {"memory": memory, "planned_queries": planned}


_SHORTLIST_SYSTEM = (
    "You choose which web search results are worth fetching. "
    "Return JSON matching the supplied schema."
)


async def _shortlist(
    ranked: list, memory: str, today: date, runtime: WorkflowRuntime, want: int
) -> list[tuple[object, str]]:
    """Model picks which hits to research. Raises so the caller can fall back."""
    pool = ranked[:SHORTLIST_POOL]
    listing = "\n".join(
        f"[{index}] {hit.title}\n     {hit.url}\n     {hit.snippet[:280]}"
        for index, hit in enumerate(pool)
    )
    prompt = f"""Today is {today.isoformat()}. Below are {len(pool)} web search
results. Pick {want} to research.

You are looking for pages belonging to a recognition programme this business
could enter. A programme's landing page, its categories page, its entry or
eligibility page are all good seeds — we follow links from whatever you pick, so
a landing page is not worse than a deep one.

ONE QUESTION DECIDES EACH RESULT: does the organisation behind this page RUN the
programme, or is it writing about someone else's?

  Runs it -> pick it. Newspapers, magazines, industry associations, chambers of
  commerce and government bodies run a large share of all awards, and they host
  those awards on their own domain. A business newspaper's awards section is
  that programme's own site. Judge the organisation and the programme, not the
  domain name.

  Writing about someone else's -> skip. A dated article reporting who won, or a
  roundup listing many different programmes, is not a programme.

Also skip: editions already finished — where the snippet names a date behind
{today.isoformat()}, or reports winners; programmes only for individuals,
students or researchers; and grants, funding or fellowships — this business
wants recognition, not money.

For each pick, the reason must say who the programme is open to, in a few words,
from what the snippet actually shows. If it is limited to a country this business
does not operate in, do not pick it however well the sector matches.

Spread your picks. Do not take {want} pages from one organisation, and do not
take {want} of the same kind of award.

You have only the title, URL and snippet. Where the snippet is thin, prefer a
programme that clearly exists over a page that merely uses the right words.

For every pick, copy the result's title into `title` exactly as it appears in
the list, and make sure `index`, `title` and `reason` all describe that same
result. A reason about a different result than the index points at means the
wrong page is fetched.

BUSINESS:
{memory}

RESULTS:
{listing}
"""
    parsed = await _structured(
        runtime, _ShortlistModel, "search_shortlist", _SHORTLIST_SYSTEM, prompt,
        max_tokens=TOKENS_SHORTLIST, light=True,
    )
    chosen: list[tuple[object, str]] = []
    seen: set[int] = set()

    def _words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 3}

    for pick in parsed.picks:
        if not (0 <= pick.index < len(pool)) or pick.index in seen:
            continue
        hit = pool[pick.index]

        # The index and the echoed title must describe the same result. When
        # they disagree the model mis-numbered, and following the index fetches
        # a page it never meant to choose — so find the result it described.
        claimed, actual = _words(pick.title), _words(hit.title)
        if claimed and not (claimed & actual):
            match = next(
                (
                    i for i, other in enumerate(pool)
                    if i not in seen and len(claimed & _words(other.title)) >= 2
                ),
                None,
            )
            if match is None:
                continue  # cannot tell what was meant — do not pay to guess
            hit = pool[match]
            seen.add(match)
        seen.add(pick.index)
        chosen.append((hit, pick.reason))
    return chosen


def _link_chooser(runtime: WorkflowRuntime, today: date):
    """An async callable the traversal uses to pick which links to follow."""

    async def choose(page, candidates: list[tuple[str, str]]) -> list[str]:
        refusal = runtime.budget.refusal("select_links")
        if refusal:
            return []
        listing = "\n".join(
            f"[{index}] {label or '(no label)'} — {url}"
            for index, (url, label) in enumerate(candidates)
        )
        prompt = f"""Today is {today.isoformat()}. While researching a
recognition programme you fetched this page:
{page.url}
{page.title}

Below are links on the same site. Pick at most {runtime.limits.max_links_per_page} that most
likely state entry eligibility, who can enter, entry requirements, categories,
fees, or the entry deadline. A brochure, entry pack, guidelines or rules
document counts — those are often where the conditions actually live, and a PDF
is readable. Prefer a specific entry, eligibility or categories
page over a general one. Skip winners, past editions, news, sponsors, contact,
login and social pages. Return an empty list if none are worth fetching.

LINKS:
{listing}
"""
        runtime.budget.consume("select_links")
        parsed = await _structured(
            runtime,
            _LinkChoiceModel,
            "link_selection",
            "Pick which links to fetch. Return JSON matching the supplied schema.",
            prompt,
            max_tokens=TOKENS_PICK_LINKS, light=True,
        )
        picked = [
            candidates[index][0]
            for index in parsed.indexes[:runtime.limits.max_links_per_page]
            if 0 <= index < len(candidates)
        ]
        await _record(
            runtime, "select_links", node="research", url=page.url,
            outcome="ok", picked=picked, reason=parsed.reason,
            considered=len(candidates),
        )
        return picked

    return choose


async def research_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services
    today = date.fromisoformat(state["as_of_date"])

    async def record_research(tool: str, **fields: object) -> None:
        await _record(runtime, tool, **fields)

    hits = list(state.get("search_hits", []))
    seen_queries = {hit.query for hit in hits}

    async def run_queries(planned_list: list[PlannedQuery], round_label: str) -> None:
        for planned in planned_list:
            if planned.query in seen_queries:
                continue
            refusal = runtime.budget.refusal("search")
            if refusal:
                break
            runtime.budget.consume("search")
            seen_queries.add(planned.query)
            try:
                found = await tavily_search(planned.query, dry_run=runtime.dry_run)
                hits.extend(found)
                await _record(
                    runtime, "search", node="research", query=planned.query,
                    outcome="ok" if found else "empty",
                    round=round_label, geography=planned.geography,
                    rationale=planned.rationale,
                    results=[
                        {"title": i.title, "url": i.url, "snippet": i.snippet}
                        for i in found
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                runtime.failures.append(
                    f"search {planned.query!r}: {type(exc).__name__}"
                )
                await _record(
                    runtime, "search", node="research", query=planned.query,
                    outcome="failed", round=round_label,
                    detail=f"{type(exc).__name__}: {exc}"[:300],
                )

    await run_queries(state["planned_queries"], "broad")

    # Order is the order the search engine returned, round-robined across
    # queries so no single query dominates. There is no keyword scoring here:
    # a regex tuned for award-marketing words scored "Sustainability Leadership
    # Awards" at zero and dropped it from two separate runs.
    per_query: dict[str, list] = {}
    for hit in hits:
        per_query.setdefault(hit.query, []).append(hit)

    existing_seeds = {bundle.seed_url for bundle in state.get("evidence_bundles", [])}
    ordered: list = []
    seen_urls: set[str] = set()
    for row in zip_longest(*per_query.values()):
        for hit in row:
            if hit is None:
                continue
            url = canonicalize_url(hit.url)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            ordered.append(
                type(hit)(hit.title, url, hit.snippet, hit.query,
                          hit.score, hit.content)
            )

    # Sites that earlier runs fetched and found nothing usable on. Dropped here
    # rather than shown to the model, so neither the tokens nor the scrape are
    # paid for again. Only after two empty visits, so one bad run cannot ban a
    # programme whose cycle had simply not opened yet.
    try:
        known_dead = await dead_end_urls(runtime.db)
    except Exception:  # noqa: BLE001 — memory is an optimisation, never a gate
        known_dead = set()

    ranked = [
        hit for hit in ordered
        if hit.url not in existing_seeds and hit.url not in known_dead
    ]
    if known_dead:
        skipped_dead = sum(1 for hit in ordered if hit.url in known_dead)
        if skipped_dead:
            await _record(
                runtime, "memory", node="research", outcome="ok",
                detail=f"skipped {skipped_dead} URL(s) earlier runs found empty",
            )

    # The model chooses what to research; search-engine order only sets the order
    # of the pool it sees. Ordering is the fallback, never the gate.
    picks: list[tuple[object, str]] = []
    if ranked and not runtime.dry_run and runtime.budget.refusal("shortlist") is None:
        try:
            runtime.budget.consume("shortlist")
            picks = await _shortlist(
                ranked, state["memory"], today, runtime, runtime.limits.max_candidates
            )
            await _record(
                runtime, "shortlist", node="research", outcome="ok",
                considered=len(ranked),
                picked=[
                    {"url": hit.url, "title": hit.title, "reason": reason}
                    for hit, reason in picks
                ],
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.warnings.append(f"shortlist fell back to ranking: {detail}")
            await _record(
                runtime, "shortlist", node="research", outcome="failed",
                considered=len(ranked), detail=detail,
            )
    if not picks:
        picks = [(hit, "search-engine order (shortlist unavailable)") for hit in ranked]

    bundles = list(state.get("evidence_bundles", []))
    choose_links = None if runtime.dry_run else _link_chooser(runtime, today)
    added = 0
    for hit, reason in picks:
        if hit.url in existing_seeds or added >= runtime.limits.max_candidates:
            continue
        if runtime.budget.remaining <= MIN_CALLS_AFTER_RESEARCH:
            break
        bundle = await resolve_evidence_bundle(
            hit, runtime, record_research, choose_links=choose_links
        )
        if bundle.pages:
            bundles.append(bundle)
            existing_seeds.add(hit.url)
            added += 1
        _ = reason

    return {"search_hits": ordered, "evidence_bundles": bundles}


def _bundle_prompt(bundle: EvidenceBundle, today: str, memory: str) -> str:
    evidence = bundle.bounded_text(ANALYSIS_PAGE_CHARS)
    return f"""Today is {today}. These pages were fetched from one site while
researching recognition programmes. Identify the distinct opportunities on it.

An event and an award on the same site are different entities.

ONE PROGRAMME, ONE ENTRY. If several categories share one entry process, one
entry form, one deadline and one set of conditions, they are categories of a
single programme — emit ONE candidate for the umbrella programme and name the
categories in its reason. Emit separate candidates only when each is entered
independently, with its own conditions. Three candidates pointing at the same
URL with the same single condition is the mistake this rule exists to prevent.

Decide pursue or skip for each, answering two questions in this order.

1. IS IT AHEAD OF US? Pursue anything whose next edition is still to come, even
   if entry has not opened yet and no dates are announced. A programme that says
   "express interest" or names only a future event date is exactly what this is
   for — knowing about it early is the point. Skip ONLY when the edition has
   demonstrably passed or its entry window has demonstrably closed.

2. IS IT FOR A BUSINESS LIKE OURS? Read the BUSINESS block and ask whether an
   organisation of this kind could plausibly be the entrant. Skip a programme
   whose entrants are a different kind of party altogether — designers,
   students, individuals, researchers, universities, or a sector this business
   does not operate in — however well the words match. Judge the entrant it
   wants, not the topic it covers.

Also skip grant, funding and fellowship programmes: this business wants
recognition, not money. Do not skip because one category fits poorly when
another category is a realistic route.

Emit at least one decision per seed bundle — use skip when the site holds no
relevant opportunity.

For every opportunity you pursue, also give its own values, read from the page:
organizing_body (the body that runs it, not the sponsor or venue), base_title
(the title with year and edition markers stripped and nothing else), cycle_year
(the year of THIS edition), status ("open", "closed" or "unclear"),
submission_deadline and event_date as "YYYY-MM-DD" or null, deadline_note when
the deadline is rolling or relative, and confidence_note for anything you were
unsure about. Use only what the pages say — never infer a deadline that is not
written there. The deadline's year may be taken from the page title or its
publication date when the deadline itself gives only a day and month.

ENTRY ELIGIBILITY is the heart of this. List every stated condition an entrant
must satisfy, each as its own item, in the words the page uses. Do not
summarise them into one line and do not invent conditions the page does not
state. Keep judging criteria (what the entry is scored on) and application
requirements (what must be submitted) in their own separate lists.

Set source_url to the most specific entry, eligibility or guidelines page
available among the pages below.

BUSINESS:
{memory}

{evidence}
"""


async def _analyze_bundle(
    bundle: EvidenceBundle,
    state: DiscoveryState,
    runtime: WorkflowRuntime,
) -> list[CandidateVerdict]:
    runtime.budget.consume("analyze")
    parsed = await _structured(
        runtime,
        _AnalysisModel,
        "opportunity_candidate_analysis",
        "Return candidate decisions as strict JSON matching the supplied schema.",
        _bundle_prompt(bundle, state["as_of_date"], state["memory"]),
        max_tokens=TOKENS_ANALYZE,
    )
    valid_urls = set(bundle.source_urls)
    candidates: list[CandidateVerdict] = []
    for item in parsed.candidates:
        if item.seed_url != bundle.seed_url:
            continue
        source_url = item.source_url if item.source_url in valid_urls else bundle.seed_url
        supporting = tuple(
            url for url in item.supporting_urls if url in valid_urls
        ) or tuple(bundle.source_urls)
        candidates.append(
            CandidateVerdict(
                seed_url=bundle.seed_url,
                source_url=source_url,
                target_title=item.target_title,
                category=item.category,
                supporting_urls=supporting,
                decision=item.decision,
                reason=item.reason,
                organizing_body=item.organizing_body,
                base_title=item.base_title,
                cycle_year=item.cycle_year,
                status=item.status,
                submission_deadline=item.submission_deadline,
                deadline_note=item.deadline_note,
                event_date=item.event_date,
                confidence_note=item.confidence_note,
                entry_eligibility=tuple(item.entry_eligibility),
                judging_criteria=tuple(item.judging_criteria),
                application_requirements=tuple(item.application_requirements),
            )
        )
    return candidates


async def analyze_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services
    analyzed = set(state.get("analyzed_seeds", []))
    bundles = [
        bundle
        for bundle in state["evidence_bundles"]
        if bundle.seed_url not in analyzed
    ]
    if not bundles:
        candidates = list(state.get("candidates", []))
        await _record(
            runtime,
            "analyze",
            node="analyze",
            outcome="no_new_evidence",
            candidates=[],
        )
        return {
            "candidates": candidates,
            "analyzed_seeds": list(analyzed),
            "analysis_errors": [],
            "replan_count": state["replan_count"] + 1,
        }

    candidates = list(state.get("candidates", []))
    errors: list[dict[str, str]] = []
    if runtime.dry_run:
        bundle = bundles[0]
        candidates.append(
            CandidateVerdict(
                seed_url=bundle.seed_url,
                source_url=bundle.seed_url,
                target_title="National Circular Economy Award 2027",
                category="award",
                supporting_urls=tuple(bundle.source_urls),
                decision="pursue",
                reason="Open synthetic fixture",
            )
        )
        analyzed.add(bundle.seed_url)
    else:
        for bundle in bundles:
            # A near-empty bundle means the fetch failed, not that the page had
            # nothing to say. Attribute it to the scrape so the failure points
            # at the stage that actually broke, and do not pay for a model call
            # on it.
            evidence_chars = len(bundle.combined_text.strip())
            if evidence_chars < MIN_BUNDLE_CHARS:
                detail = (
                    f"scrape returned only {evidence_chars} chars across "
                    f"{len(bundle.source_urls)} page(s) — treated as a failed "
                    "fetch (bot block, error page or redirect), not analysed"
                )
                errors.append({"seed_url": bundle.seed_url, "detail": detail})
                runtime.failures.append(f"scrape {bundle.seed_url}: {detail}")
                await _record(
                    runtime, "scrape", node="analyze", url=bundle.seed_url,
                    outcome="insufficient", chars=evidence_chars, detail=detail,
                )
                analyzed.add(bundle.seed_url)
                continue

            refusal = runtime.budget.refusal("analyze")
            if refusal:
                errors.append({"seed_url": bundle.seed_url, "detail": refusal})
                break
            try:
                candidates.extend(await _analyze_bundle(bundle, state, runtime))
            except Exception as exc:  # noqa: BLE001
                detail = f"{type(exc).__name__}: {exc}"[:300]
                errors.append({"seed_url": bundle.seed_url, "detail": detail})
                runtime.failures.append(f"analysis {bundle.seed_url}: {detail}")
            finally:
                analyzed.add(bundle.seed_url)

    # One entity can appear through several search hits. Keep the best canonical
    # identity instead of paying to extract it repeatedly.
    unique: dict[tuple[str, str], CandidateVerdict] = {}
    for candidate in candidates:
        key = (candidate.target_title.casefold(), candidate.source_url)
        unique[key] = candidate
    candidates = list(unique.values())
    analysis_outcome = "ok"
    if errors:
        analysis_outcome = "partial" if candidates else "failed"
    await _record(
        runtime,
        "analyze",
        node="analyze",
        outcome=analysis_outcome,
        errors=errors,
        candidates=[
            {
                "seed_url": item.seed_url,
                "url": item.source_url,
                "title": item.target_title,
                "category": item.category,
                "decision": item.decision,
                "reason": item.reason,
                "supporting_urls": list(item.supporting_urls),
                "entry_eligibility": list(item.entry_eligibility),
                "judging_criteria": list(item.judging_criteria),
                "application_requirements": list(item.application_requirements),
            }
            for item in candidates
        ],
    )
    pursued = [item for item in candidates if item.decision == "pursue"]
    return {
        "candidates": candidates,
        "analyzed_seeds": list(analyzed),
        "analysis_errors": errors,
        "replan_count": state["replan_count"] + (0 if pursued or errors else 1),
    }


def route_after_analyze(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> str:
    runtime = services
    if any(item.decision == "pursue" for item in state["candidates"]):
        return "finalize"
    if state.get("analysis_errors"):
        return "finalize"
    if (
        not state["supplied_queries"]
        and state["replan_count"] <= 1
        and runtime.budget.remaining > MIN_CALLS_AFTER_RESEARCH
    ):
        return "replan"
    return "finalize"


async def finalize_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services
    today = date.fromisoformat(state["as_of_date"])
    bundles = {bundle.seed_url: bundle for bundle in state["evidence_bundles"]}
    rejected = list(state.get("rejected", []))

    for candidate in state["candidates"]:
        if candidate.decision == "skip":
            # Recorded by `analyze`, which made the decision. Re-logging it here
            # put the same skip under `finalize` as well, so a stage that never
            # touched the candidate appeared to have rejected it.
            rejected.append(
                {
                    "url": candidate.source_url,
                    "title": candidate.target_title,
                    "reason": candidate.reason,
                    "stage": "analysis",
                }
            )
            continue

        bundle = bundles.get(candidate.seed_url)
        if bundle is None:
            continue
        # No budget check: building the record is now pure validation over what
        # analyze already produced. Refusing it at zero budget would throw away
        # the search and the scrape that were already paid for.
        canonical_page = next(
            (page for page in bundle.pages if page.url == candidate.source_url),
            bundle.pages[0],
        )
        evidence_text = bundle.extraction_text(
            candidate.supporting_urls,
            candidate.source_url,
        )
        # No second model call. Analyze already read this evidence and produced
        # the listing; this validates it into a record — edition strip on the
        # identity key, deadline grounded against the source text, pydantic
        # validation, typed failures. All the parts that were never the model's
        # to decide, and none of the parts it had already decided once.
        result = build_record(
            {
                "status": candidate.status,
                "title": candidate.target_title,
                "organizing_body": candidate.organizing_body,
                "base_title": candidate.base_title,
                "cycle_year": candidate.cycle_year,
                "category": candidate.category,
                "submission_deadline": candidate.submission_deadline,
                "deadline_note": candidate.deadline_note,
                "event_date": candidate.event_date,
                "confidence_note": candidate.confidence_note,
            },
            evidence_text,
            candidate.source_url,
            canonical_page.title,
        )
        if isinstance(result, ExtractionFailure):
            # `opportunity_closed` is the pipeline working: the page said entry
            # has closed and we believed it. Counting it as a run failure made
            # a run that correctly identified four past cycles report "Failed".
            if result.reason is not FailureReason.OPPORTUNITY_CLOSED:
                runtime.failures.append(
                    f"{candidate.source_url}: {result.reason.value}"
                )
            await record_extraction_failure(
                runtime.db,
                candidate.source_url,
                result.reason.value,
                result.detail,
                runtime.model,
                runtime.trace_url,
            )
            await _record(
                runtime,
                "extract",
                node="finalize",
                url=candidate.source_url,
                title=candidate.target_title,
                outcome="failed",
                reason=result.reason.value,
                detail=result.detail[:300],
            )
            continue

        # Analyze read the evidence and listed the entry conditions; extract
        # pulls the record's own values off the page. One read produces the
        # conditions, not two. Extract used to re-derive them from the same
        # bundle and overwrite analyze's answer with a worse one — on one run
        # analyze found six conditions for the ET awards and extract found none.
        result = result.model_copy(
            update={"eligibility_criteria": list(candidate.entry_eligibility)}
        )

        completeness = assess_completeness(
            result,
            evidence_text,
            source_count=len(bundle.pages),
        )
        await _record(
            runtime,
            "extract",
            node="finalize",
            url=candidate.source_url,
            outcome="ok",
            completeness=completeness.as_dict(),
            record={
                "title": result.title,
                "organizing_body": result.organizing_body,
                "cycle_year": result.cycle_year,
                "category": result.category,
                "submission_deadline": result.submission_deadline,
                "deadline_verified": result.deadline_verified,
                "event_date": result.event_date,
                "deadline_note": result.deadline_note,
                "base_title": result.base_title,
                "criteria": list(result.eligibility_criteria),
                "confidence_note": result.confidence_note,
            },
        )

        actionability = assess_actionability(
            result,
            evidence_text,
            today=today,
            source_url=candidate.source_url,
            source_title=canonical_page.title,
            target_status_code=canonical_page.status_code,
        )
        if actionability.status != "actionable":
            reason = "; ".join(actionability.reasons)
            rejected.append(
                {
                    "url": candidate.source_url,
                    "title": result.title,
                    "reason": reason,
                    "stage": "actionability",
                    "status": actionability.status,
                }
            )
            # Any date at all is worth recording. Requiring a submission
            # deadline meant a programme that published only an event date
            # taught the registry nothing — two ICEF editions were lost that
            # way in one run, along with the August window they implied.
            if actionability.status == "historical" and (
                result.submission_deadline or result.event_date
            ):
                await record_edition(
                    runtime.db,
                    result.organizing_body,
                    result.base_title,
                    result.cycle_year,
                    result.submission_deadline,
                    result.event_date,
                )
                runtime.historical.append(candidate.source_url)
            await _record(
                runtime,
                "actionability",
                node="finalize",
                url=candidate.source_url,
                title=result.title,
                outcome=actionability.status,
                reason=reason,
            )
            continue

        # A record with no entry conditions is real but not yet usable: the
        # eligibility stage has nothing to judge, so counting it as the run's
        # product overstates what was found. Stored, flagged, counted apart.
        usable = bool(result.eligibility_criteria)
        payload = result.model_dump()
        payload.update(
            {
                "record_state": "ready" if usable else "needs_deeper_read",
                "unfollowed_links": list(bundle.unfollowed[:20]),
                "actionability": "actionable",
                "evidence_urls": bundle.source_urls,
                "extraction_completeness": completeness.as_dict(),
                "discovery_run_id": runtime.run_id,
                # The analyser already separates these three, and until now two
                # of them were computed and thrown away. They are the details
                # someone would otherwise have to dig through the award site to
                # find, so they belong on the record: what you are judged on,
                # and what you have to submit.
                "judging_criteria": list(candidate.judging_criteria),
                "application_requirements": list(candidate.application_requirements),
            }
        )
        if runtime.dry_run:
            payload["dry_run"] = True
            payload["synthetic"] = "DRY-RUN FIXTURE — not a real opportunity"
        saved = await save_opportunity(runtime.db, payload)
        if usable:
            runtime.saved.append(candidate.source_url)
            await clear_dead_end(runtime.db, candidate.source_url)
        else:
            runtime.needs_deeper.append(candidate.source_url)
            await record_dead_end(
                runtime.db,
                candidate.source_url,
                "fetched and extracted, but the page states no entry conditions",
                result.title,
            )
        # Computed once and carried onto the event too: these say why a stored
        # record should still be treated with care, and were previously only
        # ever reachable in memory.
        warnings = record_warnings(result)
        runtime.warnings.extend(
            f"{candidate.source_url}: {warning}" for warning in warnings
        )
        await clear_extraction_failure(runtime.db, candidate.source_url)

        # Feasibility against the business profile, inside the graph. It used to
        # run in the API after the graph returned, which meant the run reported
        # "succeeded" before anything had been judged, and a failure here was
        # invisible in the journey. Free of the budget, like saving: it only
        # ever runs on a record already paid for.
        if usable:
            try:
                verdict = await asyncio.to_thread(
                    evaluate_criteria,
                    list(result.eligibility_criteria),
                    runtime.profile_text,
                    f"{result.title} — {result.organizing_body}",
                    runtime.model,
                )
                await attach_eligibility(
                    runtime.db,
                    verdict.model_dump(),
                    organizing_body=result.organizing_body,
                    base_title=result.base_title,
                    cycle_year=result.cycle_year,
                )
                await _record(
                    runtime, "feasibility", node="finalize",
                    url=candidate.source_url, title=result.title, outcome="ok",
                    counts=verdict.counts, confidence=verdict.confidence,
                    qualitative=len(verdict.qualitative_notes),
                )
            except Exception as exc:  # noqa: BLE001 — one bad verdict must not stop the run
                detail = f"{type(exc).__name__}: {exc}"[:300]
                runtime.failures.append(f"feasibility {candidate.source_url}: {detail}")
                await _record(
                    runtime, "feasibility", node="finalize",
                    url=candidate.source_url, title=result.title,
                    outcome="failed", detail=detail,
                )

        await _record(
            runtime,
            "save_opportunity",
            node="finalize",
            url=candidate.source_url,
            outcome="ok",
            action=saved.action,
            title=result.title,
            completeness=completeness.as_dict(),
            warnings=warnings,
        )

    summary = (
        f"Discovery researched {len(state['evidence_bundles'])} candidate bundle(s), "
        f"saved {len(runtime.saved)} actionable opportunity(ies), "
        f"recorded {len(runtime.historical)} historical edition(s), and rejected "
        f"{len(rejected)} candidate(s)."
    )
    return {"rejected": rejected, "summary": summary}


def _traced_node(name: str, fn, runtime: WorkflowRuntime):
    """Wrap a node so its LLM calls nest under one span named for the node."""

    async def run(state: DiscoveryState) -> dict:
        with stage_span(
            f"discovery.{name}",
            budget_spent=runtime.budget.spent,  
            budget_remaining=runtime.budget.remaining,
        ) as span:
            result = await fn(state, services=runtime)
            span.update(metadata={"budget_after": runtime.budget.spent})
            return result

    return run


def build_discovery_graph(runtime: WorkflowRuntime):
    builder = StateGraph(DiscoveryState)
    builder.add_node(
        "plan_queries", _traced_node("plan_queries", plan_queries_node, runtime)
    )
    builder.add_node("research", _traced_node("research", research_node, runtime))
    builder.add_node("analyze", _traced_node("analyze", analyze_node, runtime))
    builder.add_node("finalize", _traced_node("finalize", finalize_node, runtime))
    builder.add_edge(START, "plan_queries")
    builder.add_edge("plan_queries", "research")
    builder.add_edge("research", "analyze")
    builder.add_conditional_edges(
        "analyze",
        partial(route_after_analyze, services=runtime),
        {"replan": "plan_queries", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)
    return builder.compile()
