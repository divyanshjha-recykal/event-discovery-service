"""`save_opportunity()` — atomic upsert on the opportunity identity."""

from __future__ import annotations

from dataclasses import dataclass

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from .client import OPPORTUNITIES
from .identity import opportunity_identity
from .programs import record_edition

REQUIRED_FIELDS = ("title", "organizing_body", "base_title", "cycle_year", "source_url")


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
        )

    return SaveResult(document=document, inserted=inserted)
