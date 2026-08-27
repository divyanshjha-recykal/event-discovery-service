"""Stage 1 acceptance check, run against the real Mongo container.

Covers CLAUDE.md's two stated conditions plus the identity-normalisation and
program-registry behaviour they depend on.

    uv run python scripts/verify_storage.py            # uses a scratch database
    uv run python scripts/verify_storage.py --keep     # leave the data behind

Not a test framework — CLAUDE.md explicitly does not want one this phase.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pymongo.errors import DuplicateKeyError

from opportunity_radar.config import MissingConfig, MongoConfig
from opportunity_radar.storage import (
    OPPORTUNITIES,
    PROGRAMS,
    compute_typical_window,
    due_soon,
    ensure_indexes,
    get_client,
    known_orgs,
    save_opportunity,
)

SCRATCH_DB = "opportunity_radar_verify"

CII_2026 = {
    "title": "CII 4R Awards 2026",
    "organizing_body": "CII",
    "base_title": "4R Awards",
    "cycle_year": 2026,
    "category": "award",
    "eligibility_criteria": ["Start-ups incorporated or registered in India"],
    "submission_deadline": "2026-08-31",
    "deadline_note": None,
    "deadline_verified": True,
    "event_date": None,
    "source_url": "https://www.ciiwaste2worth.com/4R-excellence-categories.php",
}

results: list[tuple[bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")


async def run(db) -> None:
    await db[OPPORTUNITIES].delete_many({})
    await db[PROGRAMS].delete_many({})
    await ensure_indexes(db)

    print("\n=== Condition 1: same identity twice -> one document, updated ===")
    first = await save_opportunity(db, CII_2026)
    check("first save inserts", first.inserted, first.action)

    revised = {**CII_2026, "submission_deadline": "2026-09-15"}
    second = await save_opportunity(db, revised)
    check("second save updates, does not insert", not second.inserted, second.action)

    count = await db[OPPORTUNITIES].count_documents({})
    check("exactly one opportunity document", count == 1, f"found {count}")
    stored = await db[OPPORTUNITIES].find_one({})
    check(
        "deadline reflects the second write",
        stored["submission_deadline"] == "2026-09-15",
        stored["submission_deadline"],
    )

    print("\n=== Identity normalisation ===")
    messy = {**CII_2026, "organizing_body": "  the cii , ", "base_title": "4R  Awards"}
    third = await save_opportunity(db, messy)
    check("case/space/punctuation variant matches existing", not third.inserted, third.action)
    count = await db[OPPORTUNITIES].count_documents({})
    check("still one document after variant", count == 1, f"found {count}")

    print("\n=== Unique index actually enforced ===")
    try:
        await db[OPPORTUNITIES].insert_one(
            {"norm_organizing_body": "cii", "norm_base_title": "4r awards", "cycle_year": 2026}
        )
        check("raw duplicate insert rejected", False, "insert succeeded — index missing")
    except DuplicateKeyError:
        check("raw duplicate insert rejected by Mongo", True)

    print("\n=== Condition 2: new cycle_year -> new opportunity + new edition ===")
    y2027 = {**CII_2026, "title": "CII 4R Awards 2027", "cycle_year": 2027,
             "submission_deadline": "2027-08-20"}
    fourth = await save_opportunity(db, y2027)
    check("new cycle_year inserts", fourth.inserted, fourth.action)

    count = await db[OPPORTUNITIES].count_documents({})
    check("two opportunity documents now", count == 2, f"found {count}")

    programs = await db[PROGRAMS].count_documents({})
    check("still exactly one program (year not in program identity)", programs == 1,
          f"found {programs}")

    program = await db[PROGRAMS].find_one({})
    years = sorted(e["year"] for e in program["editions"])
    check("both editions recorded", years == [2026, 2027], str(years))

    print("\n=== typical_window ===")
    check(
        "computed once 2+ editions exist (both in August -> Aug..Aug)",
        program["typical_window"] == {"month_start": 8, "month_end": 8},
        str(program["typical_window"]),
    )
    check(
        "null with a single edition",
        compute_typical_window([{"year": 2026, "deadline": "2026-08-31"}]) is None,
    )
    check(
        "wraps around year end (Nov + Jan -> 11..1, not 1..11)",
        compute_typical_window(
            [{"year": 2025, "deadline": "2025-11-10"}, {"year": 2026, "deadline": "2026-01-20"}]
        ) == {"month_start": 11, "month_end": 1},
    )

    print("\n=== Registry reads ===")
    orgs = await known_orgs(db)
    check("known_orgs returns the raw name", orgs == ["CII"], str(orgs))

    await db[PROGRAMS].insert_one(
        {"norm_organizing_body": "unproven org", "norm_base_title": "new thing",
         "organizing_body": "Unproven Org", "base_title": "New Thing",
         "editions": [{"year": 2026, "deadline": "2026-08-01"}], "typical_window": None}
    )
    soon = await due_soon(db, lookahead_months=12)
    names = [p["base_title"] for p in soon]
    check("due_soon excludes null typical_window", "New Thing" not in names, str(names))
    check("due_soon includes a windowed program", "4R Awards" in names, str(names))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Do not drop the scratch database.")
    args = parser.parse_args()

    try:
        config = MongoConfig.from_env()
    except MissingConfig as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    client = get_client(config)
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot reach MongoDB — {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Is the stack up?  docker compose up -d mongodb", file=sys.stderr)
        return 1

    print(f"Connected. Using scratch database {SCRATCH_DB!r} (never the real one).")
    try:
        await run(client[SCRATCH_DB])
    finally:
        if not args.keep:
            await client.drop_database(SCRATCH_DB)
        await client.close()

    failed = [label for ok, label in results if not ok]
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} checks FAILED:", file=sys.stderr)
        for label in failed:
            print(f"  - {label}", file=sys.stderr)
        return 1
    print(f"ALL {len(results)} CHECKS PASS — Stage 1 acceptance met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
