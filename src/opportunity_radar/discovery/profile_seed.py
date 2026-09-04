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


#: Labelled lines the profile states outright, read verbatim. Nothing here
#: infers or paraphrases — if the profile does not say it, it is not a fact.
_LABELLED = re.compile(r"^\s*[-*]\s*\**(?P<label>[^:*]+?)\**\s*:\s*(?P<value>.+?)\s*$", re.M)

_MARKET_LABELS = ("primary markets", "markets served", "geograph", "operating regions")
_SECTOR_LABELS = ("sector", "sub-sectors", "materials handled", "business model")


def _labelled_values(section: str, wanted: tuple[str, ...]) -> list[str]:
    """Values of `- Label: value` lines whose label matches one of `wanted`."""
    out: list[str] = []
    for match in _LABELLED.finditer(section):
        label = match.group("label").strip().lower()
        if any(want in label for want in wanted):
            out.append(match.group("value").strip())
    return out


def _split_terms(values: list[str]) -> list[str]:
    """Break comma/slash separated values into individual terms, in order."""
    seen: list[str] = []
    for value in values:
        # Drop parentheticals and bold markers before splitting.
        cleaned = re.sub(r"\([^)]*\)", "", value).replace("*", "")
        for part in re.split(r"[,/;]| and ", cleaned):
            term = part.strip(" .-–—")
            # Two characters is a real country ("UK", "US"). An earlier length
            # floor of three silently dropped the UK from Retearn's markets.
            if term and len(term) >= 2 and term.lower() not in {t.lower() for t in seen}:
                seen.append(term)
    return seen


def profile_facts(path=None) -> dict[str, list[str]]:
    """Geography and sector the profile states, for query planning.

    The business profile is the single source of truth for who this company is,
    so the planner reads its geography and sector from here rather than from
    anything written into the code. An earlier version hardcoded
    "Cover India and the Middle East" into the planner prompt, which pointed a
    whole run at a region the company has no presence in.

    Returns empty lists rather than guessing when the profile does not say.
    """
    profile = load_business_profile(path)
    sections = _sections(profile.text)

    # Markets only — deliberately not the HQ address. A headquarters line is a
    # street and a neighbourhood, which would produce queries like
    # "circular economy awards Gachibowli". The seed text already carries the
    # HQ for the planner to read in context.
    markets = _labelled_values(sections.get("International operations", ""), _MARKET_LABELS)
    sectors = _labelled_values(sections.get("Sector and business model", ""), _SECTOR_LABELS)

    return {
        "geographies": _split_terms(markets)[:8],
        "sectors": _split_terms(sectors)[:10],
    }


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
