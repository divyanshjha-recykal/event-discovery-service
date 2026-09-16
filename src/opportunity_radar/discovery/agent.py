"""Public runner for the bounded deep-research Discovery graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from ..profile import load_business_profile
from ..storage import finish_run, start_run
from ..tracing import langfuse_client, trace_handler
from .budget import RunBudget
from .state import DiscoveryState, TraversalLimits, WorkflowRuntime
from .workflow import build_discovery_graph


@dataclass
class DiscoveryRun:
    run_id: str
    model: str
    budget: RunBudget
    saved: list[str]
    needs_deeper: list[str]
    auto_saved: list[str]
    failures: list[str]
    warnings: list[str]
    summary: str
    trace_url: str | None
    pages_scraped: int
    records_extracted: int
    journey: list[dict]
    thinking: list[str]
    rejected: list[dict]
    historical: list[str]


async def run_discovery(
    db,
    queries: list[str] | None = None,
    model: str | None = None,
    budget: RunBudget | None = None,
    dry_run: bool = False,
    run_id: str | None = None,
    limits: TraversalLimits | None = None,
) -> DiscoveryRun:
    """Run Plan -> Research -> Analyze -> Finalize without free-form tool control."""
    budget = budget or RunBudget()
    limits = limits or TraversalLimits()
    run_id = run_id or uuid4().hex
    label = model or "(OPENROUTER_MODEL)"
    runtime = WorkflowRuntime(
        db=db,
        budget=budget,
        model=model,
        dry_run=dry_run,
        run_id=run_id,
        limits=limits,
        profile_text=load_business_profile().text,
    )

    try:
        await start_run(
            db,
            run_id,
            label,
            {
                **budget.caps(),
                "max_candidates": limits.max_candidates,
                "max_links_per_page": limits.max_links_per_page,
                "max_pages_per_seed": limits.max_pages_per_seed,
                "max_depth": limits.max_depth,
                "workflow": "plan-research-analyze-finalize",
            },
            queries,
        )
    except Exception:  # noqa: BLE001
        pass

    initial: DiscoveryState = {
        "as_of_date": date.today().isoformat(),
        "supplied_queries": list(queries or []),
        "memory": "",
        "planned_queries": [],
        "search_hits": [],
        "evidence_bundles": [],
        "candidates": [],
        "analyzed_seeds": [],
        "analysis_errors": [],
        "rejected": [],
        "summary": "",
        "replan_count": 0,
    }
    result: DiscoveryState = initial
    trace_url: str | None = None
    status = "succeeded"

    client = langfuse_client()
    with client.start_as_current_observation(
        name=f"stage3.discovery:{label}", as_type="span"
    ):
        runtime.trace_url = client.get_trace_url(
            trace_id=client.get_current_trace_id()
        )
        try:
            graph = build_discovery_graph(runtime)
            result = await graph.ainvoke(
                initial,
                config={
                    "callbacks": [trace_handler()],
                    # One optional re-plan means at most seven node executions.
                    "recursion_limit": 10,
                },
            )
            # A run either worked or it did not. "Completed with rejections"
            # read as a qualified failure when setting a candidate aside is
            # normal, successful behaviour.
            if budget.cancelled:
                status = "stopped"
            elif runtime.failures and not (runtime.saved or runtime.needs_deeper):
                status = "failed"
        except Exception as exc:  # noqa: BLE001
            runtime.failures.append(f"workflow: {type(exc).__name__}: {exc}")
            result = {**initial, "summary": f"RUN ENDED EARLY: {type(exc).__name__}: {exc}"}
            status = "failed"
        trace_url = client.get_trace_url(trace_id=client.get_current_trace_id())
    client.flush()

    extracted = sum(
        1
        for event in runtime.journey
        if event.get("tool") == "extract" and event.get("outcome") == "ok"
    )
    extraction_failed = sum(
        1
        for event in runtime.journey
        if event.get("tool") == "extract" and event.get("outcome") == "failed"
    )
    pages = sum(
        1
        for event in runtime.journey
        if event.get("tool") == "scrape" and event.get("outcome") == "ok"
    )
    counts = {
        "searched": budget.searches,
        "scraped": pages,
        "extracted": extracted,
        "extraction_failed": extraction_failed,
        "saved": len(runtime.saved),
        "needs_deeper": len(runtime.needs_deeper),
        "failed": len(runtime.failures),
        "rejected": len(result.get("rejected", [])),
        "historical": len(runtime.historical),
    }
    thinking = [
        f"{query.query} — {query.rationale}"
        for query in result.get("planned_queries", [])
    ]
    try:
        await finish_run(
            db,
            run_id,
            status,
            result.get("summary", ""),
            trace_url,
            {
                # Caps as well as counters: this overwrites the whole `budget`
                # field, so omitting them left the UI metering against zero.
                **budget.caps(),
                **budget.live(),
                "max_candidates": limits.max_candidates,
                "max_links_per_page": limits.max_links_per_page,
                "max_pages_per_seed": limits.max_pages_per_seed,
                "max_depth": limits.max_depth,
                "stop_reason": budget.stop_reason,
                "workflow": "plan-research-analyze-finalize",
            },
            counts,
            thinking,
            list(runtime.warnings),
            list(runtime.failures),
        )
    except Exception:  # noqa: BLE001
        pass

    return DiscoveryRun(
        run_id=run_id,
        model=label,
        budget=budget,
        saved=list(runtime.saved),
        needs_deeper=list(runtime.needs_deeper),
        auto_saved=[],
        failures=list(runtime.failures),
        warnings=list(runtime.warnings),
        summary=result.get("summary", ""),
        trace_url=trace_url,
        pages_scraped=pages,
        records_extracted=extracted,
        journey=list(runtime.journey),
        thinking=thinking,
        rejected=list(result.get("rejected", [])),
        historical=list(runtime.historical),
    )
