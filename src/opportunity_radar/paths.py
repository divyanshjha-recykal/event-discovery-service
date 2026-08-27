"""Repo-root resolution, so nothing has to care about the working directory."""

from pathlib import Path

# src/opportunity_radar/paths.py -> src/opportunity_radar -> src -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

BUSINESS_PROFILE = REPO_ROOT / "BusinessProfile.md"
GOLDEN_SET_DIR = REPO_ROOT / "golden_set"
