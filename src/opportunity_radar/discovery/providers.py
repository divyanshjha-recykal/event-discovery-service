"""Tavily and Firecrawl adapters used by deterministic graph nodes."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, datetime
from email.utils import parsedate_to_datetime

import httpx
from typing import Any

from ..config import require
from .state import EvidencePage, SearchHit

# Ceiling on one fetched page, set far above any real award page — this exists
# only to stop a pathological directory listing dominating the bundle.
MAX_PAGE_CHARS = 200_000

# Caller-side ceilings on the two provider calls. Both run in a worker thread,
# and a thread that never returns is invisible to the budget: the wall clock is
# only checked BETWEEN tool calls, so one stalled request hangs the entire run
# with no limit able to fire and no way for Stop to take effect — Stop sets a
# flag that is read at the next tool call, which never arrives.
#
# The `timeout` handed to Firecrawl is its server-side scrape limit, not an HTTP
# read timeout, so it does not cover a stalled connection. This does. The worker
# thread cannot be killed and finishes in the background; the run stops waiting.
SEARCH_TIMEOUT_SECONDS = 90
SCRAPE_TIMEOUT_SECONDS = 180

# Firecrawl's free plan caps requests per MINUTE, so limiting concurrency alone
# does nothing: one-at-a-time still fires ~20/min when a scrape takes 3s, and
# that is how a run consumed 11, 12 and 13 requests in a minute and lost four
# pages. The lane holds for the whole scrape (never two at once) and each start
# waits out the interval since the last one.
SCRAPE_MIN_INTERVAL_SECONDS = float(os.getenv("FIRECRAWL_MIN_INTERVAL", "7"))
_SCRAPE_LANE = asyncio.Lock()
_last_scrape_started = 0.0

# Per search result, for the site-selection call only. Multiplied by the whole
# pool, so at 35 results this is roughly 21k tokens of listing — affordable, and
# the aim is enough text to tell a real entry page from a press release about
# one. Raised from 1,200 once the pool shrank from 70 results to 35: the budget
# freed by searching less buys more to read about each result.
SEARCH_CONTENT_CHARS = 2_400

# Never worth a search slot: these host no entry pages.
EXCLUDED_DOMAINS = (
    "facebook.com", "linkedin.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "reddit.com", "pinterest.com", "tiktok.com",
)

_STUB_NOTE = (
    "[DRY-RUN FIXTURE: synthetic test data. Treat this as a genuine open "
    "opportunity so the complete pipeline is exercised.]"
)
_STUB_URL = "https://fixture.local/awards/circular-2027"
_STUB_PAGE = (
    f"{_STUB_NOTE}\n\n"
    "# National Circular Economy Award 2027\n\n"
    "The National Circular Economy Foundation invites entries from companies "
    "advancing material circularity.\n\n"
    "## Who can apply\n"
    "- Companies registered and operating in India\n"
    "- At least three years of operating history\n"
    "- Demonstrable work in recycling, e-waste, plastics or materials recovery\n\n"
    "The last date for submissions is 30 November 2027.\n"
)


def _published_iso(value: object) -> str:
    """Tavily sends RFC 2822 ("Wed, 06 May 2026 00:00:00 GMT"). Store ISO.

    Slicing the first ten characters produced "Wed, 06 Ma", which reads as a
    date to nobody and was handed to the ranker as if it were one.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


