"""Put a run's queries through the real search and rank steps, once per provider.

    uv run python scripts/compare_rank.py --run 652ec9 --model deepseek/deepseek-v4.1-flash

Tavily's pool is the one the run stored, so Tavily is not called. Exa is called
once per query and cached in reference/exa-pool-<run>.json, so re-running only
spends ranking calls. Budget caps match a dashboard run (65/5/15/30), so rank
sizes its picks the way it did live.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from opportunity_radar.config import MongoConfig
from opportunity_radar.discovery import workflow as w
from opportunity_radar.discovery.budget import RunBudget
from opportunity_radar.discovery.providers import tool_exa_search
from opportunity_radar.discovery.state import PlannedQuery, SearchHit, WorkflowRuntime
from opportunity_radar.profile import load_business_profile
from opportunity_radar.storage import get_client, get_database

REFERENCE = Path(__file__).resolve().parents[1] / "reference"
HIT_FIELDS = {f.name for f in fields(SearchHit)}


def _caps() -> RunBudget:
    return RunBudget(tool_calls=65, max_searches=5, max_scrapes=15, max_llm_calls=30)


async def _load_run(db, prefix: str) -> tuple[str, list[str], dict[str, list[SearchHit]]]:
    run = await db.runs.find_one({"run_id": {"$regex": f"^{re.escape(prefix)}"}}, sort=[("_id", -1)])
    if not run:
        raise SystemExit(f"No run found for {prefix}")
    queries, tavily = [], {}
    for event in run.get("journey", []):
        query = event.get("query")
        if event.get("tool") != "search" or not query or query in tavily:
            continue
        queries.append(query)
        tavily[query] = [
            SearchHit(
                title=str(r.get("title") or ""), url=str(r.get("url") or ""),
                snippet=str(r.get("snippet") or "")[:800], query=query,
                content=str(r.get("snippet") or ""),
            )
            for r in event.get("results") or [] if r.get("url")
        ]
    return run["run_id"], queries, tavily


async def _exa_pool(run_id: str, queries: list[str]) -> dict[str, list[SearchHit]]:
    cache = REFERENCE / f"exa-pool-{run_id[:6]}.json"
    if cache.is_file():
        stored = json.loads(cache.read_text(encoding="utf-8"))
        return {q: [SearchHit(**{k: v for k, v in h.items() if k in HIT_FIELDS}) for h in hits]
                for q, hits in stored.items()}
    pool = {q: await tool_exa_search(q) for q in queries}
    cache.write_text(json.dumps({q: [asdict(h) for h in hits] for q, hits in pool.items()},
                                indent=1), encoding="utf-8")
    return pool


async def _search_and_rank(label: str, queries, hits_by_query, model: str, memory: str,
                           profile: str, today: str) -> dict:
    """The real search_node gates, then the real rank_node, over a fixed pool."""
    async def fixed_search(query: str, **_):
        return list(hits_by_query.get(query, []))

    w.search_provider = lambda *_: (label, fixed_search)
    runtime = WorkflowRuntime(db=None, budget=_caps(), model=model, dry_run=False,
                              run_id=f"compare-{label}", profile_text=profile)
    state = {
        "as_of_date": today, "supplied_queries": ["fixed"], "memory": memory,
        "planned_queries": [PlannedQuery(q, "mixed", "", 0, "") for q in queries],
        "search_hits": [], "evidence_bundles": [], "picks": [], "replan_count": 0,
    }
    state["search_hits"] = (await w.search_node(state, services=runtime))["search_hits"]
    await w.rank_node(state, services=runtime)
    return {"journey": runtime.journey, "pool": state["search_hits"],
            "raw": sum(len(v) for v in hits_by_query.values())}


def _report(label: str, result: dict, today: str) -> None:
    journey, pool = result["journey"], result["pool"]
    by_url = {h.url: h for h in pool}
    print("\n" + "=" * 96)
    print(f"{label.upper()}: {result['raw']} results -> {len(pool)} reach ranking")
    for e in journey:
        if e["tool"] == "expired":
            print(f"  dropped, closed : {str(e.get('title'))[:60]}  (deadline {e.get('entry_deadline') or '-'}, event {e.get('event_date') or '-'})")
        elif e["tool"] == "dedupe":
            print(f"  dropped, repeat : {str(e.get('title'))[:60]}")
    shortlist = next((e for e in journey if e["tool"] == "shortlist"), None)
    if not shortlist:
        print("  ranking did not run")
        return
    print(f"\n  ranker observation: {str(shortlist.get('observation') or '')[:600]}")
    picks = shortlist.get("picked") or []
    print(f"\n  ranked {len(picks)}, would fetch {sum(1 for p in picks if p.get('fetched'))}:")
    for p in picks:
        hit = by_url.get(p.get("url"))
        print(f"\n  {p.get('rank'):>2}. [{'FETCH' if p.get('fetched') else '  -  '}] {str(p.get('title'))[:70]}")
        print(f"      {str(p.get('url'))[:90]}")
        if hit:
            print(f"      saw   : {w._date_line(hit, today)[:120]}")
            if facts := w._facts_line(hit):
                print(f"      saw   : {facts[:120]}")
        print(f"      reason: {str(p.get('reason'))[:200]}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run_id prefix whose queries to use")
    parser.add_argument("--model", required=True, help="model for the ranking call")
    parser.add_argument("--only", choices=("tavily", "exa"), help="rank one pool only")
    args = parser.parse_args()

    db = get_database(get_client(), MongoConfig.from_env())
    run_id, queries, tavily = await _load_run(db, args.run)
    profile = load_business_profile().text
    memory = await w._memory(WorkflowRuntime(db=db, budget=_caps(), model=args.model,
                                             dry_run=False, run_id="compare", profile_text=profile))
    today = date.today().isoformat()
    exa = await _exa_pool(run_id, queries)
    print(f"Run {run_id[:6]}: {len(queries)} queries | ranking with {args.model} | today {today}")

    results = {}
    for label, pool in (("tavily", tavily), ("exa", exa)):
        if args.only and label != args.only:
            continue
        results[label] = await _search_and_rank(label, queries, pool, args.model, memory, profile, today)
        _report(label, results[label], today)

    out = REFERENCE / f"rank-compare-{run_id[:6]}.json"
    out.write_text(json.dumps({k: {"journey": v["journey"], "raw": v["raw"]} for k, v in results.items()},
                              indent=1, default=str), encoding="utf-8")
    print(f"\nFull journeys: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
