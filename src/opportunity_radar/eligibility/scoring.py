"""Confidence, score and the classification audit — all plain functions.

None of this is left to the model. CLAUDE.md requires `confidence` to be
derived from `criteria_results` and never self-reported, and `score` is a
formula, not a judgement. Same pattern as `deadline_verified` in Stage 2: the
model supplies the reasoning, deterministic code supplies the numbers.
"""

from __future__ import annotations

import re

from .schema import Confidence, CriterionResult, QualitativeNote

# A criterion filed as qualitative that contains one of these looks like it was
# actually fact-checkable. The risk being guarded against is a model relabelling
# "must be a registered non-profit" as a soft contextual note to avoid
# committing to not_met. Flags only — the model's classification always stands.
_FACTUAL_MARKERS = re.compile(r"\b\d+\b|\bmust\b", re.IGNORECASE)


def compute_score(criteria_results: list[CriterionResult]) -> float | None:
    """met / (met + not_met). Unclear excluded.

    None when the denominator is zero, which covers two distinct cases:
    no fact-checkable criteria at all, and fact-checkable criteria that every
    one resolved `unclear`. CLAUDE.md names only the first; the second divides
    by zero and means the same thing — no resolvable evidence either way.
    """
    met = sum(1 for r in criteria_results if r.status == "met")
    not_met = sum(1 for r in criteria_results if r.status == "not_met")
    if met + not_met == 0:
        return None
    return met / (met + not_met)


def derive_confidence(criteria_results: list[CriterionResult]) -> Confidence:
    """High only when every fact-checkable criterion resolved cleanly, and there
    was at least one to resolve.

    The second half matters as much as the first. `unclear` is a status that
    only exists for fact-checkable criteria, so a record made entirely of
    qualitative criteria has no unclear entries at all — and a rule that only
    looks for unclear would report high confidence on a verdict where nothing
    was ever verified. That is precisely what this mechanism exists to prevent:
    the system sounding more certain than its evidence supports.
    """
    if not criteria_results:
        return "low"
    if any(r.status == "unclear" for r in criteria_results):
        return "low"
    return "high"


def audit_classification(qualitative_notes: list[QualitativeNote]) -> list[str]:
    """Qualitative-filed criteria that look fact-checkable, for human review.

    Deliberately advisory. Deciding classification by keyword up front is the
    trap CLAUDE.md warns about; this rides behind the model's reasoning instead,
    the same shape as the closed-phrase backstop behind the model's `status`.
    """
    flagged = []
    for note in qualitative_notes:
        match = _FACTUAL_MARKERS.search(note.criterion)
        if match:
            flagged.append(
                f"{note.criterion!r} was filed as qualitative but contains "
                f"{match.group(0)!r} — check it is not a fact-checkable "
                "condition relabelled to avoid a not_met verdict"
            )
    return flagged
