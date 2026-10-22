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
from html import escape

from .config import MissingConfig

COLUMNS = [
    "Title", "Organising body", "Domain", "Category", "Year",
    "Submission deadline", "Deadline verified", "Event date",
    "Record state", "Fit score", "Fit confidence",
    "Conditions met", "Conditions not met", "Conditions unclear",
    "Entry conditions", "Fits our work", "Judged on", "Must submit",
    "Quotes verified", "Source", "Evidence pages",
]

DEFAULT_SUBJECT = "Opportunity Radar — discovered opportunities"


def _join(values) -> str:
    return " | ".join(str(v) for v in (values or []))


def _fits(doc: dict) -> list[str]:
    """A research venue's matches: our work, the call's topic, and how well it fits."""
    works = (doc.get("fit") or {}).get("works") or []
    return [f"{w['work']} → {w['topic']} ({w['fit']})" for w in works if w.get("fit") != "no"]


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
        _join(_fits(doc)),
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
        if doc.get("fit"):
            fit = f"fits our work: {len(_fits(doc))} line(s)"
        state = " — needs more evidence" if doc.get("record_state") == "needs_deeper_read" else ""
        lines += [
            f"* {doc.get('title')}{state}",
            f"    {doc.get('organizing_body')} — {deadline} — {fit}",
            f"    {doc.get('source_url')}",
            "",
        ]
    lines.append("Full details, entry conditions and evidence pages are in the attached CSV.")
    return "\n".join(lines)


SIGNAL_COLUMNS = ["Section", "Importance", "Company", "Kind", "Date", "Headline", "What happened",
                  "Why it matters", "Link", "Also reported by"]
TYPE_ORDER = (("award", "Awards"), ("grant", "Grants"), ("event", "Events"),
              ("conference", "Conferences"), ("research", "Research"))

# Inline styles only: mail clients drop <style> blocks and external CSS.
_WRAP = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.45;'
         'color:#1f2328;max-width:680px">')
_H1 = '<h1 style="font-size:20px;margin:0 0 4px">{}</h1>'
_SUB = '<p style="color:#59636e;margin:0 0 18px">{}</p>'
_H2 = ('<h2 style="font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#59636e;'
       'border-bottom:1px solid #d1d9e0;padding-bottom:4px;margin:22px 0 10px">{}</h2>')
_ITEM = ('<div style="margin:0 0 14px"><a href="{url}" style="font-weight:bold;color:#0969da;'
         'text-decoration:none">{title}</a><div style="font-size:12px;color:#59636e;margin:2px 0">{meta}</div>'
         '<div>{body}</div></div>')
_FOOT = '<p style="font-size:12px;color:#59636e;border-top:1px solid #d1d9e0;padding-top:8px;margin-top:22px">{}</p>'
_NOTE = '<p style="background:#f6f8fa;border-left:3px solid #0969da;padding:6px 10px;margin:0 0 12px">{}</p>'


def _e(value) -> str:
    return escape(str(value or ""), quote=True)


def _page(title: str, sub: str, blocks: list[tuple], foot: str) -> str:
    """Email HTML: heading, then each block's optional note and its items as linked title, meta line and body."""
    parts = [_WRAP, _H1.format(_e(title)), _SUB.format(_e(sub))]
    for heading, items, *note in blocks:
        parts.append(_H2.format(_e(heading)))
        if note and note[0]:
            parts.append(_NOTE.format(_e(note[0])))
        parts += [_ITEM.format(url=_e(i["url"]), title=_e(i["title"]), meta=_e(i["meta"]), body=_e(i["body"]))
                  for i in items]
    parts += [_FOOT.format(_e(foot)), "</div>"]
    return "".join(parts)


def _text(title: str, sub: str, blocks: list[tuple], foot: str) -> str:
    lines = [title, sub, ""]
    for heading, items, *note in blocks:
        lines += [heading.upper(), ""] + ([note[0], ""] if note and note[0] else [])
        for i in items:
            lines += [f"* {i['title']}", f"  {i['meta']}", f"  {i['body']}", f"  {i['url']}", ""]
    return "\n".join(lines + [foot])


