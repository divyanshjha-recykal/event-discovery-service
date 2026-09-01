"""Langfuse tracing and the OpenRouter chat model.

Every LLM call in this project goes through `chat_model()` and carries the
callback handler from `trace_handler()`. That is a stated constraint, in force
from Stage 0: an untraced call is a bug, not an optimisation.

The same handler is what a LangGraph run takes in its config, so the Discovery
and Eligibility Agents trace through this module too when they arrive.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from langchain_openai import ChatOpenAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from .config import LangfuseConfig, OpenRouterConfig


def langfuse_client(config: LangfuseConfig | None = None):
    """The configured Langfuse client. Reads credentials from the environment."""
    config = config or LangfuseConfig.from_env()
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", config.public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", config.secret_key)
    os.environ.setdefault("LANGFUSE_HOST", config.host)
    return get_client()


def trace_handler(config: LangfuseConfig | None = None) -> CallbackHandler:
    """Callback handler to pass as `config={"callbacks": [...]}` on every call."""
    langfuse_client(config)
    return CallbackHandler()


@contextmanager
def stage_span(name: str, **metadata):
    """A named span for one pipeline step, with its decisions attached.

    LangChain's own spans are called `model`, `tools`, `ChatOpenAI` and
    `LangGraph` — correctly nested, but you cannot tell which tool call is which
    without opening every one, and no decision is visible from the outside.
    This wraps each step in a span named for the stage and the thing it acted
    on, and hangs the outcome on it: budget remaining, typed failure reason,
    whether the deadline grounded, the confidence verdict.

    Yields the span so a caller can attach an outcome once it knows it. Never
    raises on a tracing problem — an untraced step is a lost detail, a crashed
    run is a lost run.
    """
    client = langfuse_client()
    try:
        with client.start_as_current_observation(name=name, as_type="span") as span:
            if metadata:
                span.update(metadata={k: v for k, v in metadata.items() if v is not None})
            yield span
    except Exception:  # noqa: BLE001 — tracing must not break the pipeline
        yield _NullSpan()


class _NullSpan:
    """Stand-in when tracing is unavailable, so callers need no special case."""

    def update(self, *args, **kwargs) -> None:
        return None


def chat_model(model: str | None = None, **kwargs) -> ChatOpenAI:
    """An OpenRouter-backed chat model.

    `model` overrides OPENROUTER_MODEL for a single call — that is how Stage 2
    and Stage 3 compare two model values in one run. There is no default model
    in code.
    """
    openrouter = OpenRouterConfig.from_env(model)
    return ChatOpenAI(
        model=openrouter.model,
        api_key=openrouter.api_key,
        base_url=openrouter.base_url,
        **kwargs,
    )
