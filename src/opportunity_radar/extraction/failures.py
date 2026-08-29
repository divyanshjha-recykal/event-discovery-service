"""Typed extraction failures.

`extract()` returns one of these instead of a record. Never a partial or
malformed record — a named failure is always preferable to a guess, because a
guess enters storage and is indistinguishable from a real find later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailureReason(str, Enum):
    #: The page itself does not carry enough to build a record from.
    INSUFFICIENT_CONTENT = "insufficient_content"
    #: The page makes clear the opportunity is no longer open.
    OPPORTUNITY_CLOSED = "opportunity_closed"
    #: The page may well be fine — the model's reply was not usable. Unparseable
    #: JSON after the retry, a record that fails validation, or a base_title that
    #: cannot be normalised. Kept separate from INSUFFICIENT_CONTENT so a Stage 3
    #: run tells you whether the page or the model was at fault.
    MALFORMED_RESPONSE = "malformed_response"


@dataclass(frozen=True)
class ExtractionFailure:
    reason: FailureReason
    detail: str
    source_url: str

    def __str__(self) -> str:
        return f"{self.reason.value}: {self.detail}"
