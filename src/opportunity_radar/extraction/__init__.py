"""Extraction — turning scraped page text into a validated opportunity record."""

from .base_title import edition_residue, strip_edition
from .extract import base_title_warning, extract
from .failures import ExtractionFailure, FailureReason
from .golden import GoldenExample, GoldenSetError, load_examples
from .grounding import GroundingResult, verify_deadline
from .schema import OpportunityRecord

__all__ = [
    "ExtractionFailure",
    "FailureReason",
    "GoldenExample",
    "GoldenSetError",
    "GroundingResult",
    "OpportunityRecord",
    "base_title_warning",
    "edition_residue",
    "extract",
    "load_examples",
    "strip_edition",
    "verify_deadline",
]
