"""Loads the golden set out of `golden_set/extraction-examples.md`.

The markdown file stays the single source of truth — it is what gets edited by
hand, so nothing can drift out of sync with it. The trade-off is that this
parser is coupled to that file's heading structure; if the headings change it
raises rather than silently returning fewer examples, which is the failure mode
we want.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import GOLDEN_SET_DIR

EXAMPLES_FILE = GOLDEN_SET_DIR / "extraction-examples.md"

_EXAMPLE = re.compile(r"^### Example (\d+)\s*[—-]\s*(.+)$", re.MULTILINE)
_SOURCE = re.compile(r"^\*\*Source:\*\*\s*(\S+)", re.MULTILINE)
_PAGE = re.compile(r"^\*\*Saved page content[^*]*\*\*\s*\n(.*?)(?=\n\*\*)", re.MULTILINE | re.DOTALL)
_EXPECTED = re.compile(r"^\*\*Correct extraction:\*\*\s*\n```\n(.*?)\n```", re.MULTILINE | re.DOTALL)
_CLOSED = re.compile(r"typed_failure:\s*`?opportunity_closed`?|`opportunity_closed`")


class GoldenSetError(RuntimeError):
    """The golden set file is missing or no longer matches the expected shape."""


@dataclass(frozen=True)
class GoldenExample:
    number: int
    label: str
    source_url: str
    page_text: str
    expected: dict | None          # None when the example has no record to produce
    expects_closed: bool           # True when the right answer is opportunity_closed

    @property
    def name(self) -> str:
        return f"Example {self.number} — {self.label}"


def _strip_blockquote(block: str) -> str:
    lines = []
    for line in block.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            lines.append(stripped[1:].lstrip() if stripped != ">" else "")
        elif not stripped:
            lines.append("")
    return "\n".join(lines).strip()


def _parse_expected(block: str) -> dict:
    """Parse the hand-written pseudo-YAML answer block.

    Not real YAML — it carries inline `#` notes and parenthetical asides — so
    this reads it leniently rather than pretending it is a strict format.
    """
    out: dict = {}
    key: str | None = None
    buffer: list[str] = []

    for raw in block.splitlines():
        line = raw.rstrip()
        if key is not None:                      # inside a multi-line [ ... ] list
            if line.strip().startswith("]"):
                out[key] = [
                    v.strip().strip(",").strip('"')
                    for v in buffer
                    if v.strip().strip(",").strip('"')
                ]
                key, buffer = None, []
            else:
                buffer.append(line)
            continue

        match = re.match(r"^(\w+):\s*(.*)$", line)
        if not match:
            continue
        name, value = match.group(1), match.group(2)

        if value.strip() == "[":
            key = name
            continue

        value = re.sub(r"\s+#.*$", "", value).strip()          # drop trailing note
        value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()  # drop parenthetical aside
        value = value.strip('"')

        if value == "null":
            out[name] = None
        elif value in ("true", "false"):
            out[name] = value == "true"
        elif re.fullmatch(r"-?\d+", value):
            out[name] = int(value)
        else:
            out[name] = value

    return out


def load_examples(path: Path | None = None) -> list[GoldenExample]:
    """Every extraction example in Part 1, in file order."""
    path = path or EXAMPLES_FILE
    if not path.is_file():
        raise GoldenSetError(f"golden set not found at {path}")

    text = path.read_text(encoding="utf-8")
    part1 = text.split("## Part 2", 1)[0]

    headings = list(_EXAMPLE.finditer(part1))
    if not headings:
        raise GoldenSetError(
            f"no '### Example N — ...' headings found in {path}. "
            "The parser is coupled to that structure; update it if the file changed."
        )

    examples = []
    for index, heading in enumerate(headings):
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(part1)
        body = part1[start:end]

        source = _SOURCE.search(body)
        page = _PAGE.search(body)
        if not source or not page:
            raise GoldenSetError(
                f"Example {heading.group(1)} is missing its **Source:** line or "
                "**Saved page content** block."
            )

        expected_match = _EXPECTED.search(body)
        expected = _parse_expected(expected_match.group(1)) if expected_match else None

        examples.append(
            GoldenExample(
                number=int(heading.group(1)),
                label=heading.group(2).strip(),
                source_url=source.group(1).strip(),
                page_text=_strip_blockquote(page.group(1)),
                expected=expected,
                expects_closed=expected is None and bool(_CLOSED.search(body)),
            )
        )

    return examples