def opportunities_email(rows: list[dict], run_id: str) -> dict:
    """Subject, plain text, HTML and CSV for one opportunity run, grouped by type."""
    def item(doc: dict) -> dict:
        verdict = doc.get("eligibility") or {}
        deadline = (f"deadline {doc['submission_deadline']}" if doc.get("submission_deadline")
                    else f"event {doc['event_date']}, no deadline stated" if doc.get("event_date")
                    else "no deadline stated")
        if doc.get("fit"):
            fit = f"fits our work: {len(_fits(doc))} line(s)"
        elif verdict.get("score") is not None:
            fit = f"fit {verdict['score']:.2f} ({verdict.get('confidence')})"
        else:
            fit = "not yet judged"
        state = " · needs more evidence" if doc.get("record_state") == "needs_deeper_read" else ""
        return {"url": doc.get("source_url"), "title": doc.get("title"),
                "meta": f"{doc.get('organizing_body')} · {deadline} · {fit}{state}",
                "body": doc.get("summary") or ""}

    blocks = [(label, [item(d) for d in rows if d.get("category") == key]) for key, label in TYPE_ORDER]
    blocks.append(("Other", [item(d) for d in rows if d.get("category") not in dict(TYPE_ORDER)]))
    blocks = [b for b in blocks if b[1]]
    filename = f"opportunity-radar-{run_id[:6]}.csv"
    args = (f"Opportunity Radar · {date.today():%d %b %Y}", f"{len(rows)} opportunit{'y' if len(rows) == 1 else 'ies'} from run {run_id[:6]}",
            blocks, f"Entry conditions, fit and evidence pages for every opportunity are in the attached {filename}.")
    return {"subject": f"{DEFAULT_SUBJECT} · {date.today():%d %b %Y}", "text": _text(*args), "html": _page(*args),
            "csv": csv_bytes(rows), "filename": filename, "count": len(rows)}


def signals_email(sections: list[dict], run: dict) -> dict:
    """Subject, plain text, HTML and CSV for one competitor-watch run, by section."""
    blocks = [(s["title"], [{"url": x["url"], "title": x["headline"], "body": x["what_happened"],
                             "meta": f"{x['importance'].capitalize()} · {x['competitor']} · {x.get('date') or 'undated'}"}
                            for x in s["signals"]]) for s in sections]
    counts = run.get("counts") or {}
    filename = f"competitor-watch-{run['run_id'][:6]}.csv"
    sub = (f"{counts.get('signals', 0)} new signals · {counts.get('merged', 0)} added to known stories · "
           f"window from {(run.get('budget') or {}).get('since', '?')}")
    args = (f"Competitor watch · {date.today():%d %b %Y}", sub, blocks,
            f"Every signal with why it matters and its other sources is in the attached {filename}."
            if sections else "Nothing new since the last watch run.")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(SIGNAL_COLUMNS)
    for s in sections:
        for x in s["signals"]:
            writer.writerow([s["title"], x["importance"], x["competitor"], x["kind"], x.get("date") or "",
                             x["headline"], x["what_happened"], x["why_it_matters"], x["url"],
                             _join(x.get("also_reported_by"))])
    return {"subject": f"Competitor watch · {date.today():%d %b %Y}", "text": _text(*args), "html": _page(*args),
            "csv": buffer.getvalue().encode("utf-8-sig"), "filename": filename,
            "count": sum(len(s["signals"]) for s in sections)}


COMPONENT_COLUMNS = ["Part ID", "Item", "Qty per machine", "Our rate per unit (₹, before GST)", "Relation",
                     "Effort", "What would change", "Product", "Seller", "Listed price", "Currency", "Listed per",
                     "GST", "Price before GST", "Units per our unit", "Price per our unit (₹)", "Compared on",
                     "Difference vs our rate (%)", "Per machine, theirs (₹)", "Per machine, ours (₹)",
                     "Saving per machine (₹)", "In stock", "Offers", "Why", "Must-have checks", "Concerns", "Link"]
EMAIL_FINDINGS_PER_PART = 5

_TABLE = '<table style="border-collapse:collapse;width:100%;font-size:12px;margin:0 0 6px">'
_TH = '<th style="text-align:left;background:#f6f8fa;padding:4px 6px;border-bottom:1px solid #d1d9e0">{}</th>'
_TD = '<td style="padding:4px 6px;border-bottom:1px solid #eaeef2;vertical-align:top">{}</td>'
_MORE = '<p style="font-size:12px;color:#59636e;margin:0 0 16px">{}</p>'


def _rs(n: float) -> str:
    return f"₹{n:,.0f}"


def listed_price(o: dict) -> str:
    """The price exactly as the seller lists it, with what it buys and its GST basis."""
    if o["price"] is None:
        return "no price shown"
    text = f"{o['currency']} {o['price']:,.0f} per {o['price_unit'] or 'unit not stated'} (GST {o['gst']})"
    if o["price_before_gst"] is not None and o["price_before_gst"] != o["price"]:
        text += f"; {o['price_before_gst']:,.0f} before GST"
    return text


