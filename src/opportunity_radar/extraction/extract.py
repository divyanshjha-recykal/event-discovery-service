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
from datetime import date

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
  eligibility_criteria  array of conditions an applicant must satisfy. \
Return [] if the page states none.

    Each entry must be ONE complete, independently checkable condition, \
written so it still makes sense on its own with no surrounding context.

    Do not split a single sentence into fragments. "Any organization of any \
type or size, from any industry, in any country" is ONE condition, not three. \
A fragment like "From any industry" cannot be judged on its own.

    Keep alternatives together in one entry. "Open to individuals or \
institutions" is ONE condition — splitting it into "Individuals" and \
"Institutions" turns a choice into two requirements, and an applicant that is \
one but not the other then looks half-ineligible.

    Do not return a paragraph either. If a sentence genuinely states several \
separate requirements ("must be registered in India, and must have three \
years of operating history"), split it there.

    Only include conditions for ENTERING. A list of who attends, who speaks, \
or which job titles the audience holds is not eligibility.
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


def _as_text(value) -> str:
    """A model field as a clean string, whatever shape the model returned.

    Models do not always honour the schema: a string field can come back as a
    dict, a list, or a number. Coerce rather than assume, because assuming here
    is what raised a KeyError mid-run and killed a whole Discovery pass.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(v) for v in value).strip()
    if isinstance(value, dict):
        # A common shape is {"name": ...} or {"value": ...}; otherwise give up
        # cleanly rather than stringifying a whole dict into the record.
        for key in ("value", "name", "text", "title"):
            if key in value:
                return _as_text(value[key])
        return ""
    return ""


def _as_date_string(value) -> str | None:
    """An ISO date string, or None if the model returned something else."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        # {"start": ..., "end": ...} / {"date": ...} — take the operative one.
        for key in ("date", "deadline", "end", "start", "value"):
            if key in value and isinstance(value[key], str):
                return value[key].strip() or None
    return None


def _as_criteria(value) -> list[str]:
    """Eligibility criteria as a list of separate condition strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        return [_as_text(v) for v in value.values() if _as_text(v)]
    if isinstance(value, (list, tuple)):
        return [text for v in value if (text := _as_text(v))]
    return []


def extract(
    scraped_text: str,
    source_url: str,
    model: str | None = None,
) -> OpportunityRecord | ExtractionFailure:
    """Build one opportunity record from page text, or fail with a named reason.

    Guaranteed never to raise: the contract is a record or a typed failure, and
    an exception escaping here takes down the whole Discovery run around it.
    """
    try:
        return _extract(scraped_text, source_url, model)
    except Exception as exc:  # noqa: BLE001 — the contract is "never raises"
        return ExtractionFailure(
            FailureReason.MALFORMED_RESPONSE,
            f"unexpected {type(exc).__name__} during extraction: {exc}",
            source_url,
        )


def _extract(
    scraped_text: str,
    source_url: str,
    model: str | None = None,
) -> OpportunityRecord | ExtractionFailure:
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

    if not isinstance(payload, dict):
        return ExtractionFailure(
            FailureReason.MALFORMED_RESPONSE,
            f"model returned {type(payload).__name__}, expected a JSON object",
            source_url,
        )

    # Fields the model does not get the final word on.
    raw_title = _as_text(payload.get("title"))
    raw_base = _as_text(payload.get("base_title")) or raw_title
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

    # Models sometimes return a date as an object ({"start": ..., "end": ...}) or
    # a list. Anything that is not a plain string is not a date we can ground, so
    # it becomes None and the record is stored unverified rather than crashing.
    deadline = _as_date_string(payload.get("submission_deadline"))
    grounding = verify_deadline(deadline, scraped_text)

    try:
        record = OpportunityRecord(
            title=raw_title,
            organizing_body=str(payload.get("organizing_body") or "").strip(),
            base_title=base,
            cycle_year=payload.get("cycle_year"),
            category=payload.get("category"),
            eligibility_criteria=_as_criteria(payload.get("eligibility_criteria")),
            submission_deadline=deadline,
            deadline_note=_as_text(payload.get("deadline_note")) or None,
            deadline_verified=grounding.verified,
            event_date=_as_date_string(payload.get("event_date")),
            source_url=source_url,
        )
    except Exception as exc:  # pydantic ValidationError and friends
        return ExtractionFailure(
            FailureReason.MALFORMED_RESPONSE,
            f"record failed validation: {exc}",
            source_url,
        )

    return record


def record_warnings(record: OpportunityRecord, today: date | None = None) -> list[str]:
    """Quality warnings on a valid record. Warnings, never rejections.

    A record can be perfectly well-formed and still be a poor find: a past
    edition, or no deadline at all because a landing page was scraped instead of
    the call for entries. These need to be visible, but not blocked —
    a genuinely rolling programme legitimately has no fixed deadline, and a past
    edition is still worth storing, because the program registry needs edition
    history to compute `typical_window` and predict the next cycle.
    """
    today = today or date.today()
    warnings: list[str] = []

    if (edition := base_title_warning(record)) is not None:
        warnings.append(edition)

    if record.cycle_year < today.year:
        warnings.append(
            f"cycle_year {record.cycle_year} is before the current year "
            f"({today.year}) — past edition, useful for the program registry "
            "but not actionable"
        )

    if record.submission_deadline is None and not record.deadline_note:
        warnings.append(
            "no submission_deadline and no deadline_note — often a sign the "
            "landing page was scraped rather than the call for entries"
        )
    elif record.submission_deadline:
        try:
            if date.fromisoformat(record.submission_deadline) < today:
                warnings.append(
                    f"submission_deadline {record.submission_deadline} has "
                    "already passed — not actionable"
                )
        except ValueError:
            pass

    if record.submission_deadline and not record.deadline_verified:
        warnings.append(
            f"deadline {record.submission_deadline} could not be grounded in "
            "the source text — treat it as unconfirmed"
        )

    return warnings


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
