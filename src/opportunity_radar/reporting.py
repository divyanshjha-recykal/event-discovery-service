"""Opportunities as a CSV, and mailing it to the configured internal recipients.

Reporting only: it mails stored records to the addresses in SMTP_TO and never
contacts an award body or submits anything.

SMTP settings come from the environment (.env, which is gitignored):

    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
    SMTP_TO      # default recipients, comma-separated
    SMTP_SSL=1   # set when the port speaks TLS directly (465), else STARTTLS
"""

from __future__ import annotations

import csv
import io
import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage

from .config import MissingConfig

COLUMNS = [
    "Title", "Organising body", "Domain", "Category", "Year",
    "Submission deadline", "Deadline verified", "Event date",
    "Record state", "Fit score", "Fit confidence",
    "Conditions met", "Conditions not met", "Conditions unclear",
    "Entry conditions", "Judged on", "Must submit",
    "Quotes verified", "Source", "Evidence pages",
]

DEFAULT_SUBJECT = "Opportunity Radar — discovered opportunities"


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


def csv_bytes(rows: list[dict]) -> bytes:
    """UTF-8 with a BOM, so Excel opens it with the right encoding."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for doc in rows:
        writer.writerow(_row(doc))
    return buffer.getvalue().encode("utf-8-sig")


def summary(rows: list[dict]) -> str:
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
        state = " — needs more evidence" if doc.get("record_state") == "needs_deeper_read" else ""
        lines += [
            f"* {doc.get('title')}{state}",
            f"    {doc.get('organizing_body')} — {deadline} — {fit}",
            f"    {doc.get('source_url')}",
            "",
        ]
    lines.append("Full details, entry conditions and evidence pages are in the attached CSV.")
    return "\n".join(lines)


def configured_recipients() -> list[str]:
    return [a.strip() for a in os.getenv("SMTP_TO", "").split(",") if a.strip()]


def send_report(
    to: list[str], rows: list[dict], filename: str, subject: str = DEFAULT_SUBJECT
) -> None:
    """Mail the rows as a CSV attachment with a plain-text summary. Raises on failure."""
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not host or not sender:
        raise MissingConfig("SMTP_HOST and SMTP_FROM (or SMTP_USERNAME) must be set in .env")
    if not to:
        raise MissingConfig("no recipient: set SMTP_TO in .env")
    port = int(os.getenv("SMTP_PORT") or (465 if os.getenv("SMTP_SSL") else 587))

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(to)
    message.set_content(summary(rows))
    message.add_attachment(
        csv_bytes(rows), maintype="text", subtype="csv", filename=filename,
    )

    context = ssl.create_default_context()
    username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
    if os.getenv("SMTP_SSL"):
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.send_message(message)
