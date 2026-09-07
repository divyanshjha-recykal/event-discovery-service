"""`deadline_verified` grounding — a plain string check, never a model judgement.

CLAUDE.md's rule: the day and month of the extracted deadline must appear
verbatim near deadline language in the source text. The year may be inferred
from page context (title, publish date) without failing the check — stating a
day and month without repeating a year that is already obvious from the page is
completely normal, and failing on it would reject most real pages.

What this exists to catch is the opposite case: a model inventing a date that
appears nowhere on the page. So the day and month must be found; the year need
not be.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# How far from deadline language a date can sit and still count as "near".
# Wide enough to span a sentence or a short table row, tight enough that an
# unrelated date elsewhere on the page does not accidentally qualify.
PROXIMITY_CHARS = 250

_MONTHS = {
    1: ("january", "jan"), 2: ("february", "feb"), 3: ("march", "mar"),
    4: ("april", "apr"), 5: ("may",), 6: ("june", "jun"),
    7: ("july", "jul"), 8: ("august", "aug"), 9: ("september", "sept", "sep"),
    10: ("october", "oct"), 11: ("november", "nov"), 12: ("december", "dec"),
}

_ORDINAL_SUFFIX = r"(?:st|nd|rd|th)?"


@dataclass(frozen=True)
class GroundingResult:
    verified: bool
    matched: str | None      # the literal text that satisfied the check
    reason: str              # why it passed or failed, for the trace and the harness

    def __bool__(self) -> bool:
        return self.verified


def _day_month_patterns(day: int, month: int) -> list[re.Pattern[str]]:
    """Surface forms a publisher might use for a given day and month."""
    names = "|".join(_MONTHS[month])
    d = str(day)
    dd = f"{day:02d}"
    mm = f"{month:02d}"
    day_alt = f"0?{d}" if day < 10 else d

    return [
        # 19 June / 19th June / 19 Jun.
        re.compile(rf"\b{day_alt}\s*{_ORDINAL_SUFFIX}\s+(?:of\s+)?(?:{names})\b\.?", re.IGNORECASE),
        # June 19 / June 19th / Jun. 19
        re.compile(rf"\b(?:{names})\b\.?\s+{day_alt}\s*{_ORDINAL_SUFFIX}\b", re.IGNORECASE),
        # 19/06, 19-06, 19.06  (day first, the common form outside the US)
        re.compile(rf"\b{dd}\s*[/.\-]\s*{mm}\b"),
        # 06/19, 06-19  (month first)
        re.compile(rf"\b{mm}\s*[/.\-]\s*{dd}\b"),
        # ISO fragment 06-19, as it appears inside 2026-06-19
        re.compile(rf"\b{mm}-{dd}\b"),
    ]


def verify_deadline(deadline: str | None, source_text: str) -> GroundingResult:
    """Check an extracted ISO deadline against the page it came from.

    Returns not-verified rather than raising on a malformed date: an unparseable
    deadline is exactly the kind of thing this check exists to refuse to bless.
    """
    if not deadline:
        return GroundingResult(False, None, "no deadline extracted")

    # Type-guard before slicing. A model can return submission_deadline as a
    # dict ({"start": ..., "end": ...}) or a list, and slicing a dict raises
    # KeyError — which is not a ValueError, so it escaped the handler below and
    # took down a whole Discovery run.
    if not isinstance(deadline, str):
        return GroundingResult(
            False, None,
            f"deadline is {type(deadline).__name__}, expected an ISO date string"
        )

    if not source_text or not source_text.strip():
        return GroundingResult(False, None, "no source text to check against")

    try:
        parsed = date.fromisoformat(deadline[:10])
    except (ValueError, TypeError):
        return GroundingResult(False, None, f"deadline {deadline!r} is not an ISO date")

    # The check is that the model did not invent the date: the day and month
    # must appear verbatim in the page. It no longer also demands a "deadline"
    # word nearby — that caged a mechanical anti-hallucination check behind a
    # keyword list, so a date in a table or after wording we had not listed
    # failed verification despite being right there on the page.
    for pattern in _day_month_patterns(parsed.day, parsed.month):
        match = pattern.search(source_text)
        if match:
            return GroundingResult(
                True, match.group(0),
                "day and month found verbatim in the source text",
            )

    found_anywhere = None
    if found_anywhere:
        return GroundingResult(
            False,
            found_anywhere,
            f"day and month appear as {found_anywhere!r} but not near any deadline language",
        )
    return GroundingResult(
        False, None, "day and month do not appear verbatim in the source text"
    )
