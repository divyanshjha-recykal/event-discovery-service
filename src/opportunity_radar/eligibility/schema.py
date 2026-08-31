"""The eligibility result, as validated models.

Per CLAUDE.md, the model produces `criteria_results` and `qualitative_notes`
and nothing else. `confidence` and `score` are computed from those by plain
functions in `scoring.py` — never self-reported, for the same reason
`deadline_verified` is a string check rather than the model's own opinion of
its own output.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["met", "not_met", "unclear"]
Confidence = Literal["high", "low"]


class CriterionResult(BaseModel):
    """One fact-checkable criterion, resolved against the business profile."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    criterion: str = Field(min_length=1)
    status: Status
    reasoning: str = Field(min_length=1)


class QualitativeNote(BaseModel):
    """A criterion that cannot be fact-checked — context only, never scored."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    criterion: str = Field(min_length=1)
    note: str = Field(min_length=1)


class EligibilityResult(BaseModel):
    """Attached to an opportunity record after `evaluate()` runs."""

    model_config = {"extra": "forbid"}

    criteria_results: list[CriterionResult] = Field(default_factory=list)
    qualitative_notes: list[QualitativeNote] = Field(default_factory=list)
    confidence: Confidence
    score: float | None = None
    #: Criteria the model filed as qualitative that look fact-checkable. A flag
    #: for review, never an override of the model's classification.
    classification_flags: list[str] = Field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        tally = {"met": 0, "not_met": 0, "unclear": 0}
        for result in self.criteria_results:
            tally[result.status] += 1
        return tally
