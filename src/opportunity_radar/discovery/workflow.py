"""Discovery graph: plan -> search -> rank -> fetch -> extract -> evaluate -> store."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import replace
from urllib.parse import urlsplit
from datetime import date
from functools import lru_cache, partial
from itertools import zip_longest
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pymongo import MongoClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import MongoConfig, discovery_temperature
from ..eligibility import evaluate_criteria
from ..extraction import (
    ExtractionFailure,
    FailureReason,
    build_record,
    record_warnings,
    strip_edition,
)
from ..storage import (
    append_event,
    attach_eligibility,
    clear_dead_end,
    clear_extraction_failure,
    dead_end_urls,
    due_soon,
    known_orgs,
    normalize,
    record_dead_end,
    record_edition,
    record_extraction_failure,
    save_opportunity,
)
from ..tracing import chat_model, stage_span, trace_handler
from .actionability import assess_actionability, assess_completeness
from .link_resolver import canonicalize_url, content_key, resolve_evidence_bundle
from ..profile import (
    SEARCH_ANGLES,
    SEARCH_CONSTRAINTS,
    profile_section,
    without_sections,
)
from .providers import SEARCH_CONTENT_CHARS, search_provider
from .state import (
    CandidateVerdict,
    DiscoveryState,
    EvidenceBundle,
    GroundedField,
    PlannedQuery,
    PreparedRecord,
    RankedPick,
    SearchHit,
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
TOKENS_PICK_LINKS = 4_000      # 1k reserved for thinking, rest for <=4 ints + a sentence
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
#: What a run is hunting, as a noun phrase. Every prompt that has to name the
#: thing takes it from here, so a research run stops being told it is looking
#: for recognition programmes.
FOCUS_NOUN = {
    "any": "programmes this business could enter or submit work to",
    "award": "awards, prizes and rankings this business could be entered for",
    "event": "events this business could speak at, exhibit at or take part in",
    "research": (
        "technical venues that take submissions — conference papers, "
        "workshops, industry and applied tracks, demo sessions and "
        "technical challenges"
    ),
}


def _constraints(runtime: WorkflowRuntime) -> str:
    return profile_section(runtime.profile_text, SEARCH_CONSTRAINTS)


def _angles(runtime: WorkflowRuntime) -> str:
    return profile_section(runtime.profile_text, SEARCH_ANGLES)


def _focus_noun(runtime: WorkflowRuntime) -> str:
    return FOCUS_NOUN.get(runtime.focus or "any", FOCUS_NOUN["any"])


FOCUS_HINT = {
    "award": (
        "THIS RUN WANTS AWARDS. Prizes, rankings and honours this business "
        "could be entered for or named to."
    ),
    "event": (
        "THIS RUN WANTS EVENTS. Conferences, summits, forums and expos this "
        "business could speak at, exhibit at or take part in."
    ),
    "research": (
        "THIS RUN WANTS TECHNICAL VENUES THAT TAKE SUBMISSIONS — conference "
        "papers, workshops, industry and applied tracks, demo sessions and "
        "technical challenges or benchmarks. These are organised by technical "
        "subfield, not by industry: computer vision, machine learning, "
        "robotics, signal processing, data mining, human-computer interaction. "
        "Search the engineering in the profile's own technology section — the "
        "methods, models, sensing, datasets, measurements and patents — and "
        "name the subfield it belongs to. Never name the product."
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
_QUERY_MECHANICS = """Query rules:
- Natural language stating what to find and who enters it. Not keywords.
    topic:  robotics awards Germany
    intent: robotics awards in Germany that companies can enter
- One angle per query, about a dozen words. Never stack several ideas.
- The entrant is always this business, as CONSTRAINTS define it.
- Name the primary market from CONSTRAINTS, or ask for programmes open to
  entrants based there.
