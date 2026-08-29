"""`extract(scraped_text, source_url)` — a plain function, not an agent.

Returns a valid `OpportunityRecord` or a typed failure. JSON mode, one retry,
then fail named. It never guesses: a half-filled record is worse than a named
failure, because once stored it is indistinguishable from a real find.

Two things are deliberately NOT left to the model:

- `deadline_verified` is a plain string check against the source text
  (`grounding.verify_deadline`), never the model's own assessment of itself.
- `base_title` gets a deterministic edition strip on top of the model's answer,
  so the identity key cannot drift between models or between years.

Closed detection is the model's `status` field, with a cheap regex backstop
behind it. The regex is not the primary check — CLAUDE.md is explicit that
closed-vs-open is Discovery's call and this is only a second line of defense —
but it costs nothing when it does not fire and catches a known failure mode
when it does.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ..tracing import chat_model, trace_handler
from .base_title import edition_residue, strip_edition
from .failures import ExtractionFailure, FailureReason
from .grounding import verify_deadline
from .schema import OpportunityRecord

# Below this, there is not enough page to build a record from. Chosen to be
# clearly-too-short rather than borderline; borderline cases should reach the
# model and fail on missing fields instead.
MIN_CONTENT_CHARS = 200

# Extraction needs room for a full record, and reasoning models spend tokens
# before emitting any. Never leave this unset: OpenRouter reserves credit
# against the requested ceiling, so an unbounded call 402s on a small balance.
MAX_OUTPUT_TOKENS = 4096

# Backstop only. Phrases that state closure outright, not ones that merely
# discuss a past cycle.
_CLOSED_PHRASES = re.compile(
    r"\b("
    r"nominations?\s+(?:are\s+|is\s+)?(?:now\s+)?closed|"
    r"submissions?\s+(?:are\s+|is\s+)?(?:now\s+)?closed|"
    r"applications?\s+(?:are\s+|is\s+)?(?:now\s+)?closed|"
    r"entries?\s+(?:are\s+|is\s+)?(?:now\s+)?closed|"
    r"registration\s+(?:is\s+)?(?:now\s+)?closed|"
    r"nomination\s+window\s+is\s+(?:currently\s+)?closed|"
    r"no\s+longer\s+accepting\s+(?:applications|nominations|entries)|"
    r"this\s+(?:award|call|programme|program)\s+(?:has\s+)?closed"
    r")",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """\
You extract structured records about awards, grants, events and conferences \
from the text of a single web page.

Return ONLY a JSON object with exactly these keys:

  status                "open" | "closed" | "unclear"
  title                 full title as written, including the year if present
  organizing_body       the body that runs it, not the sponsor or the venue
  base_title            the title with year and edition markers removed, and \
nothing else. Do not drop place names, organiser names or any other words: \
apply the same rule regardless of what words happen to appear in the title.
  cycle_year            integer year of THIS edition
  category              "award" | "grant" | "event" | "conference"
  eligibility_criteria  array of separate conditions, each its own string. \
Never return one long paragraph. Return [] if the page states none.
  submission_deadline   "YYYY-MM-DD" or null
  deadline_note         a short note if the deadline is relative or rolling \
(e.g. "rolling", "30 days after announcement"), otherwise null
  event_date            "YYYY-MM-DD" or null
  confidence_note       one short sentence on anything you were unsure about

Rules:
- status is "closed" if the page states that nominations, submissions, \
applications or entries are closed, even if the rest of the page reads like an \
open call. This matters: pages often keep all their marketing copy after closing.
- Use only what the page says. If a field is not stated, use null or []. \
Never infer a deadline that is not on the page.
- The deadline year may be inferred from the page title or its publication \
date when the deadline itself gives only a day and month.
- category is "grant" when the award includes funding for further work, \
"award" when it is recognition only.
- Output the JSON object and nothing else. No markdown fence, no commentary.\
"""


def _user_prompt(scraped_text: str, source_url: str) -> str:
    return f"Source URL: {source_url}\n\nPage text:\n\n{scraped_text}"


def _parse_json(raw: str) -> dict:
    """Parse the model's reply, tolerating a markdown fence around it."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    return json.loads(text)


