"""Stage 0 acceptance check: a real OpenRouter call, traced in Langfuse.

Sends one call per model given, so two OPENROUTER_MODEL values can be proved to
both trace in a single run. With no --model, uses OPENROUTER_MODEL from .env.

    uv run python scripts/smoke_openrouter.py --model <slug> --model <other-slug>

Prints the Langfuse trace URL for each call; open them to confirm.
"""

from __future__ import annotations

import argparse
import sys

from opportunity_radar.config import MissingConfig
from opportunity_radar.tracing import chat_model, langfuse_client, trace_handler

PROMPT = (
    "Reply with exactly one word: the name of the city where Recykal is headquartered."
)


def _force_utf8_stdout() -> None:
    """The profile contains characters (e.g. Rs sign) that cp1252 cannot encode.

    On a Windows console, printing it raises UnicodeEncodeError unless the
    stream is switched to UTF-8 first.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="OpenRouter model slug. Repeat to test more than one. "
        "Defaults to OPENROUTER_MODEL.",
    )
    args = parser.parse_args()
    models: list[str | None] = args.models or [None]

    try:
        client = langfuse_client()
        handler = trace_handler()
    except MissingConfig as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if not client.auth_check():
        print(
            "FAIL: Langfuse rejected the credentials. Check LANGFUSE_PUBLIC_KEY / "
            "LANGFUSE_SECRET_KEY / LANGFUSE_HOST and that the stack is up.",
            file=sys.stderr,
        )
        return 1
    print("Langfuse auth: ok")

    failures = 0
    for model in models:
        try:
            # max_tokens matters: OpenRouter reserves credit against the
            # requested ceiling, not actual usage. Unset, LangChain asks for the
            # model's full output window (65k here) and a small balance gets a
            # 402 before a single token is generated. This prompt wants one word.
            llm = chat_model(model, max_tokens=32, timeout=60, max_retries=5)
        except MissingConfig as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

        label = llm.model_name
        try:
            # Langfuse SDK v4: start_as_current_observation, not the v3
            # start_as_current_span. The CallbackHandler nests the LLM call
            # underneath this span, so one trace per model.
            with client.start_as_current_observation(
                name=f"stage0-smoke:{label}", as_type="span"
            ):
                response = llm.invoke(PROMPT, config={"callbacks": [handler]})
                trace_id = client.get_current_trace_id()
            trace_url = client.get_trace_url(trace_id=trace_id) or "(no url)"
        except Exception as exc:  # noqa: BLE001 - smoke test reports, does not handle
            print(f"FAIL {label}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            continue

        print(f"OK   {label}: {response.content.strip()!r}")
        print(f"     trace: {trace_url}")

    client.flush()
    if failures:
        print(f"\n{failures} of {len(models)} model(s) failed.", file=sys.stderr)
        return 1

    print(f"\n{len(models)} model(s) called and flushed to Langfuse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