- "open for entries", "accepting nominations" and "call for entries" help.
- No year; state timing in words. Exception: calls for papers.
- Never name the product category from SEARCH ANGLES.
- No quotation marks. Do not search for a programme the profile already names."""

# Per page, not per bundle. A single positional slice across the whole bundle
# meant a long seed page consumed the entire window and the L1 pages we paid to
# fetch were never read.
ANALYSIS_PAGE_CHARS = 40_000

# Below this a "page" is a bot-block stub, error page or redirect — not worth
# a model call.
MIN_BUNDLE_CHARS = 400

#: Stored when the pages never name an organiser, so the gap is visible rather
#: than filled with a guess.
ORGANISER_NOT_STATED = "not stated"

MIN_CALLS_AFTER_RESEARCH = 3

#: A search extract shorter than this is too generic to call a duplicate.
EXTRACT_KEY_CHARS = 200

# One link choice plus one analysis, per site.
CALLS_PER_SITE = 2

# Whole-attempt ceiling for one model call, enforced by the caller, small enough
# that a single stalled call cannot eat a 900-second run. Two of these calls read
# far more than the others — the ranker takes the whole result pool and analyze
# takes whole pages — so they get longer. One 180s ceiling applied to everything
# timed out the ranker on a 26,000-token pool.
CALL_TIMEOUT_SECONDS = 180
HEAVY_CALL_TIMEOUT_SECONDS = 300
# Reasoning-heavy calls get the longer ceiling. Planning belongs here: it timed
# out at 180s on a live run and fell back to a query plan built in code.
HEAVY_CALLS = frozenset({
    "search_shortlist",
    "opportunity_candidate_analysis",
    "opportunity_query_plan",
    "opportunity_query_plan_followup",
})


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

    source_url: str = Field(max_length=500)
    target_title: str = Field(max_length=200)
    category: Literal["award", "grant", "event", "conference", "research"]
    # The record's own values. Analyze reads the evidence once and produces the
    # whole listing; a second model call re-reading the same pages to fill these
    # in is what put six conditions and zero conditions on the same programme.
    # Empty when the pages never say who runs it. Required, it had to invent
    # one: "POWERED BY MUNI CAMPUS" became the organiser of the Aegis awards.
    organizing_body: str = Field(default="", max_length=200)
    domain: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=500)
    base_title: str = Field(max_length=200)
    cycle_year: int
    status: Literal["open", "closed", "unclear"]
    submission_deadline: str | None = Field(default=None, max_length=32)
    # The sentence each of the three was read from, copied verbatim. Checked
    # against the page as a measurement of how often values are invented.
    body_quote: str = Field(default="", max_length=400)
    deadline_quote: str = Field(default="", max_length=400)
    status_quote: str = Field(default="", max_length=400)
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
    # Both branches reserve room for the answer. `effort` alone is only a hint:
    # the model may ignore it and think until the whole budget is gone, which is
    # how the link picker kept returning nothing on link-heavy pages.
    if light:
        # max_tokens only: the provider rejects a request carrying both this and
        # `effort`. The reserve is the part that matters — `effort` is advisory.
        kwargs["extra_body"] = {
            "reasoning": {"max_tokens": 1_024, "exclude": True}
        }
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


def _strict_schema(schema: dict) -> dict:
    """Mark every property required, as OpenAI strict json_schema demands.

    Pydantic leaves a field with a default out of `required`, which OpenAI
    rejects outright: "'required' is required to be supplied and to be an array
    including every key in properties". Other providers tolerate it, so the
    pipeline could not run an OpenAI model at all. Defaults still apply on our
    side — this only changes what the provider is asked to emit.
    """
    for node in (schema, *(schema.get("$defs") or {}).values()):
        if not isinstance(node, dict):
            continue
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
            node.setdefault("additionalProperties", False)
    return schema


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
                "schema": _strict_schema(model_cls.model_json_schema()),
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
        f"{without_sections(runtime.profile_text, SEARCH_CONSTRAINTS, SEARCH_ANGLES)}"
        f"\n\nKnown organizing bodies: "
        f"{', '.join(orgs) if orgs else '(none)'}\n"
        f"Programs due soon:\n{programs}"
    )


_PLAN_SYSTEM = "Return a search plan as JSON matching the supplied schema."


async def _ask_for_queries(
    runtime: WorkflowRuntime, name: str, prompt: str, want: int
) -> list:
    """One planning call, and one more for any shortfall against `want`."""
    runtime.budget.consume("plan")
    parsed = await _structured(
        runtime, _QueryPlanModel, name, _PLAN_SYSTEM, prompt, max_tokens=TOKENS_PLAN
    )
    items = list(parsed.queries)[:want]
    if len(items) < want and runtime.budget.refusal("plan") is None:
        written = "\n".join(f"- {item.query}" for item in items) or "- (none)"
        runtime.budget.consume("plan")
        again = await _structured(
            runtime, _QueryPlanModel, name, _PLAN_SYSTEM,
            f"{prompt}\nAlready written, do not repeat:\n{written}\n\n"
            f"Write exactly {want - len(items)} more.",
            max_tokens=TOKENS_PLAN,
        )
        seen = {item.query.casefold() for item in items}
        items += [q for q in again.queries if q.query.casefold() not in seen]
    return items[:want]


def _dry_run_queries(today: date) -> list[PlannedQuery]:
    """Fixed queries for --dry-run only. Nothing is searched; the stub replies."""
    return [
        PlannedQuery(
            "circular economy awards that companies can enter",
            "award", "India", today.year, "dry-run fixture",
        )
    ]


async def plan_queries_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services
    today = date.fromisoformat(state["as_of_date"])
    memory = state.get("memory") or await _memory(runtime)

    asked = 0
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
        planned = _dry_run_queries(today)
    else:
        # Deliberately short. This prompt carried about sixty lines of rules,
        # each one added after a query went wrong once, and they were competing
        # with each other — the guidance that mattered sat as bullet six of
        # eight where it could not land. Most of them were standing in for an
        # observation the model was never allowed to make, so they moved to the
        # second wave below, which shows it what its queries actually returned.
        # A re-plan gets the whole allowance at once: the second wave is skipped
        # on that pass, so asking for two here would halve the retry.
        want = asked = (
            PLAN_WAVE_ONE
            if state["replan_count"] == 0
            else PLAN_WAVE_ONE + PLAN_WAVE_TWO
        )
        prompt = f"""## Objective
Today is {today.isoformat()}. Write exactly {want} web searches for programmes
this business can enter.
{_focus_line(runtime)}
CONSTRAINTS:
{_constraints(runtime)}

SEARCH ANGLES:
{_angles(runtime)}

## Rules
- Opening searches: keep them broad — a field and a kind of recognition.
- Each query takes a different angle.
- Use SEARCH ANGLES as directions, not phrases: rephrase them and reach
  adjacent fields.
{_QUERY_MECHANICS}

BUSINESS:
{memory}
"""
        try:
            refusal = runtime.budget.refusal("plan")
            if refusal:
                raise RuntimeError(refusal)
            planned = [
                PlannedQuery(
                    item.query, item.intent, item.geography,
                    item.target_year, item.rationale,
                )
                for item in await _ask_for_queries(
                    runtime, "opportunity_query_plan", prompt, want
                )
            ]
        except Exception as exc:
            # No fallback. A plan built in code searched on product names and
            # hid the real failure, which was a timeout.
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.failures.append(f"query planning failed: {detail}")
            await _record(
                runtime, "plan", node="plan", outcome="failed", detail=detail,
            )
            raise RuntimeError(f"query planning failed, run stopped: {detail}") from exc

    await _record(
        runtime,
        "plan",
        node="plan",
        outcome="short" if len(planned) < asked else "ok",
        asked=asked or len(planned),
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
    prompt = f"""## Objective
Today is {today.isoformat()}. Write exactly {want} more web searches for
programmes this business can enter that the searches below missed.
{_focus_line(runtime)}
CONSTRAINTS:
{_constraints(runtime)}

SEARCH ANGLES:
{_angles(runtime)}

You searched:
{ran}

These came back:
{listing}

## Rules
- Take angles the searches above did not: another field, kind of body, kind of
  recognition, or technology.
- If the results above are dominated by one kind of page, one corner of the
  field, or programmes this business cannot enter, go elsewhere.
- Use SEARCH ANGLES as directions, not phrases.
- Every query looks for a programme this business can enter — never reports,
  policy, standards or background reading.
- Do not repeat a search above.
{_QUERY_MECHANICS}

