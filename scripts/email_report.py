"""Export discovered opportunities to CSV and optionally email it.

    # write the CSV only — no mail sent, safe to run anytime
    uv run python scripts/email_report.py

    # send the newest run to the address configured in .env
    uv run python scripts/email_report.py --send

    # everything found in the last 7 days
    uv run python scripts/email_report.py --since 7 --to manager@example.com

Reporting only. This reads stored records and mails them to a recipient you
name; it never contacts an award body or submits anything. Nothing is sent
unless --send or --to is given.

SMTP settings come from the environment (.env, which is gitignored):

    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
    SMTP_TO      # default recipient, so --send needs no address
    SMTP_SSL=1   # set when the port speaks TLS directly (465), else STARTTLS
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opportunity_radar.config import MongoConfig
from opportunity_radar.reporting import (
    DEFAULT_SUBJECT,
    configured_recipients,
    csv_bytes,
    send_report,
    summary,
)
from opportunity_radar.storage import (
    OPPORTUNITIES,
    get_client,
    get_database,
)


async def _load(args) -> list[dict]:
    config = MongoConfig.from_env()
    db = get_database(get_client(), config)
    query: dict = {}
    if args.latest_run:
        newest = await db.runs.find_one(sort=[("_id", -1)])
        if not newest:
            return []
        query["discovery_run_id"] = newest.get("run_id")
    elif args.run:
        # The UI shows the first six characters; accept any prefix.
        query["discovery_run_id"] = {"$regex": f"^{re.escape(args.run)}"}
    elif args.since:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.since)
        query["updated_at"] = {"$gte": cutoff}
    if not args.include_thin:
        query["record_state"] = "ready"
    return [doc async for doc in db[OPPORTUNITIES].find(query).sort("_id", -1)]



async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true",
                        help="mail the newest run to SMTP_TO from .env")
    parser.add_argument("--to", action="append", default=[],
                        help="recipient, overriding SMTP_TO; repeat for several")
    parser.add_argument("--latest-run", action="store_true",
                        help="only opportunities stored by the newest run")
    parser.add_argument("--run", help="only opportunities from this run id")
    parser.add_argument("--since", type=int, help="only records updated in the last N days")
    parser.add_argument("--include-thin", action="store_true",
                        help="also include records with no entry conditions read")
    parser.add_argument("--out", default="opportunities.csv", help="CSV path")
    parser.add_argument("--subject", default=DEFAULT_SUBJECT)
    args = parser.parse_args()
    # --send is the whole demo path: newest run, address already configured.
    if args.send:
        if not (args.run or args.since):
            args.latest_run = True
        if not args.to:
            args.to = configured_recipients()
            if not args.to:
                print("--send needs SMTP_TO set in .env, or an explicit --to")
                return 1

    rows = await _load(args)
    if not rows:
        print("No matching opportunities. Nothing written, nothing sent.")
        return 1

    csv_path = Path(args.out).resolve()
    csv_path.write_bytes(csv_bytes(rows))
    print(summary(rows))
    print(f"\nCSV written: {csv_path}")

    if not args.to:
        print("No --send or --to given, so no mail was sent.")
        return 0
    send_report(args.to, rows, csv_path.name, args.subject)
    print(f"Sent to {', '.join(args.to)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
