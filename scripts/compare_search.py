"""Compare Tavily and Exa on the same queries, without touching the pipeline.

    uv run python scripts/compare_search.py                  # queries from the newest run
    uv run python scripts/compare_search.py --run 652ec9     # a specific run
    uv run python scripts/compare_search.py --fresh          # make Exa re-crawl every page

Tavily's results are read back from the run's journey, so only Exa is called.
Roughly $0.02 per query from Exa credits. Needs EXA_API_KEY in .env.
Writes reference/search-compare-<run>.json with every result.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import httpx

from opportunity_radar.config import MongoConfig
from opportunity_radar.discovery.link_resolver import canonicalize_url
from opportunity_radar.storage import get_client, get_database

EXA_URL = "https://api.exa.ai/search"
RESULTS_PER_QUERY = 7  # matches tool_tavily_search's default
PAGE_TEXT_CHARS = 12_000

SUMMARY_QUERY = (
    "Describe the award, competition, event or call for entries this page is "
    "about, using only what the page states."
)

# Ten flat properties: Exa's limit for structured summaries.
SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["is_programme_page", "status"],
    "properties": {
        "is_programme_page": {
            "type": "boolean",
            "description": "True only if the page belongs to ONE award, competition, event or "
            "call for entries and is published by the body that runs it. False for news, "
            "press releases, directories, lists of many programmes, or a company listing "
            "awards it has won.",
        },
        "programme_name": {"type": "string", "description": "Programme name; empty if not a programme page."},
        "organiser": {"type": "string", "description": "Body that runs it, as named on the page; empty if the page does not say."},
        "kind": {"type": "string", "description": "award, competition, event, conference, call for papers, or other."},
        "entry_deadline": {"type": "string", "description": "Entry or nomination deadline as YYYY-MM-DD; empty if not stated."},
        "event_date": {"type": "string", "description": "Event or ceremony date as YYYY-MM-DD; empty if not stated."},
        "status": {"type": "string", "description": "open, upcoming, closed or unclear, as the page states it."},
        "who_can_enter": {"type": "string", "description": "Who may enter, in the page's words; empty if not stated."},
        "country_restriction": {"type": "string", "description": "Country or region entrants must be from; empty if none stated."},
        "date_quote": {"type": "string", "description": "The exact sentence stating the deadline or event date, copied verbatim; empty if none."},
    },
}

_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
# Measurement only: does a day-and-month date appear in the text the ranker sees?
_DATE_IN_TEXT = re.compile(
    rf"\b\d{{1,2}}(st|nd|rd|th)?\s+{_MONTH}\b|\b{_MONTH}\s+\d{{1,2}}\b|\b20\d{{2}}-\d{{2}}-\d{{2}}\b",
    re.IGNORECASE,
)


def _squash(text: str) -> str:
    return " ".join((text or "").split()).casefold()


async def _banked_run(prefix: str | None) -> tuple[str, list[dict]]:
    """The run's queries and the Tavily results it stored for each."""
    db = get_database(get_client(), MongoConfig.from_env())
    query = {"run_id": {"$regex": f"^{re.escape(prefix)}"}} if prefix else {}
    run = await db.runs.find_one(query, sort=[("_id", -1)])
    if not run:
        raise SystemExit(f"No run found for {prefix or 'newest'}")
    searches, seen = [], set()
    for event in run.get("journey", []):
        if event.get("tool") == "search" and event.get("query") and event["query"] not in seen:
            seen.add(event["query"])
            searches.append({"query": event["query"], "tavily": event.get("results") or []})
    return run["run_id"], searches


def _exa_search(client: httpx.Client, query: str, fresh: bool) -> dict:
    contents: dict = {
        "text": {"maxCharacters": PAGE_TEXT_CHARS},
        "summary": {"query": SUMMARY_QUERY, "schema": SUMMARY_SCHEMA},
    }
    if fresh:
        contents["maxAgeHours"] = 0
    response = client.post(
        EXA_URL,
        json={"query": query, "type": "auto", "numResults": RESULTS_PER_QUERY, "contents": contents},
    )
    response.raise_for_status()
    return response.json()


def _read_exa_result(item: dict, today: str) -> dict:
    """Parse the structured summary and check its date quote against the page."""
    raw = item.get("summary") or ""
    try:
        fields = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        fields = {"unparsed_summary": raw}
    quote = fields.get("date_quote") or ""
    dates = [d for d in (fields.get("entry_deadline"), fields.get("event_date")) if d]
    deadline = fields.get("entry_deadline") or ""
    return {
        "title": item.get("title"),
        "url": canonicalize_url(item.get("url") or ""),
        "published_date": (item.get("publishedDate") or "")[:10],
        "fields": fields,
        "has_date": bool(dates),
        "date_quote_on_page": bool(quote) and _squash(quote) in _squash(item.get("text") or ""),
        "already_past": bool(deadline) and deadline < today,
    }