BUSINESS:
{memory}
"""
    items = await _ask_for_queries(
        runtime, "opportunity_query_plan_followup", prompt, want
    )
    seen = {item.query.casefold() for item in already_run}
    return [
        PlannedQuery(
            item.query, item.intent, item.geography, item.target_year, item.rationale
        )
        for item in items
        if item.query.casefold() not in seen
    ][:want]


_SHORTLIST_SYSTEM = (
    "You rank web search results by how much they are worth fetching. "
    "Return JSON matching the supplied schema."
)


_YEAR_IN_TEXT = re.compile(r"(?:^|[^\d])(20\d{2})(?:[^\d]|$)")


def _stated_years(hit) -> str:
    """Years written in the title or the address, oldest first.

    Deterministic parsing, not relevance scoring: a year is a year. Given to the
    ranker as fact so it stops inferring a page's edition from prose, which is
    what a search extract shows worst.
    """
    found = sorted({
        match
        for field in (hit.title, hit.url)
        for match in _YEAR_IN_TEXT.findall(field or "")
    })
    return ", ".join(found)


def _date_line(hit, today: str) -> str:
    """The temporal signals for one search result, dates read off the page first."""
    parts = [
        f"{label} {value}{' (passed)' if value < today else ''}"
        for label, value in (("entry deadline", hit.entry_deadline), ("event", hit.event_date))
        if value
    ]
    if hit.date_quote:
        parts.append(f'date read from: "{hit.date_quote[:200]}"')
    parts.append(
        f"published/updated {hit.published_date}"
        if hit.published_date else "publish date unknown"
    )
    if years := _stated_years(hit):
        parts.append(f"year(s) in title or address: {years}")
    return " | ".join(parts)


def _facts_line(hit) -> str:
    """Who runs it and who may enter, as the provider read them off the page."""
    return " | ".join(
        f"{label}: {value}"
        for label, value in (
            ("organiser", hit.organiser),
            ("open to", hit.who_can_enter),
            ("country", hit.country_restriction),
        )
        if value
    )


def _listing_entry(index: int, hit, today: str) -> str:
    lines = [
        f"[{index}] {hit.title}",
        f"     {hit.url}",
        f"     Query: {hit.query}" + (f" · search score {hit.score:.2f}" if hit.score else ""),
        f"     {_date_line(hit, today)}",
    ]
    if facts := _facts_line(hit):
        lines.append(f"     {facts}")
    lines.append(f"     {(hit.content or hit.snippet)[:SEARCH_CONTENT_CHARS]}")
    return "\n".join(lines)


def _programme_key(hit) -> str:
    """Programme name without its year, plus site: one programme, one pool entry."""
    if not hit.programme_name:
        return ""
    try:
        name = normalize(strip_edition(hit.programme_name))
    except ValueError:
        return ""
    return f"{urlsplit(hit.url).hostname or ''}|{name}"


async def _shortlist(
    ranked: list, memory: str, today: date, runtime: WorkflowRuntime
) -> tuple[list[tuple[object, str]], str]:
    """Rank the pool best-first. Raises; the caller stops the run.

    Returns the whole ranked list and the model's observation about the pool;
    the caller takes as many from the top as its scrape budget allows. An empty
    list is a real answer — nothing here is worth fetching — not a failure.
    """
    pool = ranked[:SHORTLIST_POOL]
    listing = "\n".join(
        _listing_entry(index, hit, today.isoformat()) for index, hit in enumerate(pool)
    )
    prompt = f"""## Objective
Today is {today.isoformat()}. Order these {len(pool)} search results by how
worth fetching each is, best first. Every result near the top costs a fetch.
{_focus_line(runtime)}
CONSTRAINTS:
{_constraints(runtime)}

## Decide
Fetch only results that meet all three:
1. Programme page — one programme, published by the body that runs it. Not a
   news article, press release, directory or list of many programmes.
2. Enterable — nothing in the extract excludes this business under
   CONSTRAINTS: entrant type, market, or what is not sought. Judge the entrant
   the programme wants, not the topic it covers.
3. Current — the edition is not finished: no winners announced, entry not
   closed, dates not behind today.
Leave out any result that fails a condition. Order the rest:
1. An entry deadline within the next 14 days.
2. The kind of opportunity CONSTRAINTS list first under "Seeking", then the next.
3. Within a kind, confidence that all three conditions hold.

Each result may show dates read from the page, with the sentence they came
from, plus its publish date and any year in its title or address. Use them for
condition 3; a publish date shows when a page was written, not whether the
programme is current. Where a result states who may
enter or a country, use it for condition 2.
Judge the organisation, not the domain: newspapers, industry bodies and
government departments run many awards.

## Output
- `observation` first: what this pool looks like as a whole.
- `picks`: best first, at most 10. Copy each title exactly as shown; `index`,
  `title` and `reason` describe the same result.
- Each reason states who the programme is open to, from the extract.
- Only results that pass. A short or empty list is correct.

BUSINESS:
{memory}

RESULTS:
{listing}
"""
    parsed = await _structured(
        runtime, _ShortlistModel, "search_shortlist", _SHORTLIST_SYSTEM, prompt,
        max_tokens=TOKENS_SHORTLIST,
    )
    chosen: list[tuple[object, str]] = []
    seen: set[int] = set()
    for pick in parsed.picks:
        if not (0 <= pick.index < len(pool)) or pick.index in seen:
            continue
        seen.add(pick.index)
        chosen.append((pool[pick.index], pick.reason))
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
        prompt = f"""Today is {today.isoformat()}. While looking for
{_focus_noun(runtime)} you fetched this page:
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
            runtime, "select_links", node="fetch", url=page.url,
            outcome="ok", picked=picked, reason=parsed.reason,
            considered=len(candidates),
        )
        return picked

    return choose


