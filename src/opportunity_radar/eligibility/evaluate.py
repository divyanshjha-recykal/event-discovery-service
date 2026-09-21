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

from ..tracing import chat_model, stage_span, trace_handler
from .schema import CriterionResult, EligibilityResult, QualitativeNote
from .scoring import audit_classification, compute_score, derive_confidence

MAX_OUTPUT_TOKENS = 4096

SYSTEM_PROMPT = """\
You judge whether a company meets each eligibility condition of an award, \
recognition programme or technical venue, using ONLY the company profile you \
are given. For a venue that accepts submitted work the conditions are its \
scope — the topics it wants — and the question is whether the profile shows \
work that fits. Judge those the same way as any other condition.

Return ONLY a JSON object with exactly two keys:

  criteria_results   array of {"criterion", "status", "reasoning"} — conditions \
a specific fact settles. status is exactly "met", "not_met" or "unclear".
  qualitative_notes  array of {"criterion", "note"} — conditions no fact can \
settle, and conditions belonging to a route this company would not take. A \
human reads these and decides.

Which bucket:
- A fact decides it — years trading, legal form, turnover, registration, \
certification, country, sector, scale, and the technical ground the profile \
states: research areas, methods, deployed systems, datasets, patents and \
measured results. Goes in criteria_results.
- It asks for a judgement of quality, innovation, leadership or impact. Goes \
in qualitative_notes.
- ALTERNATIVE CATEGORIES. When a programme offers several categories or tracks \
and an entrant enters one, judge only the conditions of the track this company \
would realistically enter. Put the other tracks' conditions in \
qualitative_notes and say which track they belong to. NEVER mark a condition \
not_met because it belongs to a category this company would not be entering.
- Do not move a genuine requirement into qualitative_notes to avoid saying \
not_met. If the profile contradicts a hard requirement, say not_met plainly.

Choosing a status:
- "met" — the profile positively establishes it.
- "not_met" — the profile positively contradicts it. Use this when the fact is \
known and simply falls short, not only when it is impossible.
- "unclear" — the profile does not say, or records the fact as unknown or \
unverified. Never guess a met or not_met to avoid an unclear.

Ground every reasoning and note in something the profile actually says, and \
name that fact. Do not invent facts, and do not use outside knowledge about \
the company.

Every condition you are given must appear exactly once, in one bucket or the \
other. Output the JSON object and nothing else. No markdown fence, no \
commentary.\
"""


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    return json.loads(text)


_ORDINAL_PREFIX = re.compile(r"^\s*\(?\d+[.)\]]?\s+")


def _strip_ordinal(text: str) -> str:
    """Remove a leading list number the model may have prepended.

    Belt and braces behind the un-numbered prompt: if a model numbers its
    criteria anyway, the digits must not reach the stored criterion text, where
    the classification audit would read them as factual markers and flag every
    numbered criterion as suspicious.
    """
    return _ORDINAL_PREFIX.sub("", text).strip()


def _user_prompt(criteria: list[str], business_profile: str, context: str) -> str:
    # Bulleted, not numbered. Numbering made the model echo "7. For ..." back
    # into the criterion field, which tripped the audit on the list number
    # rather than on anything factual.
    listed = "\n".join(f"- {c}" for c in criteria)
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

    with stage_span(
        f"stage4.evaluate: {context[:60]}",
        model=model, criteria_count=len(criteria),
    ) as span:
        return _evaluate(criteria, business_profile, context, model, span)


def _evaluate(
    criteria: list[str],
    business_profile: str,
    context: str,
    model: str | None,
    span,
) -> EligibilityResult:

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
            criterion=_strip_ordinal(str(item.get("criterion", ""))),
            status=str(item.get("status", "")).strip().lower(),
            reasoning=str(item.get("reasoning", "")).strip() or "(no reasoning given)",
        )
        for item in payload.get("criteria_results") or []
        if str(item.get("criterion", "")).strip()
    ]
    notes = [
        QualitativeNote(
            criterion=_strip_ordinal(str(item.get("criterion", ""))),
            note=str(item.get("note", "")).strip() or "(no note given)",
        )
        for item in payload.get("qualitative_notes") or []
        if str(item.get("criterion", "")).strip()
    ]

    # Computed here, never taken from the model.
    outcome = EligibilityResult(
        criteria_results=results,
        qualitative_notes=notes,
        confidence=derive_confidence(results),
        score=compute_score(results),
        classification_flags=audit_classification(notes),
    )
    span.update(metadata={
        "confidence": outcome.confidence,
        "score": outcome.score,
        **outcome.counts,
        "qualitative": len(outcome.qualitative_notes),
        "classification_flags": len(outcome.classification_flags),
    })
    return outcome


def evaluate(opportunity, business_profile: str, model: str | None = None) -> EligibilityResult:
    """Judge one stored opportunity against the business profile."""
    criteria = list(getattr(opportunity, "eligibility_criteria", None) or [])
    title = getattr(opportunity, "title", None) or "(untitled opportunity)"
    body = getattr(opportunity, "organizing_body", None) or "(unknown body)"
    if not criteria:
        raise ValueError(f"{title!r} has no eligibility_criteria to evaluate")
    return evaluate_criteria(criteria, business_profile, f"{title} — {body}", model)
