"""Public runner for the bounded deep-research Discovery graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from ..storage import finish_run, start_run
from ..tracing import langfuse_client, trace_handler
from .budget import RunBudget
from .state import DiscoveryState, WorkflowRuntime
from .workflow import build_discovery_graph


@dataclass
class DiscoveryRun:
    run_id: str
    model: str
    budget: RunBudget
    saved: list[str]
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
) -> DiscoveryRun:
    """Run Plan -> Research -> Analyze -> Finalize without free-form tool control."""
    budget = budget or RunBudget()
    run_id = run_id or uuid4().hex
    label = model or "(OPENROUTER_MODEL)"
    runtime = WorkflowRuntime(
        db=db,
        budget=budget,
        model=model,
        dry_run=dry_run,
        run_id=run_id,
    )

    try:
        await start_run(
            db,
            run_id,
            label,
            {
                "tool_calls": budget.tool_calls,
                "max_searches": budget.max_searches,
                "max_scrapes": budget.max_scrapes,
                "max_llm_calls": budget.max_llm_calls,
                "wall_clock_seconds": budget.wall_clock_seconds,
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
    status = "completed"

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
            if runtime.failures and not runtime.saved:
                status = "failed"
            elif result.get("rejected") or runtime.failures:
                status = "completed_with_rejections"
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
                "tool_calls": budget.tool_calls,
                "spent": budget.spent,
                "searches": budget.searches,
                "scrapes": budget.scrapes,
                "llm_calls": budget.llm_calls,
                "elapsed": round(budget.elapsed, 1),
                "stop_reason": budget.stop_reason,
                "workflow": "plan-research-analyze-finalize",
            },
            counts,
            thinking,
        )
    except Exception:  # noqa: BLE001
        pass

    return DiscoveryRun(
        run_id=run_id,
        model=label,
        budget=budget,
        saved=list(runtime.saved),
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