async def search_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    """Run the planned queries that have not been run yet."""
    runtime = services
    today = date.fromisoformat(state["as_of_date"])

    pool = list(state.get("search_hits", []))
    known_urls = {hit.url for hit in pool}
    seen_queries = {hit.query for hit in pool}
    found_now: list[SearchHit] = []
    provider, search = search_provider(runtime.search_provider)
    held: dict[str, str] = {}
    programmes: dict[str, str] = {}
    for hit in pool:
        if key := content_key(hit.content, EXTRACT_KEY_CHARS):
            held.setdefault(key, hit.url)
        if pkey := _programme_key(hit):
            programmes.setdefault(pkey, hit.url)

    async def run_queries(planned_list: list[PlannedQuery], round_label: str) -> None:
        for planned in planned_list:
            if planned.query in seen_queries:
                continue
            if runtime.budget.refusal("search"):
                break
            runtime.budget.consume("search")
            seen_queries.add(planned.query)
            try:
                found = await search(planned.query, dry_run=runtime.dry_run)
                # Canonicalised here rather than when the pool is ordered, so the
                # merge rule sees the same URL twice as one.
                found = [
                    replace(hit, url=canonicalize_url(hit.url))
                    for hit in found if hit.url
                ]
                kept = []
                for hit in found:
                    key = content_key(hit.content, EXTRACT_KEY_CHARS)
                    if key and held.get(key, hit.url) != hit.url:
                        await _record(
                            runtime, "dedupe", node="search", url=hit.url,
                            outcome="dropped", title=hit.title,
                            duplicate_of=held[key],
                        )
                        continue
                    if key:
                        held.setdefault(key, hit.url)
                    pkey = _programme_key(hit)
                    if pkey and programmes.get(pkey, hit.url) != hit.url:
                        await _record(
                            runtime, "dedupe", node="search", url=hit.url,
                            outcome="dropped", title=hit.title,
                            duplicate_of=programmes[pkey],
                        )
                        continue
                    if pkey:
                        programmes.setdefault(pkey, hit.url)
                    kept.append(hit)
                found = kept
                found_now.extend(found)
                await _record(
                    runtime, "search", node="search", query=planned.query,
                    outcome="ok" if found else "empty", provider=provider,
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
                            "entry_deadline": i.entry_deadline,
                            "event_date": i.event_date,
                        }
                        for i in found
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                runtime.failures.append(
                    f"search {planned.query!r}: {type(exc).__name__}"
                )
                await _record(
                    runtime, "search", node="search", query=planned.query,
                    outcome="failed", round=round_label,
                    detail=f"{type(exc).__name__}: {exc}"[:300],
                )

    await run_queries(state["planned_queries"], "broad")

    # Second wave, written with the first wave's results in front of it. Only on
    # the first pass: a re-plan already has the whole pool to look at, and the
    # queries it was given were written after seeing it.
    added_queries: list[PlannedQuery] = []
    if (
        found_now
        and not runtime.dry_run
        and not state["supplied_queries"]
        and state["replan_count"] == 0
        and runtime.budget.refusal("plan") is None
    ):
        try:
            followup = await _plan_followup(
                runtime, list(state["planned_queries"]), pool + found_now,
                state["memory"], today, PLAN_WAVE_TWO,
            )
            await _record(
                runtime, "plan", node="plan",
                outcome="short" if len(followup) < PLAN_WAVE_TWO else "ok",
                asked=PLAN_WAVE_TWO,
                detail=f"second wave, written after seeing {len(found_now)} results",
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
            added_queries.extend(followup)
            await run_queries(followup, "informed")
        except Exception as exc:  # noqa: BLE001 — wave one still stands on its own
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.warnings.append(f"second planning wave failed: {detail}")
            await _record(
                runtime, "plan", node="plan", outcome="failed", detail=detail,
            )

    return {
        "search_hits": [hit for hit in found_now if hit.url not in known_urls],
        "planned_queries": added_queries,
    }


async def rank_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> Command:
    """Order the whole pool best-first and hand each chosen site to its own fetch."""
    runtime = services
    today = date.fromisoformat(state["as_of_date"])
    existing_seeds = {bundle.seed_url for bundle in state.get("evidence_bundles", [])}
    already_picked = {pick.hit.url for pick in state.get("picks", [])}

    # Order is the order the search engine returned, round-robined across
    # queries so no single query dominates. There is no keyword scoring here:
    # a regex tuned for award-marketing words scored "Sustainability Leadership
    # Awards" at zero and dropped it from two separate runs.
    per_query: dict[str, list] = {}
    for hit in state.get("search_hits", []):
        per_query.setdefault(hit.query, []).append(hit)
    ordered: list = []
    seen_urls: set[str] = set()
    for row in zip_longest(*per_query.values()):
        for hit in row:
            if hit is None or hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            ordered.append(hit)

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
        if hit.url not in existing_seeds
        and hit.url not in known_dead
        and hit.url not in already_picked
    ]
    if known_dead:
        skipped_dead = sum(1 for hit in ordered if hit.url in known_dead)
        if skipped_dead:
            await _record(
                runtime, "memory", node="rank", outcome="ok",
                detail=f"skipped {skipped_dead} URL(s) earlier runs found empty",
            )

    # Every fetch launches at once, so the budget cannot be checked between them
    # the way a loop could. The number of sites is cut to what the remaining
    # budget covers before any of them start.
    # Fetching spends scrapes, so scrapes are what caps the site count. Sizing
    # on tool calls instead let a re-plan pick five sites with no scrape budget
    # left: every one came back with zero pages, after paying for the ranking.
    scrape_room = max(0, runtime.budget.max_scrapes - runtime.budget.scrapes)
    # Each site also costs one link choice and one analysis.
    llm_room = max(0, runtime.budget.max_llm_calls - runtime.budget.llm_calls)
    tool_room = max(0, runtime.budget.remaining - MIN_CALLS_AFTER_RESEARCH)
    seats = min(
        runtime.limits.max_candidates,
        scrape_room // max(1, runtime.limits.max_pages_per_seed),
        llm_room // CALLS_PER_SITE,
        tool_room // (runtime.limits.max_pages_per_seed + CALLS_PER_SITE),
    )

    # The model ranks the pool best-first; search-engine order only sets the
    # order it reads them in. Code takes the top of that ranking and does
    # nothing else to it — no score, no threshold, no keyword test.
    chosen: list[tuple[object, str]] = []
    if runtime.dry_run:
        # No model in a dry run; search order stands in so the graph still runs.
        chosen = [(hit, "dry run: search order") for hit in ranked[:seats]]
    elif ranked and seats:
        refusal = runtime.budget.refusal("shortlist")
        if refusal:
            raise RuntimeError(f"ranking could not run, run stopped: {refusal}")
        runtime.budget.consume("shortlist")
        try:
            ranked_shortlist, observation = await _shortlist(
                ranked, state["memory"], today, runtime
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.failures.append(f"ranking failed: {detail}")
            await _record(
                runtime, "shortlist", node="rank", outcome="failed",
                considered=len(ranked), detail=detail,
            )
            raise RuntimeError(f"ranking failed, run stopped: {detail}") from exc
        chosen = ranked_shortlist[:seats]
        await _record(
            runtime, "shortlist", node="rank", outcome="ok",
            considered=len(ranked), observation=observation,
            # The whole ranking is recorded, so near-misses below the cut stay visible.
            picked=[
                {
                    "url": hit.url, "title": hit.title, "reason": reason,
                    "rank": position, "fetched": position <= len(chosen),
                }
                for position, (hit, reason) in enumerate(ranked_shortlist, 1)
            ],
        )

    picks = [
        RankedPick(hit=hit, reason=reason, rank=position)
        for position, (hit, reason) in enumerate(chosen, 1)
    ]
    if not picks:
        if (
            not state["supplied_queries"]
            and state["replan_count"] <= 1
            and runtime.budget.remaining > MIN_CALLS_AFTER_RESEARCH
        ):
            return Command(
                update={"replan_count": state["replan_count"] + 1}, goto="plan"
            )
        return Command(goto="evaluate")

    # One fetch per site, all started together. Each carries the reason this
    # site was chosen, which the single research step used to compute and drop.
    return Command(
        update={"picks": picks},
        goto=[
            Send(
                "fetch",
                {
                    "pick": pick,
                    "as_of_date": state["as_of_date"],
                    "memory": state["memory"],
                },
            )
            for pick in picks
        ],
    )


async def fetch_node(payload: dict, *, services: WorkflowRuntime) -> Command:
    """Get the pages for ONE site. One instance runs per site, in parallel."""
    runtime = services
    pick: RankedPick = payload["pick"]
    today = date.fromisoformat(payload["as_of_date"])
    choose_links = None if runtime.dry_run else _link_chooser(runtime, today)
    try:
        bundle = await resolve_evidence_bundle(
            pick.hit, runtime, partial(_record, runtime),
            choose_links=choose_links,
        )
    except Exception as exc:  # noqa: BLE001 — one dead site must not stop the rest
        detail = f"{type(exc).__name__}: {exc}"[:300]
        runtime.failures.append(f"fetch {pick.hit.url}: {detail}")
        await _record(
            runtime, "scrape", node="fetch", url=pick.hit.url,
            outcome="failed", detail=detail,
        )
        return Command(
            update={
                "analysis_errors": [{"seed_url": pick.hit.url, "detail": detail}],
                "analyzed_seeds": [pick.hit.url],
            },
            goto="evaluate",
        )
    if bundle.duplicate_of:
        return Command(
            update={
                "analyzed_seeds": [bundle.seed_url],
                "rejected": [{
                    "url": bundle.seed_url, "title": pick.hit.title,
                    "reason": f"same page as {bundle.duplicate_of}",
                    "stage": "duplicate",
                }],
            },
            goto="evaluate",
        )
    return Command(
        update={"evidence_bundles": [bundle]},
        goto=Send("extract", {**payload, "bundle": bundle}),
    )


def _bundle_prompt(
    bundle: EvidenceBundle, today: str, memory: str, picked_because: str,
    focus_noun: str, constraints: str,
) -> str:
    evidence = bundle.bounded_text(ANALYSIS_PAGE_CHARS)
    return f"""## Objective
These pages were all fetched from ONE site. Today is {today}. Identify the
distinct {focus_noun} on it and decide pursue or skip for each. An event and an
award on the same site are different entities.

## What you are given
The pages below, in full. This is evidence — read it directly.
Why this site was picked: "{picked_because}". That is a hypothesis from a search
extract, not a finding. Confirm or contradict it from the pages.
CONSTRAINTS: who may enter as this business, and what it does not seek.
The BUSINESS block: everything else about it.

## How many candidates to emit
One programme, one candidate. Categories sharing an entry process, a deadline
and one set of conditions are one programme — emit the umbrella candidate and
name the categories in its reason.

    25 categories, one entry form   ->  ONE candidate
    a forum and its awards          ->  TWO candidates

This decides HOW MANY, never whether to pursue. An umbrella programme with many
categories is normal and is not a reason to skip.

## Pursue or skip
1. Is its next edition still ahead? Pursue anything still to come, even if entry
   has not opened and no dates are announced — "express interest", or only a
   future event date, is exactly what this is for. Skip only when the edition
   has demonstrably passed or its entry window has demonstrably closed.
2. Could this business be the entrant? Judge against CONSTRAINTS: entrant
   type and market. Judge the entrant the programme wants, not the topic it
   covers. Skip if the page restricts entry to a party or market CONSTRAINTS
   exclude.

Skip anything CONSTRAINTS list as not sought. Do not skip because one category
fits poorly when another is a realistic route. Emit at least one decision —
skip when the site holds nothing relevant.

## Did we read the programme's own page?
Set `page_belongs_to_programme` false when the pages only MENTION it — a
directory, index, event calendar, roundup, news article or press release. A name
in a list is a lead, not a record: the organising body, the conditions and the
dates would all be guesses. Set it true only when a page belonging to the
programme itself was among the pages read. A directory is never a candidate in
its own right.

## Entry eligibility — the heart of this
List every stated condition an entrant must satisfy, each as its own item, in
the words the page uses. If the page states no conditions, return an empty list
— never a sentence saying there are none, and never the event's audience or
attendee description. Do not summarise them into one line and do not invent
conditions the page does not state. Keep judging criteria (what the entry is
scored on) and application requirements (what must be submitted) in their own
separate lists.

Use category "research" for a venue that accepts submitted work — a call for
papers, a workshop, an industry track, a technical competition. These state no
conditions on who may enter, because anyone may; what decides whether it is
worth entering is whether the work fits. So for a research venue, entry
eligibility is the SCOPE: the topics, tracks and problem areas the venue says it
wants, each as its own item, in the page's own words. Submission format, page
limits and anonymity rules are application requirements, not eligibility.

## Values to read off the page
  organizing_body   who RUNS it. The page identifies them in a sentence, in a
                    heading, or by the site's own name where the site belongs to
                    the programme — any of those counts. Never a sponsor,
                    partner, platform, venue or "powered by" name, and never a
                    name that appears on the page without being identified as
                    the organiser. Leave it empty only when the pages give you
                    nothing that identifies who runs it.
  domain            the field the programme is about, in the page's own words
                    (for example "robotics", "public health", "climate
                    innovation"). Empty when the page does not say.
  summary           what it is and what taking part means, in one or two
                    sentences from the pages.
  base_title        the title with year and edition markers stripped, nothing
                    else removed.
  cycle_year        the year of THIS edition.
  status            "open", "closed" or "unclear".
  submission_deadline, event_date   "YYYY-MM-DD" or null.
  deadline_note     set when the deadline is rolling or relative.
  confidence_note   anything you were unsure about.

Use only what the pages say; never infer a deadline that is not written there. A
deadline's year may be taken from the page title or its publication date when
the deadline itself gives only a day and month.

Set `source_url` to the most specific entry, eligibility or guidelines page
among those read.

## Quotes
For organizing_body, submission_deadline and status, copy the exact text you
read each one from into its quote field, verbatim from the pages below — the
browser title and headings count as page text, not just body sentences.

CONSTRAINTS:
{constraints}

BUSINESS:
{memory}

{evidence}
"""


async def _analyze_bundle(
    bundle: EvidenceBundle,
    as_of_date: str,
    memory: str,
    picked_because: str,
    runtime: WorkflowRuntime,
) -> list[CandidateVerdict]:
    runtime.budget.consume("analyze")
    parsed = await _structured(
        runtime,
        _AnalysisModel,
        "opportunity_candidate_analysis",
        "Return candidate decisions as strict JSON matching the supplied schema.",
        _bundle_prompt(
            bundle, as_of_date, memory, picked_because, _focus_noun(runtime),
            _constraints(runtime),
        ),
        max_tokens=TOKENS_ANALYZE,
        salvage_key="candidates",
        salvage_model=_CandidateModel,
    )
    valid_urls = set(bundle.source_urls)
    candidates: list[CandidateVerdict] = []
    for item in parsed.candidates:
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
                domain=item.domain,
                summary=item.summary,
                base_title=item.base_title,
                cycle_year=item.cycle_year,
                status=item.status,
                submission_deadline=item.submission_deadline,
                deadline_note=item.deadline_note,
                event_date=item.event_date,
                confidence_note=item.confidence_note,
                body_quote=item.body_quote,
                deadline_quote=item.deadline_quote,
                status_quote=item.status_quote,
                entry_eligibility=tuple(item.entry_eligibility),
                judging_criteria=tuple(item.judging_criteria),
                application_requirements=tuple(item.application_requirements),
            )
        )
    return candidates


