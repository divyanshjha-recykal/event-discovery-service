"""Bounded Plan -> Research -> Analyze -> Finalize Discovery graph."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from functools import partial
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from ..config import discovery_temperature
from ..extraction import ExtractionFailure, extract as extract_page, record_warnings
from ..storage import (
    append_event,
    clear_extraction_failure,
    due_soon,
    known_orgs,
    record_edition,
    record_extraction_failure,
    save_opportunity,
)
from ..tracing import chat_model, stage_span, trace_handler
from .actionability import assess_actionability, assess_completeness
from .link_resolver import canonicalize_url, rank_search_hit, resolve_evidence_bundle
from .profile_seed import discovery_seed
from .providers import tavily_search
from .state import (
    CandidateVerdict,
    DiscoveryState,
    EvidenceBundle,
    PlannedQuery,
    WorkflowRuntime,
)

MAX_OUTPUT_TOKENS = 4096
MAX_RESEARCH_CANDIDATES = 3
MIN_CANDIDATE_SCORE = 3.0
ANALYSIS_BUNDLE_CHARS = 12_000
MIN_CALLS_AFTER_RESEARCH = 3


class _PlannedQueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    intent: Literal["award", "grant", "event", "conference", "mixed"]
    geography: str
    target_year: int
    rationale: str


class _QueryPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[_PlannedQueryModel] = Field(min_length=3, max_length=5)


class _CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_url: str = Field(max_length=2_000)
    source_url: str = Field(max_length=2_000)
    target_title: str = Field(max_length=250)
    category: Literal["award", "grant", "event", "conference"]
    supporting_urls: list[Annotated[str, Field(max_length=2_000)]] = Field(
        max_length=5
    )
    decision: Literal["pursue", "skip"]
    reason: str = Field(max_length=600)
    entry_eligibility: list[Annotated[str, Field(max_length=500)]] = Field(
        max_length=12
    )
    judging_criteria: list[Annotated[str, Field(max_length=500)]] = Field(
        max_length=12
    )
    application_requirements: list[
        Annotated[str, Field(max_length=500)]
    ] = Field(max_length=12)


class _AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[_CandidateModel] = Field(max_length=5)


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


def _llm(runtime: WorkflowRuntime):
    kwargs: dict = {
        "max_tokens": MAX_OUTPUT_TOKENS,
        "timeout": 120,
        "max_retries": 3,
    }
    temperature = discovery_temperature()
    if temperature is not None:
        kwargs["temperature"] = temperature
    return chat_model(runtime.model, **kwargs)


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
        await append_event(runtime.db, runtime.run_id, event)
    except Exception:  # noqa: BLE001
        pass


async def _memory(runtime: WorkflowRuntime) -> str:
    orgs = await known_orgs(runtime.db)
    upcoming = await due_soon(runtime.db, lookahead_months=2)
    programs = "\n".join(
        f"- {item['organizing_body']} — {item['base_title']}"
        for item in upcoming
    ) or "(none due soon)"
    return (
        f"{discovery_seed()}\n\nKnown organizing bodies: "
        f"{', '.join(orgs) if orgs else '(none)'}\n"
        f"Programs due soon:\n{programs}"
    )


def _fallback_queries(today: date) -> list[PlannedQuery]:
    next_year = today.year + 1
    return [
        PlannedQuery(
            f"circular economy awards {today.year} {next_year} call for entries India",
            "award",
            "India",
            today.year,
            "Core circular-economy recognition",
        ),
        PlannedQuery(
            f"waste management sustainability awards {next_year} nominations India",
            "award",
            "India",
            next_year,
            "Next-cycle waste and sustainability awards",
        ),
        PlannedQuery(
            f"EPR recycling innovation grants {today.year} {next_year} applications open",
            "grant",
            "India and Middle East",
            today.year,
            "Funding relevant to EPR and recycling technology",
        ),
        PlannedQuery(
            f"circular economy awards {next_year} call for entries Middle East Gulf",
            "award",
            "Middle East",
            next_year,
            "Recognition aligned with Recykal's regional expansion",
        ),
    ]


async def plan_queries_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services
    today = date.fromisoformat(state["as_of_date"])
    memory = state.get("memory") or await _memory(runtime)

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
        prompt = f"""Today is {today.isoformat()}.