def extract(
    scraped_text: str,
    source_url: str,
    model: str | None = None,
) -> OpportunityRecord | ExtractionFailure:
    """Build one opportunity record from page text, or fail with a named reason."""
    if not scraped_text or len(scraped_text.strip()) < MIN_CONTENT_CHARS:
        return ExtractionFailure(
            FailureReason.INSUFFICIENT_CONTENT,
            f"page text is {len(scraped_text.strip() if scraped_text else '')} chars, "
            f"under the {MIN_CONTENT_CHARS} minimum",
            source_url,
        )

    llm = chat_model(model, max_tokens=MAX_OUTPUT_TOKENS, timeout=120, max_retries=3)
    handler = trace_handler()
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(_user_prompt(scraped_text, source_url)),
    ]

    payload: dict | None = None
    last_error = ""

    # JSON mode, one retry. The retry feeds the error back rather than simply
    # asking again, so the second attempt has something to correct.
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
        except Exception as exc:  # noqa: BLE001 — reported, not handled
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt == 1:
            messages.append(
                HumanMessage(
                    f"That response could not be used ({last_error}). "
                    "Reply again with only the JSON object described above."
                )
            )

    if payload is None:
        return ExtractionFailure(
            FailureReason.MALFORMED_RESPONSE,
            f"no usable response after one retry — {last_error}",
            source_url,
        )

    # Closed check: the model's semantic judgement, with the regex behind it.
    model_status = str(payload.get("status", "")).strip().lower()
    phrase = _CLOSED_PHRASES.search(scraped_text)
    if model_status == "closed" or phrase:
        stated_by = "model status" if model_status == "closed" else "page text"
        quoted = f" ({phrase.group(0)!r})" if phrase else ""
        return ExtractionFailure(
            FailureReason.OPPORTUNITY_CLOSED,
            f"page indicates the opportunity is closed, per {stated_by}{quoted}",
            source_url,
        )

    # Fields the model does not get the final word on.
    raw_title = str(payload.get("title") or "").strip()
    raw_base = str(payload.get("base_title") or raw_title).strip()
    if not raw_title:
        return ExtractionFailure(
            FailureReason.INSUFFICIENT_CONTENT, "no title found on the page", source_url
        )

    try:
        base = strip_edition(raw_base)
    except ValueError as exc:
        return ExtractionFailure(
            FailureReason.MALFORMED_RESPONSE, f"unusable base_title: {exc}", source_url
        )

    deadline = payload.get("submission_deadline") or None
    grounding = verify_deadline(deadline, scraped_text)

    try:
        record = OpportunityRecord(
            title=raw_title,
            organizing_body=str(payload.get("organizing_body") or "").strip(),
            base_title=base,
            cycle_year=payload.get("cycle_year"),
            category=payload.get("category"),
            eligibility_criteria=payload.get("eligibility_criteria") or [],
            submission_deadline=deadline,
            deadline_note=payload.get("deadline_note"),
            deadline_verified=grounding.verified,
            event_date=payload.get("event_date") or None,
            source_url=source_url,
        )
    except Exception as exc:  # pydantic ValidationError and friends
        return ExtractionFailure(
            FailureReason.MALFORMED_RESPONSE,
            f"record failed validation: {exc}",
            source_url,
        )

    return record


def base_title_warning(record: OpportunityRecord) -> str | None:
    """Anything edition-shaped still in `base_title`, for the caller to surface.

    Not an error: an unrecognised naming scheme should be visible rather than
    silently fragmenting the program registry, but it should not block the
    record from being stored.
    """
    residue = edition_residue(record.base_title)
    return (
        f"base_title {record.base_title!r} still contains {residue!r} — "
        "identity may not match other editions of this program"
        if residue
        else None
    )
