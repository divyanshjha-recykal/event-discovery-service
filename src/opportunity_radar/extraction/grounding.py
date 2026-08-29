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

_DEADLINE_LANGUAGE = re.compile(
    r"\b("
    r"deadline|last\s+date|closing\s+date|closes?\b|closed\b|"
    r"due\s+(?:date|by|on)|submit\s+by|submission[s]?\b|apply\s+by|"
    r"applications?\s+(?:close|due|accepted)|entries?\s+close|"
    r"nominations?\s+(?:close|due)|cut[-\s]?off|final\s+date|"
    r"last\s+day|valid\s+(?:till|until)|open\s+(?:till|until)"
    r")",
    re.IGNORECASE,
)

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
    if not source_text or not source_text.strip():
        return GroundingResult(False, None, "no source text to check against")

    try:
        parsed = date.fromisoformat(deadline[:10])
    except (ValueError, TypeError):
        return GroundingResult(False, None, f"deadline {deadline!r} is not an ISO date")

    anchors = [m.span() for m in _DEADLINE_LANGUAGE.finditer(source_text)]
    if not anchors:
        return GroundingResult(
            False, None, "no deadline language found anywhere in the source text"
        )

    found_anywhere: str | None = None

    for pattern in _day_month_patterns(parsed.day, parsed.month):
        for match in pattern.finditer(source_text):
            found_anywhere = found_anywhere or match.group(0)
            start, end = match.span()
            for a_start, a_end in anchors:
                # Near = the date and the deadline phrase overlap or sit within
                # PROXIMITY_CHARS of each other, in either order.
                distance = max(a_start - end, start - a_end, 0)
                if distance <= PROXIMITY_CHARS:
                    return GroundingResult(
                        True,
                        match.group(0),
                        f"day and month found verbatim {distance} chars from deadline language",
                    )

    if found_anywhere:
        return GroundingResult(
            False,
            found_anywhere,
            f"day and month appear as {found_anywhere!r} but not near any deadline language",
        )
    return GroundingResult(
        False, None, "day and month do not appear verbatim in the source text"
    )
