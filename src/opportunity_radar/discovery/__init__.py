"""Discovery Agent — the reasoning loop that finds opportunities."""

from .agent import DiscoveryRun, run_discovery
from .budget import BudgetExhausted, RunBudget, estimate_cost
from .profile_seed import ProfileSectionMissing, discovery_seed, seed_stats
from .state import (
    CandidateVerdict,
    DiscoveryState,
    EvidenceBundle,
    EvidencePage,
    PlannedQuery,
    SearchHit,
)

__all__ = [
    "BudgetExhausted",
    "CandidateVerdict",
    "DiscoveryRun",
    "DiscoveryState",
    "EvidenceBundle",
    "EvidencePage",
    "PlannedQuery",
    "ProfileSectionMissing",
    "RunBudget",
    "SearchHit",
    "discovery_seed",
    "estimate_cost",
    "run_discovery",
    "seed_stats",
]
