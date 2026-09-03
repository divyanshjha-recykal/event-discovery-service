"""Stage 3: run the Discovery Agent.

    # no cost — stubs Tavily and Firecrawl, proves loop/budget/tracing
    uv run python scripts/run_discovery.py --dry-run

    # live, one model
    uv run python scripts/run_discovery.py --model google/gemma-4-31b-it

    # the acceptance run: two models, then repeat to prove deduplication
    uv run python scripts/run_discovery.py --model google/gemma-4-31b-it --model qwen/qwen3-32b

Unattended by design — there is no confirmation prompt, because CLAUDE.md's
done-when requires an unattended run. Cost is bounded by --budget and printed
up front instead.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dataclasses import replace

from opportunity_radar.config import MissingConfig, MongoConfig
from opportunity_radar.discovery.agent import run_discovery
from opportunity_radar.discovery.budget import (
    DEFAULT_MAX_SCRAPES,
    DEFAULT_MAX_SEARCHES,
    DEFAULT_TOOL_CALLS,
    DEFAULT_WALL_CLOCK_SECONDS,
    RunBudget,
    estimate_cost,
)
from opportunity_radar.storage import OPPORTUNITIES, ensure_indexes, get_client, get_database

# Published OpenRouter prices, USD per million tokens, for the up-front estimate
# only. Stale prices make the estimate wrong, never the run.
KNOWN_PRICING = {
    "google/gemma-4-31b-it": (0.09, 0.34),
    "qwen/qwen3-32b": (0.08, 0.28),
    "z-ai/glm-4.7-flash": (0.06, 0.40),
    "ibm-granite/granite-4.1-8b": (0.05, 0.10),
    "mistralai/ministral-8b-2512": (0.15, 0.15),
}


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


async def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", dest="models",
                        help="OpenRouter slug. Repeat to run more than one.")
    parser.add_argument("--budget", type=int, default=DEFAULT_TOOL_CALLS,
                        help=f"Hard tool-call ceiling (default {DEFAULT_TOOL_CALLS}).")
    parser.add_argument("--max-searches", type=int, default=DEFAULT_MAX_SEARCHES)
    parser.add_argument("--max-scrapes", type=int, default=DEFAULT_MAX_SCRAPES)
    parser.add_argument("--timeout", type=int, default=DEFAULT_WALL_CLOCK_SECONDS,
                        help=f"Wall-clock seconds (default {DEFAULT_WALL_CLOCK_SECONDS}).")
    parser.add_argument("--query", action="append", dest="queries",
                        help="Optional line of enquiry to seed the run. Repeatable.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Stub Tavily and Firecrawl. No network cost.")
    args = parser.parse_args()

    models: list[str | None] = args.models or [None]

    # A ':free' slug is a shared upstream pool. One 429 mid-loop ends the whole
    # run, and an agent makes many sequential calls, so the odds compound.
    resolved = [m or os.getenv("OPENROUTER_MODEL", "").strip() for m in models]
    free = [m for m in resolved if m.endswith(":free")]
    if free:
        print("WARNING: free-tier model(s) in this run:", ", ".join(free))
        print("  Free slugs share an upstream rate-limit pool. A single 429 ends")
        print("  the run. Pass --model with a paid slug for anything that matters.\n")

    print("Planned run")
    print(f"  models        : {', '.join(m or f'(OPENROUTER_MODEL={resolved[0]})' for m in models)}")
    print(f"  tool budget   : {args.budget} per model")
    print(f"  provider caps : {args.max_searches} searches / {args.max_scrapes} scrapes")
    print(f"  wall clock    : {args.timeout}s")
    print(f"  mode          : {'DRY RUN (no live calls)' if args.dry_run else 'LIVE'}")

    if not args.dry_run:
        total = 0.0
        for model in models:
            pricing = KNOWN_PRICING.get(model or "")
            if not pricing:
                print(f"  est. cost     : {model} — unknown pricing, not estimated")
                continue
            probe = RunBudget(tool_calls=args.budget)
            cost = estimate_cost(probe, *pricing)
            total += cost
            print(f"  est. cost     : {model} up to ~${cost:.3f}")
        if total:
            print(f"  est. total    : up to ~${total:.3f} (model tokens only; "
                  "Tavily/Firecrawl quota not included)")

    try:
        config = MongoConfig.from_env()
    except MissingConfig as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1

    client = get_client(config)
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        print(f"\nFAIL: cannot reach MongoDB — {exc}", file=sys.stderr)
        print("Is the stack up?  docker compose up -d mongodb", file=sys.stderr)
        return 1

    # A dry run must never write fixtures into the real collections. An earlier
    # version did, and the synthetic record then turned up in a live run's counts.
    if args.dry_run:
        config = replace(config, database=f"{config.database}_dryrun")
        print(f"  dry-run database: {config.database} (real data untouched)")

    db = get_database(client, config)
    await ensure_indexes(db)
    before = await db[OPPORTUNITIES].count_documents({})
    print(f"\nOpportunities already stored: {before}")

    runs = []
    actionability_checks: list[bool] = []
    try:
        for model in models:
            budget = RunBudget(
                tool_calls=args.budget,
                max_searches=args.max_searches,
                max_scrapes=args.max_scrapes,
                wall_clock_seconds=args.timeout,
            )
            print(f"\n{'=' * 72}\nRUN: {model or '(OPENROUTER_MODEL)'}\n{'=' * 72}")
            run = await run_discovery(
                db, queries=args.queries, model=model, budget=budget, dry_run=args.dry_run
            )
            runs.append(run)
            saved_docs = [
                await db[OPPORTUNITIES].find_one({"source_url": url})
                for url in run.saved
            ]
            actionability_checks.append(
                all(doc and doc.get("actionability") == "actionable" for doc in saved_docs)
            )

            print("\n-- tool calls --")
            for line in run.budget.log:
                print(f"   {line}")
            print(f"\n-- budget --\n   {run.budget.summary()}")
            print(f"\n-- outcome --")
            print(f"   pages scraped    : {run.pages_scraped}")
            print(f"   records extracted: {run.records_extracted}")
            print(f"   saved            : {len(run.saved)}")
            for url in run.saved:
                marker = "*" if url in run.auto_saved else "+"
                print(f"     {marker} {url}")
            if run.auto_saved:
                print(f"   ({len(run.auto_saved)} marked * were auto-saved — the model "
                      "extracted them but never called save_opportunity)")
            print(f"   rejected         : {len(run.rejected)}")
            print(f"   historical only  : {len(run.historical)}")
            for failure in run.failures:
                print(f"     ! {failure}")
            if run.warnings:
                print(f"\n-- quality warnings ({len(run.warnings)}) --")
                for warning in run.warnings:
                    print(f"   ? {warning}")
            print(f"\n-- agent summary --\n{run.summary}")
            print(f"\n-- trace --\n   {run.trace_url}")
    finally:
        after = await db[OPPORTUNITIES].count_documents({})
        await client.close()

    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}")
    print(f"opportunities before: {before}   after: {after}   new: {after - before}")
    header = f"{'model':<32} {'calls':>10} {'scraped':>8} {'extracted':>10} {'saved':>6} {'in budget':>10}"
    print(header)
    print("-" * len(header))
    for run in runs:
        within = run.budget.spent <= run.budget.tool_calls and not run.budget.timed_out
        print(f"{run.model:<32} {run.budget.spent:>4}/{run.budget.tool_calls:<5}"
              f" {run.pages_scraped:>8} {run.records_extracted:>10} {len(run.saved):>6}"
              f" {'yes' if within else 'NO':>10}")

    total_warnings = sum(len(r.warnings) for r in runs)
    if total_warnings:
        print(f"\n{total_warnings} quality warning(s) — these records WERE stored, "
              "but review them before treating them as actionable:")
        for run in runs:
            for warning in run.warnings:
                print(f"  ? {warning}")

    print("\nAcceptance (CLAUDE.md Stage 3):")
    any_saved = any(run.saved for run in runs)
    all_in_budget = all(
        run.budget.spent <= run.budget.tool_calls and not run.budget.timed_out
        for run in runs
    )
    traced = all(run.trace_url for run in runs)
    actionable_only = all(actionability_checks)
    print(f"  produced at least one stored opportunity : {'PASS' if any_saved else 'FAIL'}")
    print(f"  stayed within budget                     : {'PASS' if all_in_budget else 'FAIL'}")
    print(f"  run visible as a Langfuse trace          : {'PASS' if traced else 'FAIL'}")
    print(f"  saved only actionability-gated records   : {'PASS' if actionable_only else 'FAIL'}")
    print("  deduplicates on a second run             : re-run with the SAME "
          "--query flags and check 'new' is 0.")
    print("      (without --query the agent invents different queries each run, "
          "so it finds different opportunities and 'new' will not be 0 — that is "
          "not a dedup failure. Storage-level dedup is proven by verify_storage.py.)")

    return 0 if (any_saved and all_in_budget and traced and actionable_only) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
