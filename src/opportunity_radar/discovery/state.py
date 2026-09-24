"""Typed state and evidence models for the Discovery workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict

from .budget import RunBudget

Category = Literal["award", "grant", "event", "conference", "research"]

#: What a run is looking for. "any" searches everything, as before. The operator
#: picks this; it steers what gets searched and never rejects anything in code.
Focus = Literal["any", "award", "event", "research"]


@dataclass(frozen=True)
class PlannedQuery:
    query: str
    intent: Category | Literal["mixed"]
    geography: str
    target_year: int
    rationale: str


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    query: str
    score: float = 0.0
    #: When the search engine says the page was published or last updated, or
    #: "" when it could not tell. A deterministic date the ranker is given
    #: outright, rather than one it has to infer from the extract.
    published_date: str = ""
    #: Page text Tavily returns on the same search call. Choosing which sites to
    #: read from an 800-character marketing blurb is what let a design
    #: competition through and dropped the ET awards; this is what replaces it.
    content: str = ""
    #: Facts a provider read off the page; empty when it gives none (Tavily).
    programme_name: str = ""
    organiser: str = ""
    entry_deadline: str = ""
    event_date: str = ""
    who_can_enter: str = ""
    country_restriction: str = ""
    #: The sentence the provider read the date from.
    date_quote: str = ""


@dataclass(frozen=True)
class EvidencePage:
    url: str
    depth: int
    markdown: str
    title: str = ""
    description: str = ""
    status_code: int | None = None
    content_type: str = ""
    links: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceBundle:
    seed_url: str
    pages: tuple[EvidencePage, ...]
    #: Same-site links seen but not followed, so a thin bundle can say whether
    #: there was anywhere left to look or the site simply had nothing.
    unfollowed: tuple[str, ...] = ()
    #: Set when the seed page matched one already fetched this run.
    duplicate_of: str = ""

    @property
    def source_urls(self) -> list[str]:
        return [page.url for page in self.pages]

    def bounded_text(self, per_page_chars: int) -> str:
        """Evidence with a per-page cap, so later pages survive truncation."""
        sections: list[str] = []
        for page in self.pages:
            header = [f"=== SOURCE PAGE: {page.url} ==="]
            if page.title:
                header.append(f"Browser title: {page.title}")
            if page.description:
                header.append(f"Meta description: {page.description}")
            sections.append(
                "\n".join(header) + "\n\n" + page.markdown[:per_page_chars]
            )
        return "\n\n".join(sections)

    @property
    def combined_text(self) -> str:
        return self.bounded_text(10**9)

    def extraction_text(
        self,
        supporting_urls: tuple[str, ...],
        canonical_url: str,
        *,
        per_page_chars: int = 20_000,
    ) -> str:
        """Bound model input per source without dropping later evidence pages."""
        priority = (canonical_url, *supporting_urls)
        order = {url: index for index, url in enumerate(dict.fromkeys(priority))}
        pages = sorted(
            self.pages,
            key=lambda page: (order.get(page.url, len(order)), page.depth),
        )
        sections: list[str] = []
        for page in pages:
            header = [f"=== SOURCE PAGE: {page.url} ==="]
            if page.title:
                header.append(f"Browser title: {page.title}")
            if page.description:
                header.append(f"Meta description: {page.description}")
            sections.append(
                "\n".join(header) + "\n\n" + page.markdown[:per_page_chars]
            )
        return "\n\n".join(sections)


@dataclass(frozen=True)
class CandidateVerdict:
    seed_url: str
    source_url: str
    target_title: str
    category: Category
    supporting_urls: tuple[str, ...]
    decision: Literal["pursue", "skip"]
    reason: str
    organizing_body: str = ""
    #: The field the programme is about, in the page's own words.
    domain: str = ""
    #: What the programme is, from the pages.
    summary: str = ""
    base_title: str = ""
    cycle_year: int = 0
    status: str = "unclear"
    submission_deadline: str | None = None
    deadline_note: str | None = None
    event_date: str | None = None
    confidence_note: str = ""
    #: The sentence each value was read from, in the page's own words.
    body_quote: str = ""
    deadline_quote: str = ""
    status_quote: str = ""
    entry_eligibility: tuple[str, ...] = ()
    judging_criteria: tuple[str, ...] = ()
    application_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankedPick:
    """A site rank chose, and why. The reason travels on to extraction."""

    hit: SearchHit
    reason: str
    rank: int


@dataclass(frozen=True)
class GroundedField:
    """Whether one extracted value was quoted from the page. Measured, not enforced."""

    field: str
    value: str
    quote: str
    found: bool


@dataclass
class PreparedRecord:
    """A validated record waiting to be judged and stored."""

    record: Any                      # OpportunityRecord
    seed_url: str
    source_url: str
    evidence_urls: list[str]
    completeness: dict[str, Any]
    judging_criteria: list[str]
    application_requirements: list[str]
    unfollowed_links: list[str]
    grounding: list[GroundedField]
    warnings: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.record.base_title.casefold()}|{self.record.cycle_year}"


@dataclass
class TraversalLimits:
    """How far research is allowed to go. Set per run from the configurator.

    `max_depth=1` means only the seed's links are followed. Raising it lets a
    followed page have its own links chosen too — which the code refused to do
    at any setting until the `depth > 0` guard was removed.
    """

    max_candidates: int = 6      # seeds taken from the search pool
    max_links_per_page: int = 2
    max_pages_per_seed: int = 3
    max_depth: int = 1


@dataclass
class WorkflowRuntime:
    db: Any
    budget: RunBudget
    model: str | None
    dry_run: bool
    run_id: str
    limits: TraversalLimits = field(default_factory=TraversalLimits)
    #: Full BusinessProfile.md, for the feasibility check. Discovery gets a
    #: distilled seed; feasibility needs everything, because any field could
    #: settle any condition.
    profile_text: str = ""
    #: What this run is looking for. One line in the planning and site-selection
    #: prompts; nothing in code filters on it.
    focus: str = "any"
    #: "exa" or "tavily"; empty means SEARCH_PROVIDER from .env.
    search_provider: str = ""
    trace_url: str | None = None
    journey: list[dict[str, Any]] = field(default_factory=list)
    saved: list[str] = field(default_factory=list)
    #: Stored, but with no entry conditions to judge — counted apart from saved.
    needs_deeper: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    historical: list[str] = field(default_factory=list)
    #: Seed page content key -> URL, shared by the parallel fetch branches.
    seen_pages: dict[str, str] = field(default_factory=dict)


def _merge(key):
    """Build a merge rule that appends new items and drops repeats by `key`."""

    def merge(current: list, incoming: list) -> list:
        out = list(current or [])
        seen = {key(item) for item in out}
        for item in incoming or []:
            if (marker := key(item)) not in seen:
                seen.add(marker)
                out.append(item)
        return out

    return merge


def _append(current: list, incoming: list) -> list:
    return list(current or []) + list(incoming or [])


# Fields that collect things across steps. Without these every step overwrites
# the whole list, so only one step can ever write a field and "for each site"
# has to be a loop inside one step. Steps now return only what they added.
class DiscoveryState(TypedDict):
    as_of_date: str
    supplied_queries: list[str]
    memory: str
    planned_queries: Annotated[list[PlannedQuery], _merge(lambda q: q.query)]
    search_hits: Annotated[list[SearchHit], _merge(lambda h: h.url)]
    evidence_bundles: Annotated[list[EvidenceBundle], _merge(lambda b: b.seed_url)]
    candidates: Annotated[
        list[CandidateVerdict],
        _merge(lambda c: (c.target_title.casefold(), c.source_url)),
    ]
    picks: Annotated[list[RankedPick], _merge(lambda p: p.hit.url)]
    records: Annotated[list[PreparedRecord], _merge(lambda r: r.key)]
    # Kept apart from `records` rather than written onto them: the merge rule
    # drops a repeat by key, so a record re-sent with its verdict attached would
    # be discarded and the verdict lost. `store` joins the two on `key`.
    verdicts: Annotated[list[dict[str, Any]], _merge(lambda v: v["key"])]
    analyzed_seeds: Annotated[list[str], _merge(lambda s: s)]
    analysis_errors: Annotated[list[dict[str, str]], _append]
    rejected: Annotated[list[dict[str, Any]], _append]
    summary: str
    replan_count: int