Plan 3-5 non-overlapping web searches for currently actionable awards, grants,
events or conferences relevant to the business memory below. Prioritize calls
whose deadline has not passed and next-cycle programmes. Do not search past
years. Cover India and the Middle East and vary sector/opportunity type.

This is replanning attempt {state['replan_count']}. Earlier searches or evidence:
{[hit.query for hit in state.get('search_hits', [])][-8:]}

Business memory:
{memory}
"""
        try:
            refusal = runtime.budget.refusal("plan")
            if refusal:
                raise RuntimeError(refusal)
            runtime.budget.consume("plan")
            response = await asyncio.to_thread(
                _llm(runtime).invoke,
                [
                    SystemMessage(
                        "Return a precise search plan as JSON matching the supplied schema."
                    ),
                    HumanMessage(prompt),
                ],
                config={"callbacks": [trace_handler()]},
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "opportunity_query_plan",
                        "strict": True,
                        "schema": _QueryPlanModel.model_json_schema(),
                    },
                },
            )
            parsed = _QueryPlanModel.model_validate(_parse_json(response.content))
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
            runtime.warnings.append(
                f"query planning fell back to deterministic plan: {type(exc).__name__}: {exc}"
            )

    await _record(
        runtime,
        "plan",
        node="plan",
        outcome="ok",
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


async def research_node(
    state: DiscoveryState, *, services: WorkflowRuntime
) -> dict:
    runtime = services

    async def record_research(tool: str, **fields: object) -> None:
        await _record(runtime, tool, **fields)

    hits = list(state.get("search_hits", []))
    seen_queries = {hit.query for hit in hits}
    for planned in state["planned_queries"]:
        if planned.query in seen_queries:
            continue
        refusal = runtime.budget.refusal("search")
        if refusal:
            break
        runtime.budget.consume("search")
        try:
            found = await tavily_search(
                planned.query, dry_run=runtime.dry_run
            )
            hits.extend(found)
            await _record(
                runtime,
                "search",
                node="research",
                query=planned.query,
                outcome="ok" if found else "empty",
                results=[
                    {"title": item.title, "url": item.url, "snippet": item.snippet}
                    for item in found
                ],
            )
        except Exception as exc:  # noqa: BLE001
            runtime.failures.append(f"search {planned.query!r}: {type(exc).__name__}")
            await _record(
                runtime,
                "search",
                node="research",
                query=planned.query,
                outcome="failed",
                detail=f"{type(exc).__name__}: {exc}"[:300],
            )

    current_year = date.fromisoformat(state["as_of_date"]).year
    by_url = {}
    for hit in hits:
        canonical_url = canonicalize_url(hit.url)
        scored = type(hit)(
            hit.title,
            canonical_url,
            hit.snippet,
            hit.query,
            rank_search_hit(hit, current_year=current_year),
        )
        previous = by_url.get(canonical_url)
        if previous is None or scored.score > previous.score:
            by_url[canonical_url] = scored
    ranked = sorted(by_url.values(), key=lambda item: (-item.score, item.url))

    existing_seeds = {bundle.seed_url for bundle in state.get("evidence_bundles", [])}
    bundles = list(state.get("evidence_bundles", []))
    added = 0
    for hit in ranked:
        if hit.url in existing_seeds or added >= MAX_RESEARCH_CANDIDATES:
            continue
        if hit.score < MIN_CANDIDATE_SCORE:
            continue
        if runtime.budget.remaining <= MIN_CALLS_AFTER_RESEARCH:
            break
        bundle = await resolve_evidence_bundle(hit, runtime, record_research)
        if bundle.pages:
            bundles.append(bundle)
            existing_seeds.add(hit.url)
            added += 1

    return {"search_hits": list(by_url.values()), "evidence_bundles": bundles}


def _bundle_prompt(bundle: EvidenceBundle, today: str, memory: str) -> str:
    evidence = bundle.combined_text[:ANALYSIS_BUNDLE_CHARS]
    return f"""Today is {today}. Analyze these researched official-page bundles.
Be concise: return at most five entities, short reasons, and only criteria
explicitly supported by the evidence.
Identify distinct opportunity entities; an event and an award on one site are
different entities. Pursue only a currently open/currently actionable entity.
Skip entities whose explicit entry eligibility excludes this business (for
example student-only or individual-only programmes). Do not skip merely because
some category is a poor fit when another category provides a realistic route.
Prefer the umbrella award programme over one category/track when they share one
entry process. Emit a separate track only when it is independently entered and
has materially different entry eligibility. For every seed bundle, emit at
least one decision; use a skip decision when it contains no relevant entity.
Use a specific application/guidelines page as source_url when available.
Separate judging criteria and application-document requirements from entry
eligibility. Never treat a past edition as a current opportunity.

