"""Trigger one component-watch run over a product's parts.

    uv run python scripts/component_watch.py ace --model deepseek/deepseek-v4.1-flash          # weekly: top 80% of spend
    uv run python scripts/component_watch.py ace --model ... --all                             # every part
    uv run python scripts/component_watch.py ace --model ... --only ACE-012 ACE-001 --test-db  # named parts

Spends one model call per 16 parts to plan, then up to two Exa searches (same part
from any seller, and alternatives) and one model call per part searched. `--test-db`
writes to <database>_cmtest instead of the real database.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from dataclasses import replace

from opportunity_radar.config import MongoConfig
from opportunity_radar.discovery.component_watch import run_component_watch, run_offers
from opportunity_radar.reporting import offer_price
from opportunity_radar.storage import get_client, get_database


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", help="product folder name, e.g. ace")
    parser.add_argument("--model", required=True)
    parser.add_argument("--only", nargs="*", help="only these Part IDs")
    parser.add_argument("--all", action="store_true",
                        help="every off-the-shelf part, not only those making up 80%% of their spend")
    parser.add_argument("--test-db", action="store_true", help="write to <database>_cmtest")
    args = parser.parse_args()
    config = MongoConfig.from_env()
    if args.test_db:
        config = replace(config, database=f"{config.database}_cmtest")
    db = get_database(get_client(config), config)
    result = await run_component_watch(db, args.product, model=args.model, only=args.only or None,
                                       scope="all" if args.all else "priority")
    print(f"run {result['run_id']} [{result['status']}] {result['summary']}  (database: {config.database})")
    digest = await run_offers(db, result["run_id"])
    ov = digest["overview"]
    print(f"\nSearched {ov['searched']} parts ({ov['searched_share']:.0%} of off-the-shelf spend) of a ₹{ov['machine_cost']:,.0f} machine")
    for label, rows, key in (("1. SAME PART, CHEAPER SELLER", digest["same_part"], "best_same"),
                             ("2. BETTER OR NEWER, FITS", digest["upgrades"], "best_upgrade"),
                             ("3. CHEAPER ALTERNATIVES", digest["alternatives"], "best_alternative")):
        print(f"\n{label} ({len(rows)})")
        for r in rows:
            o = r[key]
            print(f"  {r['part_id']} {r['item'][:40]} · {o['product'][:40]} at {o['seller']} · {o['effort']}"
                  + (f" · saves ₹{o['saving_per_machine']:,.0f} per machine" if (o['saving_per_machine'] or 0) > 0 else "")
                  + f" · {o['url']}")
    for part in digest["parts"]:
        rate = (f"₹{part['rate']:,.0f} per unit, {part['qty'] or 1:g} per machine"
                if part["rate"] else "no rate")
        print(f"\n## {part['part_id']} {part['item']}  (ours: {rate})\n  >> {part['summary']}")
        for o in part["offers"]:
            label = "same part" if o["relation"] == "same part" else o["effort"]
            print(f"  [{label}] {o['product']} · {o['seller']} · {offer_price(o)}"
                  + (f" · {', '.join(o['offers'])}" if o["offers"] else "")
                  + (f"\n    {o['why']}" if o["why"] else "")
                  + (f"\n    would change: {o['changes']}" if o["changes"] else "")
                  + (f"\n    concerns: {o['concerns']}" if o["concerns"] else "") + f"\n    {o['url']}")
    if digest["unjudged"]:
        print("\nCould not be judged: " + "; ".join(f"{p['part_id']} {p['item']} ({p['reason']})" for p in digest["unjudged"]))
    if digest["nothing"]:
        print("\nNothing found: " + "; ".join(f"{p['part_id']} {p['item']}" for p in digest["nothing"]))
    if digest["deferred"]:
        print("\nLow spend, not searched this run: " + "; ".join(f"{p['part_id']} {p['item']}" for p in digest["deferred"]))
    if digest["custom"]:
        print("\nCustom, not searched: " + "; ".join(f"{p['part_id']} {p['item']}" for p in digest["custom"]))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
