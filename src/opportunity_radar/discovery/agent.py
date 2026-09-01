"""The Discovery Agent — a LangGraph reasoning loop over the five tools.

Tracing is not optional here: CLAUDE.md requires the full run to be visible in
Langfuse tool call by tool call, so the handler goes on the graph config and
every tool call becomes a span under one trace.

The budget is enforced inside the tools, not by asking the model nicely. The
graph's `recursion_limit` is a second, absolute ceiling in case a model spins
without calling anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from ..storage import (
    finish_run,
    save_opportunity as store_opportunity,
    start_run,
)
from ..tracing import chat_model, langfuse_client, trace_handler
from .budget import RunBudget
from .tools import DiscoveryContext, build_tools

MAX_OUTPUT_TOKENS = 2048

SYSTEM_PROMPT = """\
You find awards, grants, events and conferences that Recykal could realistically \
enter, and store the genuine ones.

Work in this order:

1. Call read_memory() FIRST, once. It tells you what Recykal does, where it \
operates, what it has already won, and which programs are already tracked.
2. search() for opportunities that fit. Use specific queries — name sectors, \
regions and years. Do not repeat programs already tracked unless it is a new \
edition.

   PERSIST. A single search is never enough. If a query returns academic \
papers, listicles, news articles or closed programmes, that is a bad query, \
not proof that no opportunity exists. Rewrite it and search again. Vary the \
angle across searches — Recykal works in EPR compliance, plastics, e-waste, \
metals, paper, tyres, batteries and deposit return systems, across India and \
the Middle East, so there are many distinct angles to try.

   Queries that tend to work name the thing you want and the year: \
"<sector> award 2026 call for entries India", "<sector> grant applications \
open 2026", "sustainability awards 2026 nominations open India". Queries that \
tend to fail are broad topic phrases like "circular economy companies".

   Do not conclude that nothing exists until you have tried at least four \
genuinely different queries and still found nothing worth scraping.
3. scrape() a promising result to read the actual page.
4. Judge it yourself before spending anything else. Skip the page if:
   - nominations, submissions or applications are closed;
   - the deadline has already passed;
   - it is not something an Indian waste-management or circular-economy \
technology company could enter;
   - it is a news article or listicle about an award rather than the award's \
own call for entries.

   Two things to get right here, because they are the most common way a run \
produces technically-valid but useless records:

   a) SCRAPE THE CALL FOR ENTRIES, NOT THE HOMEPAGE. A site's landing page \
usually has no deadline and no eligibility list. If the page you fetched is a \
homepage or an "about" page, look for the specific entry, nomination or \
"how to apply" page and scrape that instead. A record with no deadline is \
close to useless.

   b) GET THE CURRENT CYCLE. Prefer the edition that is open now or opens \
next. If the page is about a past year's edition, look for the current year's \
page before settling for the old one. An award that closed last year is not \
an opportunity.
5. extract() ONLY pages that survive step 4. Each one costs a model call.
6. save_opportunity() when extraction succeeds.

Rules:
- You have a hard tool-call budget. When a tool replies with STOP, the run is \
over — stop calling tools and write your summary immediately.
- Until then, USE the budget. Stopping with most of it unspent and nothing \
saved is a failed run, not a careful one. Searching costs little; a wasted \
budget costs the whole run.
- read_memory() and save_opportunity() are free — they never consume budget. \
Save every record that extracts successfully; never leave one unsaved.
- Judging relevance is your job, not the extractor's. Extraction is the second \
line of defense, not the filter.
- Prefer a few genuine, currently-open opportunities over many weak ones.
- When you are done, or the budget stops you, reply with a short plain-text \
summary of what you found and what you skipped, and why.\
"""

# Appended only under --dry-run. It has to live in the system prompt rather than
# in the tool output: an earlier version put the instruction inside the search
# result, and the model correctly ranked the system prompt's "skip anything that
# isn't a genuine opportunity" above a note buried in tool data. The skip was
# good judgement — the fix is to make the exception authoritative, not to try to
# fool the agent with a more convincing fake.
DRY_RUN_NOTE = """

DRY-RUN MODE — READ THIS CAREFULLY. This run is a pipeline test. `search` and \
`scrape` return synthetic fixture data instead of live results, and that is \
expected. Your task in this mode is NOT to judge whether the fixture is a real \
opportunity. It is not real, and you already know that.

