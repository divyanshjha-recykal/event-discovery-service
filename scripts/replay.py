"""Replay a past run's model calls against its own banked search results.

    uv run python scripts/replay.py                 # newest run
    uv run python scripts/replay.py --run 70386a    # a specific run
    uv run python scripts/replay.py --repeat 3      # same pool three times

Every run writes its search results into `runs.journey`, so the pool a run saw
can be fed back through the ranking and second-wave planning calls without
touching Tavily or Firecrawl. Costs a fraction of a cent in model tokens and
answers the only question that matters before a live run: do these two calls
come back with something usable, or do they fail the way they failed last time.

Tavily's relevance score is not stored on the event, so replayed hits carry 0.0
there. Everything the prompt actually reads — title, URL, snippet — is exact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opportunity_radar.discovery.budget import RunBudget  # noqa: E402
from opportunity_radar.discovery.state import (  # noqa: E402
    PlannedQuery,
    SearchHit,
    TraversalLimits,
    WorkflowRuntime,
)
from opportunity_radar.discovery.workflow import (  # noqa: E402
    _memory,
    _plan_followup,
    _shortlist,
)
from opportunity_radar.profile import load_business_profile  # noqa: E402
from opportunity_radar.storage import get_client, get_database  # noqa: E402


def pool_from(journey: list[dict]) -> list[SearchHit]:
    """Rebuild the ranked pool from the run's own search events."""
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for event in journey:
        if event.get("tool") != "search" or event.get("outcome") != "ok":
            continue
        query = event.get("query", "")
        for row in event.get("results") or []:
            url = row.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            text = row.get("snippet") or ""
            hits.append(
                SearchHit(
                    title=row.get("title") or "(no title)",
                    url=url,
                    snippet=text[:800],
                    query=query,
                    score=0.0,
                    content=text,
                )
            )
    return hits


def queries_from(journey: list[dict]) -> list[PlannedQuery]:
    planned: list[PlannedQuery] = []
    for event in journey:
        if event.get("tool") != "plan":
            continue
        for row in event.get("queries") or []:
            planned.append(
                PlannedQuery(
                    row.get("query", ""), row.get("intent", "mixed"),
                    row.get("geography", ""), row.get("target_year", 0),
                    row.get("rationale", ""),
                )
            )
    return planned


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="run_id prefix; default is the newest run")
    ap.add_argument(
        "--fixture",
        help="replay a saved pool JSON instead of reading Mongo, e.g. "
             "reference/pool-70386a.json. Survives a cleared database.",
    )
    ap.add_argument("--model", help="override OPENROUTER_MODEL")
    ap.add_argument("--repeat", type=int, default=1, help="runs per call, to see variance")
    ap.add_argument("--focus", default="", help="award | event | research")
    ap.add_argument("--only", choices=("rank", "plan"), help="just one call")
    args = ap.parse_args()

    db = get_database(get_client())

    if args.fixture:
        saved = json.loads(pathlib.Path(args.fixture).read_text(encoding="utf-8"))
        pool = [
            SearchHit(
                title=row["title"], url=row["url"],
                snippet=row["snippet"][:800], query=row["query"],
                score=0.0, content=row["snippet"],
            )
            for row in saved["results"]
        ]
        planned = [
            PlannedQuery(q["query"], "award", "", 0, q.get("rationale", ""))
            for q in saved.get("queries", [])
        ]
        focus = args.focus or saved.get("focus") or "any"
        run = {"run_id": saved.get("run_id", "fixture"),
               "model": saved.get("model"), "status": "fixture"}
    else:
        query = {"run_id": {"$regex": f"^{args.run}"}} if args.run else {}
        run = await db["runs"].find_one(query, sort=[("started_at", -1)])
        if not run:
            print("no matching run", file=sys.stderr)
            return 1
        journey = run.get("journey") or []
        pool = pool_from(journey)
        planned = queries_from(journey)
        focus = args.focus or (run.get("budget") or {}).get("focus") or "any"

    print(f"run {run['run_id'][:6]} · {run.get('model')} · {run.get('status')}")
    print(f"{len(pool)} results banked from {len(planned)} planned query(ies) · focus={focus}\n")
    if not pool:
        print("this run banked no search results — nothing to replay", file=sys.stderr)
        return 1

    runtime = WorkflowRuntime(
        db=db, budget=RunBudget(tool_calls=999, max_llm_calls=999),
        model=args.model, dry_run=False, run_id="replay",
        limits=TraversalLimits(), profile_text=load_business_profile().text,
        focus=focus,
    )
    memory = await _memory(runtime)
    today = date.today()

    for attempt in range(1, args.repeat + 1):
        tag = f" [{attempt}/{args.repeat}]" if args.repeat > 1 else ""

        if args.only != "plan":
            print(f"=== RANK{tag} " + "=" * 52)
            try:
                ranked, observation = await _shortlist(pool, memory, today, runtime)
                print(f"observation: {observation}\n")
                for position, (hit, reason) in enumerate(ranked, 1):
                    host = hit.url.split("/")[2] if "://" in hit.url else hit.url
                    print(f"{position:>2}. {hit.title[:70]}")
                    print(f"    {host}")
                    print(f"    {reason}\n")
                if not ranked:
                    print("   (nothing judged worth fetching)\n")
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED: {type(exc).__name__}: {exc}\n")

        if args.only != "rank" and planned:
            print(f"=== WAVE 2 QUERIES{tag} " + "=" * 44)
            try:
                followup = await _plan_followup(
                    runtime, planned[:2], pool, memory, today, 3
                )
                for item in followup:
                    print(f"  ({len(item.query.split())} words) {item.query}")
                if not followup:
                    print("  (none returned)")
                print()
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED: {type(exc).__name__}: {exc}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
