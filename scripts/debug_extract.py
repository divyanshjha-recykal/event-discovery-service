"""Scrape one page and show exactly what extraction does with it.

For diagnosing extraction failures where the page clearly has content but
extract() reports otherwise. Prints the raw model reply before any parsing, so
the difference between "model returned nothing useful", "reply was truncated"
and "our parsing dropped it" is visible.

    uv run python scripts/debug_extract.py https://sustainability-awards.me
    uv run python scripts/debug_extract.py <url> --model qwen/qwen3-32b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from langchain_core.messages import HumanMessage, SystemMessage

from opportunity_radar.config import require
from opportunity_radar.extraction import ExtractionFailure, extract
from opportunity_radar.extraction.extract import MAX_OUTPUT_TOKENS


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        r = getattr(stream, "reconfigure", None)
        if r:
            r(encoding="utf-8", errors="replace")


async def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--model", default="google/gemma-4-31b-it",
                        help="OpenRouter slug. Defaults to gemma so this works "
                             "with OPENROUTER_MODEL unset.")
    parser.add_argument("--chars", type=int, default=12000,
                        help="Truncate the page as the discovery tool does (default 12000).")
    args = parser.parse_args()

    from firecrawl import Firecrawl

    print(f"scraping {args.url} …")
    client = Firecrawl(api_key=require("FIRECRAWL_API_KEY"))
    doc = await asyncio.to_thread(
        client.scrape, args.url, formats=["markdown"], only_main_content=True
    )
    text = getattr(doc, "markdown", None) or getattr(doc, "content", "") or ""
    meta = getattr(doc, "metadata", None)
    page_title = ((getattr(meta, "title", None) or getattr(meta, "og_title", None) or "").strip()
                  if meta else "")
    print(f"  scraped {len(text)} chars")
    print(f"  browser <title>: {page_title!r}")

    truncated = text[: args.chars]
    print(f"  handing {len(truncated)} chars to extract() "
          f"({'TRUNCATED' if len(text) > args.chars else 'whole page'})")
    print(f"  max output tokens: {MAX_OUTPUT_TOKENS}")

    print("\n--- first 400 chars of what the model will see ---")
    print(truncated[:400].replace("\n", " ")[:400])

    # The raw reply, before any of our parsing touches it.
    from opportunity_radar.extraction.extract import SYSTEM_PROMPT, _user_prompt
    from opportunity_radar.tracing import chat_model, trace_handler

    llm = chat_model(args.model, max_tokens=MAX_OUTPUT_TOKENS, timeout=120, max_retries=3)
    print("\n--- raw model reply ---")
    response = llm.invoke(
        [SystemMessage(SYSTEM_PROMPT), HumanMessage(_user_prompt(truncated, args.url, page_title))],
        config={"callbacks": [trace_handler()]},
        response_format={"type": "json_object"},
    )
    raw = response.content
    print(f"  {len(raw)} chars returned")
    print(f"  finish_reason: {response.response_metadata.get('finish_reason')}")
    print(raw[:1500])
    if len(raw) > 1500:
        print(f"  … {len(raw) - 1500} more chars")

    print("\n--- parsed ---")
    try:
        payload = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        print(f"  keys: {sorted(payload)}")
        print(f"  title repr : {payload.get('title')!r}")
        print(f"  status     : {payload.get('status')!r}")
        print(f"  criteria   : {len(payload.get('eligibility_criteria') or [])}")
    except Exception as exc:  # noqa: BLE001
        print(f"  JSON PARSE FAILED: {type(exc).__name__}: {exc}")

    print("\n--- what extract() returns ---")
    result = extract(truncated, args.url, args.model, page_title)
    if isinstance(result, ExtractionFailure):
        print(f"  FAILURE {result.reason.value}: {result.detail[:300]}")
    else:
        print(f"  OK: {result.title}")
        print(f"      deadline {result.submission_deadline} verified={result.deadline_verified}")
        print(f"      {len(result.eligibility_criteria)} criteria")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
