"""Storage layer — the Mongo collections and the program registry."""

from .client import OPPORTUNITIES, PROGRAMS, ensure_indexes, get_client, get_database
from .failures import (
    DEAD_ENDS,
    EXTRACTION_FAILURES,
    clear_dead_end,
    clear_extraction_failure,
    dead_end_urls,
    ensure_dead_end_indexes,
    ensure_failure_indexes,
    failure_counts,
    record_dead_end,
    record_extraction_failure,
)
from .identity import normalize, opportunity_identity, program_identity
from .opportunities import SaveResult, attach_eligibility, save_opportunity
from .programs import (
    compute_typical_window,
    due_soon,
    known_orgs,
    known_programs,
    record_edition,
)
from .runs import (
    RUNS,
    append_event,
    ensure_run_indexes,
    finish_run,
    get_run,
    list_runs,
    start_run,
)

__all__ = [
    "DEAD_ENDS",
    "EXTRACTION_FAILURES",
    "OPPORTUNITIES",
    "PROGRAMS",
    "RUNS",
    "SaveResult",
    "append_event",
    "attach_eligibility",
    "clear_dead_end",
    "clear_extraction_failure",
    "dead_end_urls",
    "compute_typical_window",
    "due_soon",
    "ensure_dead_end_indexes",
    "ensure_failure_indexes",
    "ensure_indexes",
    "ensure_run_indexes",
    "failure_counts",
    "finish_run",
    "get_client",
    "get_database",
    "get_run",
    "known_orgs",
    "known_programs",
    "list_runs",
    "normalize",
    "opportunity_identity",
    "program_identity",
    "record_edition",
    "record_dead_end",
    "record_extraction_failure",
    "save_opportunity",
    "start_run",
]
