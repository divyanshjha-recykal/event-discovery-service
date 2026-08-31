"""Loads the hand-written reference criteria sets from Part 2 of the golden set.

Same principle as the extraction loader: the markdown file stays the single
source of truth, and this parser raises rather than silently returning fewer
sets if the file's structure changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..paths import GOLDEN_SET_DIR

EXAMPLES_FILE = GOLDEN_SET_DIR / "extraction-examples.md"

_SET = re.compile(r"^\*\*Set (\d+)\s*[—-]\s*(.+?)\*\*\s*$", re.MULTILINE)
_CRITERION = re.compile(r"^>\s*Criterion:\s*[\"“](.+?)[\"”]\s*$", re.MULTILINE)
_EXPECTED = re.compile(r"^>\s*Expected:\s*(.+?)\s*$", re.MULTILINE)


class CriteriaSetError(RuntimeError):
    """Part 2 is missing or no longer matches the expected shape."""


@dataclass(frozen=True)
class CriteriaSet:
    number: int
    label: str
    criterion: str
    expectation: str          # the hand-written expectation, verbatim
    expected_status: str | None   # "met" | "not_met" | "unclear", or None if qualitative
    expects_qualitative: bool

    @property
    def name(self) -> str:
        return f"Set {self.number} — {self.label}"


def _classify(label: str, expectation: str) -> tuple[str | None, bool]:
    """Read the expected verdict path out of the hand-written text.

    The heading label is authoritative and the explanation is only a fallback.
    Set 4's heading says `unclear` while its explanation reads "should never
    resolve to met or not_met on a guess" — searching both at once matched
    `not_met` inside that sentence and mislabelled the set.
    """
    for source in (label.lower(), expectation.lower()):
        if "qualitative" in source or "contextual note" in source:
            return None, True
        # not_met before met: "met" is a substring of "not_met".
        for status in ("not_met", "unclear", "met"):
            if status in source:
                return status, False
    return None, False


def load_criteria_sets(path: Path | None = None) -> list[CriteriaSet]:
    """Every reference criteria set in Part 2, in file order."""
    path = path or EXAMPLES_FILE
    if not path.is_file():
        raise CriteriaSetError(f"golden set not found at {path}")

    text = path.read_text(encoding="utf-8")
    if "## Part 2" not in text:
        raise CriteriaSetError(
            f"{path} has no '## Part 2' section — the reference criteria sets "
            "Stage 4 is validated against are missing."
        )
    part2 = text.split("## Part 2", 1)[1]

    headings = list(_SET.finditer(part2))
    if not headings:
        raise CriteriaSetError(
            "no '**Set N — ...**' headings found in Part 2. This parser is "
            "coupled to that structure; update it if the file changed."
        )

    sets = []
    for index, heading in enumerate(headings):
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(part2)
        body = part2[start:end]

        criterion = _CRITERION.search(body)
        expected = _EXPECTED.search(body)
        if not criterion or not expected:
            raise CriteriaSetError(
                f"Set {heading.group(1)} is missing its '> Criterion:' or "
                "'> Expected:' line."
            )

        label = heading.group(2).strip()
        status, qualitative = _classify(label, expected.group(1))
        sets.append(
            CriteriaSet(
                number=int(heading.group(1)),
                label=label,
                criterion=criterion.group(1).strip(),
                expectation=expected.group(1).strip(),
                expected_status=status,
                expects_qualitative=qualitative,
            )
        )

    return sets
