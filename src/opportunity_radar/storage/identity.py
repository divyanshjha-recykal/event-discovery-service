"""Identity normalisation for the upsert keys.

`organizing_body + base_title` arrives from extraction as free text, so the same
program shows up as "CII", "cii", "CII " and "The CII". Matching on the raw
string would let all four become separate records and quietly break Stage 3's
deduplication requirement.

The normalised form is stored alongside the raw value and carries the unique
index; the raw value is what gets displayed. Deliberately no alias table — this
does not know that "CII" and "Confederation of Indian Industry" are one body,
and treats them as two programs. That is a known, accepted limit.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def normalize(value: str) -> str:
    """Fold a name to its match form: unaccented, lowercase, unpunctuated.

    >>> normalize("  The  CII, Ltd. ")
    'cii ltd'
    """
    if not value or not value.strip():
        raise ValueError("identity component cannot be empty")

    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _PUNCT.sub(" ", folded.lower())
    folded = _WHITESPACE.sub(" ", folded).strip()
    folded = _LEADING_ARTICLE.sub("", folded).strip()

    if not folded:
        raise ValueError(f"identity component normalised to nothing: {value!r}")
    return folded


def program_identity(organizing_body: str, base_title: str) -> dict[str, str]:
    """Identity of a program: organizing body + base title, no year."""
    return {
        "norm_organizing_body": normalize(organizing_body),
        "norm_base_title": normalize(base_title),
    }


def opportunity_identity(
    organizing_body: str, base_title: str, cycle_year: int
) -> dict[str, str | int]:
    """Identity of one edition: the program identity plus its cycle year."""
    if not isinstance(cycle_year, int) or isinstance(cycle_year, bool):
        raise ValueError(f"cycle_year must be an int, got {cycle_year!r}")
    return {**program_identity(organizing_body, base_title), "cycle_year": cycle_year}
