"""Run only the ranker on a pool saved by search_only.py: no searches, no scraping.

    uv run python scripts/rank_pool.py reference/search-tests/<file>.json --model deepseek/deepseek-v4.1-flash

One model call. Prints the ranker's view of the pool, what it would fetch (the top
6), what it ranked below that, and every result it left out.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from dataclasses import fields, replace
from datetime import date
from itertools import zip_longest
from pathlib import Path

from opportunity_radar.config import MongoConfig
from opportunity_radar.discovery import workflow as w
from opportunity_radar.discovery.budget import RunBudget
from opportunity_radar.discovery.state import SearchHit, WorkflowRuntime
from opportunity_radar.profile import load_business_profile
from opportunity_radar.storage import get_client, get_database

SEATS = 6


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pool", type=Path)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    saved = json.loads(args.pool.read_text(encoding="utf-8"))
    names = {f.name for f in fields(SearchHit)}
    raw = [SearchHit(**{k: v for k, v in hit.items() if k in names}) for hit in saved["hits"]]
    track_of = {e["query"]: e.get("track", "") for e in saved["journey"] if e.get("tool") == "search"}
    raw = [replace(hit, track=track_of.get(hit.query, hit.track)) for hit in raw]
    # As rank_node orders a pool: queries interleaved, each URL once.
    per_query: dict[str, list] = {}
    for hit in raw:
        per_query.setdefault(hit.query, []).append(hit)
    hits, seen = [], set()
    for row in zip_longest(*per_query.values()):
        for hit in row:
            if hit is not None and hit.url not in seen:
                seen.add(hit.url)
                hits.append(hit)
    runtime = WorkflowRuntime(
        db=get_database(get_client(), MongoConfig.from_env()), budget=RunBudget(),
        model=args.model, dry_run=False, run_id="rank-pool", focus=saved["focus"],
        profile_text=load_business_profile().text,
    )
    memory = await w._memory(runtime)
    picks, observation, excluded = await w._shortlist(
        hits, memory, date.fromisoformat(saved["date"]), runtime, SEATS
    )

    print(f"Pool: {len(hits)} results ({saved['focus']}, searched {saved['date']})\n")
    print(f"RANKER'S VIEW: {observation}\n")
    picked = {hit.url for hit, _ in picks}
    for rank, (hit, reason) in enumerate(picks, 1):
        tag = "FETCH" if rank <= SEATS else "below"
        track = f" [{hit.track}]" if hit.track else ""
        when = f"deadline {hit.entry_deadline or '-'} / event {hit.event_date or '-'}"
        print(f"{rank:>2}. [{tag}]{track} {hit.title[:80]}\n      {hit.url[:100]}\n      {when}\n      why: {reason[:300]}")
    print("\nEXCLUDED, WITH THE RANKER'S REASON:")
    for hit, reason in excluded:
        print(f"   - {hit.title[:70]}\n       {reason[:220]}")
    print(f"\nLEFT OUT ({len(hits) - len(picked)}):")
    for hit in hits:
        if hit.url not in picked:
            when = hit.entry_deadline or hit.event_date or "no date"
            print(f"   - {hit.title[:80]} | {when} | {hit.url[:80]}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
