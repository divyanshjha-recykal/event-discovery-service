"""`base_title` normalisation — the identity-critical half of extraction.

The model proposes a base title; this module strips anything edition-specific
that survives, so the identity key cannot drift between models or between years.

Why that matters more than it looks: `base_title` is part of the identity key
(`organizing_body + base_title + cycle_year`). If "2026" leaks into base_title,
the 2027 edition of the same program gets a different identity, so it is stored
as a brand-new program instead of a new edition. Deduplication and the program
registry both fail silently.

Every pattern here matches by *shape* — a year-range number, an ordinal before
an edition word, a roman numeral beside one — never by any specific title's
wording. It will still miss schemes nobody anticipated, so `edition_residue()`
reports anything edition-shaped that survives, and callers surface that rather
than assuming the strip was complete.
"""

from __future__ import annotations

import re

# --- markers meaning "which run of the program this is" ----------------------

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 2025-26, 2025/2026, 2025–26
    re.compile(r"\b(?:19|20)\d{2}\s*[-/–—]\s*(?:(?:19|20)?\d{2})\b"),
    # FY2026, FY 26, AY2026
    re.compile(r"\b(?:FY|AY)\s*'?\d{2,4}\b", re.IGNORECASE),
    # plain 4-digit year
    re.compile(r"\b(?:19|20)\d{2}\b"),
    # apostrophe year: '26
    re.compile(r"(?<!\w)'\d{2}\b"),
    # 4th Annual / 12th Edition / 3rd Cycle / 2nd Round
    re.compile(
        r"\b\d+\s*(?:st|nd|rd|th)?\s*"
        r"(?:annual|edition|cycle|round|series|volume|vol\.?)\b",
        re.IGNORECASE,
    ),
    # Fourth Edition / Twenty-First Annual
    re.compile(
        r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
        r"eighteenth|nineteenth|twentieth|twenty[-\s]?\w+)\s+"
        r"(?:annual|edition|cycle|round|series)\b",
        re.IGNORECASE,
    ),
    # Edition IV / Volume XII  (roman numeral after the edition word)
    re.compile(
        r"\b(?:annual|edition|cycle|round|series|volume|vol\.?)\s+"
        r"(?=[MDCLXVI]{1,10}\b)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})\b",
        re.IGNORECASE,
    ),
    # IV Edition / XII Annual  (roman numeral before the edition word)
    re.compile(
        r"\b(?=[MDCLXVI]{1,10}\s)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
        r"\s+(?:annual|edition|cycle|round|series)\b",
        re.IGNORECASE,
    ),
    # Round 2 / Cycle 3 / Edition 4 / Series 2
    re.compile(
        r"\b(?:annual|edition|cycle|round|series|volume|vol\.?)\s+\d+\b", re.IGNORECASE
    ),
    # a bare trailing "Edition" / "Annual" left after a year was removed
    re.compile(r"\b(?:the\s+)?(?:annual|edition)\b\s*$", re.IGNORECASE),
    # season qualifiers that identify a run
    re.compile(
        r"\b(?:spring|summer|autumn|fall|winter)\s+(?:edition|cycle|round)\b",
        re.IGNORECASE,
    ),
)

_WHITESPACE = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\s,\-–—:|()\[\]]+|[\s,\-–—:|()\[\]]+$")
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")
# "Fourth Edition of the X" leaves "of the X" once the edition part is removed.
# Only applied when a removal actually happened — see strip_edition.
_LEADING_CONNECTIVE = re.compile(r"^(?:of|for|in)\s+(?:the\s+)?", re.IGNORECASE)

# Anything still edition-shaped after stripping. Deliberately broad: this is a
# warning channel, not a matcher, so false positives are cheap.
_RESIDUE = re.compile(
    r"\b(?:19|20)\d{2}\b"
    r"|(?<!\w)'\d{2}\b"
    r"|\b\d+\s*(?:st|nd|rd|th)\b"
    r"|\b(?:annual|edition|cycle|round)\b",
    re.IGNORECASE,
)


def strip_edition(title: str) -> str:
    """Remove years and edition markers from a title.

    >>> strip_edition("CII 4R Awards 2026")
    'CII 4R Awards'
    >>> strip_edition("Sustainability Awards, 4th Edition")
    'Sustainability Awards'
    >>> strip_edition("For Good Awards")
    'For Good Awards'
    """
    if not title or not title.strip():
        raise ValueError("title cannot be empty")

    cleaned = title
    for pattern in _PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    # Only tidy a dangling connective if a removal actually created one.
    # Applied unconditionally this mauls titles that simply start with a
    # preposition: "For Good Awards" would become "Good Awards".
    removed_something = cleaned != title

    cleaned = _EMPTY_BRACKETS.sub(" ", cleaned)
    if removed_something:
        cleaned = _LEADING_CONNECTIVE.sub("", cleaned.lstrip())

    cleaned = _WHITESPACE.sub(" ", cleaned)
    cleaned = _EDGE_PUNCT.sub("", cleaned).strip()

    if not cleaned:
        raise ValueError(f"title reduced to nothing by edition stripping: {title!r}")
    return cleaned


def edition_residue(base_title: str) -> str | None:
    """Anything edition-shaped left in a base title, or None if it looks clean.

    Surfaced by `extract()` so an unrecognised naming scheme shows up as a
    warning on the record rather than silently fragmenting the program registry.
    """
    match = _RESIDUE.search(base_title)
    return match.group(0) if match else None
