"""Typed state and evidence models for the Discovery workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from .budget import RunBudget

Category = Literal["award", "grant", "event", "conference"]


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
    #: Page text Tavily returns on the same search call. Choosing which sites to
    #: read from an 800-character marketing blurb is what let a design
    #: competition through and dropped the ET awards; this is what replaces it.
    content: str = ""


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
    base_title: str = ""
    cycle_year: int = 0
    status: str = "unclear"
    submission_deadline: str | None = None
    deadline_note: str | None = None
    event_date: str | None = None
    confidence_note: str = ""
    entry_eligibility: tuple[str, ...] = ()
    judging_criteria: tuple[str, ...] = ()
    application_requirements: tuple[str, ...] = ()


@dataclass
class TraversalLimits:
    """How far research is allowed to go. Set per run from the configurator.

    `max_depth=1` means only the seed's links are followed. Raising it lets a
    followed page have its own links chosen too — which the code refused to do
    at any setting until the `depth > 0` guard was removed.
    """

    max_candidates: int = 5      # seeds taken from the search pool
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
    trace_url: str | None = None
    journey: list[dict[str, Any]] = field(default_factory=list)
    saved: list[str] = field(default_factory=list)
    #: Stored, but with no entry conditions to judge — counted apart from saved.
    needs_deeper: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    historical: list[str] = field(default_factory=list)


class DiscoveryState(TypedDict):
    as_of_date: str
    supplied_queries: list[str]
    memory: str
    planned_queries: list[PlannedQuery]
    search_hits: list[SearchHit]
    evidence_bundles: list[EvidenceBundle]
    candidates: list[CandidateVerdict]
    analyzed_seeds: list[str]
    analysis_errors: list[dict[str, str]]
    rejected: list[dict[str, Any]]
    summary: str
    replan_count: int
