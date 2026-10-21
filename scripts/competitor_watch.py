"""Trigger one competitor-watch run.

    uv run python scripts/competitor_watch.py --model deepseek/deepseek-v4.1-flash
    uv run python scripts/competitor_watch.py --model ... --only Tomra Envipco "Endlos Innovations" --test-db

Spends about one Exa search per lane per competitor plus ~8 market searches, and
one model call per 20 new pages. `--test-db` writes to <database>_cwtest instead
of the real database, so a trial leaves real data untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from dataclasses import replace
from datetime import date

from opportunity_radar.config import MongoConfig
from opportunity_radar.discovery.competitor_watch import run_competitor_watch, run_digest
from opportunity_radar.storage import get_client, get_database


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--only", nargs="*", help="watch only these competitors (names as in Competitors.xlsx)")
    parser.add_argument("--test-db", action="store_true", help="write to <database>_cwtest")
    parser.add_argument("--since", type=date.fromisoformat, help="search from this date (YYYY-MM-DD) instead of the last run")
    args = parser.parse_args()
    config = MongoConfig.from_env()
    if args.test_db:
        config = replace(config, database=f"{config.database}_cwtest")
    db = get_database(get_client(config), config)
    result = await run_competitor_watch(db, model=args.model, only=args.only or None, since=args.since)
    print(f"run {result['run_id']} [{result['status']}] {result['summary']}  (database: {config.database})")
    for section in await run_digest(db, result["run_id"]):
        print(f"\n## {section['title']}")
        for s in section["signals"]:
            print(f"\n[{s['importance']:6}] {s['competitor']} · {s['kind']} · {s['date'] or 'undated'}\n"
                  f"  {s['headline']}\n  {s['what_happened']}\n  {s['url']}")
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