def compared_price(o: dict) -> str:
    """The seller's price per our unit against our rate, or why it was not compared."""
    if o["unit_price"] is None:
        if o["price"] is None:
            return "—"
        return "not compared: " + ("not a rupee price" if o["currency"].strip().upper() not in ("INR", "₹", "RS", "RS.")
                                   else f"listed per {o['price_unit'] or 'an unstated unit'}, not clearly one of our units")
    basis = "" if o["compared_on"] == "before GST" else f", on their price with GST {o['gst']}"
    return f"{_rs(o['unit_price'])} per unit · {o['diff_pct']:+.0f}% vs ours {_rs(o['rate'])}{basis}"


def per_machine(o: dict) -> str:
    if o["machine_theirs"] is None:
        return "—"
    return f"{_rs(o['machine_theirs'])} vs ours {_rs(o['machine_ours'])} for {o['qty'] or 1:g}"


def offer_price(o: dict) -> str:
    """One line for a terminal: listed price, then the comparison."""
    return f"{listed_price(o)} → {compared_price(o)}"


def _short(text: str, n: int = 180) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def components_email(digest: dict, run: dict) -> dict:
    """Subject, plain text, HTML and CSV for one component-watch run: a table of the top findings per part."""
    product = (run.get("budget") or {}).get("product", "")
    filename = f"component-watch-{product.lower()}-{run['run_id'][:6]}.csv"
    count = sum(len(p["offers"]) for p in digest["parts"])
    title = f"Component watch · {product} · {date.today():%d %b %Y}"
    sub = (f"{product}: {count} finding(s) for {len(digest['parts'])} part(s) · nothing found for "
           f"{len(digest['nothing'])} · {len(digest['custom'])} custom and {len(digest['deferred'])} low-spend part(s) "
           f"not searched. Prices are compared per unit as our BOM counts it, before GST where the seller states it.")
    head = ["Type", "Product · seller", "Listed price", "Per unit vs ours", "Per machine", "Notes"]
    html = [_WRAP, _H1.format(_e(title)), _SUB.format(_e(sub))]
    text = [title, sub, ""]
    ov = digest["overview"]
    lead = (f"Possible saving: {_rs(ov['saving_per_machine'])} per machine, like for like, on a {_rs(ov['machine_cost'])} "
            f"machine. {ov['searched']} parts searched ({ov['searched_share']:.0%} of off-the-shelf spend); "
            f"{ov['verdicts']['We pay the lowest found']} where we already pay the lowest price found; "
            f"{ov['upgrades']} with a better or newer option that fits.")
    html.append(_NOTE.format(_e(lead)))
    text += [lead, ""]
    for label, rows, pick in (("Act on: cheaper, like for like", digest["act_on"], "best"),
                              ("Worth a look: cheaper, but changes needed", digest["review"], "best_change")):
        if not rows:
            continue
        html += [_H2.format(_e(label)), _TABLE, "<tr>" + "".join(_TH.format(h) for h in (
            "Part", "Ours per machine", "Option · seller", "Per unit vs ours", "Saving per machine", "Effort")) + "</tr>"]
        text += [label.upper(), ""]
        for r in rows:
            o = r[pick]
            cells = [_e(f"{r['part_id']} · {r['item']}"), _e(_rs(r["line_cost"])),
                     f'<a href="{_e(o["url"])}" style="color:#0969da;text-decoration:none">{_e(o["product"] or o["title"])}</a>'
                     f'<br><span style="color:#59636e">{_e(o["seller"])}</span>',
                     _e(compared_price(o)), _e(_rs(o["saving_per_machine"])),
                     _e("same part" if o["relation"] == "same part" else o["effort"])]
            html.append("<tr>" + "".join(_TD.format(c) for c in cells) + "</tr>")
            text += [f"* {r['part_id']} {r['item']}: {o['product']} at {o['seller']}, saves {_rs(o['saving_per_machine'])}"
                     f" per machine ({compared_price(o)}) {o['url']}", ""]
        html.append("</table>")
    if digest["upgrades"]:
        label = "Better or newer options that fit"
        html += [_H2.format(_e(label)), _TABLE, "<tr>" + "".join(_TH.format(h) for h in (
            "Part", "Option · seller", "What is better", "Effort", "Per unit vs ours")) + "</tr>"]
        text += [label.upper(), ""]
        for r in digest["upgrades"]:
            o = r["best_upgrade"]
            better = f"{', '.join(o['offers'])}: {o['why']}"
            cells = [_e(f"{r['part_id']} · {r['item']}"),
                     f'<a href="{_e(o["url"])}" style="color:#0969da;text-decoration:none">{_e(o["product"] or o["title"])}</a>'
                     f'<br><span style="color:#59636e">{_e(o["seller"])}</span>',
                     _e(_short(better, 240)), _e(o["effort"] + (f": {o['changes']}" if o["changes"] else "")),
                     _e(compared_price(o))]
            html.append("<tr>" + "".join(_TD.format(c) for c in cells) + "</tr>")
            text += [f"* {r['part_id']} {r['item']}: {o['product']} at {o['seller']} ({o['effort']}) — {better} {o['url']}", ""]
        html.append("</table>")
    html.append(_H2.format("Every part searched"))
    for part in digest["parts"]:
        rate = f"ours {_rs(part['rate'])} per unit, {part['qty'] or 1:g} per machine" if part["rate"] else "no rate on file"
        heading = f"{part['part_id']} · {part['item']} · {rate}"
        shown, more = part["offers"][:EMAIL_FINDINGS_PER_PART], len(part["offers"]) - EMAIL_FINDINGS_PER_PART
        html += [_H2.format(_e(heading)), _NOTE.format(_e(part["summary"])), _TABLE,
                 "<tr>" + "".join(_TH.format(h) for h in head) + "</tr>"]
        text += [heading.upper(), part["summary"], ""]
        for o in shown:
            kind = "same part" if o["relation"] == "same part" else o["effort"]
            notes = " ".join(x for x in (f"Would change: {o['changes']}." if o["changes"] else "",
                                         f"Concerns: {o['concerns']}" if o["concerns"] else "") if x)
            cells = [_e(kind), f'<a href="{_e(o["url"])}" style="color:#0969da;text-decoration:none">'
                                f'{_e(o["product"] or o["title"])}</a><br><span style="color:#59636e">{_e(o["seller"])}</span>',
                     _e(listed_price(o)), _e(compared_price(o)), _e(per_machine(o)), _e(_short(notes))]
            html.append("<tr>" + "".join(_TD.format(c) for c in cells) + "</tr>")
            text += [f"* [{kind}] {o['product']} · {o['seller']}", f"  {listed_price(o)}",
                     f"  {compared_price(o)} · per machine: {per_machine(o)}", f"  {o['url']}", ""]
        html.append("</table>")
        if more > 0:
            html.append(_MORE.format(_e(f"{more} more finding(s) for this part in the attached {filename} and on the dashboard.")))
            text += [f"  ({more} more in {filename})", ""]
    foot = (f"Nothing found for: {'; '.join(p['item'] for p in digest['nothing']) or 'none'}. "
            + (f"Low spend, left for a full run: {'; '.join(p['item'] for p in digest['deferred'])}. " if digest["deferred"] else "")
            + f"Every finding with its must-have checks is in the attached {filename}.")
    html += [_FOOT.format(_e(foot)), "</div>"]
    text.append(foot)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COMPONENT_COLUMNS)
    blank = lambda v: "" if v is None else v  # noqa: E731
    for part in digest["parts"]:
        for o in part["offers"]:
            writer.writerow([part["part_id"], part["item"], blank(part["qty"]), blank(part["rate"]),
                             o["relation"], o["effort"], o["changes"], o["product"], o["seller"], blank(o["price"]),
                             o["currency"], o["price_unit"], o["gst"], blank(o["price_before_gst"]),
                             blank(o["units_per_part"]), blank(o["unit_price"]), blank(o["compared_on"]),
                             blank(o["diff_pct"]), blank(o["machine_theirs"]), blank(o["machine_ours"]),
                             blank(o["saving_per_machine"]), o["in_stock"], _join(o["offers"]), o["why"],
                             _join(f"{c['requirement']}: {c['status']}" for c in o["checks"]), o["concerns"], o["url"]])
    return {"subject": title, "text": "\n".join(text), "html": "".join(html),
            "csv": buffer.getvalue().encode("utf-8-sig"), "filename": filename, "count": count}


