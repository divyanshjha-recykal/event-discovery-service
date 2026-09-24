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
import csv
import os
import smtplib
import ssl
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from opportunity_radar.config import MissingConfig, MongoConfig
from opportunity_radar.storage import (
    OPPORTUNITIES,
    get_client,
    get_database,
)

COLUMNS = [
    "Title", "Organising body", "Domain", "Category", "Year",
    "Submission deadline", "Deadline verified", "Event date",
    "Record state", "Fit score", "Fit confidence",
    "Conditions met", "Conditions not met", "Conditions unclear",
    "Entry conditions", "Judged on", "Must submit",
    "Quotes verified", "Source", "Evidence pages",
]


def _join(values) -> str:
    return " | ".join(str(v) for v in (values or []))


def _row(doc: dict) -> list:
    verdict = doc.get("eligibility") or {}
    results = verdict.get("criteria_results") or []
    counts = {key: sum(1 for r in results if r.get("status") == key)
              for key in ("met", "not_met", "unclear")}
    grounding = doc.get("grounding") or []
    quotes = (
        f"{sum(1 for g in grounding if g.get('found'))}/{len(grounding)}"
        if grounding else "not measured"
    )
    return [
        doc.get("title", ""),
        doc.get("organizing_body", ""),
        doc.get("domain", ""),
        doc.get("category", ""),
        doc.get("cycle_year", ""),
        doc.get("submission_deadline") or "not stated",
        "yes" if doc.get("deadline_verified") else "no",
        doc.get("event_date") or "",
        doc.get("record_state", ""),
        verdict.get("score") if verdict.get("score") is not None else "",
        verdict.get("confidence", ""),
        counts["met"], counts["not_met"], counts["unclear"],
        _join(doc.get("eligibility_criteria")),
        _join(doc.get("judging_criteria")),
        _join(doc.get("application_requirements")),
        quotes,
        doc.get("source_url", ""),
        _join(doc.get("evidence_urls")),
    ]


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
        query["discovery_run_id"] = args.run
    elif args.since:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.since)
        query["updated_at"] = {"$gte": cutoff}
    if not args.include_thin:
        query["record_state"] = "ready"
    return [doc async for doc in db[OPPORTUNITIES].find(query).sort("_id", -1)]


def _write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for doc in rows:
            writer.writerow(_row(doc))


def _summary(rows: list[dict]) -> str:
    lines = [
        f"Opportunity Radar — {len(rows)} opportunity(ies), "
        f"{date.today().isoformat()}",
        "",
    ]
    for doc in rows:
        verdict = doc.get("eligibility") or {}
        deadline = doc.get("submission_deadline") or doc.get("event_date") or "no date stated"
        score = verdict.get("score")
        fit = f"fit {score:.2f} ({verdict.get('confidence')})" if score is not None else "not yet judged"
        lines += [
            f"* {doc.get('title')}",
            f"    {doc.get('organizing_body')} — {deadline} — {fit}",
            f"    {doc.get('source_url')}",
            "",
        ]
    lines.append("Full details, entry conditions and evidence pages are in the attached CSV.")
    return "\n".join(lines)


def _send(args, csv_path: Path, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not host or not sender:
        raise MissingConfig(
            "SMTP_HOST and SMTP_FROM (or SMTP_USERNAME) must be set in .env"
        )
    port = int(os.getenv("SMTP_PORT") or (465 if os.getenv("SMTP_SSL") else 587))

    message = EmailMessage()
    message["Subject"] = args.subject
    message["From"] = sender
    message["To"] = ", ".join(args.to)
    message.set_content(body)
    message.add_attachment(
        csv_path.read_bytes(), maintype="text", subtype="csv",
        filename=csv_path.name,
    )

    context = ssl.create_default_context()
    username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
    if os.getenv("SMTP_SSL"):
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.send_message(message)


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
    parser.add_argument("--subject", default="Opportunity Radar — discovered opportunities")
    args = parser.parse_args()
    # --send is the whole demo path: newest run, address already configured.
    if args.send:
        if not (args.run or args.since):
            args.latest_run = True
        if not args.to:
            configured = os.getenv("SMTP_TO", "")
            args.to = [a.strip() for a in configured.split(",") if a.strip()]
            if not args.to:
                print("--send needs SMTP_TO set in .env, or an explicit --to")
                return 1

    rows = await _load(args)
    if not rows:
        print("No matching opportunities. Nothing written, nothing sent.")
        return 1

    csv_path = Path(args.out).resolve()
    _write_csv(rows, csv_path)
    body = _summary(rows)
    print(body)
    print(f"\nCSV written: {csv_path}")

    if not args.to:
        print("No --send or --to given, so no mail was sent.")
        return 0
    _send(args, csv_path, body)
    print(f"Sent to {', '.join(args.to)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
