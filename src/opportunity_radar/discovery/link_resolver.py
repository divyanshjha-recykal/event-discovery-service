"""Bounded same-domain traversal. Which links to follow is the model's call."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import replace
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlsplit,
    urlunsplit,
)

from .providers import tool_firecrawl_fetch
from .state import EvidenceBundle, EvidencePage, SearchHit, WorkflowRuntime

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")

# What extraction actually reads per page, so the preview stored on the journey
# is the evidence the model saw rather than an arbitrary slice of it.
SCRAPE_PREVIEW_CHARS = 20_000

# Firecrawl cannot read raster images and errors on them, so following one is a
# paid call that can only fail. PDFs are deliberately absent from this list —
# award guidelines and entry terms are very often PDFs and Firecrawl does read
# those.
_BINARY_SUFFIXES = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".tiff", ".svg",
    ".ico", ".mp4", ".webm", ".mov", ".avi", ".mp3", ".wav", ".zip", ".gz",
    ".rar", ".7z", ".exe", ".dmg", ".woff", ".woff2", ".ttf", ".eot", ".css",
    ".js", ".json", ".xml", ".rss",
)


def _is_binary(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return path.endswith(_BINARY_SUFFIXES)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.").lower()


def _same_site(left: str, right: str) -> bool:
    left_host, right_host = _host(left), _host(right)
    return (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


def canonicalize_url(url: str) -> str:
    """Normalize harmless URL variants before ranking, traversal and dedup."""
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    port = parsed.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
        )
    )
    scheme = "https" if parsed.scheme in {"http", "https"} else parsed.scheme
    return urlunsplit((scheme, netloc, path, query, ""))


_URL = re.compile(r"https?://\S+")
#: A seed page shorter than this is too thin to call a duplicate.
SEED_KEY_CHARS = 500


def content_key(text: str, min_chars: int) -> str:
    """Text two copies of one page share, URLs removed; empty if too short to tell."""
    key = " ".join(_URL.sub("", text or "").split()).casefold()
    return key if len(key) >= min_chars else ""


def _candidate_links(page: EvidencePage, seed_url: str) -> list[tuple[str, str]]:
    """Same-site, non-binary links as (url, label), in page order.

    No scoring: which link is worth following is a judgement and the model makes
    it. This only removes what cannot be fetched.
    """
    labelled: dict[str, str] = {url: url for url in page.links}
    for label, url in _MARKDOWN_LINK.findall(page.markdown):
        labelled[url] = label
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url, label in labelled.items():
        absolute = canonicalize_url(urljoin(page.url, url))
        if absolute in seen or _is_binary(absolute):
            continue
        if not absolute.startswith("https://") or not _same_site(absolute, seed_url):
            continue
        seen.add(absolute)
        out.append((absolute, label.strip()[:120]))
    return out


def _low_quality(page: EvidencePage) -> bool:
    if page.status_code is not None and not (200 <= page.status_code < 300):
        return True
    if len(page.markdown.strip()) < 500:
        return True
    identity = bool(page.title or re.search(r"(?m)^#\s+\S", page.markdown))
    return not identity


async def resolve_evidence_bundle(
    hit: SearchHit,
    runtime: WorkflowRuntime,
    record_event: Callable[..., Awaitable[None]],
    *,
    max_depth: int | None = None,
    max_pages: int | None = None,
    reserve_calls: int = 3,
    choose_links: Callable[..., Awaitable[list[str]]] | None = None,
) -> EvidenceBundle:
    """Fetch a seed and the same-domain links the model picks, within hard caps.

    When `choose_links` is absent or fails we follow nothing rather than guess.
    """
    limits = runtime.limits
    max_depth = limits.max_depth if max_depth is None else max_depth
    max_pages = limits.max_pages_per_seed if max_pages is None else max_pages

    pages: list[EvidencePage] = []
    seen: set[str] = set()
    unfollowed: set[str] = set()
    seed_url = canonicalize_url(hit.url)
    queue: deque[tuple[str, int]] = deque([(seed_url, 0)])

    while queue and len(pages) < max_pages:
        if runtime.budget.remaining <= reserve_calls:
            break
        url, depth = queue.popleft()
        url = canonicalize_url(url)
        if url in seen or depth > max_depth:
            continue
        seen.add(url)
        refusal = runtime.budget.refusal("scrape")
        if refusal:
            break
        runtime.budget.consume("scrape")
        try:
            page = await tool_firecrawl_fetch(
                url, depth=depth, dry_run=runtime.dry_run
            )
            page = replace(page, url=canonicalize_url(page.url))
        except Exception as exc:  # noqa: BLE001
            await record_event(
                "scrape",
                node="fetch",
                url=url,
                depth=depth,
                outcome="failed", source="firecrawl",
                detail=f"{type(exc).__name__}: {exc}"[:1500],
            )
            continue

        # A successful Firecrawl request can still wrap a target 404 or return
        # mostly chrome. Retry once with the full rendered page when affordable.
        if (
            _low_quality(page)
            and runtime.budget.remaining > reserve_calls
            and runtime.budget.refusal("scrape") is None
        ):
            try:
                runtime.budget.consume("scrape")
                fallback = await tool_firecrawl_fetch(
                    url,
                    depth=depth,
                    dry_run=runtime.dry_run,
                    only_main_content=False,
                    wait_for=1_500,
                )
                if len(fallback.markdown) > len(page.markdown):
                    page = replace(fallback, url=canonicalize_url(fallback.url))
            except Exception:  # noqa: BLE001
                pass

        pages.append(page)
        await record_event(
            "scrape",
            node="fetch",
            url=page.url,
            depth=depth,
            outcome="ok",
            chars=len(page.markdown),
            status_code=page.status_code,
            bare_domain=urlparse(page.url).path in ("", "/"),
            page_title=page.title,
            page_description=page.description,
            links_found=len(page.links),
            # The fetched text itself, so what the model read is inspectable
            # rather than only its character count.
            preview=page.markdown[:SCRAPE_PREVIEW_CHARS],
            truncated=len(page.markdown) > SCRAPE_PREVIEW_CHARS,
        )
        if depth == 0:
            key = content_key(page.markdown, SEED_KEY_CHARS)
            twin = runtime.seen_pages.get(key) if key else None
            if twin and twin != page.url:
                await record_event(
                    "dedupe", node="fetch", url=page.url, outcome="dropped",
                    title=page.title, duplicate_of=twin,
                )
                return EvidenceBundle(seed_url=seed_url, pages=(), duplicate_of=twin)
            if key:
                runtime.seen_pages[key] = page.url
        if depth >= max_depth:
            continue
        candidates = [
            item for item in _candidate_links(page, seed_url) if item[0] not in seen
        ]
        if not candidates or choose_links is None:
            continue

        # Link choice runs at every depth below max_depth. A `depth > 0` guard
        # here used to stop it after the seed, which made max_depth dead: real
        # depth was always 1 whatever it was set to.
        # If the model cannot choose, follow nothing — the pages already fetched
        # beat a keyword guess at which link matters.
        followed: list[str] = []
        try:
            followed = await choose_links(page, candidates[:40])
        except Exception as exc:  # noqa: BLE001
            await record_event(
                "select_links", node="fetch", url=page.url,
                outcome="failed", detail=f"{type(exc).__name__}: {exc}"[:1000],
            )
        followed = followed[: max_pages - len(pages)]
        unfollowed.update(url for url, _ in candidates if url not in followed)

        for link in followed:
            if link not in seen:
                queue.append((link, depth + 1))

    return EvidenceBundle(
        seed_url=seed_url,
        pages=tuple(pages),
        unfollowed=tuple(url for url in unfollowed if url not in seen),
    )