def configured_recipients() -> list[str]:
    return [a.strip() for a in os.getenv("SMTP_TO", "").split(",") if a.strip()]


def send_report(
    to: list[str], rows: list[dict], filename: str, subject: str = DEFAULT_SUBJECT
) -> None:
    """Mail opportunity rows with a readable body and the CSV attached. Raises on failure."""
    mail = opportunities_email(rows, rows[0].get("discovery_run_id") or "")
    send_mail(to, {**mail, "subject": subject, "filename": filename})


def send_mail(to: list[str], mail: dict) -> None:
    """Send an email built by opportunities_email or signals_email. Raises on failure."""
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not host or not sender:
        raise MissingConfig("SMTP_HOST and SMTP_FROM (or SMTP_USERNAME) must be set in .env")
    if not to:
        raise MissingConfig("no recipient: set SMTP_TO in .env")
    port = int(os.getenv("SMTP_PORT") or (465 if os.getenv("SMTP_SSL") else 587))

    message = EmailMessage()
    message["Subject"] = mail["subject"]
    message["From"] = sender
    message["To"] = ", ".join(to)
    message.set_content(mail["text"])
    message.add_alternative(mail["html"], subtype="html")
    message.add_attachment(mail["csv"], maintype="text", subtype="csv", filename=mail["filename"])

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