def _print_query(n: int, block: dict) -> None:
    print("\n" + "=" * 96)
    print(f"Q{n}: {block['query']}")
    print("-" * 96)
    print(f"TAVILY ({len(block['tavily'])})")
    for i, hit in enumerate(block["tavily"], 1):
        date_flag = "date in text" if _DATE_IN_TEXT.search(hit.get("snippet") or "") else "no date"
        print(f"  {i}. {str(hit.get('title'))[:62]:64s} [{date_flag}]")
        print(f"     {str(hit.get('url'))[:88]}")
    print(f"EXA ({len(block['exa'])})")
    for i, hit in enumerate(block["exa"], 1):
        f = hit["fields"]
        page = "PROGRAMME" if f.get("is_programme_page") else "not a programme page"
        quote = " quote on page" if hit["date_quote_on_page"] else (" quote NOT on page" if f.get("date_quote") else "")
        past = "  PAST" if hit["already_past"] else ""
        print(f"  {i}. {str(hit['title'])[:62]:64s} [{page}]")
        print(f"     {hit['url'][:88]}")
        print(f"     status {f.get('status') or '-'} | deadline {f.get('entry_deadline') or '-'} | "
              f"event {f.get('event_date') or '-'}{quote}{past}")
        if f.get("who_can_enter") or f.get("country_restriction"):
            print(f"     enters: {str(f.get('who_can_enter') or '-')[:70]} | "
                  f"country: {f.get('country_restriction') or '-'}")


def _totals(blocks: list[dict], cost: float) -> None:
    tav = [h for b in blocks for h in b["tavily"]]
    exa = [h for b in blocks for h in b["exa"]]
    tav_urls = {canonicalize_url(h.get("url") or "") for h in tav}
    exa_urls = {h["url"] for h in exa}
    dated = [h for h in exa if h["has_date"]]
    quoted = [h for h in dated if h["date_quote_on_page"]]
    print("\n" + "=" * 96)
    print("TOTALS")
    print(f"  {'':44s}{'Tavily':>14s}{'Exa':>14s}")
    rows = [
        ("results", len(tav), len(exa)),
        ("unique URLs", len(tav_urls), len(exa_urls)),
        ("URLs found by both", len(tav_urls & exa_urls), len(tav_urls & exa_urls)),
        ("date available at search time", sum(1 for h in tav if _DATE_IN_TEXT.search(h.get("snippet") or "")), len(dated)),
        ("  of which quoted verbatim on the page", "-", len(quoted)),
        ("programme pages (Exa's own judgement)", "-", sum(1 for h in exa if h["fields"].get("is_programme_page"))),
        ("deadline already past", "-", sum(1 for h in exa if h["already_past"])),
    ]
    for label, t, e in rows:
        print(f"  {label:44s}{t!s:>14s}{e!s:>14s}")
    print(f"\n  Exa cost reported: ${cost:.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", help="run_id prefix; default is the newest run")
    parser.add_argument("--fresh", action="store_true", help="force Exa to re-crawl every page")
    args = parser.parse_args()

    key = os.getenv("EXA_API_KEY", "").strip()
    if not key:
        print("EXA_API_KEY is not set in .env")
        return 1

    run_id, blocks = asyncio.run(_banked_run(args.run))
    if not blocks:
        print(f"Run {run_id[:6]} has no search events to compare")
        return 1
    print(f"Run {run_id[:6]}: {len(blocks)} queries, Tavily results from the run, Exa called live")

    today = date.today().isoformat()
    cost, failed = 0.0, 0
    with httpx.Client(headers={"x-api-key": key}, timeout=120) as client:
        for n, block in enumerate(blocks, 1):
            try:
                body = _exa_search(client, block["query"], args.fresh)
            except httpx.HTTPError as exc:
                failed += 1
                block["exa"], block["error"] = [], f"{type(exc).__name__}: {exc}"
                print(f"\nQ{n} Exa failed: {block['error'][:200]}")
                continue
            cost += float((body.get("costDollars") or {}).get("total") or 0)
            block["exa"] = [_read_exa_result(item, today) for item in body.get("results") or []]
            _print_query(n, block)

    _totals(blocks, cost)
    out = Path(__file__).resolve().parents[1] / "reference" / f"search-compare-{run_id[:6]}.json"
    out.write_text(json.dumps({"run_id": run_id, "today": today, "fresh": args.fresh,
                               "queries": blocks}, indent=1, default=str), encoding="utf-8")
    print(f"  Full results: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