def _squash(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def _grounding(candidate: CandidateVerdict, evidence: str) -> list[GroundedField]:
    """Did the sentence the model says it read actually appear on the page?

    This does not look for the value in the text — that is word matching, and it
    fails both ways ("PRCA" matches "practical", "Times Internet" misses "TOI").
    It checks the model's OWN quote, which it had to copy to produce. Measured
    and stored; nothing is rejected on it.
    """
    page = _squash(evidence)
    fields = (
        ("organizing_body", candidate.organizing_body, candidate.body_quote),
        ("submission_deadline", candidate.submission_deadline or "",
         candidate.deadline_quote),
        ("status", candidate.status, candidate.status_quote),
    )
    out: list[GroundedField] = []
    for name, value, quote in fields:
        if not value:
            continue
        squashed = _squash(quote)
        out.append(
            GroundedField(
                field=name, value=str(value), quote=quote,
                found=bool(squashed) and squashed in page,
            )
        )
    return out


async def _prepare(
    candidate: CandidateVerdict,
    bundle: EvidenceBundle,
    runtime: WorkflowRuntime,
    today: date,
) -> tuple[PreparedRecord | None, dict | None]:
    """Turn one pursued candidate into a validated record, or say why not."""
    canonical_page = next(
        (page for page in bundle.pages if page.url == candidate.source_url),
        bundle.pages[0],
    )
    evidence_text = bundle.extraction_text(
        candidate.supporting_urls, candidate.source_url
    )
    # No second model call. Analyze already read this evidence and produced the
    # listing; this validates it into a record — edition strip on the identity
    # key, deadline grounded against the source text, pydantic validation,
    # typed failures. None of the parts the model had already decided once.
    organiser = (candidate.organizing_body or "").strip()
    if not organiser:
        runtime.warnings.append(
            f"{candidate.source_url}: the page never says who runs this"
        )
    result = build_record(
        {
            "status": candidate.status,
            "title": candidate.target_title,
            "organizing_body": organiser or ORGANISER_NOT_STATED,
            "domain": candidate.domain,
            "summary": candidate.summary,
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
        # `opportunity_closed` is the pipeline working: the page said entry has
        # closed and we believed it. Counting it as a run failure made a run
        # that correctly identified four past cycles report "Failed".
        if result.reason is not FailureReason.OPPORTUNITY_CLOSED:
            runtime.failures.append(f"{candidate.source_url}: {result.reason.value}")
        await record_extraction_failure(
            runtime.db, candidate.source_url, result.reason.value,
            result.detail, runtime.model, runtime.trace_url,
        )
        await _record(
            runtime, "extract", node="extract", url=candidate.source_url,
            title=candidate.target_title, outcome="failed",
            reason=result.reason.value, detail=result.detail[:300],
        )
        return None, {
            "url": candidate.source_url,
            "title": candidate.target_title,
            "reason": result.detail[:300],
            "stage": "extraction",
        }

    # Analyze read the evidence and listed the entry conditions; this pulls the
    # record's own values off the page. One read produces the conditions, not
    # two — re-deriving them here once overwrote six conditions with none.
    result = result.model_copy(
        update={"eligibility_criteria": list(candidate.entry_eligibility)}
    )
    completeness = assess_completeness(
        result, evidence_text, source_count=len(bundle.pages)
    )
    await _record(
        runtime, "extract", node="extract", url=candidate.source_url,
        outcome="ok", completeness=completeness.as_dict(),
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
        result, evidence_text, today=today,
        source_url=candidate.source_url,
        source_title=canonical_page.title,
        target_status_code=canonical_page.status_code,
    )
    if actionability.status != "actionable":
        reason = "; ".join(actionability.reasons)
        await _record(
            runtime, "actionability", node="extract", url=candidate.source_url,
            title=result.title, outcome=actionability.status, reason=reason,
        )
        rejection = {
            "url": candidate.source_url,
            "title": result.title,
            "reason": reason,
            "stage": "actionability",
            "status": actionability.status,
        }
        # Any date at all is worth recording. Requiring a submission deadline
        # meant a programme that published only an event date taught the
        # registry nothing — two ICEF editions were lost that way in one run.
        # Carried to `store`, which owns every write to Mongo.
        if actionability.status == "historical" and (
            result.submission_deadline or result.event_date
        ):
            rejection["edition"] = {
                "organizing_body": result.organizing_body,
                "base_title": result.base_title,
                "cycle_year": result.cycle_year,
                "submission_deadline": result.submission_deadline,
                "event_date": result.event_date,
            }
        return None, rejection

    grounding = _grounding(candidate, evidence_text)
    ungrounded = [item.field for item in grounding if not item.found]
    if ungrounded:
        runtime.warnings.append(
            f"{candidate.source_url}: could not find the quoted sentence for "
            f"{', '.join(ungrounded)}"
        )
    await _record(
        runtime, "grounding", node="extract", url=candidate.source_url,
        title=result.title,
        outcome="ok" if not ungrounded else "partial",
        fields=[
            {"field": i.field, "value": i.value, "quote": i.quote, "found": i.found}
            for i in grounding
        ],
    )

    return PreparedRecord(
        record=result,
        seed_url=candidate.seed_url,
        source_url=candidate.source_url,
        evidence_urls=bundle.source_urls,
        completeness=completeness.as_dict(),
        judging_criteria=list(candidate.judging_criteria),
        application_requirements=list(candidate.application_requirements),
        unfollowed_links=list(bundle.unfollowed[:20]),
        grounding=grounding,
        warnings=record_warnings(result),
    ), None


async def extract_node(payload: dict, *, services: WorkflowRuntime) -> dict:
    """Read ONE site: name the opportunities on it and validate each into a record."""
    runtime = services
    bundle: EvidenceBundle = payload["bundle"]
    pick: RankedPick = payload["pick"]
    today = date.fromisoformat(payload["as_of_date"])

    base = {"analyzed_seeds": [bundle.seed_url]}

    # A near-empty bundle means the fetch failed, not that the page had nothing
    # to say. Attribute it to the scrape so the failure points at the stage that
    # actually broke, and do not pay for a model call on it.
    evidence_chars = len(bundle.combined_text.strip())
    if evidence_chars < MIN_BUNDLE_CHARS:
        detail = (
            "Firecrawl returned no page; its error is on the Fetch step"
            if not bundle.pages else
            f"pages held {evidence_chars} chars, under our {MIN_BUNDLE_CHARS}-char "
            "minimum for analysis"
        )
        runtime.failures.append(f"scrape {bundle.seed_url}: {detail}")
        await _record(
            runtime, "scrape", node="extract", url=bundle.seed_url,
            outcome="insufficient", chars=evidence_chars, detail=detail,
            source="firecrawl" if not bundle.pages else "pipeline",
        )
        return base | {
            "analysis_errors": [{"seed_url": bundle.seed_url, "detail": detail}]
        }

    if runtime.dry_run:
        candidates = [
            CandidateVerdict(
                seed_url=bundle.seed_url,
                source_url=bundle.seed_url,
                target_title="National Circular Economy Award 2027",
                category="award",
                supporting_urls=tuple(bundle.source_urls),
                decision="pursue",
                reason="Open synthetic fixture",
                # Taken from the fixture page. Left blank, the stub could never
                # pass validation, so the dry run reported the full loop as
                # broken every time and proved nothing past the scrape.
                organizing_body="National Circular Economy Foundation",
                base_title="National Circular Economy Award",
                cycle_year=2027,
                status="open",
                submission_deadline="2027-11-30",
                body_quote=(
                    "The National Circular Economy Foundation invites entries "
                    "from companies advancing material circularity."
                ),
                deadline_quote="The last date for submissions is 30 November 2027.",
                status_quote="The last date for submissions is 30 November 2027.",
                entry_eligibility=(
                    "Companies registered and operating in India",
                    "At least three years of operating history",
                ),
            )
        ]
    else:
        if runtime.budget.refusal("analyze"):
            return base | {
                "analysis_errors": [
                    {"seed_url": bundle.seed_url,
                     "detail": runtime.budget.refusal("analyze")}
                ]
            }
        try:
            candidates = await _analyze_bundle(
                bundle, payload["as_of_date"], payload["memory"], pick.reason, runtime
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.failures.append(f"analysis {bundle.seed_url}: {detail}")
            return base | {
                "analysis_errors": [{"seed_url": bundle.seed_url, "detail": detail}]
            }

    await _record(
        runtime, "analyze", node="extract", url=bundle.seed_url,
        outcome="ok" if candidates else "empty",
        picked_because=pick.reason,
        candidates=[
            {
                "seed_url": bundle.seed_url,
                "url": item.source_url,
                "title": item.target_title,
                "category": item.category,
                "decision": item.decision,
                "reason": item.reason,
                "summary": item.summary,
                "organizing_body": item.organizing_body,
                "domain": item.domain,
                "cycle_year": item.cycle_year,
                "status": item.status,
                "submission_deadline": item.submission_deadline,
                "deadline_note": item.deadline_note,
                "event_date": item.event_date,
                "confidence_note": item.confidence_note,
                "quotes": {
                    "organiser": item.body_quote,
                    "deadline": item.deadline_quote,
                    "status": item.status_quote,
                },
                "supporting_urls": list(item.supporting_urls),
                "entry_eligibility": list(item.entry_eligibility),
                "judging_criteria": list(item.judging_criteria),
                "application_requirements": list(item.application_requirements),
            }
            for item in candidates
        ],
    )

    records: list[PreparedRecord] = []
    rejected: list[dict] = []
    for candidate in candidates:
        if candidate.decision == "skip":
            # Already recorded by the analyse call above, which made the
            # decision. Kept here only so the journey shows what was dropped.
            rejected.append(
                {
                    "url": candidate.source_url,
                    "title": candidate.target_title,
                    "reason": candidate.reason,
                    "stage": "analysis",
                }
            )
            continue
        if not bundle.pages:
            continue
        prepared, rejection = await _prepare(candidate, bundle, runtime, today)
        if prepared is not None:
            records.append(prepared)
        if rejection is not None:
            rejected.append(rejection)

    return base | {
        "candidates": candidates,
        "records": records,
        "rejected": rejected,
    }


def _feasibility_context(result) -> str:
    """What the eligibility call is being asked to judge.

    A research venue's conditions are its scope, not entry rules, so it is told
    that rather than left to infer it from topic strings that read nothing like
    an eligibility list.
    """
    context = f"{result.title} — {result.organizing_body}"
    if result.category == "research":
        return (
            f"{context} (an opportunity that accepts submitted work; the conditions "
            "below are the topics it wants, so judge whether this business has "
            "work that fits)"
        )
    return context


async def evaluate_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    """Judge each prepared record against the business profile, condition by condition.

    Runs before anything is written, so a record reaches Mongo once, already
    carrying its verdict. It used to be judged after saving, which meant the run
    reported success before anything had been judged at all.
    """
    runtime = services
    judged = {item["key"] for item in state.get("verdicts", [])}
    verdicts: list[dict] = []

    for prepared in state.get("records", []):
        if prepared.key in judged:
            continue
        result = prepared.record
        if not result.eligibility_criteria:
            # Real, but with nothing to judge. Counted apart from saved rather
            # than passed off as a finished find.
            verdicts.append(
                {
                    "key": prepared.key,
                    "verdict": None,
                    "note": "the page states no entry conditions",
                }
            )
            continue
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
            verdicts.append({"key": prepared.key, "verdict": verdict.model_dump()})
            await _record(
                runtime, "feasibility", node="evaluate",
                url=prepared.source_url, title=result.title, outcome="ok",
                counts=verdict.counts, confidence=verdict.confidence,
                qualitative=len(verdict.qualitative_notes),
                criteria_results=[r.model_dump() for r in verdict.criteria_results],
                qualitative_notes=[n.model_dump() for n in verdict.qualitative_notes],
            )
        except Exception as exc:  # noqa: BLE001 — one bad verdict must not stop the run
            detail = f"{type(exc).__name__}: {exc}"[:300]
            runtime.failures.append(f"feasibility {prepared.source_url}: {detail}")
            verdicts.append(
                {"key": prepared.key, "verdict": None, "note": detail}
            )
            await _record(
                runtime, "feasibility", node="evaluate",
                url=prepared.source_url, title=result.title,
                outcome="failed", detail=detail,
            )

    # Incremented here rather than in `extract`: extract runs once per site in
    # parallel, so N empty sites would count as N re-plans. This is the one
    # place that sees the whole run at once.
    return {
        "verdicts": verdicts,
        "replan_count": state["replan_count"] + (0 if state.get("records") else 1),
    }


def route_after_evaluate(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> str:
    runtime = services
    if state.get("records") or state.get("analysis_errors"):
        return "store"
    if (
        not state["supplied_queries"]
        and state["replan_count"] <= 1
        and runtime.budget.remaining > MIN_CALLS_AFTER_RESEARCH
    ):
        return "plan"
    return "store"


async def store_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    """Write each record once, with its verdict, plus the registry side-effects."""
    runtime = services
    verdicts = {item["key"]: item for item in state.get("verdicts", [])}

    for prepared in state.get("records", []):
        result = prepared.record
        judged = verdicts.get(prepared.key, {})
        verdict = judged.get("verdict")
        ready = bool(result.eligibility_criteria)
        payload = result.model_dump()
        payload.update(
            {
                "record_state": "ready" if ready else "needs_deeper_read",
                "unfollowed_links": prepared.unfollowed_links,
                "actionability": "actionable",
                "evidence_urls": prepared.evidence_urls,
                "extraction_completeness": prepared.completeness,
                "discovery_run_id": runtime.run_id,
                # The analyser already separates these three. They are the
                # details someone would otherwise dig through the award site to
                # find: what you are judged on, and what you have to submit.
                "judging_criteria": prepared.judging_criteria,
                "application_requirements": prepared.application_requirements,
                # Whether each value was quoted from the page. Stored so the
                # rate can be read off real runs; it gates nothing.
                "grounding": [
                    {"field": i.field, "value": i.value,
                     "quote": i.quote, "found": i.found}
                    for i in prepared.grounding
                ],
            }
        )
        if runtime.dry_run:
            payload["dry_run"] = True
            payload["synthetic"] = "DRY-RUN FIXTURE — not a real opportunity"
        saved = await save_opportunity(runtime.db, payload)

        if verdict:
            await attach_eligibility(
                runtime.db, verdict,
                organizing_body=result.organizing_body,
                base_title=result.base_title,
                cycle_year=result.cycle_year,
            )
        if ready:
            runtime.saved.append(prepared.source_url)
            await clear_dead_end(runtime.db, prepared.source_url)
        else:
            runtime.needs_deeper.append(prepared.source_url)
            await record_dead_end(
                runtime.db, prepared.source_url,
                "fetched and extracted, but the page states no entry conditions",
                result.title,
            )
        runtime.warnings.extend(
            f"{prepared.source_url}: {warning}" for warning in prepared.warnings
        )
        await clear_extraction_failure(runtime.db, prepared.source_url)
        await _record(
            runtime, "save_opportunity", node="store", url=prepared.source_url,
            outcome="ok", action=saved.action, title=result.title,
            completeness=prepared.completeness, warnings=prepared.warnings,
        )

    # Past editions teach the registry when a programme usually opens, so they
    # are worth keeping even though they are not opportunities.
    for rejection in state.get("rejected", []):
        edition = rejection.get("edition")
        if not edition:
            continue
        await record_edition(
            runtime.db, edition["organizing_body"], edition["base_title"],
            edition["cycle_year"], edition["submission_deadline"],
            edition["event_date"],
        )
        runtime.historical.append(rejection["url"])

    summary = (
        f"Discovery researched {len(state.get('evidence_bundles', []))} candidate "
        f"bundle(s), saved {len(runtime.saved)} actionable opportunity(ies), "
        f"recorded {len(runtime.historical)} historical edition(s), and rejected "
        f"{len(state.get('rejected', []))} candidate(s)."
    )
    return {"summary": summary}


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


# Our own state types, so they come back as themselves after being saved rather
# than as plain dictionaries.
_STATE_TYPES = [
    ("opportunity_radar.discovery.state", name)
    for name in (
        "PlannedQuery", "SearchHit", "EvidencePage",
        "EvidenceBundle", "CandidateVerdict", "RankedPick",
        "GroundedField", "PreparedRecord",
    )
# The record itself travels inside PreparedRecord. Left off this list it comes
# back as a plain dictionary, and the step that reads it breaks on the field
# access rather than on the restore, which is much harder to trace.
] + [("opportunity_radar.extraction.schema", "OpportunityRecord")]
_SERDE = JsonPlusSerializer(
    allowed_msgpack_modules=_STATE_TYPES,
    allowed_json_modules=_STATE_TYPES,
)


@lru_cache(maxsize=1)
def _progress_saver():
    """Where a run's finished steps are kept so it can resume after a failure.

    Mongo, so progress outlives a server restart. Falls back to memory if Mongo
    is unreachable: a run that cannot save progress should still run.
    """
    try:
        config = MongoConfig.from_env()
        saver = MongoDBSaver(
            client=MongoClient(config.uri, serverSelectionTimeoutMS=3_000),
            db_name=config.database,
            checkpoint_collection_name="run_progress",
            writes_collection_name="run_progress_writes",
            serde=_SERDE,
        )
        next(saver.list(None, limit=1), None)  # fail here, not mid-run
        return saver
    except Exception:  # noqa: BLE001
        return InMemorySaver(serde=_SERDE)


# Where the two Command-returning nodes can send control. Declared because a
# Command goto is decided at runtime, so the graph cannot infer these edges.
_DESTINATIONS = {
    "rank": ("fetch", "plan", "evaluate"),
    "fetch": ("extract", "evaluate"),
}


def build_discovery_graph(runtime: WorkflowRuntime):
    """One job per node, so a failure names the step that actually broke.

    `fetch` and `extract` run once per site rather than looping inside one step:
    rank fans out with Send, and each fetch hands its own site straight to its
    own extract. `evaluate` is the single fan-in, which is why the re-plan
    decision lives there — it is the one point that sees the whole run at once.
    """
    builder = StateGraph(DiscoveryState)
    for name, fn in (
        ("plan", plan_queries_node),
        ("search", search_node),
        ("rank", rank_node),
        ("fetch", fetch_node),
        ("extract", extract_node),
        ("evaluate", evaluate_node),
        ("store", store_node),
    ):
        builder.add_node(
            name, _traced_node(name, fn, runtime),
            destinations=_DESTINATIONS.get(name),
        )
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "search")
    builder.add_edge("search", "rank")
    builder.add_edge("extract", "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        partial(route_after_evaluate, services=runtime),
        {"plan": "plan", "store": "store"},
    )
    builder.add_edge("store", END)
    return builder.compile(checkpointer=_progress_saver())
