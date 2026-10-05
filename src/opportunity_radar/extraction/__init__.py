"""Extraction — turning scraped page text into a validated opportunity record."""

from .base_title import edition_residue, strip_edition
from .extract import base_title_warning, build_record, extract, record_warnings
from .failures import ExtractionFailure, FailureReason
from .grounding import GroundingResult, verify_deadline
from .schema import OpportunityRecord

__all__ = [
    "ExtractionFailure",
    "FailureReason",
    "GroundingResult",
    "OpportunityRecord",
    "base_title_warning",
    "build_record",
    "record_warnings",
    "edition_residue",
    "extract",
    "strip_edition",
    "verify_deadline",
]
