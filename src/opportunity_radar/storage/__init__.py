"""Storage layer — the two Mongo collections and the program registry."""

from .client import OPPORTUNITIES, PROGRAMS, ensure_indexes, get_client, get_database
from .identity import normalize, opportunity_identity, program_identity
from .opportunities import SaveResult, save_opportunity
from .programs import compute_typical_window, due_soon, known_orgs, record_edition

__all__ = [
    "OPPORTUNITIES",
    "PROGRAMS",
    "SaveResult",
    "compute_typical_window",
    "due_soon",
    "ensure_indexes",
    "get_client",
    "get_database",
    "known_orgs",
    "normalize",
    "opportunity_identity",
    "program_identity",
    "record_edition",
    "save_opportunity",
]
