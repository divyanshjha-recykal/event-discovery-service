"""Loads the business profile.

The Discovery and Eligibility Agents reason against this document, so it is read
from disk at run time and passed into prompts whole. It is never copied into a
prompt string by hand, and nothing in the pipeline writes back to it.

Callers get the text. Two sections with fixed headings are also read verbatim,
so discovery can put the hard constraints at the top of its prompts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import BUSINESS_PROFILE, REPO_ROOT

# BusinessProfile.md is the name in the repo; the other is the name the document
# has been circulated under. Both resolve, so neither breaks the loader.
#: BusinessProfile.md is the profile. One name, so there is no ambiguity about
#: which file defines the business.
_CANDIDATE_NAMES = ("BusinessProfile.v2.md",)

SEARCH_CONSTRAINTS = "Search constraints"
SEARCH_ANGLES = "Search angles"


class ProfileNotFound(FileNotFoundError):
    """The business profile is missing, empty, or not where we looked."""


class ProfileSectionMissing(RuntimeError):
    """A section the pipeline reads by name is missing or empty."""


def profile_section(text: str, heading: str) -> str:
    """Body of one `## heading` section, verbatim."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == f"## {heading}"), None
    )
    if start is None:
        raise ProfileSectionMissing(f"business profile has no '## {heading}' section")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    body = "\n".join(lines[start + 1:end]).strip()
    if not body:
        raise ProfileSectionMissing(f"business profile section '## {heading}' is empty")
    return body


def without_sections(text: str, *headings: str) -> str:
    """The profile with the named `## ` sections removed."""
    kept, skipping = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            skipping = line[3:].strip() in headings
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


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
