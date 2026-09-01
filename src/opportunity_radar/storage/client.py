"""Mongo connection and index setup.

PyMongo's native async client (`AsyncMongoClient`), not Motor — Motor is past
end of life, per CLAUDE.md's constraint.
"""

from __future__ import annotations

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from ..config import MongoConfig

OPPORTUNITIES = "opportunities"
PROGRAMS = "programs"


def get_client(config: MongoConfig | None = None) -> AsyncMongoClient:
    config = config or MongoConfig.from_env()
    return AsyncMongoClient(config.uri)


def get_database(
    client: AsyncMongoClient, config: MongoConfig | None = None
) -> AsyncDatabase:
    config = config or MongoConfig.from_env()
    return client[config.database]


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Create the unique identity indexes.

    "Never a duplicate" is enforced here rather than in application logic: a
    second insert on the same identity fails at the database, so a bug in the
    upsert path surfaces as an error instead of a silent duplicate row.
    """
    await db[OPPORTUNITIES].create_index(
        [("norm_organizing_body", 1), ("norm_base_title", 1), ("cycle_year", 1)],
        unique=True,
        name="opportunity_identity",
    )
    await db[PROGRAMS].create_index(
        [("norm_organizing_body", 1), ("norm_base_title", 1)],
        unique=True,
        name="program_identity",
    )
    # Stage 5's collections. Imported here rather than at module scope to keep
    # client.py free of cycles.
    from .failures import ensure_failure_indexes
    from .runs import ensure_run_indexes

    await ensure_failure_indexes(db)
    await ensure_run_indexes(db)
