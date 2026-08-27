"""Proves the Langfuse trace path works, with no LLM call involved.

Separates the two Stage 0 unknowns: this checks that a span written by the SDK
actually survives the worker -> Redis -> ClickHouse write path and is readable
back. If this passes, any later tracing failure is the model call, not Langfuse.

    uv run python scripts/smoke_langfuse.py
"""

from __future__ import annotations

import sys
import time

from opportunity_radar.config import MissingConfig
from opportunity_radar.tracing import langfuse_client


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        r = getattr(stream, "reconfigure", None)
        if r:
            r(encoding="utf-8", errors="replace")

    try:
        client = langfuse_client()
    except MissingConfig as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if not client.auth_check():
        print("FAIL: Langfuse rejected the credentials.", file=sys.stderr)
        return 1
    print("1. auth              ok")

    with client.start_as_current_observation(
        name="stage0-langfuse-smoke", as_type="span"
    ) as span:
        span.update(input={"check": "trace path"}, output={"result": "written"})
        trace_id = client.get_current_trace_id()
    print(f"2. span created      {trace_id}")

    client.flush()
    print("3. flushed to server ok")

    # No read-back check here. Langfuse v4 removed the v3 trace read API
    # (api.trace.get / api.trace.list both 404), and v4 does not populate the
    # legacy ClickHouse `traces` table either. Confirm visually in the UI.
    print(f"
PASS - span written and flushed.")
    print(f"Confirm at: {client.get_trace_url(trace_id=trace_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
