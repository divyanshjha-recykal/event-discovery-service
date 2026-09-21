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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import discovery_temperature
from ..eligibility import evaluate_criteria
from ..extraction import (
    ExtractionFailure,
    FailureReason,
    body_is_grounded,
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
from .providers import SEARCH_CONTENT_CHARS, tavily_search
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
# These are TOTAL output budgets, and on a reasoning model the hidden reasoning
# tokens come out of the same allowance before a single character of JSON is
# emitted. Sized for non-reasoning models, they silently produce an EMPTY reply:
# the model thinks until the budget is gone and returns nothing. That is what
# killed the second planning wave on deepseek-v4.1-flash — 364 seconds of
# reasoning against a 3,000-token ceiling, then an empty string.
TOKENS_PICK_LINKS = 2_500      # <=4 ints + one sentence
# <=10 ranked picks (int + 120-char title + 300-char reason) plus a 400-char
# observation is roughly 1,300 tokens. The headroom is for reasoning tokens:
# this call no longer runs at low effort, and under strict json_schema a reply
# truncated mid-object is unparseable, which loses the whole ranking.
TOKENS_SHORTLIST = 12_000
# Wave two reads 24 result lines plus the whole profile before writing, so it
# reasons far more than wave one — which is why wave one survived 3,000 tokens
# and wave two did not.
TOKENS_PLAN = 8_000            # <=6 queries with rationales
# Schema maxes near 10,400 tokens, and 40% now goes to reasoning, so the
# content reserve has to clear that on its own: 20,000 leaves 12,000.
TOKENS_ANALYZE = 20_000

# Traversal sizes now live on `runtime.limits`, set per run from the
# configurator. These remain only as the fallback for callers without a runtime.
MAX_RESEARCH_CANDIDATES = 4

# Large enough for six Tavily result sets while retaining re-plan results.
SHORTLIST_POOL = 80
MAX_LINKS_PER_PAGE = 2

# Planning runs in two waves. The first is written blind from the profile; the
# second is written with the first wave's results in front of it. Same number of
# Tavily calls, one extra model call, and it is what lets the rules about query
# shape come out of the prompt — the model can see what a query returned instead
# of being told in advance what it would return.
PLAN_WAVE_ONE = 2
PLAN_WAVE_TWO = 3

# What a run is looking for. Set by the operator, injected as one line into
# planning and site selection — it steers what is searched for and never
# rejects anything in code. Deliberately says nothing about sector, geography
# or technology: those come from the profile, so the same text works for any
# business whose profile is loaded.
FOCUS_HINT = {
    "award": (
        "THIS RUN WANTS AWARDS. Prizes, rankings, honours and listings that "
        "name a winner."
    ),
    "event": (
        "THIS RUN WANTS EVENTS. Conferences, summits, forums and expos this "
        "business could speak at, exhibit at or take part in."
    ),
    "research": (
        "THIS RUN WANTS TECHNICAL VENUES THAT ACCEPT SUBMITTED WORK — calls "
        "for papers, workshops, industry tracks and technical competitions. "
        "Search the engineering described in the profile's own technology "
        "section: the methods, models, datasets, measurements and patents. "
        "Name the research field, never the product. Here a year IS worth "
        "naming in some queries — unlike award bodies, conferences publish "
        "next year's call months ahead, so the year is on the page you want."
    ),
}


def _focus_line(runtime: WorkflowRuntime) -> str:
    """The operator's chosen focus as one prompt line, or nothing."""
    hint = FOCUS_HINT.get(runtime.focus or "any", "")
    return f"\n{hint}\n" if hint else ""


# How the search engine matches — the one thing the model cannot work out by
# looking at its own results, because a result set contains no counterfactual.
#
# This said "three or four content words each; every extra word narrows what
# comes back", which is how a boolean keyword engine behaves and not how Tavily
# behaves. Tavily is semantic: it parses intent, and its own guidance is natural
# language up to 400 characters, with longer queries doing BETTER on the
# `advanced` depth we use. So the rule was capping queries at four words on the
# one setting that rewards detail, and turning every search into a topic lookup.
_QUERY_MECHANICS = """Write each query as natural language saying what you want
to find. Not a bag of keywords.

The search engine reads intent — it parses the query, identifies the entities
and works out what kind of page would answer it. So a query that names a TOPIC
returns everything ever written about that topic: articles about who won last
year, pages where companies list awards they have already collected, indexes of
events. A query that names an INTENT returns pages that do the thing.

  topic:   circular economy awards India
  intent:  circular economy awards in India that companies can enter

Say who would be entering, and what state the programme should be in, when that
helps. Phrases like open for entries, accepting nominations or call for entries
are useful — they describe what you are looking for.

Do not name a year. Measured across runs, a year in the query pulls back press
releases and conference directories instead of programmes' own pages, because a
programme's page often does not carry next year's number until late. Say the
timing you want in words instead.

THE ENTRANT NEVER CHANGES. Every query is looking for something THIS business
enters. Vary how a programme is organised — the field, the kind of body, the
kind of recognition, the market — never who it is for. A query for awards that
designers, municipalities, government departments, FMCG brands, packaging firms,
students or agencies enter is searching on behalf of someone else, however close
the subject. Ask of each query: could we submit the entry?

Never name the product or the product category. Search the technology and the
field instead. Programmes are organised around disciplines and markets, so
naming the hardware returns vendors selling the same thing.

No quotation marks. Do not search for a programme the profile already names —
we know about those."""

# Per page, not per bundle. A single positional slice across the whole bundle
# meant a long seed page consumed the entire window and the L1 pages we paid to
# fetch were never read.
ANALYSIS_PAGE_CHARS = 40_000

# Below this a "page" is a bot-block stub, error page or redirect — not worth
# a model call.
MIN_BUNDLE_CHARS = 400

MIN_CALLS_AFTER_RESEARCH = 3

# Whole-attempt ceiling for one model call, enforced by the caller, small enough
# that a single stalled call cannot eat a 900-second run. Two of these calls read
# far more than the others — the ranker takes the whole result pool and analyze
# takes whole pages — so they get longer. One 180s ceiling applied to everything
# timed out the ranker on a 26,000-token pool.
CALL_TIMEOUT_SECONDS = 180
HEAVY_CALL_TIMEOUT_SECONDS = 300
HEAVY_CALLS = frozenset({"search_shortlist", "opportunity_candidate_analysis"})


class _PlannedQueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    # No "grant": this business wants recognition, not funding.
    intent: Literal["award", "event", "conference", "research", "mixed"]
    geography: str
    target_year: int
    rationale: str


class _QueryPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Count is asked for in the prompt, not pinned in the schema: planning now
    # runs in two waves and the second is sized by what the first found.
    queries: list[_PlannedQueryModel] = Field(min_length=1, max_length=6)


# Bounded so a MAXIMAL conforming answer still fits under TOKENS_ANALYZE.
# The old limits permitted ~41,000 tokens against a 16,000 cap, so a legal reply
# could truncate — and under strict json_schema a truncated reply is unparseable,
# losing the whole analysis. Two bundles died that way in one run.
class _CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_url: str = Field(max_length=500)
    source_url: str = Field(max_length=500)
    target_title: str = Field(max_length=200)
    category: Literal["award", "grant", "event", "conference", "research"]
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
    confidence_note: str = Field(default="", max_length=600)
    supporting_urls: list[Annotated[str, Field(max_length=500)]] = Field(
        max_length=3
    )
    decision: Literal["pursue", "skip"]
    # 800, not 400: a reasoned pursue/skip runs longer than 400 characters,
    # and because this is validated after the reply arrives, one over-long
    # reason threw away every candidate in the bundle. ICEF was lost that way
    # on a page that said 'open to all organizations of any kind'.
    reason: str = Field(max_length=800)
    # Whether a page belonging to THIS programme was actually read, or only a
    # page that mentions it. A directory names dozens of real programmes in one
    # line each; mining those names produced records with an invented organising
    # body and entry conditions paraphrased from a blurb, for events nothing in
    # the run had ever fetched a page about. A name found in a list is a lead,
    # not a record.
    page_belongs_to_programme: bool = True
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
    reason: str = Field(max_length=600)


class _ShortlistModel(BaseModel):
    """A ranked shortlist, best first — not a set of picks.

    Listwise ranking (RankGPT-style permutation) rather than a score per result:
    an LLM asked for an absolute 0-100 score invents the scale and it collapses,
    so the numbers tie and drift between runs. Asked which of two results is
    better it is reliable, and ordering is all the caller needs — it takes as
    many from the top as the scrape budget allows.

    `observation` is first deliberately. A rationale written before the verdict
    forces specific evidence to surface; written after, it rationalises a choice
    already made.
    """

    model_config = ConfigDict(extra="forbid")

    observation: str = Field(default="", max_length=1_200)
    picks: list[_ShortlistPickModel] = Field(max_length=10)


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
    # An empty reply surfaced as "JSONDecodeError: Expecting value: line 1
    # column 1 (char 0)", which reads like a malformed response and is not —
    # the model returned nothing at all, having spent its whole output budget
    # on reasoning tokens. Naming it points at max_tokens instead of the prompt.
    if not text:
        raise ValueError(
            "model returned an empty response — it most likely exhausted its "
            "output budget on reasoning tokens before emitting any JSON. Raise "
            "this call's max_tokens."
        )
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("structured response was not a JSON object")
    return value


# Share of a call's output budget a reasoning model may spend thinking. The
# rest is reserved for the JSON, which is the only part we can use.
#
# Reasoning tokens are drawn from the SAME allowance as content, and a reasoning
# model will spend whatever it is given: raising the ranking call's ceiling from
# 6,000 to 12,000 simply produced completion_tokens=12000 of which
# reasoning_tokens=12000 and content zero. The ceiling was never the constraint,
# the absence of a reserve was — so bound the thinking, not the total.
REASONING_SHARE = 0.4


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
    else:
        kwargs["extra_body"] = {
            "reasoning": {
                "max_tokens": max(int(max_tokens * REASONING_SHARE), 1_024),
                "exclude": True,
            }
        }
    temperature = discovery_temperature()
    if temperature is not None:
        kwargs["temperature"] = temperature
    return chat_model(runtime.model, **kwargs)


def _trim_overlong(payload: dict, exc: ValidationError) -> bool:
    """Truncate every field that failed only on length. True if anything changed.

    Covers both an over-long string and an over-long list, so a wordy answer or
    one extra list item can never discard a call we have already paid for. A cap
    is guidance to the model, not grounds to throw the reply away.
    """
    trimmed = False
    for error in exc.errors():
        if error["type"] not in ("string_too_long", "too_long"):
            continue
        limit = (error.get("ctx") or {}).get("max_length")
        path = error["loc"]
        if not limit or not path:
            continue
        node = payload
        try:
            for key in path[:-1]:
                node = node[key]
            value = node[path[-1]]
            if isinstance(value, (str, list)):
                node[path[-1]] = value[:limit]
                trimmed = True
        except (KeyError, IndexError, TypeError):
            continue
    return trimmed


async def _structured(runtime: WorkflowRuntime, model_cls, name: str,
                      system: str, user: str, *, max_tokens: int,
                      light: bool = False,
                      salvage_key: str | None = None,
                      salvage_model=None):
    """One strict-JSON model call, validated into `model_cls`.

    `salvage_key`/`salvage_model` name a list field whose items can be validated
    one at a time. Without them a single malformed item discards the whole
    reply: one candidate wrote a reason four characters over its limit and every
    other candidate in that bundle was lost with it, including the only page
    that stated who could enter.
    """
    call = asyncio.to_thread(
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
    # A hard ceiling on the caller's side. The client's own `timeout=90` did not
    # hold — one planning call ran 364 seconds, four times its setting, because
    # that timeout governs the HTTP read rather than the whole attempt and a
    # retry starts the clock again. The worker thread cannot be killed and will
    # finish in the background, but the run stops waiting on it.
    limit = (
        HEAVY_CALL_TIMEOUT_SECONDS if name in HEAVY_CALLS else CALL_TIMEOUT_SECONDS
    )
    try:
        response = await asyncio.wait_for(call, timeout=limit)
    except TimeoutError as exc:
        raise RuntimeError(f"{name} exceeded {limit}s and was abandoned") from exc

    payload = _parse_json(response.content)
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        # An over-long string is the model being wordy, not wrong. Trim it and
        # revalidate rather than discard a call we have already paid for.
        if _trim_overlong(payload, exc):
            try:
                return model_cls.model_validate(payload)
            except ValidationError:
                pass
        if not (salvage_key and salvage_model):
            raise
    except Exception:
        if not (salvage_key and salvage_model):
            raise
        # Keep the items that do validate. A partial analysis beats none, and
        # the alternative is paying for a scrape and a model call and storing
        # nothing because one field ran long.
        kept = []
        for item in payload.get(salvage_key) or []:
            try:
                kept.append(salvage_model.model_validate(item))
            except Exception:  # noqa: BLE001 — drop only the item that is wrong
                continue
        if not kept:
            raise
        runtime.warnings.append(
            f"{name}: kept {len(kept)} of "
            f"{len(payload.get(salvage_key) or [])} item(s); the rest failed validation"
        )
        return model_cls.model_construct(**{salvage_key: kept})


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

    Every term here comes from BusinessProfile.md.
    A fallback that searches for the wrong company is worse than no
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
    # Shaped like the queries the planner is asked for: an intent in natural
    # language, no year. This fired on the last run and wrote
    # "reverse vending hardware awards 2026 call for entries India" — a keyword
    # bag with a year in it, which is the pattern the planner prompt now warns
    # against. A fallback that contradicts the instructions is a trap.
    return [
        PlannedQuery(
            f"{sector} awards in {primary} that companies can enter",
            "award",
            primary,
            today.year,
            f"Fallback plan: {sector} is a sector the profile states, "
            f"searched in {primary}",
        )
        for sector in sectors[:4]
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
        # Deliberately short. This prompt carried about sixty lines of rules,
        # each one added after a query went wrong once, and they were competing
        # with each other — the guidance that mattered sat as bullet six of
        # eight where it could not land. Most of them were standing in for an
        # observation the model was never allowed to make, so they moved to the
        # second wave below, which shows it what its queries actually returned.
        # A re-plan gets the whole allowance at once: the second wave is skipped
        # on that pass, so asking for two here would halve the retry.
        want = (
            PLAN_WAVE_ONE
            if state["replan_count"] == 0
            else PLAN_WAVE_ONE + PLAN_WAVE_TWO
        )
        prompt = f"""Today is {today.isoformat()}. This business wants
recognition — awards, prizes, rankings, summits, conferences, forums. Never
funding: no grants, no fellowships.
{_focus_line(runtime)}
Write {want} web searches to find programmes it could enter.

These are the OPENING searches of a wider plan. Keep them broad — name the field
and the kind of recognition, not a narrow slice of either. A broad opening shows
you what is out there; you will see everything these return and write narrower
searches afterwards. Do not try to be precise yet.

{_QUERY_MECHANICS}

Sectors from the profile: {sectors}
Primary market: {primary}

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
            ][:want]
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


async def _plan_followup(
    runtime: WorkflowRuntime,
    already_run: list[PlannedQuery],
    hits: list,
    memory: str,
    today: date,
    want: int,
) -> list[PlannedQuery]:
    """The second planning wave, written with the first wave's results visible.

    The whole point of the split. Planning used to write every query before
    seeing a single result, so it could not know that a wording returned
    directories, or that a field was already saturated. Every rule this prompt
    does not contain is one the model can now simply observe.
    """
    listing = "\n".join(
        f"  {hit.url.split('/')[2] if '://' in hit.url else hit.url}  —  "
        f"{hit.title[:90]}"
        for hit in hits[:24]
    ) or "  (nothing came back)"
    ran = "\n".join(f"  {index}. {item.query}" for index, item in enumerate(already_run, 1))

    # The objective is restated here deliberately. Without it this prompt said
    # only "reach ground these missed", and the model read that as topics
    # missed rather than programmes missed — it went looking for policy
    # frameworks, industry standards and pilot metrics, none of which anyone can
    # enter. Every prompt that writes queries has to say what it is hunting.
    prompt = f"""Today is {today.isoformat()}. You are finding recognition
programmes this business could enter — awards, prizes, rankings, summits,
conferences, forums. Never funding.

You searched:
{ran}

These came back:
{listing}
{_focus_line(runtime)}
Write {want} more searches for programmes the ones above missed.

NOW GO SOMEWHERE ELSE. The searches above covered one angle; each of these
should take a DIFFERENT angle the first ones could not reach — a different
field, a different kind of body, a different kind of recognition, a different
market the profile names.

ONE ANGLE PER QUERY. Write these the same length and shape as the ones above:
a single clear intent, around a dozen words. Do NOT stack attributes. A query
listing everything this business does — its technology, its markets, its
customers, its categories — reads as a description of the COMPANY, and returns
documents about the sector: policy papers, project pages, consultancy
brochures. It does not return programmes. If a query names more than one idea,
split it into two, or drop the weaker half.

Stay on the SAME hunt. Every query must still be looking for a
programme someone can enter. Background reading is not the job: policy
frameworks, market reports, industry standards and published metrics are not
things this business can enter, however relevant the subject. If you find
yourself writing a query you could not enter the answer to, you have drifted.

Look at what actually came back before writing. If the results are all the same
kind of page, all from one corner of the field, or all from bodies of one kind,
go somewhere else. Widen a query that returned almost nothing; narrow one that
returned the same well-known pages. The technical work described in the profile
is named by a different set of programmes than its market is, and those are
invisible to a query about the market.

{_QUERY_MECHANICS}

Do not repeat a search above.

BUSINESS:
{memory}
"""
    runtime.budget.consume("plan")
    parsed = await _structured(
        runtime,
        _QueryPlanModel,
        "opportunity_query_plan_followup",
        "Return a precise search plan as JSON matching the supplied schema.",
        prompt,
        max_tokens=TOKENS_PLAN,
    )
    seen = {item.query.casefold() for item in already_run}
    return [
        PlannedQuery(
            item.query, item.intent, item.geography, item.target_year, item.rationale
        )
        for item in parsed.queries
        if item.query.casefold() not in seen
    ][:want]


_SHORTLIST_SYSTEM = (
    "You rank web search results by how much they are worth fetching. "
    "Return JSON matching the supplied schema."
)


async def _shortlist(
    ranked: list, memory: str, today: date, runtime: WorkflowRuntime
) -> tuple[list[tuple[object, str]], str]:
    """Rank the pool best-first. Raises so the caller can fall back.

    Returns the whole ranked list and the model's observation about the pool;
    the caller takes as many from the top as its scrape budget allows. An empty
    list is a real answer — nothing here is worth fetching — not a failure.
    """
    pool = ranked[:SHORTLIST_POOL]
    listing = "\n".join(
        f"[{index}] {hit.title}\n"
        f"     {hit.url}\n"
        f"     Query: {hit.query} · Tavily score: {hit.score:.4f}\n"
        f"     {(hit.content or hit.snippet)[:SEARCH_CONTENT_CHARS]}"
        for index, hit in enumerate(pool)
    )
    prompt = f"""Today is {today.isoformat()}. Below are {len(pool)} web search
results. Put the ones worth fetching in order, best first.

Every result you rank near the top costs a page fetch, so this order is what
decides where the run's budget goes. Rank at most 10.
{_focus_line(runtime)}
Ask three things of each result, in this order:

1. WHAT KIND OF PAGE IS THIS? Decide first, because it decides everything else.

   A page belonging to ONE programme, run by the body that runs it -> this is
   what we want. Judge the organisation, not the domain: newspapers, magazines,
   industry associations and government bodies run a large share of all awards
   and host them on their own site.

   A news article or press release ABOUT a programme -> rank far below the
   programme's own page. It carries no entry conditions, and the page we would
   actually have to read is somewhere else.

   A directory, index or roundup LISTING MANY programmes -> rank at the bottom.
   Conference indexes, event calendars and "top 10 awards" roundups are not
   programmes. We do not follow links off them, so everything we could learn
   from one is the handful of names in its own text, which is not enough to
   act on.

2. WOULD A BUSINESS LIKE OURS BE THE ENTRANT? Judge the entrant the programme
   wants, not the topic it covers. A programme open only to individuals,
   students, designers or a sector this business is not in belongs near the
   bottom, however well the words match.

3. IS IT STILL AHEAD OF US? A page reporting winners, listing finalists, or
   naming a date already behind {today.isoformat()} is a finished edition —
   rank it low.

   This question comes last on purpose. A directory of future conferences and a
   press release announcing an open call both pass it easily, so answering it
   first floats exactly the pages question 1 is there to sink.

A programme's landing page, categories page or entry page are all good — links
get followed from whatever is fetched, so a landing page is not worse than a
deep one. Where a snippet is thin, prefer a programme that clearly exists over
a page that merely uses the right words.

Rank low rather than omit. Return fewer than 10 when fewer are worth any
consideration, and an empty list when the pool holds nothing worth fetching —
an empty list sends the run back to search, which is the right outcome for a
bad pool and costs nothing.

BUSINESS:
{memory}

RESULTS:
{listing}

Write `observation` first: what you notice about this pool as a whole. Then
`picks`, best first. For each, copy the result's title into `title` exactly as
it appears above, and make `index`, `title` and `reason` describe that same
result — a reason about a different result than the index points at means the
wrong page gets fetched. Each reason says who the programme is open to, in a
few words, from what the snippet actually shows.
"""
    parsed = await _structured(
        runtime, _ShortlistModel, "search_shortlist", _SHORTLIST_SYSTEM, prompt,
        max_tokens=TOKENS_SHORTLIST,
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
    return chosen, parsed.observation


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
                        # `content` not `snippet`: this is what the ranking call
                        # actually reads, and the journey was showing the
                        # shorter one, so what you could inspect was not what it
                        # saw.
                        {
                            "title": i.title,
                            "url": i.url,
                            "snippet": i.content or i.snippet,
                        }
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

    # Second wave, written with the first wave's results in front of it. Only on
    # the first pass: a re-plan already has the whole pool to look at, and the
    # queries it was given were written after seeing it.
    planned_all = list(state["planned_queries"])
    if (
        hits
        and not runtime.dry_run
        and not state["supplied_queries"]
        and state["replan_count"] == 0
        and runtime.budget.refusal("plan") is None
    ):
        try:
            followup = await _plan_followup(
                runtime, planned_all, hits, state["memory"], today, PLAN_WAVE_TWO
            )
            await _record(
                runtime, "plan", node="research", outcome="ok",
                detail=f"second wave, written after seeing {len(hits)} results",
                queries=[
                    {
                        "query": item.query, "intent": item.intent,
                        "geography": item.geography,
                        "target_year": item.target_year,
                        "rationale": item.rationale,
                    }
                    for item in followup
                ],
            )
            planned_all.extend(followup)
            await run_queries(followup, "informed")
        except Exception as exc:  # noqa: BLE001 — wave one still stands on its own
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.warnings.append(f"second planning wave failed: {detail}")
            await _record(
                runtime, "plan", node="research", outcome="failed", detail=detail,
            )

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

    # The model ranks the pool best-first; search-engine order only sets the
    # order it reads them in. Code takes the top of that ranking and does
    # nothing else to it — no score, no threshold, no keyword test.
    picks: list[tuple[object, str]] = []
    ranked_shortlist: list[tuple[object, str]] = []
    shortlist_answered = False
    if ranked and not runtime.dry_run and runtime.budget.refusal("shortlist") is None:
        try:
            runtime.budget.consume("shortlist")
            ranked_shortlist, observation = await _shortlist(
                ranked, state["memory"], today, runtime
            )
            shortlist_answered = True
            picks = ranked_shortlist[:runtime.limits.max_candidates]
            await _record(
                runtime, "shortlist", node="research", outcome="ok",
                considered=len(ranked), observation=observation,
                # The whole ranking is recorded, not only what was fetched, so
                # the near-misses just below the cut are visible. Whether the
                # good programme sat one place too low was previously
                # unanswerable.
                picked=[
                    {
                        "url": hit.url, "title": hit.title, "reason": reason,
                        "rank": position, "fetched": position <= len(picks),
                    }
                    for position, (hit, reason) in enumerate(ranked_shortlist, 1)
                ],
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.warnings.append(f"shortlist fell back to ranking: {detail}")
            await _record(
                runtime, "shortlist", node="research", outcome="failed",
                considered=len(ranked), detail=detail,
            )
    # A shortlist that ran and returned nothing is an answer: the pool held
    # nothing worth a fetch, and the run should search again rather than spend
    # scrapes on the least-bad result. Falling back to search-engine order here
    # meant declining was impossible — the top hits got fetched anyway.
    if not picks and not shortlist_answered:
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

    return {
        "search_hits": ordered,
        "evidence_bundles": bundles,
        # Both waves, so the run's record of what it searched is complete.
        "planned_queries": planned_all,
    }


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

This rule is about HOW MANY candidates to emit, never about whether to pursue.
Being one umbrella programme with many categories is completely normal and is
not a reason to skip: emit the single umbrella candidate and decide pursue or
skip on its merits. A run once set aside a 25-category awards programme whose
own page said anyone working toward sustainability may nominate, giving the
reason "one umbrella programme, not 25 opportunities" — that is this rule being
read backwards.

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

WHOSE PAGE DID WE ACTUALLY READ? Set `page_belongs_to_programme` false whenever
the pages below only MENTION this programme — a directory, index, event
calendar or roundup that lists many different programmes, a news article, or a
press release. Those name real programmes, but one line in a list is not enough
to build a listing from: the organising body, the conditions and the dates all
have to be guessed, and a guessed record is worse than none. Set it true only
when a page belonging to this programme itself was among the pages read.

A directory is not itself an opportunity either. Do not emit the index page as a
candidate in its own right — "Waste Management Conferences 2026" run by a
listings website is a web page, not a programme anyone enters.

For every opportunity you pursue, also give its own values, read from the page:
organizing_body (the body that runs it, named on the page; if the page names
none, leave it empty rather than inferring one from elsewhere), base_title
(the title with year and edition markers stripped and nothing else), cycle_year
(the year of THIS edition), status ("open", "closed" or "unclear"),
submission_deadline and event_date as "YYYY-MM-DD" or null, deadline_note when
the deadline is rolling or relative, and confidence_note for anything you were
unsure about. Use only what the pages say — never infer a deadline that is not
written there. The deadline's year may be taken from the page title or its
publication date when the deadline itself gives only a day and month.

ENTRY ELIGIBILITY is the heart of this. List every stated condition an entrant
must satisfy, each as its own item, in the words the page uses. If the page
states no conditions, return an empty list — never a sentence saying there are
none, and never the event's audience or attendee description. Do not
summarise them into one line and do not invent conditions the page does not
state. Keep judging criteria (what the entry is scored on) and application
requirements (what must be submitted) in their own separate lists.

Use category "research" for a venue that accepts submitted work — a call for
papers, a workshop, an industry track, a technical competition. These state no
conditions on who may enter, because anyone may; what decides whether it is
worth entering is whether the work fits. So for a research venue, entry
eligibility is the SCOPE: list the topics, tracks and problem areas the venue
says it wants, each as its own item, in the page's own words. That is what gets
judged against what this business actually works on. Submission format, page
limits and anonymity rules are application requirements, not eligibility.

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
        salvage_key="candidates",
        salvage_model=_CandidateModel,
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
        # A programme we only read ABOUT cannot be stored, whatever the analyser
        # decided — every field of that record would be inferred from a one-line
        # mention. Turned into a skip rather than dropped, so the lead and its
        # reason stay visible instead of vanishing from the journey.
        decision, reason = item.decision, item.reason
        if decision == "pursue" and not item.page_belongs_to_programme:
            decision = "skip"
            reason = (
                "only mentioned on the pages read, never its own page — the "
                f"body, dates and conditions would all be guesses. {item.reason}"
            )[:400]
        candidates.append(
            CandidateVerdict(
                seed_url=bundle.seed_url,
                source_url=source_url,
                target_title=item.target_title,
                category=item.category,
                supporting_urls=supporting,
                decision=decision,
                reason=reason,
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


def _feasibility_context(result) -> str:
    """What the eligibility call is being asked to judge.

    A research venue's conditions are its scope, not entry rules, so it is told
    that rather than left to infer it from topic strings that read nothing like
    an eligibility list.
    """
    context = f"{result.title} — {result.organizing_body}"
    if result.category == "research":
        return (
            f"{context} (a venue that accepts submitted work; the conditions "
            "below are the topics it wants, so judge whether this business has "
            "work that fits)"
        )
    return context


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

        # A record with nothing for the eligibility stage to judge is real but
        # not finished: counting it as the run's product overstates what was
        # found. Stored, flagged, counted apart. The same test serves every
        # category because analyze puts a research venue's scope in the same
        # field an award's entry conditions go in — that scope is what gets
        # judged, so a call for papers is complete on its own terms rather than
        # filed as thin for lacking conditions it was never going to state.
        grounded = body_is_grounded(result.organizing_body, evidence_text)
        if not grounded:
            runtime.warnings.append(
                f"{candidate.source_url}: organizing_body "
                f"{result.organizing_body!r} does not appear in the page"
            )
        ready = bool(result.eligibility_criteria) and grounded
        payload = result.model_dump()
        payload.update(
            {
                "record_state": "ready" if ready else "needs_deeper_read",
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
        if ready:
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
        if ready:
            try:
                verdict = await asyncio.wait_for(
                    asyncio.to_thread(
                        evaluate_criteria,
                        list(result.eligibility_criteria),
                        runtime.profile_text,
                        _feasibility_context(result),
                        runtime.model,
                    ),
                    timeout=HEAVY_CALL_TIMEOUT_SECONDS,
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