async def tool_tavily_search(
    query: str, *, max_results: int = 7, dry_run: bool = False
) -> list[SearchHit]:
    if dry_run:
        return [
            SearchHit(
                title="National Circular Economy Award 2027",
                url=_STUB_URL,
                snippet=(
                    "Applications open. The last date is 30 November 2027. "
                    "Open to Indian recycling companies. " + _STUB_NOTE
                ),
                query=query,
            )
        ]

    from tavily import TavilyClient  # pylint: disable=import-error,import-outside-toplevel

    client = TavilyClient(api_key=require("TAVILY_API_KEY"))
    # No `country`: measured against live queries it never biased toward the
    # named market, and combined with the market in the query text it returned
    # zero results. Geography belongs in the query text, which does work.
    search = asyncio.to_thread(
        client.search,
        query,
        max_results=max_results,
        search_depth="advanced",
        chunks_per_source=3,
        exclude_domains=list(EXCLUDED_DOMAINS),
        # Reaches the API body through the client's **kwargs. Off by default
        # outside topic=news, so without it every result arrives undated and
        # the ranker has to guess a page's age from its wording.
        include_published_date=True,
        # Deliberately NOT include_raw_content: `raw_content` is the whole page
        # from the top, which on an award site is navigation and hero banner.
        # `content` below is Tavily's relevance-selected extract — the part that
        # actually matches the query. Swapping one for the other cost a run.
    )
    try:
        payload = await asyncio.wait_for(search, timeout=SEARCH_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise RuntimeError(
            f"Tavily search exceeded {SEARCH_TIMEOUT_SECONDS}s and was abandoned"
        ) from exc

    hits: list[SearchHit] = []
    for item in payload.get("results", []):
        if not item.get("url"):
            continue
        content = str(item.get("content") or "")
        hits.append(
            SearchHit(
                title=str(item.get("title") or "(no title)"),
                url=str(item.get("url") or ""),
                snippet=content[:800],
                query=query,
                score=float(item.get("score") or 0.0),
                published_date=_published_iso(item.get("published_date")),
                content=content[:SEARCH_CONTENT_CHARS],
            )
        )
    return hits


EXA_URL = "https://api.exa.ai/search"
#: Exa writes a summary per result, so a search takes longer than Tavily's.
EXA_TIMEOUT_SECONDS = 120
#: Page text is fetched only to verify dates; the ranker never sees it.

_EXA_SUMMARY_QUERY = (
    "State what this page says about the award, competition, event or call for "
    "entries it describes. Use only what the page states."
)
# Facts only. Judgements (open or closed, is this a programme page) stay with our ranker.
_EXA_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "programme_name": {"type": "string", "description": "Programme name; empty if none."},
        "organiser": {"type": "string", "description": "Body that runs it, as named on the page; empty if not stated."},
        "entry_deadline": {"type": "string", "description": "Entry or nomination deadline as YYYY-MM-DD; empty if not stated."},
        "event_date": {"type": "string", "description": "Event or ceremony date as YYYY-MM-DD; empty if not stated."},
        "who_can_enter": {"type": "string", "description": "Who may enter, in the page's words; empty if not stated."},
        "country_restriction": {"type": "string", "description": "Country or region entrants must be from; empty if none stated."},
        "date_quote": {"type": "string", "description": "The sentence stating the deadline or event date, copied verbatim; empty if none."},
    },
}

_ISO_PREFIX = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})")


def _strict_date(value: object) -> str:
    """A real YYYY-MM-DD, taking the first date of a range; otherwise empty."""
    match = _ISO_PREFIX.match(str(value or ""))
    if not match:
        return ""
    try:
        return date.fromisoformat(match.group(1)).isoformat()
    except ValueError:
        return ""


def _exa_facts(summary: object) -> dict[str, str]:
    """The structured summary as strings; empty when Exa returned none or prose."""
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except json.JSONDecodeError:
            return {}
    if not isinstance(summary, Mapping):
        return {}
    return {key: str(summary.get(key) or "").strip() for key in _EXA_SUMMARY_SCHEMA["properties"]}


async def tool_exa_search(
    query: str, *, max_results: int = 7, dry_run: bool = False
) -> list[SearchHit]:
    if dry_run:
        return [
            SearchHit(
                title="National Circular Economy Award 2027",
                url=_STUB_URL,
                snippet="The last date for submissions is 30 November 2027. " + _STUB_NOTE,
                query=query,
                content="The last date for submissions is 30 November 2027. " + _STUB_NOTE,
                programme_name="National Circular Economy Award 2027",
                organiser="National Circular Economy Foundation",
                entry_deadline="2027-11-30",
                who_can_enter="Companies registered and operating in India",
                date_quote="The last date for submissions is 30 November 2027.",
            )
        ]

    payload = {
        "query": query,
        "type": "auto",
        "numResults": max_results,
        "excludeDomains": list(EXCLUDED_DOMAINS),
        "contents": {
            "highlights": True,
            "summary": {"query": _EXA_SUMMARY_QUERY, "schema": _EXA_SUMMARY_SCHEMA},
        },
    }
    try:
        async with httpx.AsyncClient(
            headers={"x-api-key": require("EXA_API_KEY")}, timeout=EXA_TIMEOUT_SECONDS
        ) as client:
            response = await asyncio.wait_for(
                client.post(EXA_URL, json=payload), timeout=EXA_TIMEOUT_SECONDS
            )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Exa search exceeded {EXA_TIMEOUT_SECONDS}s and was abandoned"
        ) from exc
    response.raise_for_status()

    hits: list[SearchHit] = []
    for item in response.json().get("results") or []:
        if not item.get("url"):
            continue
        facts = _exa_facts(item.get("summary"))
        deadline = _strict_date(facts.get("entry_deadline"))
        event = _strict_date(facts.get("event_date"))
        extract = " ... ".join(str(h) for h in item.get("highlights") or [])
        hits.append(
            SearchHit(
                title=str(item.get("title") or "(no title)"),
                url=str(item["url"]),
                snippet=extract[:800],
                query=query,
                published_date=_published_iso(item.get("publishedDate")),
                content=extract[:SEARCH_CONTENT_CHARS],
                programme_name=facts.get("programme_name", ""),
                organiser=facts.get("organiser", ""),
                entry_deadline=deadline,
                event_date=event,
                who_can_enter=facts.get("who_can_enter", ""),
                country_restriction=facts.get("country_restriction", ""),
                date_quote=facts.get("date_quote", "") if deadline or event else "",
            )
        )
    return hits


