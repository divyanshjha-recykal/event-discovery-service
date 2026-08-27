"""Langfuse tracing and the OpenRouter chat model.

Every LLM call in this project goes through `chat_model()` and carries the
callback handler from `trace_handler()`. That is a stated constraint, in force
from Stage 0: an untraced call is a bug, not an optimisation.

The same handler is what a LangGraph run takes in its config, so the Discovery
and Eligibility Agents trace through this module too when they arrive.
"""

from __future__ import annotations

import os

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
