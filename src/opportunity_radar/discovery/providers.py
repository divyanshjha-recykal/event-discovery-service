"""Tavily and Firecrawl adapters used by deterministic graph nodes."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ..config import require
from .state import EvidencePage, SearchHit

# A ceiling on any single fetched page. Set well above a real award page so it
# never costs us eligibility content — a directory listing at 887k characters is
# what this is for, not an awards site.
MAX_PAGE_CHARS = 200_000

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


async def tavily_search(
    query: str, *, max_results: int = 5, dry_run: bool = False
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
    payload = await asyncio.to_thread(
        client.search,
        query,
        max_results=max_results,
        search_depth="advanced",
    )
    return [
        SearchHit(
            title=str(item.get("title") or "(no title)"),
            url=str(item.get("url") or ""),
            snippet=str(item.get("content") or "")[:800],
            query=query,
        )
        for item in payload.get("results", [])
        if item.get("url")
    ]


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


async def firecrawl_fetch(
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
    doc = await asyncio.to_thread(client.scrape, url, **kwargs)
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
