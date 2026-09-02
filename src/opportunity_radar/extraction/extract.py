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

from ..tracing import chat_model, stage_span, trace_handler
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
  title                 the opportunity's own name, including the year if \
present. Where the page body has no readable title — some sites render their \
name only as a logo image — the browser page title and meta description are \
given to you as evidence. Use them ONLY when they genuinely name the \
opportunity. A navigation label ("Home"), a CMS default ("Untitled Document"), \
or the name of the site rather than the award is not a title: return null and \
let the record be rejected. A wrongly-named record is worse than no record, \
because the name is what identifies it later.
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


def _user_prompt(
    scraped_text: str,
    source_url: str,
    page_title: str | None = None,
    page_description: str | None = None,
) -> str:
    """Everything the page says about itself, not just its markdown body.

    Some sites render their name only as a logo image, so the markdown has no
    readable title and a model asked to name the opportunity correctly finds
    nothing. That information was never missing — it is in the page metadata,
    which an earlier version of this code discarded.

    Supplying it as evidence is the fix. A downstream fallback that substitutes
    the raw <title> is not: "Home" would then become the record's name, and the
    name feeds `base_title`, which is part of the identity key.
    """
    header = f"Source URL: {source_url}"
    if page_title:
        header += f"\nBrowser page title: {page_title}"
    if page_description:
        header += f"\nMeta description: {page_description}"
    return f"{header}\n\nPage text:\n\n{scraped_text}"


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
    page_title: str | None = None,
    page_description: str | None = None,
) -> OpportunityRecord | ExtractionFailure:
    """Build one opportunity record from page text, or fail with a named reason.

    Guaranteed never to raise: the contract is a record or a typed failure, and
    an exception escaping here takes down the whole Discovery run around it.
    """
    from urllib.parse import urlparse

    host = urlparse(source_url).netloc or source_url
    with stage_span(
        f"stage2.extract: {host}", source_url=source_url, model=model,
        page_chars=len(scraped_text or ""),
    ) as span:
        try:
            result = _extract(scraped_text, source_url, model, page_title, page_description)
        except Exception as exc:  # noqa: BLE001 — the contract is "never raises"
            result = ExtractionFailure(
                FailureReason.MALFORMED_RESPONSE,
                f"unexpected {type(exc).__name__} during extraction: {exc}",
                source_url,
            )

        # The outcome on the span, so a trace shows what extraction decided
        # without anyone opening the payload.
        if isinstance(result, ExtractionFailure):
            span.update(metadata={"outcome": "failed", "reason": result.reason.value,
                                  "detail": result.detail[:200]})
        else:
            span.update(metadata={
                "outcome": "ok",
                "title": result.title,
                "cycle_year": result.cycle_year,
                "category": result.category,
                "submission_deadline": result.submission_deadline,
                "deadline_verified": result.deadline_verified,
                "criteria_count": len(result.eligibility_criteria),
            })
        return result


def _extract(
    scraped_text: str,
    source_url: str,
    model: str | None = None,
    page_title: str | None = None,
    page_description: str | None = None,
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
        HumanMessage(_user_prompt(scraped_text, source_url, page_title, page_description)),
    ]

    payload: dict | None = None
    last_error = ""

    # JSON mode, one retry. The retry feeds the error back rather than simply
    # asking again, so the second attempt has something to correct.
    #
    # The retry covers schema validation as well as JSON parsing. A model that
    # emits cycle_year: -1 once will very likely emit 2026 when told what was
    # wrong — an earlier version only retried parse errors, so that record was
    # lost outright after the scrape had already been paid for.
    for attempt in (1, 2):
        try:
            response = llm.invoke(
                messages,
                config={"callbacks": [handler]},
                response_format={"type": "json_object"},
            )
            payload = _parse_json(response.content)
        except json.JSONDecodeError as exc:
            last_error = f"model did not return valid JSON: {exc}"
            payload = None
        except Exception as exc:  # noqa: BLE001 — reported, not handled
            last_error = f"{type(exc).__name__}: {exc}"
            payload = None

        if payload is not None:
            outcome = _build_record(payload, scraped_text, source_url, page_title)
            # Only a malformed reply is worth a second attempt. A closed page
            # and a page with nothing on it are settled answers, not mistakes.
            if (
                not isinstance(outcome, ExtractionFailure)
                or outcome.reason is not FailureReason.MALFORMED_RESPONSE
                or attempt == 2
            ):
                return outcome
            last_error = outcome.detail

        if attempt == 1:
            messages.append(
                HumanMessage(
                    f"That response could not be used ({last_error}). "
                    "Correct exactly that problem and reply again with only the "
                    "JSON object described above."
                )
            )

    return ExtractionFailure(
        FailureReason.MALFORMED_RESPONSE,
        f"no usable response after one retry — {last_error}",
        source_url,
    )


def _build_record(
    payload: dict, scraped_text: str, source_url: str, page_title: str | None = None
) -> OpportunityRecord | ExtractionFailure:
    """Turn a parsed model reply into a record, or say why it cannot be one."""
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
        # No fallback here on purpose. The model was given the page text, the
        # URL, the browser title and the meta description. If it still cannot
        # name the opportunity, that is a judgement, and substituting a raw
        # <title> would put "Home" or "Untitled Document" into base_title —
        # which is part of the identity key, so a wrong name breaks dedup
        # silently rather than merely reading badly.
        return ExtractionFailure(
            FailureReason.INSUFFICIENT_CONTENT,
            "the page does not name an identifiable opportunity",
            source_url,
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
