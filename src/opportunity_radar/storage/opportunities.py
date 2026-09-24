"""`save_opportunity()` — atomic upsert on the opportunity identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from .client import OPPORTUNITIES
from .identity import normalize, opportunity_identity
from .programs import record_edition

REQUIRED_FIELDS = ("title", "organizing_body", "base_title", "cycle_year", "source_url")

#: Normalised form of the placeholder stored when a page never names an
#: organiser. Kept out of the identity key so it cannot split a programme.
_UNKNOWN_BODY_KEY = "not stated"


@dataclass(frozen=True)
class SaveResult:
    document: dict
    inserted: bool  # True on a genuinely new identity, False on an update

    @property
    def action(self) -> str:
        return "inserted" if self.inserted else "updated"


async def save_opportunity(db: AsyncDatabase, record: dict) -> SaveResult:
    """Insert or update one opportunity, keyed on organizing_body+base_title+cycle_year.

    A new identity also records an edition against its program. That wiring lives
    here rather than at the call site so the registry cannot drift out of sync
    with what has actually been stored.
    """
    missing = [f for f in REQUIRED_FIELDS if record.get(f) in (None, "")]
    if missing:
        raise ValueError(f"record is missing required field(s): {', '.join(missing)}")

    identity = opportunity_identity(
        record["organizing_body"], record["base_title"], record["cycle_year"]
    )
    payload = {k: v for k, v in record.items() if k not in identity}

    before = await db[OPPORTUNITIES].find_one(identity, {"_id": 1})
    if before is None:
        # The same programme read once with an organiser and once without is one
        # programme. Without this, "not stated" mints its own identity and the
        # two are stored side by side — seen on the A' Design award, once with
        # five conditions and a deadline, once with neither.
        known = normalize(record["organizing_body"]) != _UNKNOWN_BODY_KEY
        lookup = {
            "norm_base_title": identity["norm_base_title"],
            "cycle_year": identity["cycle_year"],
        }
        # A named record adopts the placeholder. An unnamed one joins whatever
        # record already exists for this programme, whoever it names.
        if known:
            lookup["norm_organizing_body"] = _UNKNOWN_BODY_KEY
        twin = await db[OPPORTUNITIES].find_one(
            lookup, {"_id": 1, "norm_organizing_body": 1}
        )
        if twin is not None:
            if known:
                await db[OPPORTUNITIES].update_one(
                    {"_id": twin["_id"]}, {"$set": identity}
                )
            else:
                identity = {
                    **lookup,
                    "norm_organizing_body": twin["norm_organizing_body"],
                }
                payload.pop("organizing_body", None)
            before = {"_id": twin["_id"]}
    document = await db[OPPORTUNITIES].find_one_and_update(
        identity,
        {"$set": payload, "$setOnInsert": identity},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    inserted = before is None

    if inserted:
        await record_edition(
            db,
            organizing_body=record["organizing_body"],
            base_title=record["base_title"],
            year=record["cycle_year"],
            deadline=record.get("submission_deadline"),
            event_date=record.get("event_date"),
        )

    return SaveResult(document=document, inserted=inserted)


async def attach_eligibility(
    db: AsyncDatabase,
    result: dict,
    *,
    organizing_body: str,
    base_title: str,
    cycle_year: int,
) -> dict | None:
    """Store an eligibility verdict on its opportunity record.

    Keyed on the identity, not on `source_url`. One page routinely carries
    several programmes — three records once shared a single awards page — and
    `find_one_and_update` on a non-unique key updates exactly one of them. The
    verdict landed on whichever matched first, so two records showed "no entry
    conditions" while holding four each, and the third was given a verdict
    computed from someone else's conditions.
    """
    identity = opportunity_identity(organizing_body, base_title, cycle_year)
    return await db[OPPORTUNITIES].find_one_and_update(
        identity,
        {"$set": {"eligibility": result, "eligibility_evaluated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
