"""Distils `BusinessProfile.md` down to what Discovery actually needs.

Mechanical on purpose: this pulls named sections verbatim, it does not
paraphrase and it does not ask a model to summarise. A mechanical extraction
cannot drift from the source; a paraphrase can, and silently.

Why Discovery gets a subset while Eligibility gets the whole document: any field
in the profile could matter to any eligibility criterion, so pre-filtering there
risks cutting something relevant. Discovery's need is narrow and known ahead of
time — sub-sectors, geography, recognition history — and it is read on every
loop turn rather than once per opportunity, so the full document would be paid
for repeatedly across a run.
"""

from __future__ import annotations

import re

from ..profile import load_business_profile

# Verbatim sections, in the order Discovery finds them useful. Names must match
# the `## ` headings in BusinessProfile.md exactly; a rename raises rather than
# silently returning a thinner block.
DISCOVERY_SECTIONS = (
    "Identity",
    "Sector and business model",
    "International operations",
    "Recognition history",
    "Known exclusions",
)


class ProfileSectionMissing(RuntimeError):
    """A named section is no longer in the profile — the distillation is stale."""


def _sections(text: str) -> dict[str, str]:
    """Split the profile into `## heading` -> body, verbatim."""
    found: dict[str, str] = {}
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        found[match.group(1).strip()] = text[match.end():end].strip()
    return found


def discovery_seed(path=None) -> str:
    """The distilled profile block handed to the Discovery Agent each turn."""
    profile = load_business_profile(path)
    available = _sections(profile.text)

    missing = [name for name in DISCOVERY_SECTIONS if name not in available]
    if missing:
        raise ProfileSectionMissing(
            f"BusinessProfile.md has no section(s) named {missing}. "
            f"Found: {sorted(available)}. Update DISCOVERY_SECTIONS to match."
        )

    parts = [f"## {name}\n\n{available[name]}" for name in DISCOVERY_SECTIONS]
    return "\n\n".join(parts).strip()


def seed_stats(path=None) -> dict[str, int]:
    """Sizes, so the saving over passing the whole document is visible."""
    profile = load_business_profile(path)
    seed = discovery_seed(path)
    return {
        "full_profile_chars": len(profile.text),
        "seed_chars": len(seed),
        "sections_included": len(DISCOVERY_SECTIONS),
        "sections_available": len(_sections(profile.text)),
    }