Instead, process the fixture exactly as if it were genuine so that every stage \
of the pipeline is exercised: scrape it, extract it, and save it. Do not skip \
it for being synthetic. Do not keep searching for better results — repeated \
searches return the same fixture. One pass of \
search -> scrape -> extract -> save_opportunity is the whole objective here.\
"""


# How many times the loop may be restarted after an early stop. One nudge is
# enough to tell persistence from genuine exhaustion; more just burns budget
# arguing with a model that has already looked.
MAX_ATTEMPTS = 2

# Below this fraction of budget spent, concluding with nothing saved looks like
# giving up rather than finishing.
EARLY_STOP_THRESHOLD = 0.5


def unsaved_records(context) -> list[str]:
    """URLs that extracted cleanly but were never stored.

    This is the most expensive possible failure: the search, the scrape and the
    extraction model call have all been paid for, a valid record exists, and it
    is about to be discarded because the model wrote a summary instead of
    calling save_opportunity. One model did exactly that and then claimed in its
    summary that it had saved them.
    """
    return [url for url in context.records if url not in context.saved]


def _stopped_early(context, budget) -> bool:
    """Did the agent conclude with work left on the table?"""
    # Unsaved extracted records are a failure regardless of budget. There is no
    # reading under which paying for an extraction and then dropping it is right.
    if unsaved_records(context):
        return True
    if context.saved:
        return False                       # it found and stored something
    if budget.exhausted or budget.stop_reason:
        return False                       # it was stopped, it did not choose to
    spent_fraction = budget.spent / max(budget.tool_calls, 1)
    return spent_fraction <= EARLY_STOP_THRESHOLD


def _nudge(context, budget) -> str:
    """Concrete direction for a second attempt, not a repeat of the prompt."""
    pending = unsaved_records(context)
    if pending:
        listed = "\n".join(f"  - save_opportunity({url!r})" for url in pending)
        return (
            f"Stop. You extracted {len(pending)} record(s) and never saved them. "
            "Do not describe saving in a summary — saving only happens when you "
            "actually call the tool.\n\n"
            f"Call these now, one per record:\n{listed}\n\n"
            "save_opportunity() is free and never consumes budget. Then carry on "
            "if you have budget left, or write your summary."
        )

    tried = "\n".join(f"  - {line}" for line in budget.log) or "  (almost nothing)"
    return (
        "Stop. You concluded the run with "
        f"{budget.remaining} of {budget.tool_calls} tool calls still unspent and "
        "nothing saved. That is a failed run, not a careful one.\n\n"
        f"What you actually did:\n{tried}\n\n"
        "Poor search results mean your queries were wrong, not that no "
        "opportunity exists. Recykal is an Indian waste-management and circular-"
        "economy technology company, and awards for that sector demonstrably "
        "exist right now.\n\n"
        "Continue the run. Try several genuinely different queries before "
        "concluding again — vary the sector (EPR compliance, plastics, e-waste, "
        "metals, batteries, deposit return systems), vary the framing "
        "(awards, grants, recognition, innovation challenges), and name the "
        "current or next year explicitly. Scrape anything that looks like a "
        "real call for entries, and save whatever extracts cleanly."
    )


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


async def run_discovery(
    db,
    queries: list[str] | None = None,
    model: str | None = None,
    budget: RunBudget | None = None,
    dry_run: bool = False,
    run_id: str | None = None,
) -> DiscoveryRun:
    """One Discovery run. Returns what happened; raises nothing on budget stop."""
    budget = budget or RunBudget()
    run_id = run_id or uuid4().hex
    label = model or "(OPENROUTER_MODEL)"

    context = DiscoveryContext(
        db=db, budget=budget, model=model, dry_run=dry_run, run_id=run_id
    )
    tools = build_tools(context)

    # Recorded before the loop starts so a UI can show the run as in-progress,
    # and so a crash still leaves the journey it got through.
    try:
        await start_run(
            db, run_id, label,
            {"tool_calls": budget.tool_calls, "max_searches": budget.max_searches,
             "max_scrapes": budget.max_scrapes,
             "wall_clock_seconds": budget.wall_clock_seconds},
            queries,
        )
    except Exception:  # noqa: BLE001 — telemetry never blocks a run
        pass

    llm = chat_model(model, max_tokens=MAX_OUTPUT_TOKENS, timeout=120, max_retries=3)
    # langchain.agents.create_agent, not langgraph.prebuilt.create_react_agent —
    # the latter is deprecated in LangGraph v1 and removed in v2.
    system_prompt = SYSTEM_PROMPT + (DRY_RUN_NOTE if dry_run else "")
    agent = create_agent(llm, tools, system_prompt=system_prompt)

    opening = (
        "Find opportunities for Recykal. Start by reading memory."
        if not queries
        else (
            "Find opportunities for Recykal. Start by reading memory, then "
            "investigate these lines of enquiry:\n"
            + "\n".join(f"- {q}" for q in queries)
        )
    )

    client = langfuse_client()
    handler = trace_handler()
    trace_url = None
    summary = ""
    auto_saved: list[str] = []
    thinking: list[str] = []

    with client.start_as_current_observation(
        name=f"stage3.discovery:{label}", as_type="span"
    ):
        # Available to the tools immediately, so a persisted extraction failure
        # can link straight to the trace that produced it.
        context.trace_url = client.get_trace_url(trace_id=client.get_current_trace_id())
        config = {
            "callbacks": [handler],
            # Absolute ceiling: the budget stops tool calls, this stops
            # a model that keeps thinking without calling anything.
            "recursion_limit": budget.tool_calls * 3 + 10,
        }
        messages = [HumanMessage(opening)]

        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                result = await agent.ainvoke({"messages": messages}, config=config)
                messages = result.get("messages", messages)
                summary = messages[-1].content if messages else ""
                thinking = [
                    m.content.strip()
                    for m in messages
                    if getattr(m, "type", "") == "ai"
                    and isinstance(getattr(m, "content", ""), str)
                    and m.content.strip()
                ]

                # Early-stop guard. Models differ wildly in persistence: one will
                # run four searches before concluding, another gives up after one
                # bad result set with most of the budget unspent. That difference
                # should not decide whether a run produces anything, so push back
                # once with concrete direction rather than accepting the verdict.
                if attempt >= MAX_ATTEMPTS or not _stopped_early(context, budget):
                    break

                messages = list(messages) + [HumanMessage(_nudge(context, budget))]
        except Exception as exc:  # noqa: BLE001 — reported, run still summarised
            summary = f"RUN ENDED EARLY: {type(exc).__name__}: {exc}"
            budget.stop_reason = budget.stop_reason or f"{type(exc).__name__}"
        # Last resort. If the model still has not saved records it extracted,
        # store them here rather than discard them. The agent already made the
        # judgement call by choosing to extract these pages, extraction already
        # validated them, and the work is already paid for — the only thing
        # missing is a tool call the model failed to make.
        for url in unsaved_records(context):
            try:
                result = await store_opportunity(context.db, context.records[url].model_dump())
                context.saved.append(url)
                auto_saved.append(url)
                context.warnings.append(
                    f"{url}: auto-saved ({result.action}) — the model extracted this "
                    "record but never called save_opportunity"
                )
            except Exception as exc:  # noqa: BLE001
                context.failures.append(f"{url}: auto-save failed — {type(exc).__name__}")

        trace_url = client.get_trace_url(trace_id=client.get_current_trace_id())

    client.flush()

    counts = {
        "searched": budget.searches,
        "scraped": len(context.pages),
        "extracted": len(context.records),
        "saved": len(context.saved),
        "failed": len(context.failures),
    }
    try:
        await finish_run(
            db, run_id,
            "failed" if summary.startswith("RUN ENDED EARLY") else "completed",
            summary, trace_url,
            {"tool_calls": budget.tool_calls, "spent": budget.spent,
             "searches": budget.searches, "scrapes": budget.scrapes,
             "elapsed": round(budget.elapsed, 1),
             "stop_reason": budget.stop_reason},
            counts, thinking,
        )
    except Exception:  # noqa: BLE001
        pass

    return DiscoveryRun(
        run_id=run_id,
        model=model or "(OPENROUTER_MODEL)",
        budget=budget,
        saved=context.saved,
        auto_saved=auto_saved,
        failures=context.failures,
        warnings=context.warnings,
        summary=summary,
        trace_url=trace_url,
        pages_scraped=len(context.pages),
        records_extracted=len(context.records),
        journey=context.journey,
        thinking=thinking,
    )