SearchTool = Callable[..., Awaitable[list[SearchHit]]]


def search_provider(name: str = "") -> tuple[str, SearchTool]:
    """The named provider, else SEARCH_PROVIDER, else Exa. An unknown name stops the run."""
    tools: dict[str, SearchTool] = {"tavily": tool_tavily_search, "exa": tool_exa_search}
    name = (name or os.getenv("SEARCH_PROVIDER") or "exa").strip().lower()
    if name not in tools:
        raise ValueError(f"SEARCH_PROVIDER must be one of {sorted(tools)}, got {name!r}")
    return name, tools[name]


def _metadata_dict(doc: Any) -> dict[str, Any]:
    value = getattr(doc, "metadata_dict", None)
    if isinstance(value, Mapping):
        return dict(value)
    value = getattr(doc, "metadata", None)
    if isinstance(value, Mapping):
        return dict(value)
    if value is not None:
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            result = dump(exclude_none=True)
            if isinstance(result, Mapping):
                return dict(result)
    return {}


def _first_text(meta: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _links(doc: Any) -> tuple[str, ...]:
    raw = getattr(doc, "links", None) or []
    links: list[str] = []
    for item in raw:
        if isinstance(item, str):
            links.append(item)
        elif isinstance(item, Mapping):
            value = item.get("url") or item.get("href")
            if isinstance(value, str):
                links.append(value)
    return tuple(dict.fromkeys(links))


async def tool_firecrawl_fetch(
    url: str,
    *,
    depth: int,
    dry_run: bool = False,
    only_main_content: bool = True,
    wait_for: int = 0,
) -> EvidencePage:
    if dry_run:
        return EvidencePage(
            url=url,
            depth=depth,
            markdown=_STUB_PAGE,
            title="National Circular Economy Award 2027",
            description="Open circular economy award for Indian companies.",
            status_code=200,
            content_type="text/html",
        )

    from firecrawl import Firecrawl  # pylint: disable=import-error,import-outside-toplevel

    client = Firecrawl(api_key=require("FIRECRAWL_API_KEY"))
    kwargs: dict[str, Any] = {
        "formats": ["markdown", "links"],
        "only_main_content": only_main_content,
        "timeout": 120_000,
    }
    if wait_for:
        kwargs["wait_for"] = wait_for
    global _last_scrape_started
    try:
        async with _SCRAPE_LANE:
            wait = SCRAPE_MIN_INTERVAL_SECONDS - (
                time.monotonic() - _last_scrape_started
            )
            if wait > 0:
                await asyncio.sleep(wait)
            _last_scrape_started = time.monotonic()
            doc = await asyncio.wait_for(
                asyncio.to_thread(client.scrape, url, **kwargs),
                timeout=SCRAPE_TIMEOUT_SECONDS,
            )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Firecrawl scrape exceeded {SCRAPE_TIMEOUT_SECONDS}s and was "
            f"abandoned: {url}"
        ) from exc
    markdown = str(
        getattr(doc, "markdown", None) or getattr(doc, "content", "") or ""
    )
    # Directory and listing sites return enormous pages — one conference index
    # came back at 887,000 characters. Deliberately far above any real award
    # page so this never truncates eligibility text; it exists only to stop a
    # pathological page from dominating memory and bundle assembly.
    if len(markdown) > MAX_PAGE_CHARS:
        markdown = markdown[:MAX_PAGE_CHARS]
    meta = _metadata_dict(doc)
    resolved_url = _first_text(meta, "source_url", "sourceURL") or url
    status = meta.get("status_code", meta.get("statusCode"))
    return EvidencePage(
        url=resolved_url,
        depth=depth,
        markdown=markdown,
        title=_first_text(meta, "title", "og_title", "ogTitle"),
        description=_first_text(
            meta, "description", "og_description", "ogDescription"
        ),
        status_code=int(status) if isinstance(status, (int, float)) else None,
        content_type=_first_text(meta, "content_type", "contentType"),
        links=_links(doc),
    )
