"""Eligibility — judging an opportunity's criteria against the business profile."""

from .criteria_sets import CriteriaSet, CriteriaSetError, load_criteria_sets
from .evaluate import evaluate, evaluate_criteria
from .schema import (
    Confidence,
    CriterionResult,
    EligibilityResult,
    QualitativeNote,
    Status,
)
from .scoring import audit_classification, compute_score, derive_confidence

__all__ = [
    "Confidence",
    "CriteriaSet",
    "CriteriaSetError",
    "CriterionResult",
    "EligibilityResult",
    "QualitativeNote",
    "Status",
    "audit_classification",
    "compute_score",
    "derive_confidence",
    "evaluate",
    "evaluate_criteria",
    "load_criteria_sets",
]
