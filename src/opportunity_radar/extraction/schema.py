"""The opportunity record, as a validated model.

`extract()` returns either an instance of this or a typed failure — never a
partial or half-valid record. Validation is strict on purpose: a record that
reaches storage is indistinguishable from a real find later, so anything
doubtful should fail loudly here rather than be stored with a shrug.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["award", "grant", "event", "conference"]

# Sanity bounds on cycle_year. Wide enough for a program announced well ahead,
# tight enough that a model emitting a page number or a phone fragment fails.
MIN_CYCLE_YEAR = 1990
MAX_CYCLE_YEAR = 2100

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class OpportunityRecord(BaseModel):
    """One edition of an award, grant, event or conference."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    title: str = Field(min_length=2)
    organizing_body: str = Field(min_length=1)
    base_title: str = Field(min_length=1)
    cycle_year: int
    category: Category
    eligibility_criteria: list[str] = Field(default_factory=list)
    submission_deadline: str | None = None
    deadline_note: str | None = None
    deadline_verified: bool = False
    event_date: str | None = None
    source_url: str

    @field_validator("cycle_year")
    @classmethod
    def _year_in_range(cls, value: int) -> int:
        if not MIN_CYCLE_YEAR <= value <= MAX_CYCLE_YEAR:
            raise ValueError(
                f"cycle_year {value} outside {MIN_CYCLE_YEAR}-{MAX_CYCLE_YEAR}"
            )
        return value

    @field_validator("submission_deadline", "event_date")
    @classmethod
    def _iso_date_or_none(cls, value: str | None) -> str | None:
        if value in (None, "", "null"):
            return None
        if not _ISO_DATE.match(value):
            raise ValueError(f"{value!r} is not an ISO date (YYYY-MM-DD)")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{value!r} is not a real calendar date") from exc
        return value

    @field_validator("deadline_note")
    @classmethod
    def _blank_note_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("eligibility_criteria")
    @classmethod
    def _separate_conditions(cls, value: list[str]) -> list[str]:
        """Criteria must be individually stated conditions, never one paragraph.

        A single very long entry means the model returned a blob instead of
        splitting it, which makes per-criterion eligibility reasoning at Stage 4
        impossible. Reject rather than store something Stage 4 cannot use.
        """
        cleaned = [c.strip() for c in value if c and c.strip()]
        if len(cleaned) == 1 and len(cleaned[0]) > 400:
            raise ValueError(
                "eligibility_criteria is one long paragraph; it must be split "
                "into individually stated conditions"
            )
        return cleaned

    @field_validator("source_url")
    @classmethod
    def _plausible_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError(f"source_url {value!r} is not an http(s) URL")
        return value
