"""Site-agnostic candidate ranking and bounded same-domain traversal."""

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

from .providers import firecrawl_fetch
from .state import EvidenceBundle, EvidencePage, SearchHit, WorkflowRuntime

_POSITIVE = re.compile(
    r"\b(apply|application|nominate|nomination|enter|entry|eligible|criteria|"
    r"categor|guideline|timeline|deadline|register|award|grant|brochure|terms)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\b(winner|result|recap|gallery|privacy|cookie|login|sign[-_ ]?in|"
    r"sponsor|contact|press[-_ ]?release|news|speaker|create[-_ ]?account|"
    r"submit[-_ ]?(?:an[-_ ])?event|add[-_ ]?event)\b",
    re.IGNORECASE,
)
_DIRECTORY = re.compile(
    r"\b(list of|directory|conference alerts?|conferences?\s+20\d{2}\s*[/,-]\s*20\d{2}|"
    r"upcoming conferences)\b",
    re.IGNORECASE,
)
_SECONDARY_SOURCE = re.compile(
    r"(?:^|[/_-])(news|article|blog|press[-_ ]?release|opinion)(?:[/_-]|$)|"
    r"\b(reports?|announces?|announced|launches?|launched|extends?|extended|coverage)\b",
    re.IGNORECASE,
)
_OPEN_SIGNAL = re.compile(
    r"\b(applications?|entries|nominations?|registration)\s+"
    r"(?:are\s+|is\s+)?(?:now\s+)?open\b|\bapply\s+now\b|\bsubmit\b",
    re.IGNORECASE,
)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


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


def rank_search_hit(hit: SearchHit, *, current_year: int) -> float:
    text = f"{hit.title} {hit.url} {hit.snippet}"
    score = 0.0
    score += min(len(_POSITIVE.findall(text)), 4) * 1.5
    score -= min(len(_NEGATIVE.findall(text)), 3) * 2.0
    if str(current_year) in text:
        score += 2.5
    if str(current_year + 1) in text:
        score += 2.0
    for year in re.findall(r"\b20\d{2}\b", text):
        if int(year) < current_year:
            score -= 3.0
    path = urlparse(hit.url).path
    if path in ("", "/"):
        score -= 0.5
    if _DIRECTORY.search(text):
        score -= 6.0
    if _SECONDARY_SOURCE.search(
        f"{urlparse(hit.url).path} {hit.title}"
    ):
        score -= 12.0
    if (
        re.search(r"\bconferences\b", hit.title, re.IGNORECASE)
        and not _OPEN_SIGNAL.search(text)
    ):
        score -= 4.0
    if _host(hit.url) in {
        "facebook.com",
        "linkedin.com",
        "instagram.com",
        "x.com",
        "youtube.com",
    }:
        score -= 12.0
    return score


def score_link(url: str, label: str, *, seed_url: str) -> float | None:
    absolute = canonicalize_url(urljoin(seed_url, url))
    if not absolute.startswith("https://"):
        return None
    if not _same_site(absolute, seed_url):
        return None
    text = f"{label} {urlparse(absolute).path.replace('-', ' ')}"
    if _NEGATIVE.search(text):
        return None
    matches = len(_POSITIVE.findall(text))
    return float(matches * 2) if matches else 0.25


def _candidate_links(page: EvidencePage, seed_url: str) -> list[tuple[float, str]]:
    labelled: dict[str, str] = {url: url for url in page.links}
    for label, url in _MARKDOWN_LINK.findall(page.markdown):
        labelled[url] = label
    ranked: list[tuple[float, str]] = []
    for url, label in labelled.items():
        absolute = canonicalize_url(urljoin(page.url, url))
        score = score_link(absolute, label, seed_url=seed_url)
        if score is not None:
            ranked.append((score, absolute))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked


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
    max_depth: int = 3,
    max_pages: int = 3,
    reserve_calls: int = 3,
) -> EvidenceBundle:
    """Fetch a seed and its highest-value same-domain links within hard caps."""
    pages: list[EvidencePage] = []
    seen: set[str] = set()
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
            page = await firecrawl_fetch(
                url, depth=depth, dry_run=runtime.dry_run
            )
            page = replace(page, url=canonicalize_url(page.url))
        except Exception as exc:  # noqa: BLE001
            await record_event(
                "scrape",
                node="research",
                url=url,
                depth=depth,
                outcome="failed",
                detail=f"{type(exc).__name__}: {exc}"[:300],
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
                fallback = await firecrawl_fetch(
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
            node="research",
            url=page.url,
            depth=depth,
            outcome="ok",
            chars=len(page.markdown),
            status_code=page.status_code,
            bare_domain=urlparse(page.url).path in ("", "/"),
        )
        if depth >= max_depth:
            continue
        for score, link in _candidate_links(page, seed_url):
            if link not in seen and score >= 2:
                queue.append((link, depth + 1))

    return EvidenceBundle(seed_url=seed_url, pages=tuple(pages))


def has_open_signal(text: str) -> bool:
    return bool(_OPEN_SIGNAL.search(text))
