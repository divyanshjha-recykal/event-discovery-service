"""Loads the Recykal business profile.

The Discovery and Eligibility Agents reason against this document, so it is read
from disk at run time and passed into prompts whole. It is never copied into a
prompt string by hand, and nothing in the pipeline writes back to it.

The profile is prose on purpose — it states where facts are uncertain and how to
treat that uncertainty — so this loader deliberately does not parse it into
fields. Callers get the text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import BUSINESS_PROFILE, REPO_ROOT

# BusinessProfile.md is the name in the repo; the other is the name the document
# has been circulated under. Both resolve, so neither breaks the loader.
_CANDIDATE_NAMES = (
    "BusinessProfile.md",
    "recykal-business-profile-final.md",
)


class ProfileNotFound(FileNotFoundError):
    """The business profile is missing, empty, or not where we looked."""


@dataclass(frozen=True)
class BusinessProfile:
    path: Path
    text: str

    @property
    def sections(self) -> list[str]:
        """Top-level `## ` headings, for logging and sanity checks only."""
        return [
            line[3:].strip()
            for line in self.text.splitlines()
            if line.startswith("## ")
        ]


def _resolve(path: str | Path | None) -> Path:
    if path:
        return Path(path).expanduser()

    env_path = os.getenv("BUSINESS_PROFILE_PATH", "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        return candidate if candidate.is_absolute() else REPO_ROOT / candidate

    for name in _CANDIDATE_NAMES:
        candidate = REPO_ROOT / name
        if candidate.is_file():
            return candidate
    return BUSINESS_PROFILE


def load_business_profile(path: str | Path | None = None) -> BusinessProfile:
    """Read the profile from disk. Raises rather than returning a partial one."""
    resolved = _resolve(path)
    if not resolved.is_file():
        raise ProfileNotFound(
            f"No business profile at {resolved}. Expected one of "
            f"{', '.join(_CANDIDATE_NAMES)} at the repo root, or "
            f"BUSINESS_PROFILE_PATH pointing at it."
        )

    text = resolved.read_text(encoding="utf-8")
    if not text.strip():
        raise ProfileNotFound(f"Business profile at {resolved} is empty.")

    return BusinessProfile(path=resolved, text=text)
