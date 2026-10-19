"""Plan and search only: no ranking, no scraping, nothing written to the runs collection.

    uv run python scripts/search_only.py --focus research --model deepseek/deepseek-v4.1-flash

Spends Exa searches (up to the run's search cap, normally 5) and a few model calls.
Prints each query with its track and year, every result with Exa's facts, and a
summary; saves the whole test to reference/search-tests/ for later comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from opportunity_radar.config import MongoConfig
from opportunity_radar.discovery import workflow as w
from opportunity_radar.discovery.budget import RunBudget
from opportunity_radar.discovery.state import WorkflowRuntime
from opportunity_radar.profile import load_business_profile
from opportunity_radar.storage import get_client, get_database

OUT = Path(__file__).resolve().parents[1] / "reference" / "search-tests"
_YEAR = re.compile(r"\b20\d\d\b")


def _when(hit: dict, today: str) -> str:
    when = hit.get("entry_deadline") or hit.get("event_date") or ""
    if not when:
        return "no date"
    return "past" if when < today else "ahead"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focus", required=True, choices=("any", "award", "event", "research"))
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    async def _no_write(*_args, **_kwargs):
        return None
    w.append_event = _no_write  # results go to a file, not the runs collection

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    today = date.today()
    runtime = WorkflowRuntime(
        db=get_database(get_client(), MongoConfig.from_env()), budget=RunBudget(),
        model=args.model, dry_run=False, run_id=f"search-test-{stamp}",
        focus=args.focus, profile_text=load_business_profile().text, search_provider="exa",
    )
    state = {"as_of_date": today.isoformat(), "supplied_queries": [], "replan_count": 0, "search_hits": []}
    state.update(await w.plan_queries_node(state, services=runtime))
    found = (await w.search_node(state, services=runtime))["search_hits"]

    searches = [e for e in runtime.journey if e["tool"] == "search"]
    for event in runtime.journey:
        if event["tool"] == "plan" and event.get("assessment"):
            print(f"\n[STEP {event.get('step')}] {event['assessment']}\n   gaps: {event.get('gaps')}")
        if event["tool"] != "search":
            continue
        query = event.get("query", "")
        print(f"\n[{event.get('track') or '-'}] {query}   (year in query: {'yes' if _YEAR.search(query) else 'NO'})")
        for hit in event.get("results") or []:
            print(f"   {_when(hit, today.isoformat()):7} | {hit.get('opportunity_type') or '-':12} | "
                  f"{hit['title'][:70]} | sponsor: {(hit.get('sponsor') or '-')[:30]} | "
                  f"{hit.get('entry_deadline') or '-'} / {hit.get('event_date') or '-'} | {hit['url'][:70]}")

    results = [hit for e in searches for hit in e.get("results") or []]
    timing = Counter(_when(hit, today.isoformat()) for hit in results)
    print("\nSUMMARY")
    print(f"  searches: {len(searches)} | results: {len(results)}")
    print(f"  queries by track: {dict(Counter(e.get('track') or '-' for e in searches))}")
    print(f"  queries with a year: {sum(1 for e in searches if _YEAR.search(e.get('query', '')))} of {len(searches)}")
    print(f"  result dates: {dict(timing)}")
    print(f"  Exa type labels: {dict(Counter(hit.get('opportunity_type') or '-' for hit in results))}")
    print(f"  model calls: {runtime.budget.llm_calls} | searches spent: {runtime.budget.searches}")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{stamp}-{args.focus}.json"
    path.write_text(json.dumps({
        "focus": args.focus, "model": args.model, "date": today.isoformat(),
        "journey": runtime.journey,
        "hits": [asdict(hit) for hit in found],
    }, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {path}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
