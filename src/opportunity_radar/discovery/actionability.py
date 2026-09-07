"""Deterministic actionability and extraction-completeness checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from ..extraction import OpportunityRecord


@dataclass(frozen=True)
class ActionabilityVerdict:
    status: Literal["actionable", "upcoming", "historical", "reject"]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionCompleteness:
    score: float
    identity: bool
    open_state: bool
    deadline: bool
    eligibility: bool
    source_coverage: bool
    gaps: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "identity": self.identity,
            "open_state": self.open_state,
            "deadline": self.deadline,
            "eligibility": self.eligibility,
            "source_coverage": self.source_coverage,
            "gaps": list(self.gaps),
        }


def _temporal_status(
    record: OpportunityRecord, today: date
) -> tuple[date | None, date | None, ActionabilityVerdict | None]:
    deadline = (
        date.fromisoformat(record.submission_deadline)
        if record.submission_deadline
        else None
    )
    event_date = date.fromisoformat(record.event_date) if record.event_date else None
    if deadline is not None and deadline < today:
        return deadline, event_date, ActionabilityVerdict(
            "historical",
            (f"submission deadline {deadline.isoformat()} passed before {today.isoformat()}",),
        )
    if event_date is not None and event_date < today:
        return deadline, event_date, ActionabilityVerdict(
            "historical",
            (f"event date {event_date.isoformat()} passed before {today.isoformat()}",),
        )
    if record.cycle_year < today.year:
        return deadline, event_date, ActionabilityVerdict(
            "historical",
            (f"cycle year {record.cycle_year} is before {today.year}",),
        )
    return deadline, event_date, None


def assess_actionability(
    record: OpportunityRecord,
    evidence_text: str,
    *,
    today: date,
    source_url: str,
    source_title: str = "",
    target_status_code: int | None = None,
) -> ActionabilityVerdict:
    if target_status_code is not None and not (200 <= target_status_code < 300):
        return ActionabilityVerdict(
            "reject", (f"target page returned HTTP {target_status_code}",)
        )
    deadline, event_date, temporal = _temporal_status(record, today)
    if temporal is not None:
        return temporal
    # Nothing below reads the page's wording. Closure, past editions and whether
    # a programme is open are meaning, and the analyser and extractor — both of
    # which read the whole page — already judge them. A keyword regex here was a
    # third and worse opinion: "Nominate Now" and "Express Interest" failed it,
    # so Greentech, CII and the ET Sustainability Awards were each discarded.

    if deadline is None and event_date is None and not record.deadline_note:
        # A missing date is a gap in what we read, not evidence the programme is
        # shut. Surface it under "No date confirmed" rather than discarding a
        # real programme found on its organiser's own site.
        return ActionabilityVerdict(
            "actionable",
            ("no date found in the evidence — verify on the source page",),
        )
    return ActionabilityVerdict("actionable", ("current and not shown as closed",))


def assess_completeness(
    record: OpportunityRecord,
    evidence_text: str,
    *,
    source_count: int,
) -> ExtractionCompleteness:
    identity = bool(record.title and record.organizing_body and record.base_title)
    open_state = bool(record.submission_deadline or record.deadline_note)
    deadline = bool(record.submission_deadline or record.deadline_note)
    eligibility = bool(record.eligibility_criteria)
    source_coverage = source_count > 1 or bool(
        re.search(
            r"\b(eligib|who can apply|how to apply|nomination|application)\b",
            evidence_text,
            re.IGNORECASE,
        )
    )
    checks = (identity, open_state, deadline, eligibility, source_coverage)
    labels = ("identity", "open state", "deadline", "eligibility", "source coverage")
    gaps = tuple(label for label, ok in zip(labels, checks, strict=True) if not ok)
    return ExtractionCompleteness(
        score=round(sum(checks) / len(checks), 2),
        identity=identity,
        open_state=open_state,
        deadline=deadline,
        eligibility=eligibility,
        source_coverage=source_coverage,
        gaps=gaps,
    )
