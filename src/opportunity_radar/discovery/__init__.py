"""Discovery Agent — the reasoning loop that finds opportunities."""

from .agent import DiscoveryRun, run_discovery
from .budget import BudgetExhausted, RunBudget, estimate_cost
from .profile_seed import ProfileSectionMissing, discovery_seed, seed_stats
from .tools import DiscoveryContext, build_tools

__all__ = [
    "BudgetExhausted",
    "DiscoveryContext",
    "DiscoveryRun",
    "ProfileSectionMissing",
    "RunBudget",
    "build_tools",
    "discovery_seed",
    "estimate_cost",
    "run_discovery",
    "seed_stats",
]