BUSINESS MEMORY:
{memory}

{evidence}
"""


async def _analyze_bundle(
    bundle: EvidenceBundle,
    state: DiscoveryState,
    runtime: WorkflowRuntime,
) -> list[CandidateVerdict]:
    runtime.budget.consume("analyze")
    response = await asyncio.to_thread(
        _llm(runtime).invoke,
        [
            SystemMessage(
                "Return candidate decisions as strict JSON matching the supplied schema."
            ),
            HumanMessage(
                _bundle_prompt(
                    bundle,
                    state["as_of_date"],
                    state["memory"],
                )
            ),
        ],
        config={"callbacks": [trace_handler()]},
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "opportunity_candidate_analysis",
                "strict": True,
                "schema": _AnalysisModel.model_json_schema(),
            },
        },
    )
    parsed = _AnalysisModel.model_validate(_parse_json(response.content))
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
            rejected.append(
                {
                    "url": candidate.source_url,
                    "title": candidate.target_title,
                    "reason": candidate.reason,
                    "stage": "analysis",
                }
            )
            await _record(
                runtime,
                "skip",
                node="finalize",
                url=candidate.source_url,
                title=candidate.target_title,
                outcome="skipped",
                reason=candidate.reason,
            )
            continue

        bundle = bundles.get(candidate.seed_url)
        if bundle is None:
            continue
        refusal = runtime.budget.refusal("extract")
        if refusal:
            rejected.append(
                {
                    "url": candidate.source_url,
                    "title": candidate.target_title,
                    "reason": refusal,
                    "stage": "budget",
                }
            )
            continue
        runtime.budget.consume("extract")
        canonical_page = next(
            (page for page in bundle.pages if page.url == candidate.source_url),
            bundle.pages[0],
        )
        evidence_text = bundle.extraction_text(
            candidate.supporting_urls,
            candidate.source_url,
        )
        result = await asyncio.to_thread(
            extract_page,
            evidence_text,
            candidate.source_url,
            runtime.model,
            canonical_page.title,
            canonical_page.description,
            candidate.target_title,
        )
        if isinstance(result, ExtractionFailure):
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
                "criteria": list(result.eligibility_criteria),
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
            if (
                actionability.status == "historical"
                and result.submission_deadline
            ):
                await record_edition(
                    runtime.db,
                    result.organizing_body,
                    result.base_title,
                    result.cycle_year,
                    result.submission_deadline,
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

        payload = result.model_dump()
        payload.update(
            {
                "actionability": "actionable",
                "evidence_urls": bundle.source_urls,
                "extraction_completeness": completeness.as_dict(),
                "discovery_run_id": runtime.run_id,
            }
        )
        if runtime.dry_run:
            payload["dry_run"] = True
            payload["synthetic"] = "DRY-RUN FIXTURE — not a real opportunity"
        saved = await save_opportunity(runtime.db, payload)
        runtime.saved.append(candidate.source_url)
        runtime.warnings.extend(
            f"{candidate.source_url}: {warning}"
            for warning in record_warnings(result)
        )
        await clear_extraction_failure(runtime.db, candidate.source_url)
        await _record(
            runtime,
            "save_opportunity",
            node="finalize",
            url=candidate.source_url,
            outcome="ok",
            action=saved.action,
            title=result.title,
            completeness=completeness.as_dict(),
        )

    summary = (
        f"Discovery researched {len(state['evidence_bundles'])} candidate bundle(s), "
        f"saved {len(runtime.saved)} actionable opportunity(ies), "
        f"recorded {len(runtime.historical)} historical edition(s), and rejected "
        f"{len(rejected)} candidate(s)."
    )
    return {"rejected": rejected, "summary": summary}


def build_discovery_graph(runtime: WorkflowRuntime):
    builder = StateGraph(DiscoveryState)
    builder.add_node("plan_queries", partial(plan_queries_node, services=runtime))
    builder.add_node("research", partial(research_node, services=runtime))
    builder.add_node("analyze", partial(analyze_node, services=runtime))
    builder.add_node("finalize", partial(finalize_node, services=runtime))
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
