"""What Firecrawl actually returns, and what our current settings throw away.

No model calls — this is pure scraping and inspection, so it costs Firecrawl
credits only.

The question it exists to answer: our scrape uses
`formats=["markdown"], only_main_content=True`. That flag strips navigation,
headers and footers. If a page puts its name in a hero banner or header, we may
be deleting the title before extraction ever sees the page — which would look
identical to "the model failed to find a title".

So it fetches each page twice, the way we do it now and the way that keeps
everything, and reports whether the programme's name survives.

    uv run python scripts/diagnose_scrape.py
    uv run python scripts/diagnose_scrape.py <url> <url> ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

from opportunity_radar.config import require

# The three pages that failed extraction with "no title found on the page".
DEFAULT_URLS = [
    "https://sustainability-awards.me",
    "https://events.incarabia.com/bestinbusinessawards-riyadh",
    "https://ic-ce.com/icef2026-ace-awards-enterprise",
]

_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_STOPWORDS = {"the", "and", "for", "awards", "award", "2026", "2025"}


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        r = getattr(stream, "reconfigure", None)
        if r:
            r(encoding="utf-8", errors="replace")


def _significant_words(title: str) -> list[str]:
    """Distinctive words from the page title, for checking survival."""
    words = re.findall(r"[A-Za-z]{4,}", title.lower())
    return [w for w in words if w not in _STOPWORDS][:6]


def _survives(title: str, text: str) -> tuple[bool, list[str]]:
    """Does the page's own name appear in this rendering of the page?"""
    if not title or not text:
        return False, []
    lowered = text.lower()
    if title.lower() in lowered:
        return True, ["exact title"]
    words = _significant_words(title)
    found = [w for w in words if w in lowered]
    return (len(found) >= max(1, len(words) // 2)), found


def _json_ld(raw_html: str) -> list[dict]:
    blocks = []
    for match in _JSON_LD.finditer(raw_html or ""):
        try:
            parsed = json.loads(match.group(1).strip())
        except Exception:  # noqa: BLE001 — malformed JSON-LD is common
            continue
        blocks.extend(parsed if isinstance(parsed, list) else [parsed])
    return blocks


async def inspect(url: str) -> None:
    from firecrawl import Firecrawl

    client = Firecrawl(api_key=require("FIRECRAWL_API_KEY"))
    print(f"\n{'=' * 78}\n{url}\n{'=' * 78}")

    # A: exactly what the pipeline does today.
    try:
        a = await asyncio.to_thread(
            client.scrape, url, formats=["markdown"], only_main_content=True
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  SCRAPE A FAILED: {type(exc).__name__}: {exc}")
        return

    # B: everything, nothing stripped.
    try:
        b = await asyncio.to_thread(
            client.scrape, url,
            formats=["markdown", "html", "rawHtml", "links", "summary"],
            only_main_content=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  SCRAPE B FAILED: {type(exc).__name__}: {exc}")
        b = None

    md_a = getattr(a, "markdown", "") or ""
    md_b = getattr(b, "markdown", "") or "" if b else ""
    html_b = getattr(b, "html", "") or "" if b else ""
    raw_b = getattr(b, "raw_html", "") or "" if b else ""
    summary_b = getattr(b, "summary", "") or "" if b else ""

    print("\n-- sizes --")
    print(f"  A markdown (only_main_content=True) : {len(md_a):>8,} chars")
    print(f"  B markdown (only_main_content=False): {len(md_b):>8,} chars")
    print(f"  B html                              : {len(html_b):>8,} chars")
    print(f"  B rawHtml                           : {len(raw_b):>8,} chars")
    print(f"  B summary                           : {len(summary_b):>8,} chars")

    meta = getattr(a, "metadata", None)
    title = ""
    print("\n-- metadata (what we currently discard) --")
    if meta is None:
        print("  (none returned)")
    else:
        for field in ("title", "description", "og_title", "og_description",
                      "status_code", "url", "language"):
            value = getattr(meta, field, None)
            if value:
                shown = str(value)[:110]
                print(f"  {field:16}: {shown}")
                if field == "title":
                    title = str(value)

    print("\n-- THE QUESTION: does the page's own name survive each rendering? --")
    if not title:
        print("  no metadata title to test against")
    else:
        print(f"  testing for: {title!r}")
        for label, text in (
            ("A markdown (what extraction sees today)", md_a),
            ("B markdown (nothing stripped)", md_b),
            ("B rawHtml", raw_b),
        ):
            ok, hits = _survives(title, text)
            print(f"    {'YES' if ok else 'NO ':4} {label}"
                  + (f"   [{', '.join(hits)}]" if hits else ""))

    print("\n-- structured data (schema.org JSON-LD) --")
    blocks = _json_ld(raw_b)
    if not blocks:
        print("  none found")
    for block in blocks[:4]:
        kind = block.get("@type", "?")
        name = block.get("name") or block.get("headline") or ""
        print(f"  @type={kind}  name={str(name)[:70]!r}")
        for key in ("startDate", "endDate", "location", "organizer", "url"):
            if key in block:
                print(f"      {key}: {str(block[key])[:70]}")

    print("\n-- first 260 chars, A vs B --")
    print(f"  A: {md_a[:260].replace(chr(10), ' ')}")
    print(f"  B: {md_b[:260].replace(chr(10), ' ')}")


async def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", default=None)
    args = parser.parse_args()

    urls = args.urls or DEFAULT_URLS
    print(f"Inspecting {len(urls)} page(s). Two Firecrawl calls each, no model calls.")
    for url in urls:
        await inspect(url)

    print(f"\n{'=' * 78}")
    print("Read the 'does the name survive' block. If A says NO and B says YES,")
    print("only_main_content=True is deleting the title before extraction sees it,")
    print("and the missing-title failures are our scrape settings, not the model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
