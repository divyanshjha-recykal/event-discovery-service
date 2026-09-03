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

    @property
    def source_urls(self) -> list[str]:
        return [page.url for page in self.pages]

    @property
    def combined_text(self) -> str:
        sections: list[str] = []
        for page in self.pages:
            header = [f"=== SOURCE PAGE: {page.url} ==="]
            if page.title:
                header.append(f"Browser title: {page.title}")
            if page.description:
                header.append(f"Meta description: {page.description}")
            sections.append("\n".join(header) + "\n\n" + page.markdown)
        return "\n\n".join(sections)

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
    entry_eligibility: tuple[str, ...] = ()
    judging_criteria: tuple[str, ...] = ()
    application_requirements: tuple[str, ...] = ()


@dataclass
class WorkflowRuntime:
    db: Any
    budget: RunBudget
    model: str | None
    dry_run: bool
    run_id: str
    trace_url: str | None = None
    journey: list[dict[str, Any]] = field(default_factory=list)
    saved: list[str] = field(default_factory=list)
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
