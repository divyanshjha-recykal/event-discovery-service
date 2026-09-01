"""Stage 4 acceptance: run evaluate() against the Stage 0 reference criteria sets.

CLAUDE.md requires this before evaluate() touches anything Stage 3 discovered.

    uv run python scripts/run_eligibility.py --model google/gemma-4-31b-it

Done when: every reference set produces the verdict path written by hand in
Stage 0, and the qualitative criterion never appears inside `score`.

    --stored   after the reference sets pass, also evaluate stored opportunities
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opportunity_radar.config import MissingConfig, MongoConfig
from opportunity_radar.eligibility import (
    evaluate_criteria,
    load_criteria_sets,
)
from opportunity_radar.profile import load_business_profile
from opportunity_radar.storage import (
    OPPORTUNITIES,
    attach_eligibility,
    get_client,
    get_database,
)


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def check_reference_sets(profile_text: str, model: str | None) -> bool:
    sets = load_criteria_sets()
    print(f"Loaded {len(sets)} reference criteria set(s).\n")

    passed = 0
    for spec in sets:
        print(f"--- {spec.name}")
        print(f"    criterion: {spec.criterion}")
        try:
            result = evaluate_criteria(
                [spec.criterion], profile_text, spec.name, model
            )
        except Exception as exc:  # noqa: BLE001
            print(f"    ERROR: {type(exc).__name__}: {exc}\n")
            continue

        scored = result.criteria_results
        noted = result.qualitative_notes

        if spec.expects_qualitative:
            # The whole point of Set 5: it must be a note, and must not be scored.
            ok = bool(noted) and not scored and result.score is None
            got = "qualitative note" if noted else (
                f"scored as {scored[0].status}" if scored else "nothing"
            )
            print(f"    expected : qualitative note, never scored")
            print(f"    got      : {got}")
            print(f"    score    : {result.score}  (must be None)")
            if noted:
                print(f"    note     : {noted[0].note[:100]}")
        else:
            ok = len(scored) == 1 and scored[0].status == spec.expected_status
            got = scored[0].status if scored else (
                "filed as qualitative" if noted else "nothing"
            )
            print(f"    expected : {spec.expected_status}")
            print(f"    got      : {got}")
            if scored:
                print(f"    reasoning: {scored[0].reasoning[:130]}")

        print(f"    confidence: {result.confidence}")
        for flag in result.classification_flags:
            print(f"    ! {flag}")
        print(f"    {'PASS' if ok else 'FAIL'}\n")
        passed += ok

    print(f"{passed}/{len(sets)} reference sets produced the expected verdict path.")
    return passed == len(sets)


async def check_stored(profile_text: str, model: str | None) -> None:
    try:
        config = MongoConfig.from_env()
    except MissingConfig as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return

    client = get_client(config)
    db = get_database(client, config)
    try:
        docs = [d async for d in db[OPPORTUNITIES].find({})]
        await _evaluate_and_store(db, docs, profile_text, model)
    finally:
        await client.close()


async def _evaluate_and_store(db, docs, profile_text: str, model: str | None) -> None:

    print(f"\n{'=' * 72}\nSTORED OPPORTUNITIES ({len(docs)})\n{'=' * 72}")
    for doc in docs:
        criteria = doc.get("eligibility_criteria") or []
        title = doc.get("title", "(untitled)")
        if not criteria:
            print(f"\n--- {title}\n    skipped: no eligibility_criteria stored")
            continue

        print(f"\n--- {title}")
        try:
            result = evaluate_criteria(
                criteria, profile_text, f"{title} — {doc.get('organizing_body')}", model
            )
        except Exception as exc:  # noqa: BLE001
            print(f"    ERROR: {type(exc).__name__}: {exc}")
            continue

        counts = result.counts
        score = "n/a" if result.score is None else f"{result.score:.2f}"
        print(f"    score {score}  confidence {result.confidence}  "
              f"(met {counts['met']} / not_met {counts['not_met']} / unclear {counts['unclear']}"
              f", {len(result.qualitative_notes)} qualitative)")
        for r in result.criteria_results:
            print(f"      [{r.status:8}] {r.criterion[:72]}")
            print(f"                 {r.reasoning[:100]}")
        for n in result.qualitative_notes:
            print(f"      [note    ] {n.criterion[:72]}")
        for flag in result.classification_flags:
            print(f"      ! {flag}")

        # Persisted so Stage 5 can read verdicts from Mongo. CLAUDE.md puts the
        # eligibility result on the opportunity record itself.
        await attach_eligibility(db, doc["source_url"], result.model_dump())
        print("      (verdict saved to the opportunity record)")


async def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="OpenRouter slug. Defaults to OPENROUTER_MODEL.")
    parser.add_argument("--stored", action="store_true",
                        help="Also evaluate the opportunities Stage 3 stored.")
    args = parser.parse_args()

    profile = load_business_profile()
    print(f"Business profile: {profile.path.name}, {len(profile.text):,} chars\n")

    ok = check_reference_sets(profile.text, args.model)

    print("\nAcceptance (CLAUDE.md Stage 4):")
    print(f"  every reference set produces its expected verdict path : "
          f"{'PASS' if ok else 'FAIL'}")
    print("  qualitative criterion never appears inside score        : "
          "checked per-set above (Set 5 must show score None)")

    if args.stored:
        if not ok:
            print("\nSkipping stored opportunities — reference sets must pass first "
                  "(CLAUDE.md runs them before anything Stage 3 discovered).")
        else:
            await check_stored(profile.text, args.model)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
