"""`evaluate(opportunity, business_profile)` — one call, per criterion.

The model reasons about each criterion separately and sorts it into
fact-checkable or qualitative. It does NOT produce `confidence` or `score` —
those are computed from its results by plain functions, because a model asked
to rate its own certainty rates its own certainty, not the evidence.

Eligibility gets the full business profile, unlike Discovery which gets a
distilled seed. Any field could matter to any criterion, so pre-filtering here
risks cutting the one section a given criterion needed. This runs once per
opportunity rather than every loop turn, so the cost is paid once.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ..tracing import chat_model, trace_handler
from .schema import CriterionResult, EligibilityResult, QualitativeNote
from .scoring import audit_classification, compute_score, derive_confidence

MAX_OUTPUT_TOKENS = 4096

SYSTEM_PROMPT = """\
You judge whether a company meets each eligibility criterion of an award, \
grant or programme, using ONLY the company profile you are given.

Return ONLY a JSON object with exactly two keys:

  criteria_results   array of {"criterion", "status", "reasoning"} for every \
FACT-CHECKABLE criterion. status is exactly one of "met", "not_met", "unclear".
  qualitative_notes  array of {"criterion", "note"} for every QUALITATIVE \
criterion — ones asking for a judgement of quality, leadership, innovation or \
impact that no fact in the profile can settle.

Sorting criteria correctly:
- FACT-CHECKABLE means a specific fact decides it: years of operation, legal \
form, turnover, registration, certification, geography. These go in \
criteria_results with a met/not_met/unclear status.
- QUALITATIVE means no fact settles it — "demonstrates innovative leadership", \
"shows commitment to sustainability". These go in qualitative_notes and are \
never scored.
- Do NOT move a fact-checkable criterion into qualitative_notes to avoid \
committing to not_met. If the profile contradicts a hard requirement, say \
not_met plainly.

Choosing a status:
- "met" — the profile positively establishes it.
- "not_met" — the profile positively contradicts it. Use this when the fact is \
known and simply falls short, not only when it is impossible.
- "unclear" — the profile does not say, or explicitly records the fact as \
unknown or unverified. Never guess a met or not_met to avoid an unclear. The \
profile marks some facts as genuinely unknown; those are unclear, by design.

Ground every "reasoning" in something the profile actually says. Cite the \
specific fact. Do not invent facts, and do not import outside knowledge about \
the company.

Do not output a confidence value or a score. Those are computed separately \
from your results.

Output the JSON object and nothing else. No markdown fence, no commentary.\
"""


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    return json.loads(text)


def _user_prompt(criteria: list[str], business_profile: str, context: str) -> str:
    listed = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))
    return (
        f"COMPANY PROFILE\n\n{business_profile}\n\n"
        f"{'=' * 60}\n\nOPPORTUNITY: {context}\n\n"
        f"ELIGIBILITY CRITERIA TO JUDGE:\n\n{listed}\n\n"
        "Judge each criterion above. Every criterion must appear exactly once, "
        "in criteria_results or in qualitative_notes."
    )


def evaluate_criteria(
    criteria: list[str],
    business_profile: str,
    context: str = "(criteria evaluated standalone)",
    model: str | None = None,
) -> EligibilityResult:
    """Judge a bare list of criteria. Used by the Stage 0 reference sets.

    Raises on an unusable model reply rather than returning a hollow result —
    unlike extraction, there is no partial answer worth storing here.
    """
    if not criteria:
        raise ValueError("no criteria to evaluate")

    llm = chat_model(model, max_tokens=MAX_OUTPUT_TOKENS, timeout=120, max_retries=3)
    handler = trace_handler()
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(_user_prompt(criteria, business_profile, context)),
    ]

    payload: dict | None = None
    last_error = ""
    for attempt in (1, 2):
        try:
            response = llm.invoke(
                messages,
                config={"callbacks": [handler]},
                response_format={"type": "json_object"},
            )
            payload = _parse_json(response.content)
            break
        except json.JSONDecodeError as exc:
            last_error = f"model did not return valid JSON: {exc}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt == 1:
            messages.append(
                HumanMessage(
                    f"That response could not be used ({last_error}). "
                    "Reply again with only the JSON object described above."
                )
            )

    if payload is None:
        raise RuntimeError(f"eligibility evaluation failed after one retry — {last_error}")

    results = [
        CriterionResult(
            criterion=str(item.get("criterion", "")).strip(),
            status=str(item.get("status", "")).strip().lower(),
            reasoning=str(item.get("reasoning", "")).strip() or "(no reasoning given)",
        )
        for item in payload.get("criteria_results") or []
        if str(item.get("criterion", "")).strip()
    ]
    notes = [
        QualitativeNote(
            criterion=str(item.get("criterion", "")).strip(),
            note=str(item.get("note", "")).strip() or "(no note given)",
        )
        for item in payload.get("qualitative_notes") or []
        if str(item.get("criterion", "")).strip()
    ]

    # Computed here, never taken from the model.
    return EligibilityResult(
        criteria_results=results,
        qualitative_notes=notes,
        confidence=derive_confidence(results),
        score=compute_score(results),
        classification_flags=audit_classification(notes),
    )


def evaluate(opportunity, business_profile: str, model: str | None = None) -> EligibilityResult:
    """Judge one stored opportunity against the business profile."""
    criteria = list(getattr(opportunity, "eligibility_criteria", None) or [])
    title = getattr(opportunity, "title", None) or "(untitled opportunity)"
    body = getattr(opportunity, "organizing_body", None) or "(unknown body)"
    if not criteria:
        raise ValueError(f"{title!r} has no eligibility_criteria to evaluate")
    return evaluate_criteria(criteria, business_profile, f"{title} — {body}", model)
