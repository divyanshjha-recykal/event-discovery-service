"""What is actually in Mongo right now. Read-only.

    uv run python scripts/inspect_state.py
    uv run python scripts/inspect_state.py --dryrun    # the fixture database

A script rather than an inline one-liner, because multi-line `python -c` does
not survive PowerShell quoting.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import replace
from datetime import date

from opportunity_radar.config import MongoConfig
from opportunity_radar.storage import (
    EXTRACTION_FAILURES,
    OPPORTUNITIES,
    PROGRAMS,
    RUNS,
    get_client,
    get_database,
)


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


async def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dryrun", action="store_true",
                        help="Inspect the dry-run database instead.")
    parser.add_argument("--criteria", action="store_true",
                        help="Print every eligibility criterion in full.")
    args = parser.parse_args()

    config = MongoConfig.from_env()
    if args.dryrun:
        config = replace(config, database=f"{config.database}_dryrun")

    client = get_client(config)
    db = get_database(client, config)
    today = date.today()

    try:
        print(f"database: {config.database}\n")
        for col in (OPPORTUNITIES, PROGRAMS, RUNS, EXTRACTION_FAILURES):
            print(f"  {col:22} {await db[col].count_documents({})}")

        print(f"\n{'=' * 72}\nOPPORTUNITIES\n{'=' * 72}")
        actionable = 0
        async for d in db[OPPORTUNITIES].find({}):
            deadline = d.get("submission_deadline")
            live = False
            if deadline:
                try:
                    live = date.fromisoformat(deadline) >= today
                except ValueError:
                    pass
            usable = live or bool(d.get("deadline_note"))
            actionable += usable

            flag = " [DRY-RUN FIXTURE]" if d.get("dry_run") else ""
            print(f"\n{d.get('title')}{flag}")
            print(f"  {d.get('source_url')}")
            print(f"  {d.get('organizing_body')} · {d.get('category')} · cycle {d.get('cycle_year')}")
            print(f"  deadline {deadline or '-'}  verified={d.get('deadline_verified')}"
                  f"  note={d.get('deadline_note') or '-'}"
                  f"  {'(future)' if live else '(past/none)'}")

            criteria = d.get("eligibility_criteria") or []
            print(f"  criteria: {len(criteria)}")
            if args.criteria:
                for c in criteria:
                    print(f"     - {c}")

            e = d.get("eligibility")
            if not e:
                print("  eligibility: not evaluated")
                continue
            counts = {"met": 0, "not_met": 0, "unclear": 0}
            for r in e.get("criteria_results", []):
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            print(f"  eligibility: score={e.get('score')} confidence={e.get('confidence')}"
                  f"  met={counts['met']} not_met={counts['not_met']} unclear={counts['unclear']}"
                  f"  qualitative={len(e.get('qualitative_notes') or [])}"
                  f"  flags={len(e.get('classification_flags') or [])}")

        print(f"\n{'=' * 72}\nEXTRACTION FAILURES\n{'=' * 72}")
        async for f in db[EXTRACTION_FAILURES].find({}, {"_id": 0}):
            print(f"\n  {f['source_url']}")
            print(f"    {f['reason']}  (attempts {f.get('attempts')})")
            print(f"    {f.get('detail', '')[:160]}")

        print(f"\n{'=' * 72}\nRUNS\n{'=' * 72}")
        async for r in db[RUNS].find({}, {"_id": 0, "journey": 0}).sort("started_at", -1).limit(5):
            b = r.get("budget", {})
            print(f"  {r.get('started_at')}  {r.get('model')}  {r.get('status')}"
                  f"  spent {b.get('spent')}/{b.get('tool_calls')}  {r.get('counts')}")

        total = await db[OPPORTUNITIES].count_documents({})
        print(f"\nactionable (future deadline or rolling note): {actionable}/{total}")
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
