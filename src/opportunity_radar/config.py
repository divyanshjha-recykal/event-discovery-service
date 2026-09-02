"""Environment configuration.

Everything the pipeline needs from the outside world is named here, read from
`.env` (or the real environment, which wins). Nothing has a hardcoded fallback
that would let a run silently proceed against the wrong model or an untraced
endpoint — `require()` raises instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .paths import REPO_ROOT

load_dotenv(REPO_ROOT / ".env")


class MissingConfig(RuntimeError):
    """A required environment variable is unset or empty."""


def require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingConfig(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


def optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    base_url: str

    @classmethod
    def from_env(cls, model: str | None = None) -> "OpenRouterConfig":
        """`model` overrides OPENROUTER_MODEL — for comparing models in one run.

        The model is never defaulted in code; it comes from the environment or
        from an explicit argument, per the CLAUDE.md constraint.
        """
        return cls(
            api_key=require("OPENROUTER_API_KEY"),
            model=(model.strip() if model else require("OPENROUTER_MODEL")),
            base_url=optional("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )


def discovery_temperature() -> float | None:
    """Sampling temperature for the Discovery Agent only.

    Deliberately not applied to extraction or eligibility. Those must be
    reproducible: eligibility is checked against fixed reference sets, and a
    verdict that drifts between runs cannot be trusted or compared. Discovery is
    the only stage where more exploration is arguably useful.

    Unset means "use the provider default" rather than forcing 0, so this
    changes nothing until it is set.
    """
    raw = optional("OPENROUTER_TEMPERATURE")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return min(max(value, 0.0), 2.0)


@dataclass(frozen=True)
class LangfuseConfig:
    public_key: str
    secret_key: str
    host: str

    @classmethod
    def from_env(cls) -> "LangfuseConfig":
        return cls(
            public_key=require("LANGFUSE_PUBLIC_KEY"),
            secret_key=require("LANGFUSE_SECRET_KEY"),
            host=optional("LANGFUSE_HOST", "http://localhost:3000"),
        )


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    database: str

    @classmethod
    def from_env(cls) -> "MongoConfig":
        return cls(
            uri=require("MONGO_URI"),
            database=optional("MONGO_DB_NAME", "opportunity_radar"),
        )
