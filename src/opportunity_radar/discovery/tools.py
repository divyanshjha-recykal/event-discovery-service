"""The five Discovery tools.

`search`, `scrape`, `extract`, `read_memory`, `save_opportunity`. Each one
checks the run budget before doing anything, so the budget is a hard stop rather
than a request the model may ignore.

Extraction stays its own visible step. `scrape` never extracts (that would run a
full extraction call on every page including ones the agent discards) and
`save_opportunity` never extracts (that would collapse scrape-succeeded,
extraction-succeeded and storage-succeeded into one opaque trace entry, which is
the opposite of why tracing exists).

One deviation worth naming: the `save_opportunity` *tool* takes a `source_url`
rather than a full record. The underlying plain function still takes a record —
the tool looks up the record `extract` produced earlier in this run. Passing a
whole record back through the model would cost tokens and invite transcription
drift on fields the extractor already validated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Any

from langchain_core.tools import StructuredTool

from ..config import require
from ..extraction import (
    ExtractionFailure,
    OpportunityRecord,
    extract as extract_page,
    record_warnings,
)
from ..storage import due_soon, known_orgs, save_opportunity as store_opportunity
from .budget import RunBudget
from .profile_seed import discovery_seed

MAX_PAGE_CHARS = 12_000       # what we hand the extractor; pages can be huge
MAX_SNIPPET_CHARS = 400       # per search result, back to the model
DEFAULT_SEARCH_RESULTS = 5


@dataclass
class DiscoveryContext:
    """Everything the tools share for one run."""

    db: Any
    budget: RunBudget
    model: str | None = None
    dry_run: bool = False

    pages: dict[str, str] = field(default_factory=dict)             # url -> text
    records: dict[str, OpportunityRecord] = field(default_factory=dict)
    saved: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seen_urls: set[str] = field(default_factory=set)


# --- stubs for --dry-run -----------------------------------------------------

# The fixture announces itself rather than pretending to be a real page. An
# earlier version was titled "Example ..." and a capable model correctly refused
# to scrape obvious placeholder data — good judgement, but it meant the dry run
# could never exercise scrape -> extract -> save, which is the path most worth
# testing before spending money. So it now tells the agent to proceed.
_STUB_NOTE = (
    "[DRY-RUN FIXTURE: this is synthetic test data, not a live result. "
    "Treat it as a genuine open opportunity and continue the normal "
    "scrape -> extract -> save sequence so the pipeline is exercised.]"
)

_STUB_RESULTS = [
    {
        "title": "National Circular Economy Award 2027",
        "url": "https://fixture.local/awards/circular-2027",
        "content": "Applications open. The last date is 30 November 2027. Open to "
                   "companies working in recycling and waste management in India. "
                   + _STUB_NOTE,
    },
]
_STUB_PAGE = (
    f"{_STUB_NOTE}\n\n"
    "# National Circular Economy Award 2027\n\n"
    "The National Circular Economy Foundation invites entries for the National "
    "Circular Economy Award 2027, recognising organisations advancing material "
    "circularity.\n\n"
    "## Who can apply\n\n"
    "- Companies registered and operating in India\n"
    "- At least three years of operating history\n"
    "- Demonstrable work in recycling, e-waste, plastics or materials recovery\n"
    "- Annual turnover above INR 10 crore\n\n"
    "## How to apply\n\n"
    "Submit the online entry form with supporting impact data. There is no "
    "entry fee. The last date for submissions is 30 November 2027.\n"
)


def build_tools(context: DiscoveryContext) -> list[StructuredTool]:
    """Construct the tool set bound to one run's context and budget."""

    def _guard(name: str) -> str | None:
        return context.budget.refusal(name)

    # -- search ---------------------------------------------------------------

    async def search(query: str) -> str:
        """Search the live web for award, grant, event and conference pages.

        Args:
            query: A specific search query. Prefer concrete program names,
                sectors and years over vague phrases.
        """
        refusal = _guard("search")
        if refusal:
            return refusal
        context.budget.consume("search")

        if context.dry_run:
            results = _STUB_RESULTS
        else:
            from tavily import TavilyClient

            client = TavilyClient(api_key=require("TAVILY_API_KEY"))
            payload = await asyncio.to_thread(
                client.search, query, max_results=DEFAULT_SEARCH_RESULTS
            )
            results = payload.get("results", [])

        if not results:
            return f"No results for {query!r}."

        lines = [f"{len(results)} result(s) for {query!r}:"]
        for item in results:
            url = item.get("url", "")
            context.seen_urls.add(url)
            snippet = (item.get("content") or "")[:MAX_SNIPPET_CHARS]
            lines.append(f"\n- {item.get('title', '(no title)')}\n  {url}\n  {snippet}")

        # Make the remaining headroom explicit. A model that cannot see how much
        # budget is left tends to behave as if it has none.
        lines.append(
            f"\n[{context.budget.remaining} of {context.budget.tool_calls} tool "
            f"calls remaining. {len(context.saved)} opportunity(ies) saved so far. "
            "If these results are poor, search again with a different angle.]"
        )
        return "\n".join(lines)

    # -- scrape ---------------------------------------------------------------

    async def scrape(url: str) -> str:
        """Fetch the readable text of one page so you can judge whether it is a
        genuine, currently-open opportunity worth extracting.

        Args:
            url: The page URL, taken from a search result.
        """
        refusal = _guard("scrape")
        if refusal:
            return refusal

        if url in context.pages:
            return (
                f"(already fetched this run)\n\n{context.pages[url][:MAX_PAGE_CHARS]}"
            )

        context.budget.consume("scrape")

        if context.dry_run:
            text = _STUB_PAGE
        else:
            from firecrawl import Firecrawl

            client = Firecrawl(api_key=require("FIRECRAWL_API_KEY"))
            try:
                doc = await asyncio.to_thread(
                    client.scrape, url, formats=["markdown"], only_main_content=True
                )
            except Exception as exc:  # noqa: BLE001 — reported to the model
                return f"SCRAPE FAILED for {url}: {type(exc).__name__}: {exc}"
            text = getattr(doc, "markdown", None) or getattr(doc, "content", "") or ""

        if not text.strip():
            return f"SCRAPE FAILED for {url}: page returned no readable text."

        context.pages[url] = text

        # Tool-level nudge, because the prompt alone did not hold: a run scraped
        # four bare domains and produced four records with no deadline. The
        # warning arrives at the moment of the decision rather than 2000 tokens
        # earlier in the system prompt, which is where it actually lands.
        note = ""
        if urlparse(url).path in ("", "/"):
            note = (
                f"\n\n[NOTE: {url} is a site homepage, not a call for entries. "
                "Homepages rarely state a deadline or eligibility list, and a "
                "record without a deadline is close to useless. Before "
                "extracting, look in the text above for a link to the specific "
                "nominate / apply / entry / categories page and scrape that "
                "instead.]"
            )

        return text[:MAX_PAGE_CHARS] + note

    # -- extract --------------------------------------------------------------

    async def extract(url: str) -> str:
        """Turn a page you have already scraped and judged genuine into a
        structured opportunity record. Call this only for pages that are a real,
        currently-open opportunity — it costs a model call.

        Args:
            url: A URL you have already passed to scrape.
        """
        refusal = _guard("extract")
        if refusal:
            return refusal

        if url not in context.pages:
            return f"Call scrape({url!r}) first — no page text held for that URL."

        context.budget.consume("extract")
        # extract() promises never to raise, but this is the last line between
        # one bad page and the loss of an entire run's work. Belt and braces.
        try:
            result = await asyncio.to_thread(
                extract_page, context.pages[url], url, context.model
            )
        except Exception as exc:  # noqa: BLE001 — reported to the model, run continues
            context.failures.append(f"{url}: {type(exc).__name__}")
            return (
                f"EXTRACTION CRASHED ({type(exc).__name__}: {exc}). "
                "Do not save this one. Move on to another page."
            )

        if isinstance(result, ExtractionFailure):
            context.failures.append(f"{url}: {result.reason.value}")
            return (
                f"EXTRACTION FAILED ({result.reason.value}): {result.detail}\n"
                "Do not save this one. Move on."
            )

        # Clear any earlier failure for this URL. A model may extract the same
        # page twice and succeed on the second attempt; leaving the stale entry
        # makes a URL count as both a success and a failure, which would make
        # Stage 5's extraction success/failure counts wrong.
        context.failures = [f for f in context.failures if not f.startswith(f"{url}:")]

        context.records[url] = result
        return (
            "Extracted successfully:\n"
            f"  title      : {result.title}\n"
            f"  body       : {result.organizing_body}\n"
            f"  base_title : {result.base_title}\n"
            f"  cycle_year : {result.cycle_year}\n"
            f"  category   : {result.category}\n"
            f"  deadline   : {result.submission_deadline} (verified={result.deadline_verified})\n"
            f"  criteria   : {len(result.eligibility_criteria)} item(s)\n"
            f"Call save_opportunity({url!r}) to store it."
        )

    # -- read_memory ----------------------------------------------------------

    async def read_memory() -> str:
        """What we already know: who Recykal is, and which programs are already
        tracked. Read this before searching so you do not repeat known ground.
        """
        refusal = _guard("read_memory")
        if refusal:
            return refusal
        context.budget.consume("read_memory")

        orgs = await known_orgs(context.db)
        upcoming = await due_soon(context.db, lookahead_months=2)

        known = ", ".join(orgs) if orgs else "(none stored yet)"
        windows = (
            "\n".join(
                f"  - {p['organizing_body']} — {p['base_title']} "
                f"(months {p['typical_window']['month_start']}"
                f"-{p['typical_window']['month_end']})"
                for p in upcoming
            )
            or "  (none)"
        )

        return (
            f"{discovery_seed()}\n\n"
            "## Already tracked\n\n"
            f"Organising bodies on record: {known}\n\n"
            f"Programs whose usual window is open or opening soon:\n{windows}\n\n"
            "Prefer finding opportunities not already on that list."
        )

    # -- save_opportunity -----------------------------------------------------

    async def save_opportunity(source_url: str) -> str:
        """Store the record you extracted from a page.

        Args:
            source_url: The URL you previously passed to extract.
        """
        refusal = _guard("save_opportunity")
        if refusal:
            return refusal

        record = context.records.get(source_url)
        if record is None:
            return f"Nothing extracted for {source_url!r} yet — call extract first."

        context.budget.consume("save_opportunity")
        result = await store_opportunity(context.db, record.model_dump())
        context.saved.append(source_url)

        # Quality warnings are surfaced, never blocking. A past edition still
        # earns its place in the program registry, and a rolling programme
        # legitimately has no deadline.
        warnings = record_warnings(record)
        for warning in warnings:
            context.warnings.append(f"{source_url}: {warning}")

        note = ""
        if warnings:
            listed = "\n".join(f"  - {w}" for w in warnings)
            note = (
                "\nQuality warnings on this record:\n"
                + listed
                + "\nIf a better page exists for the current cycle, prefer it "
                "next time rather than saving another stale record."
            )

        return (
            f"{result.action}: {record.title} "
            f"({record.organizing_body}, {record.cycle_year}). "
            f"Budget remaining: {context.budget.remaining} tool call(s).{note}"
        )

    return [
        StructuredTool.from_function(coroutine=search, name="search"),
        StructuredTool.from_function(coroutine=scrape, name="scrape"),
        StructuredTool.from_function(coroutine=extract, name="extract"),
        StructuredTool.from_function(coroutine=read_memory, name="read_memory"),
        StructuredTool.from_function(coroutine=save_opportunity, name="save_opportunity"),
    ]
