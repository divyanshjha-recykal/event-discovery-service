"""Program registry — plain functions over the `programs` collection only.

Never touches `opportunities`. A program is a recurring award/grant/event
identified by `organizing_body + base_title`; each year it runs is an edition.
"""

from __future__ import annotations

from datetime import date

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from .client import PROGRAMS
from .identity import program_identity


def _month_of(deadline: str | None) -> int | None:
    """Month from an ISO date string, or None if absent/unparseable."""
    if not deadline:
        return None
    try:
        return date.fromisoformat(deadline[:10]).month
    except ValueError:
        return None


def compute_typical_window(editions: list[dict]) -> dict[str, int | str] | None:
    """Smallest month range covering the editions' dates.

    Three dates are kept distinct and never conflated:
      cycle year  the year the edition runs
      deadline    when applications close
      event_date  when the event itself happens

    The window prefers deadlines, because that is when a person must act. It
    falls back to event dates when no deadline was ever published, and records
    which was used in `source` so the estimate is never mistaken for a deadline.

    None until two editions carry a usable date. The range is computed on a
    12-month circle, so a program running Nov-Jan yields {11, 1} rather than the
    nonsensical {1, 11} a naive min/max gives.
    """
    # Count editions, not distinct months: two editions both falling in August
    # is a real, useful window (August), not insufficient data.
    source = "deadline"
    dated = [m for e in editions if (m := _month_of(e.get("deadline")))]
    if len(dated) < 2:
        from_events = [m for e in editions if (m := _month_of(e.get("event_date")))]
        if len(from_events) < 2:
            return None
        dated, source = from_events, "event_date"
    months = sorted(set(dated))

    # Try each month as the start; keep the wrap-around arc that spans least.
    best_start, best_span = months[0], 12
    for start in months:
        span = max((m - start) % 12 for m in months)
        if span < best_span:
            best_start, best_span = start, span

    return {
        "month_start": best_start,
        "month_end": (best_start + best_span - 1) % 12 + 1,
        "source": source,
    }


async def record_edition(
    db: AsyncDatabase,
    organizing_body: str,
    base_title: str,
    year: int,
    deadline: str | None,
    event_date: str | None = None,
) -> dict:
    """Append an edition to its program, creating the program if new.

    Records both dates, separately. An edition with only an event date is still
    worth recording: the caller used to skip those entirely, so a programme
    whose page published a date but no deadline taught the registry nothing.

    Idempotent on `year`: recording the same year twice updates that edition
    rather than appending a duplicate. Recomputes `typical_window` after every
    change.
    """
    identity = program_identity(organizing_body, base_title)

    program = await db[PROGRAMS].find_one_and_update(
        identity,
        {
            "$setOnInsert": {
                **identity,
                "organizing_body": organizing_body,
                "base_title": base_title,
                "editions": [],
                "typical_window": None,
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    editions = [e for e in program.get("editions", []) if e.get("year") != year]
    editions.append({"year": year, "deadline": deadline, "event_date": event_date})
    editions.sort(key=lambda e: e["year"])

    return await db[PROGRAMS].find_one_and_update(
        identity,
        {"$set": {"editions": editions, "typical_window": compute_typical_window(editions)}},
        return_document=ReturnDocument.AFTER,
    )


async def known_orgs(db: AsyncDatabase) -> list[str]:
    """Distinct organizing bodies already in the registry, as originally written."""
    return sorted(await db[PROGRAMS].distinct("organizing_body"))


async def due_soon(db: AsyncDatabase, lookahead_months: int = 1) -> list[dict]:
    """Programs whose `typical_window` is active now or opens within the lookahead.

    A null `typical_window` (fewer than two recorded editions) never qualifies —
    there isn't enough history to predict anything, and guessing would send the
    Discovery Agent chasing programs on no evidence.
    """
    if lookahead_months < 0:
        raise ValueError("lookahead_months cannot be negative")

    this_month = date.today().month
    # Months we care about: now, plus the next `lookahead_months`.
    horizon = {(this_month - 1 + offset) % 12 + 1 for offset in range(lookahead_months + 1)}

    matches = []
    async for program in db[PROGRAMS].find({"typical_window": {"$ne": None}}):
        window = program["typical_window"]
        start, end = window["month_start"], window["month_end"]
        span = (end - start) % 12
        active = {(start - 1 + offset) % 12 + 1 for offset in range(span + 1)}
        if active & horizon:
            matches.append(program)

    return sorted(matches, key=lambda p: (p["typical_window"]["month_start"], p["base_title"]))


async def known_programs(db: AsyncDatabase) -> list[dict]:
    """Every programme already recorded, as `organizing_body` + `base_title`.

    Handed to Analyze so it can reuse a name it has already used. The identity
    key is built from these two strings, so "A' Design Award", "A' Design Award
    & Competition" and "A' Design Award & Competition SRL" become three separate
    programmes — all true, all different, one award. Naming is a judgement, and
    the model making it can see what it called the thing last time.
    """
    cursor = db[PROGRAMS].find(
        {}, {"_id": 0, "organizing_body": 1, "base_title": 1}
    ).sort("organizing_body", 1)
    return [doc async for doc in cursor]
