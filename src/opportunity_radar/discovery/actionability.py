"""Deterministic actionability and extraction-completeness checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from ..extraction import OpportunityRecord
from .link_resolver import has_open_signal

_CLOSED = re.compile(
    r"\b(nominations?|applications?|submissions?|entries|registration)\s+"
    r"(?:are\s+|is\s+)?(?:now\s+)?closed\b|"
    r"\bno\s+longer\s+accepting\b|\bdeadline\s+(?:has\s+)?passed\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d{2})\b")


@dataclass(frozen=True)
class ActionabilityVerdict:
    status: Literal["actionable", "historical", "reject"]
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


def _year_conflict(
    record: OpportunityRecord, source_url: str, source_title: str
) -> ActionabilityVerdict | None:
    sources = (
        ("source URL", _YEAR.findall(urlparse(source_url).path)),
        ("source title", _YEAR.findall(source_title)),
    )
    for label, values in sources:
        years = {int(value) for value in values}
        if years and record.cycle_year not in years:
            return ActionabilityVerdict(
                "reject",
                (
                    f"{label} year(s) {sorted(years)} conflict with "
                    f"extracted cycle {record.cycle_year}",
                ),
            )
    return None


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
    conflict = _year_conflict(record, source_url, source_title)
    if conflict is not None:
        return conflict

    if match := _CLOSED.search(evidence_text):
        # Bundles sometimes include a past-edition recap alongside an open
        # current call. A grounded future deadline plus explicit open language
        # is stronger evidence than an unscoped "entries closed" fragment.
        future_open = bool(
            deadline is not None
            and deadline >= today
            and has_open_signal(evidence_text)
        )
        if not future_open:
            return ActionabilityVerdict(
                "reject",
                (f"source explicitly indicates closure: {match.group(0)!r}",),
            )

    open_state = has_open_signal(evidence_text)
    if deadline is None and not record.deadline_note and not open_state:
        reason = (
            "no deadline, event date, deadline note, or explicit open-state evidence"
            if event_date is None
            else "future event found, but registration/open state is not explicit"
        )
        return ActionabilityVerdict("reject", (reason,))
    return ActionabilityVerdict("actionable", ("current and not shown as closed",))


def assess_completeness(
    record: OpportunityRecord,
    evidence_text: str,
    *,
    source_count: int,
) -> ExtractionCompleteness:
    identity = bool(record.title and record.organizing_body and record.base_title)
    open_state = bool(
        has_open_signal(evidence_text)
        or record.submission_deadline
        or record.deadline_note
    )
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
