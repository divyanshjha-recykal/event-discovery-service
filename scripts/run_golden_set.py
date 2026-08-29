"""Stage 2 acceptance check: run the golden set through one or more models.

CLAUDE.md requires comparing schema-compliance rate and `deadline_verified`
accuracy across more than one OPENROUTER_MODEL before Stage 3 starts.

    uv run python scripts/run_golden_set.py --model <slug-a> --model <slug-b>

Done when every page yields either a schema-valid record or a named typed
failure, never a malformed or partial one, and Example 2 yields
opportunity_closed rather than a record.
"""

from __future__ import annotations

import argparse
import sys

from opportunity_radar.config import MissingConfig
from opportunity_radar.extraction import (
    ExtractionFailure,
    FailureReason,
    OpportunityRecord,
    base_title_warning,
    extract,
    load_examples,
)

# Fields worth comparing against the hand-written answers. eligibility_criteria
# is compared by count only — exact wording will differ between models and
# demanding a string match would punish a correct extraction.
COMPARED = (
    "organizing_body",
    "base_title",
    "cycle_year",
    "category",
    "submission_deadline",
    "deadline_verified",
)


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def _compare(record: OpportunityRecord, expected: dict) -> list[str]:
    """Field-level mismatches against the golden answer."""
    diffs = []
    for field in COMPARED:
        if field not in expected:
            continue
        got, want = getattr(record, field), expected[field]
        if isinstance(want, str) and isinstance(got, str):
            if got.strip().lower() != want.strip().lower():
                diffs.append(f"{field}: got {got!r}, expected {want!r}")
        elif got != want:
            diffs.append(f"{field}: got {got!r}, expected {want!r}")
    return diffs


def run_model(model: str | None, examples: list) -> dict:
    label = model or "(OPENROUTER_MODEL)"
    print(f"\n{'=' * 72}\nMODEL: {label}\n{'=' * 72}")

    stats = {
        "model": label,
        "well_formed": 0,      # schema-valid record OR named failure — never malformed
        "records": 0,
        "failures": 0,
        "deadline_correct": 0,
        "deadline_checked": 0,
        "field_matches": 0,
        "field_total": 0,
        "outcome_correct": 0,
        "warnings": [],
    }

    for example in examples:
        print(f"\n--- {example.name}")
        try:
            result = extract(example.page_text, example.source_url, model=model)
        except Exception as exc:  # noqa: BLE001
            print(f"  CRASHED: {type(exc).__name__}: {exc}")
            continue

        stats["well_formed"] += 1  # extract() returns a record or a typed failure

        if isinstance(result, ExtractionFailure):
            stats["failures"] += 1
            print(f"  -> typed failure: {result.reason.value}")
            print(f"     {result.detail}")
            correct = example.expects_closed and result.reason is FailureReason.OPPORTUNITY_CLOSED
            if example.expects_closed:
                stats["outcome_correct"] += int(correct)
                print(f"     expected opportunity_closed: {'YES' if correct else 'NO'}")
            else:
                print("     EXPECTED A RECORD — this is a miss")
            continue

        stats["records"] += 1
        if example.expects_closed:
            print("  -> record produced, but this page is CLOSED — this is the Stage 2 failure case")
            continue
        stats["outcome_correct"] += 1

        warning = base_title_warning(result)
        if warning:
            stats["warnings"].append(f"{example.name}: {warning}")
            print(f"  ! {warning}")

        print(f"  title            : {result.title}")
        print(f"  organizing_body  : {result.organizing_body}")
        print(f"  base_title       : {result.base_title}")
        print(f"  cycle_year       : {result.cycle_year}")
        print(f"  category         : {result.category}")
        print(f"  deadline         : {result.submission_deadline}  verified={result.deadline_verified}")
        print(f"  criteria         : {len(result.eligibility_criteria)} item(s)")

        if not example.expected:
            continue

        diffs = _compare(result, example.expected)
        compared = [f for f in COMPARED if f in example.expected]
        stats["field_total"] += len(compared)
        stats["field_matches"] += len(compared) - len(diffs)

        if "deadline_verified" in example.expected:
            stats["deadline_checked"] += 1
            stats["deadline_correct"] += int(
                result.deadline_verified == example.expected["deadline_verified"]
                and result.submission_deadline == example.expected.get("submission_deadline")
            )

        if diffs:
            print("  mismatches vs golden answer:")
            for d in diffs:
                print(f"    - {d}")
        else:
            print("  matches the golden answer on every compared field")

        expected_count = len(example.expected.get("eligibility_criteria", []))
        if expected_count:
            print(f"  criteria count   : got {len(result.eligibility_criteria)}, golden {expected_count}")

    return stats


def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", dest="models",
                        help="OpenRouter slug. Repeat to compare models.")
    args = parser.parse_args()
    models: list[str | None] = args.models or [None]

    try:
        examples = load_examples()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: could not load the golden set — {exc}", file=sys.stderr)
        return 1
    print(f"Loaded {len(examples)} golden-set example(s).")

    all_stats = []
    for model in models:
        try:
            all_stats.append(run_model(model, examples))
        except MissingConfig as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}")
    header = f"{'model':<34} {'well-formed':>11} {'outcome':>8} {'fields':>9} {'deadline':>9}"
    print(header)
    print("-" * len(header))
    total = len(examples)
    for s in all_stats:
        fields = f"{s['field_matches']}/{s['field_total']}" if s["field_total"] else "-"
        deadline = f"{s['deadline_correct']}/{s['deadline_checked']}" if s["deadline_checked"] else "-"
        well_formed = f"{s['well_formed']}/{total}"
        outcome = f"{s['outcome_correct']}/{total}"
        print(f"{s['model']:<34} {well_formed:>11} {outcome:>8} {fields:>9} {deadline:>9}")

    print("\nAcceptance (CLAUDE.md Stage 2):")
    ok = True
    for s in all_stats:
        well = s["well_formed"] == len(examples)
        outcome = s["outcome_correct"] == len(examples)
        print(f"  {s['model']}")
        print(f"    every page -> record or named failure : {'PASS' if well else 'FAIL'}")
        print(f"    Example 2 -> opportunity_closed       : {'PASS' if outcome else 'FAIL'}")
        ok = ok and well and outcome
        for w in s["warnings"]:
            print(f"    ! {w}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
