"""Make one tiny real call of every shape the pipeline uses, and report which work.

    uv run python scripts/smoke_calls.py --model deepseek/deepseek-v4.1-flash

Costs a cent or two and touches no Tavily or Firecrawl. Run it after changing a
model, a schema, or anything passed to the provider.

This exists because `--dry-run` cannot catch provider-parameter errors: the dry
run skips the link chooser and the eligibility call entirely, so a malformed
`reasoning` block on either only ever surfaced on a paid live run.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from opportunity_radar.discovery.budget import RunBudget
from opportunity_radar.discovery.state import WorkflowRuntime
from opportunity_radar.discovery.workflow import (
    TOKENS_ANALYZE,
    TOKENS_PICK_LINKS,
    TOKENS_PLAN,
    TOKENS_SHORTLIST,
    _AnalysisModel,
    _LinkChoiceModel,
    _QueryPlanModel,
    _ShortlistModel,
    _structured,
)
from opportunity_radar.discovery.providers import search_provider
from opportunity_radar.eligibility import evaluate_criteria

TODAY = date.today().isoformat()

# Each entry mirrors a real call site: same schema, same token budget, same
# `light` flag. The prompts are deliberately trivial — this checks the request
# is accepted and the reply validates, not that the answer is any good.
CALLS = [
    ("opportunity_query_plan", _QueryPlanModel, TOKENS_PLAN, False,
     "Return a search plan as JSON matching the supplied schema.",
     f"Today is {TODAY}. Write 1 web search to find awards a recycling "
     "company in India could enter."),
    ("search_shortlist", _ShortlistModel, TOKENS_SHORTLIST, False,
     "Rank search results. Return JSON matching the supplied schema.",
     f"Today is {TODAY}. Rank these:\n[0] National Recycling Awards — "
     "https://example.com/awards — entries open\n[1] Winners announced — "
     "https://example.com/news"),
    # The one that broke: light=True is the only call using that branch.
    ("link_selection", _LinkChoiceModel, TOKENS_PICK_LINKS, True,
     "Pick which links to fetch. Return JSON matching the supplied schema.",
     "Pick at most 2 links that state entry eligibility.\n"
     "[0] Eligibility — https://example.com/eligibility\n"
     "[1] Past winners — https://example.com/winners"),
    ("opportunity_candidate_analysis", _AnalysisModel, TOKENS_ANALYZE, False,
     "Return candidate decisions as strict JSON matching the supplied schema.",
     f"Today is {TODAY}. One page:\n=== SOURCE PAGE: https://example.com/awards ===\n"
     "National Recycling Awards 2027. Run by the Example Foundation. Open to "
     "companies registered in India. Entries close 30 November 2027."),
]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="OPENROUTER_MODEL override")
    parser.add_argument("--search", action="store_true",
                        help="also make one live call to SEARCH_PROVIDER (spends a search)")
    args = parser.parse_args()

    runtime = WorkflowRuntime(
        db=None, budget=RunBudget(max_llm_calls=99, tool_calls=99),
        model=args.model, dry_run=False, run_id="smoke",
        profile_text="A recycling technology company registered in India.",
    )

    failures = 0
    for name, model_cls, tokens, light, system, user in CALLS:
        try:
            await _structured(
                runtime, model_cls, name, system, user,
                max_tokens=tokens, light=light,
            )
            print(f"  ok      {name}" + ("  (light)" if light else ""))
        except Exception as exc:  # noqa: BLE001 — reporting every shape is the point
            failures += 1
            print(f"  FAILED  {name}: {type(exc).__name__}: {exc}"[:400])

    # Eligibility lives outside the graph and is likewise skipped by --dry-run.
    try:
        await asyncio.to_thread(
            evaluate_criteria,
            ["Open to companies registered in India"],
            runtime.profile_text,
            "National Recycling Awards — Example Foundation",
            args.model,
        )
        print("  ok      feasibility")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"  FAILED  feasibility: {type(exc).__name__}: {exc}"[:400])

    shapes = len(CALLS) + 1
    if args.search:
        shapes += 1
        name, search = search_provider()
        try:
            hits = await search("technology innovation awards that companies can enter")
            if not hits:
                raise RuntimeError("no results")
            dated = sum(1 for h in hits if h.entry_deadline or h.event_date)
            print(f"  ok      search ({name}): {len(hits)} hits, {dated} with a date")
        except Exception as exc:  # noqa: BLE001 — reporting every shape is the point
            failures += 1
            print(f"  FAILED  search ({name}): {type(exc).__name__}: {exc}"[:400])

    print(f"\n{shapes - failures}/{shapes} call shapes accepted")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
