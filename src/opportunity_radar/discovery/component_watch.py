"""Component watch: for every BOM part, look for the same part from any seller and for alternatives.

Runs only when triggered. The model plans two searches per off-the-shelf part
(the current model from any seller, and other models that do the same job),
then judges each page against the part's brief, including how much effort a
switch would take. Code compares prices with the BOM rate, which never reaches
the model.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import httpx
from openai import ContentFilterFinishReasonError, LengthFinishReasonError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from ..config import require
from ..product_profile import Part, load_product_profile
from ..storage import finish_run, start_run
from ..storage.runs import RUNS
from . import workflow as w
from .budget import RunBudget
from .link_resolver import canonicalize_url
from .providers import EXA_TIMEOUT_SECONDS, EXA_URL
from .state import WorkflowRuntime

OFFERS = "component_offers"
FOCUS = "components"

PLAN_BATCH = 16
RESULTS_PER_SEARCH = 5
TEXT_CHARS = 3_000
JUDGE_TEXT_CHARS = 1_400
HIGHLIGHT_CHARS = 1_000
# Picks which passages of each page come back; it does not change which pages are found.
HIGHLIGHTS_QUERY = "price in rupees, pack size or quantity, GST, stock, specifications and ratings"
CONCURRENCY = 4
#: A priority run searches the off-the-shelf parts that make up this share of their cost per machine.
PRIORITY_SHARE = 0.8
TOKENS_PLAN = 20_000
TOKENS_JUDGE = 24_000
OFFER_KINDS = ("newer model", "better spec", "more efficient")
EFFORTS = ("drop-in", "minor changes", "major changes", "needs verification")
PAGE_KINDS = ("seller listing", "manufacturer page", "other")
SELLER_KINDS = ("maker", "authorised distributor", "other seller")


class _PartPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part_id: str = Field(max_length=40)
    off_the_shelf: bool
    reason: str = Field(max_length=200)
    same_part_query: str = Field(max_length=200)
    alternative_query: str = Field(max_length=200)


class _Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parts: list[_PartPlan]


class _Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str = Field(max_length=200)
    status: Literal["met", "not met", "unclear"]


class _Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep: bool
    product: str = Field(max_length=160)
    maker: str = Field(max_length=80)
    seller: str = Field(max_length=120)
    seller_kind: Literal[SELLER_KINDS]
    page_kind: Literal[PAGE_KINDS]
    price: float | None
    gst: Literal["included", "excluded", "not stated"]
    currency: str = Field(max_length=8)
    rupee_price: bool
    price_unit: str = Field(max_length=60)
    units_per_part: float | None
    price_unclear: bool
    in_stock: Literal["yes", "no", "not stated"]
    relation: Literal["same part", "alternative"]
    effort: Literal[EFFORTS]
    changes: str = Field(max_length=300)
    offers: list[Literal[OFFER_KINDS]]
    why: str = Field(max_length=400)
    checks: list[_Check]
    certifications: list[str]
    discontinued: bool
    concerns: str = Field(max_length=300)
    reason: str = Field(max_length=80)


def _assessment(pages: int) -> type[BaseModel]:
    """One required slot per page, so a reply that leaves a page out fails instead of losing it."""
    return create_model("_Assessment", __config__=ConfigDict(extra="forbid"),
                        **{f"page_{i}": (_Offer, ...) for i in range(pages)})


async def exa_product_search(query: str) -> list[dict]:
    """Product pages for one query, with highlights and capped text; raises on any failure."""
    body = {"query": query, "type": "auto", "numResults": RESULTS_PER_SEARCH,
            "contents": {"highlights": {"query": HIGHLIGHTS_QUERY, "maxCharacters": HIGHLIGHT_CHARS},
                         "text": {"maxCharacters": TEXT_CHARS}}}
    async with httpx.AsyncClient(headers={"x-api-key": require("EXA_API_KEY")}, timeout=EXA_TIMEOUT_SECONDS) as client:
        response = await asyncio.wait_for(client.post(EXA_URL, json=body), timeout=EXA_TIMEOUT_SECONDS)
    response.raise_for_status()
    return [{"url": canonicalize_url(item["url"]), "title": item.get("title") or "",
             "highlights": " … ".join(item.get("highlights") or []), "text": (item.get("text") or "")[:TEXT_CHARS]}
            for item in response.json().get("results", []) if item.get("url")]


async def _plan(runtime: WorkflowRuntime, product: str, parts: list[Part]) -> list[_PartPlan]:
    listing = "\n\n".join(f"[{p.part_id}] {p.subsystem}\n" + p.brief() for p in parts)
    prompt = f"""## Objective
These are parts of the {product} machine's bill of materials. For each part, decide whether
it is bought off the shelf, and write the searches that would find it from any seller and
find newer, better or more efficient models that could replace it.

## Decide, for every part listed
- `off_the_shelf`: false for parts made to this machine's own design (enclosure fabrication,
  moulded or printed parts, harnesses, overlays, custom brackets); true for catalogue parts
  anyone can buy. `reason` says which, in one line.
- `same_part_query`: a description of the page wanted: an Indian seller's product page for
  the exact current model, with its manufacturer and model number from the brief, showing its
  price. Empty when the brief names no specific model or the part is not off the shelf.
- `alternative_query`: a description of the page wanted: an Indian seller's product page, with
  its price, for a newer or more capable replacement for the current model (its successor from
  the same maker, or an equivalent from another maker), naming the current model as what it
  replaces and stating the needs as minimums ("at least …", from Why chosen and Must have,
  else the current model's own class and ratings), never as the current model's exact figures,
  which find the current model itself. Name no manufacturer or model the brief does not name.
  Empty when the part is not off the shelf.
- Write each as one plain sentence describing that page, about 15 to 25 words, not a list of
  keywords; the search engine matches pages to descriptions of them.
- Leave compliance marks and certifications out of both searches; each page is checked for
  them separately. Never name the current vendor in a search.

PARTS:
{listing}
"""
    runtime.budget.consume("plan")
    plan = (await w._structured(runtime, _Plan, "component_plan", w._PLAN_SYSTEM, prompt,
                                max_tokens=TOKENS_PLAN)).parts
    return [p for p in plan if p.part_id in {x.part_id for x in parts}]


async def _assess(runtime: WorkflowRuntime, part: Part, pages: list[dict]) -> list[tuple[int, _Offer]]:
    listing = "\n\n".join(
        f"[page_{i}] {p['title']}\n    {p['url']}\n    found by: {p['lane']} search\n"
        f"    highlights: {p['highlights'][:HIGHLIGHT_CHARS]}\n    text: {p['text'][:JUDGE_TEXT_CHARS]}"
        for i, p in enumerate(pages)
    )
    prompt = f"""## Objective
These pages were found while looking for one part of a machine from other sellers, and for
models that could replace it. Answer every page, each under its own key (page_0, page_1, …).

## Decide
- `page_kind`: "seller listing" (a shop or distributor page where this one product can be bought
  or quoted), "manufacturer page" (the maker's own page for this one product), or "other".
- `keep`: true only for a page about one specific product of the same kind as this part, made
  for the same use, and only when:
  for the same part, it is a seller listing from which a private company can buy the part in
  India (a rupee price, or an Indian seller that quotes on request); government-only
  marketplaces such as GeM are not;
  for an alternative, it is such a seller listing or a manufacturer page.
  False for datasheets, manuals, user guides and other documentation; parts-broker pages that
  list a part number with stock or price placeholders; price-comparison sites; category or
  listing pages; articles; products of a different kind or meant for a different use (a
  household item for a machine part); products that cannot do the job; and listings the page
  says are out of stock, sold out, unavailable, on pre-order or back-order; products the page
  says are discontinued, end of life or no longer made; and listings priced in a currency other
  than Indian rupees, since the business buys only in India. `reason` says why.
- `product`: name and model as the page gives them. `maker`: who makes it, as the page names
  them; empty when the page does not say. `seller`: who sells it on this page. `seller_kind`:
  "maker" when the maker itself sells it; "authorised distributor" only when the page says the
  seller is an authorised distributor or dealer of that maker; otherwise "other seller".
- `relation`: "same part" when it is the current model, whoever sells it; otherwise "alternative".
- `effort`: what switching to it would take in this machine.
  "drop-in": fits the current design as it is: same job, interfaces, size, mounting, ratings
  and software. Only when the page itself states the facts that matter for this part (size or
  dimensions, electrical ratings, interface and mounting) and they match the brief. A part with
  a safety function needs the same safety rating to be drop-in. The same part is always drop-in.
  "minor changes": only a cable, connector, bracket or setting changes, and the page shows the
  same interface and protocol, the same supply voltage and the same mounting otherwise, and,
  for a part with a safety function, the same safety class. When the page shows that a new
  driver or protocol, a different supply voltage, a lower safety class or a new mount would be
  needed, it is "major changes"; when
  the page does not say, it is "needs verification".
  "major changes": redesign, a different software stack or drivers, porting or retraining
  models, new mounting, or requalification.
  "needs verification": the brief or the page lacks the facts needed to tell whether it would work
  in this machine (load, size, mounting, ratings, features the use needs).
  Fit is judged on the specs and description the page states. Certifications and compliance
  marks are never fit facts: their absence never makes an option "needs verification",
  "minor changes" or "major changes"; record the ones the page states in `certifications`.
  `changes` says what would have to change, or for "needs verification" which facts are missing;
  empty for drop-in.
- `offers`: what an alternative offers over the current part, from: "newer model" (a later
  version or successor), "better spec" (a spec that matters to this part is better), "more
  efficient" (lower power or losses). Empty when none, and for the same part. `why` gives
  the page's facts behind each one, or what the page offers for the same part.
- `price`: the price exactly as the page states it, as a number; null when the page shows none
  or says price on request. `currency` as written (INR, USD…); `rupee_price` true when the price
  is in Indian rupees. `gst`: "included" when the page says incl. GST or inclusive of all taxes,
  or gives an MRP (which in India includes all taxes); "excluded" when it says + GST, excl. GST
  or ex-tax; "not stated" only when it says nothing about GST.
- `in_stock`: "no" when the page says out of stock, sold out, unavailable, pre-order or
  back-order, wherever on the page it says so; "yes" when it says in stock or shows a quantity
  available; otherwise "not stated".
- `price_unclear`: true when the price looks wrong for this product: far below what the other
  pages here ask for the same product, contradicted elsewhere on the page, or the price of a
  different item or an accessory; `concerns` says why.
- `price_unit`: what that price buys, as the page states it ("1 piece", "1 metre", "pack of
  100", "90 m coil"). `units_per_part`: how many of those make one unit of this part as the
  brief's "Qty per machine" counts it: 1 when they are the same; 0.01 for a pack of 100 when
  the part is counted in pieces; 1/90 for a 90 m coil when it is counted in metres. Null when
  it is not clear what one unit of this part is, or what the page's price buys.
- `checks`: one per Must have item in the brief, met / not met / unclear by the page's own specs;
  empty when the brief states no Must have.
- `certifications`: the marks the page itself states for this product (for example CE, RoHS,
  UL, UKCA, FCC, BIS), as written on the page; empty when it states none. Never add a mark the
  page does not state.
- `discontinued`: true when the page says this product is discontinued, end of life or no
  longer made.
- `concerns`: anything else that may stop it replacing the current part (pack quantity,
  conflicting specs on the page, unclear seller, out of stock). Never repeat Must have results
  here, such as a compliance mark the page does not state; they belong in `checks` only.
For a dropped page, decide only `keep` and `reason` (a few words, such as "Category page");
fill every other field with an empty
value (empty text and lists, null numbers, "other", "needs verification", "not stated", false).

PART:
{part.brief()}

PAGES:
{listing}
"""
    runtime.budget.consume("analyze")
    parsed = await w._structured(runtime, _assessment(len(pages)), "component_assess",
                                 "Judge product pages for one part. Return JSON matching the supplied schema.",
                                 prompt, max_tokens=TOKENS_JUDGE)
    return [(i, getattr(parsed, f"page_{i}")) for i in range(len(pages))]


def price_difference(price: float | None, rupee_price: bool, units_per_part: float | None, rate: float | None,
                     qty: float | None, gst: str = "not stated", gst_rate: float | None = None) -> dict:
    """The seller's listed price against ours on the same GST basis, per our unit and per machine, in code.

    The seller's price is never changed: when it includes GST, our rate has our GST added instead.
    Compared only for a rupee price, a known rate and a known unit conversion.
    """
    none = {"unit_price": None, "ours_unit": None, "diff_pct": None, "machine_theirs": None, "machine_ours": None,
            "saving_per_machine": None, "compared_on": None}
    if price is None or not rate or not rupee_price or not units_per_part:
        return none
    if gst == "included":
        ours, basis = rate * (1 + gst_rate), "incl. GST"
    else:
        ours, basis = rate, "before GST" if gst == "excluded" else "GST not stated"
    theirs, n = price * units_per_part, qty or 1
    return {"unit_price": round(theirs, 2), "ours_unit": round(ours, 2), "diff_pct": round((theirs - ours) / ours * 100, 1),
            "machine_theirs": round(theirs * n, 2), "machine_ours": round(ours * n, 2),
            "saving_per_machine": round((ours - theirs) * n, 2), "compared_on": basis}


def part_summary(rate: float | None, offers: list[dict]) -> str:
    """One line per part from the stored findings: lowest same-part price, then alternatives by effort."""
    same_found = any(o["relation"] == "same part" for o in offers)
    unclear = sum(1 for o in offers if o["relation"] == "same part" and o.get("price_unclear"))
    offers = [o for o in offers if not o.get("price_unclear")]
    priced = sorted((o for o in offers if o["relation"] == "same part" and o["diff_pct"] is not None),
                    key=lambda o: o["diff_pct"])
    if priced:
        low = priced[0]
        d = price_display(low)
        line = (f"Lowest same-part price: {d['listed']} at {d['seller']}, {d['versus']}"
                + ("; our rate is the lowest found." if low["diff_pct"] >= 0 else "."))
    elif same_found:
        line = "Same part found, but with no clear rupee price to compare."
    else:
        line = "Same part not found from another seller."
    sellers = {o["seller"] for o in offers if o["relation"] == "same part"}
    if sellers or unclear:
        line += f" Same part from {len(sellers) + unclear} seller(s)" + (f", {unclear} with an unclear price." if unclear else ".")
    unverified = sum(1 for o in offers if o["relation"] == "alternative" and o["effort"] == "needs verification")
    alternatives = [o for o in offers if o["relation"] == "alternative" and o["effort"] != "needs verification"]
    if unverified:
        line += f" Needs verification: {unverified}."
    if not alternatives:
        return line + " No alternatives."
    makers = Counter(o["maker"].strip().lower() for o in alternatives if o.get("maker"))
    shown = {o["maker"].strip().lower(): o["maker"].strip() for o in alternatives if o.get("maker")}
    if makers:
        line += " Makes found: " + ", ".join(f"{shown[m]} ({n})" for m, n in makers.most_common()) + "."
    counts = ", ".join(f"{n} {e}" for e in EFFORTS[:3] if (n := sum(1 for o in alternatives if o["effort"] == e)))
    line += f" Alternatives: {counts}."
    for effort in ("drop-in", "minor changes"):
        cheaper = [o for o in alternatives if o["effort"] == effort and (o["diff_pct"] or 0) < 0]
        if cheaper:
            best = min(cheaper, key=lambda o: o["diff_pct"])
            line += f" Cheapest {effort}: {best['product']}, {price_display(best)['listed']} ({best['diff_pct']:+.0f}%)."
    return line


class OutdatedRunError(ValueError):
    """The run's findings were stored by an earlier version of this pipeline and lack fields it now needs."""


def line_cost(rate: float | None, qty: float | None) -> float:
    return (rate or 0) * (qty or 1)


def select_priority(parts: list[Part], share: float) -> tuple[list[Part], list[Part]]:
    """The highest-spend parts that together make up `share` of these parts' cost per machine, and the rest."""
    ranked = sorted(parts, key=lambda p: line_cost(p.rate, p.qty), reverse=True)
    total = sum(line_cost(p.rate, p.qty) for p in ranked)
    chosen, running = [], 0.0
    for p in ranked:
        if total and running >= share * total:
            break
        chosen.append(p)
        running += line_cost(p.rate, p.qty)
    return chosen, [p for p in ranked if p not in chosen]


VERDICTS = ("Cheaper seller found", "Cheaper drop-in found", "Changes needed to save", "We pay the lowest found",
            "No comparable price", "Could not be judged", "Nothing found", "Low spend, not searched this run",
            "Custom, not searched")

# A fault in one part's reply (cut off, unreadable, wrong shape) fails that part; anything else stops the run.
REPLY_ERRORS = (LengthFinishReasonError, ContentFilterFinishReasonError, ValueError)


def reply_error(exc: Exception) -> str:
    """What went wrong with a judge reply, in words that point at the cause."""
    usage = exc.completion.usage if isinstance(exc, LengthFinishReasonError) else None
    if usage:
        thought = usage.completion_tokens_details.reasoning_tokens if usage.completion_tokens_details else None
        return (f"the model's reply was cut off at its {usage.completion_tokens:,}-token output limit"
                + (f", {thought:,} of them spent reasoning" if thought else ""))
    missing = [str(e["loc"][0]) for e in exc.errors() if e["type"] == "missing" and len(e["loc"]) == 1]         if isinstance(exc, ValidationError) else []
    if missing:
        return f"the reply left out {', '.join(missing)}"
    return f"{type(exc).__name__}: {exc}"[:300]


def price_display(o: dict) -> dict:
    """The same words for one finding's price on the page and in the email: as listed, and against ours on its GST basis."""
    seller = o["seller"] or urlparse(o["url"]).netloc.removeprefix("www.")
    kind = o.get("seller_kind")
    out = {"seller": f"{seller} ({kind})" if kind in ("maker", "authorised distributor") else seller,
           "listed": "Price not available", "each": "", "versus": "", "saving": "",
           "doubt": "Price unclear" if o.get("price_unclear") else "",
           "certifications": f"Certified: {', '.join(o['certifications'])}" if o.get("certifications") else ""}
    if o["price"] is None:
        return out
    tag = {"included": "incl. GST", "excluded": "+ GST"}.get(o["gst"], "GST not stated")
    lot = "" if o["units_per_part"] == 1 else f" for {o['price_unit'] or 'an unstated quantity'}"
    out["listed"] = f"{'₹' if o.get('rupee_price') else o['currency'] + ' '}{o['price']:,.0f}{lot}, {tag}"
    if o["unit_price"] is None:
        return out
    ours = "incl. GST" if o["compared_on"] == "incl. GST" else "+ GST"
    if o["units_per_part"] != 1:
        out["each"] = f"₹{o['unit_price']:,.0f} each"
    out["versus"] = f"{o['diff_pct']:+.0f}% vs ours ₹{o.get('ours_unit') or o['rate']:,.0f} {ours}"
    if o["saving_per_machine"] > 0:
        out["saving"] = f"₹{o['saving_per_machine']:,.0f} per machine, {'incl.' if o['compared_on'] == 'incl. GST' else 'before'} GST"
    return out


def part_decision(offers: list[dict]) -> dict:
    """What one part's findings mean, in code: the best like-for-like option, or why there is none."""
    offers = [o for o in offers if not o.get("price_unclear")]  # an unclear price is shown, never counted
    plain = lambda o: o.get("seller_kind") not in ("maker", "authorised distributor")  # noqa: E731
    named = lambda o: "maker" not in o or bool(o["maker"])  # noqa: E731 — runs before makers were recorded keep theirs
    like = [o for o in offers if o["diff_pct"] is not None
            and (o["relation"] == "same part" or (o["effort"] == "drop-in" and named(o)))]
    best = min(like, key=lambda o: o["diff_pct"], default=None)
    same = min((o for o in offers if o["relation"] == "same part" and o["diff_pct"] is not None and o["diff_pct"] < 0),
               key=lambda o: (plain(o), o["diff_pct"]), default=None)
    cheaper = [o for o in offers if o["diff_pct"] is not None and o["diff_pct"] < 0 and named(o)
               and all(c["status"] != "not met" for c in o["checks"])
               and o["relation"] == "alternative" and o["effort"] in ("drop-in", "minor changes", "major changes")]
    alternative = min(cheaper, key=lambda o: (EFFORTS.index(o["effort"]), plain(o), o["diff_pct"]), default=None)
    # Better, newer or more efficient, no must-have failed; major changes included, after the rest, for procurement to weigh.
    upgrades = [o for o in offers if o["relation"] == "alternative" and o["offers"] and named(o)
                and o["effort"] in ("drop-in", "minor changes", "major changes")
                and all(c["status"] != "not met" for c in o["checks"])]
    upgrade = min(upgrades, key=lambda o: (EFFORTS.index(o["effort"]), plain(o), -len(o["offers"]),
                                            o["diff_pct"] if o["diff_pct"] is not None else float("inf")), default=None)
    # Like-for-like first: a cheaper option needing changes never hides that we already pay the lowest.
    if best and best["diff_pct"] < 0:
        verdict = "Cheaper seller found" if best["relation"] == "same part" else "Cheaper drop-in found"
    elif best:
        verdict = "We pay the lowest found"
    elif alternative:
        verdict = "Changes needed to save"
    elif offers:
        verdict = "No comparable price"
    else:
        verdict = "Nothing found"
    saving = best["saving_per_machine"] if best and best["diff_pct"] < 0 else 0
    return {"verdict": verdict, "best": best, "best_same": same, "best_alternative": alternative,
            "best_upgrade": upgrade, "upgrades": len(upgrades), "saving_per_machine": saving}


async def run_offers(db, run_id: str) -> dict:
    """A run's results: one row per BOM part with its verdict, the decisions overview, and every finding by part."""
    run = await db[RUNS].find_one({"run_id": run_id}, {"journey": 1})
    journey = (run or {}).get("journey") or []
    planned = [p for e in journey if e.get("tool") == "plan" for p in e.get("parts") or []]
    deferred = {d["part_id"] for e in journey if e.get("tool") == "scope" for d in e.get("deferred") or []}
    unjudged = {e["part_id"]: e["detail"] for e in journey if e.get("tool") == "assess" and e.get("outcome") == "failed"}
    by_part: dict[str, list[dict]] = {}
    async for o in db[OFFERS].find({"run_id": run_id}, {"_id": 0}):
        if o.get("effort") == "fit unclear":
            o["effort"] = "needs verification"
        if "unit_price" not in o:
            raise OutdatedRunError(f"run {run_id[:6]} was stored before per-unit pricing; delete it and start a new run")
        by_part.setdefault(o["part_id"], []).append(o)
    order = {"same part": 0, **{e: i + 1 for i, e in enumerate(EFFORTS)}}
    parts, rows = [], []
    for p in planned:
        found = sorted(by_part.get(p["part_id"], []), key=lambda o: (
            order["same part"] if o["relation"] == "same part" else order[o["effort"]], bool(o.get("price_unclear")),
            o["diff_pct"] if o["diff_pct"] is not None else float("inf")))
        base = {k: p.get(k) for k in ("part_id", "item", "subsystem", "rate", "qty", "gst", "part_number")}
        base["line_cost"] = line_cost(p.get("rate"), p.get("qty"))
        if not p["off_the_shelf"]:
            rows.append({**base, "verdict": "Custom, not searched", "note": p["reason"], "findings": 0,
                         "best": None, "best_same": None, "best_alternative": None, "best_upgrade": None,
                         "upgrades": 0,
                         "saving_per_machine": 0})
        elif p["part_id"] in deferred:
            rows.append({**base, "verdict": "Low spend, not searched this run", "note": "", "findings": 0,
                         "best": None, "best_same": None, "best_alternative": None, "best_upgrade": None,
                         "upgrades": 0,
                         "saving_per_machine": 0})
        elif p["part_id"] in unjudged:
            rows.append({**base, "verdict": "Could not be judged", "note": unjudged[p["part_id"]], "findings": 0,
                         "best": None, "best_same": None, "best_alternative": None, "best_upgrade": None,
                         "upgrades": 0,
                         "saving_per_machine": 0})
        else:
            for o in found:
                o["display"] = price_display(o)
            summary = part_summary(p["rate"], found) if found else "Nothing found."
            rows.append({**base, **part_decision(found), "note": summary, "findings": len(found)})
            if found:
                parts.append({**base, "summary": summary, "offers": found})
    machine = sum(r["line_cost"] for r in rows)
    shelf = [r for r in rows if r["verdict"] != "Custom, not searched"]
    searched = [r for r in shelf if r["verdict"] != "Low spend, not searched this run"]
    checked = [o for f in by_part.values() for o in f if o.get("check") in ("holds", "does not hold")]
    overview = {
        "machine_cost": machine, "parts": len(rows), "searched": len(searched),
        "deferred": len(shelf) - len(searched), "custom": len(rows) - len(shelf),
        "searched_share": (sum(r["line_cost"] for r in searched) / sum(r["line_cost"] for r in shelf))
        if sum(r["line_cost"] for r in shelf) else 0,
        "saving_per_machine": sum(r["saving_per_machine"] for r in rows),
        "verdicts": {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS},
        "upgrades": sum(1 for r in rows if r.get("best_upgrade")),
        "checks": {"holds": sum(1 for o in checked if o["check"] == "holds"),
                   "does not hold": sum(1 for o in checked if o["check"] == "does not hold")},
    }
    return {
        "overview": overview, "rows": rows, "parts": parts,
        "same_part": sorted((r for r in rows if r.get("best_same")), key=lambda r: -r["best_same"]["saving_per_machine"]),
        "upgrades": sorted((r for r in rows if r.get("best_upgrade")),
                           key=lambda r: (EFFORTS.index(r["best_upgrade"]["effort"]), -r["line_cost"])),
        "alternatives": sorted((r for r in rows if r.get("best_alternative")),
                               key=lambda r: (EFFORTS.index(r["best_alternative"]["effort"]),
                                              -r["best_alternative"]["saving_per_machine"])),
        "custom": [{"part_id": r["part_id"], "item": r["item"], "reason": r["note"]} for r in rows
                   if r["verdict"] == "Custom, not searched"],
        "nothing": [{"part_id": r["part_id"], "item": r["item"]} for r in rows if r["verdict"] == "Nothing found"],
        "unjudged": [{"part_id": r["part_id"], "item": r["item"], "reason": r["note"]} for r in rows
                     if r["verdict"] == "Could not be judged"],
        "deferred": [{"part_id": r["part_id"], "item": r["item"], "line_cost": r["line_cost"]} for r in rows
                     if r["verdict"] == "Low spend, not searched this run"],
    }


CHECKS = ("holds", "does not hold", "")


async def record_check(db, offer_id: str, check: str, note: str) -> dict:
    """Procurement's verdict on one finding after asking the seller: holds, does not hold, or cleared."""
    if check not in CHECKS:
        raise ValueError(f"check must be one of {CHECKS[:2]} or empty")
    result = await db[OFFERS].find_one_and_update(
        {"offer_id": offer_id},
        {"$set": {"check": check, "check_note": note[:300], "checked_at": datetime.now(timezone.utc)}},
        projection={"_id": 0, "offer_id": 1, "check": 1, "check_note": 1}, return_document=True)
    if not result:
        raise KeyError(offer_id)
    return result


async def run_component_watch(db, product: str, model: str | None = None, run_id: str | None = None,
                              budget: RunBudget | None = None, only: list[str] | None = None,
                              scope: Literal["priority", "all"] = "priority") -> dict:
    """One triggered run over a product's parts; returns its counts. A part whose judge reply fails is
    marked "Could not be judged" and the run goes on; any other failed step stops the run.

    "priority" searches the off-the-shelf parts that make up PRIORITY_SHARE of their cost per
    machine; "all" searches every off-the-shelf part; `only` searches the parts named.
    """
    run_id = run_id or uuid4().hex
    budget = budget or RunBudget(tool_calls=240, max_searches=150, max_llm_calls=80)
    profile = load_product_profile(product)
    parts = [p for p in profile.parts if not only or p.part_id in only]
    if not parts:
        raise ValueError(f"none of {only} is a part of {profile.product}")
    runtime = WorkflowRuntime(db=db, budget=budget, model=model, dry_run=False, run_id=run_id, focus="any",
                              profile_text="")
    meta = {**budget.caps(), "focus": FOCUS, "workflow": "component-watch", "product": profile.product,
            "parts": len(parts), "scope": "named" if only else scope}
    await start_run(db, run_id, model or "(OPENROUTER_MODEL)", meta, [])
    counts = {"parts": len(parts), "searched_parts": 0, "deferred": 0, "searched": 0, "pages": 0, "offers": 0,
              "dropped": 0, "judged": 0, "unjudged": 0}
    unjudged: list[str] = []
    status, summary = "succeeded", ""
    gate = asyncio.Semaphore(CONCURRENCY)
    try:
        plans: dict[str, _PartPlan] = {}
        for start in range(0, len(parts), PLAN_BATCH):
            batch = parts[start:start + PLAN_BATCH]
            for p in await _plan(runtime, profile.product, batch):
                plans.setdefault(p.part_id, p)
            await w._record(runtime, "plan", node="plan", outcome="ok", asked=len(batch), parts=[
                {"part_id": x.part_id, "item": x.item, "subsystem": x.subsystem, "rate": x.rate, "qty": x.qty, "gst": x.gst,
                 "part_number": x.part_number,
                 "off_the_shelf": plans[x.part_id].off_the_shelf, "reason": plans[x.part_id].reason,
                 "queries": [q for q in (plans[x.part_id].same_part_query, plans[x.part_id].alternative_query) if q]}
                for x in batch if x.part_id in plans])
        unplanned = [x.part_id for x in parts if x.part_id not in plans]
        if unplanned:
            runtime.failures.append(f"the plan left out {len(unplanned)} part(s): {', '.join(unplanned)}")

        def unusable(o: _Offer) -> str:
            """Why a page goes no further, or empty: what cannot be bought in India is not stored."""
            if not o.keep:
                return o.reason
            if o.in_stock == "no":
                return "Out of stock"
            if o.discontinued:
                return "Discontinued"
            if o.price is not None and not o.rupee_price:
                return "Not sold in India"
            return ""

        async def one_part(part: Part) -> None:
            plan = plans[part.part_id]
            pages: dict[str, dict] = {}
            async with gate:
                for lane, query in (("same part", plan.same_part_query), ("alternative", plan.alternative_query)):
                    if not query:
                        continue
                    budget.consume("search")
                    results = await exa_product_search(query)
                    counts["searched"] += 1
                    for r in results:
                        pages.setdefault(r["url"], {**r, "lane": lane, "query": query})
                    await w._record(runtime, "search", node="search", query=query, outcome="ok", lane=lane,
                                    part_id=part.part_id, count=len(results),
                                    results=[{"title": r["title"], "url": r["url"]} for r in results])
                found = list(pages.values())
                counts["pages"] += len(found)
                if not found:
                    return
                try:
                    verdicts = await _assess(runtime, part, found)
                except REPLY_ERRORS as exc:
                    detail = reply_error(exc)
                    counts["unjudged"] += 1
                    unjudged.append(f"{part.part_id} could not be judged: {detail}")
                    await w._record(runtime, "assess", node="evaluate", outcome="failed", part_id=part.part_id,
                                    item=part.item, considered=len(found), detail=detail)
                    return
                counts["judged"] += 1
            now = datetime.now(timezone.utc)
            kept = []
            for i, o in verdicts:
                page = found[i]
                if unusable(o):
                    counts["dropped"] += 1
                    continue
                kept.append({
                    "offer_id": uuid4().hex[:10], "run_id": run_id, "product": profile.product,
                    "part_id": part.part_id, "item": part.item, "rate": part.rate, "qty": part.qty, "gst_rate": part.gst,
                    "url": page["url"], "title": page["title"], "lane": page["lane"], "query": page["query"],
                    "found_at": now, **o.model_dump(exclude={"index", "keep", "reason"}),
                    **price_difference(o.price, o.rupee_price, o.units_per_part, part.rate, part.qty, o.gst, part.gst),
                })
            if kept:
                await db[OFFERS].insert_many([dict(k) for k in kept])
            counts["offers"] += len(kept)
            await w._record(runtime, "assess", node="evaluate", outcome="ok", part_id=part.part_id, item=part.item,
                            considered=len(found),
                            kept=[{k: o[k] for k in ("product", "seller", "relation", "effort", "offers", "price",
                                                     "currency", "diff_pct", "url")} for o in kept],
                            excluded=[{"title": found[i]["title"], "url": found[i]["url"], "reason": unusable(o)}
                                      for i, o in verdicts if unusable(o)])

        shelf = [x for x in parts if x.part_id in plans and plans[x.part_id].off_the_shelf]
        # Named parts are always searched; otherwise the highest-spend parts, unless every part is asked for.
        searchable, deferred = (shelf, []) if only or scope == "all" else select_priority(shelf, PRIORITY_SHARE)
        await w._record(runtime, "scope", node="plan", outcome="ok", scope="named" if only else scope,
                        share=PRIORITY_SHARE, searched=[x.part_id for x in searchable],
                        deferred=[{"part_id": x.part_id, "item": x.item, "line_cost": line_cost(x.rate, x.qty)}
                                  for x in deferred])
        counts["searched_parts"], counts["deferred"] = len(searchable), len(deferred)
        # A TaskGroup cancels the other parts when one fails, so a broken step stops the spending.
        async with asyncio.TaskGroup() as group:
            for x in searchable:
                group.create_task(one_part(x))
        summary = (f"{counts['offers']} finding(s) for {counts['searched_parts']} off-the-shelf part(s) of {len(parts)}, "
                   f"from {counts['pages']} page(s) across {counts['searched']} searches; {counts['dropped']} page(s) dropped"
                   + (f"; {counts['deferred']} low-spend part(s) left for a full run" if counts["deferred"] else "")
                   + (f"; {counts['unjudged']} part(s) could not be judged." if counts["unjudged"] else "."))
        if runtime.failures or (counts["unjudged"] and not counts["judged"]):
            status = "failed"
        runtime.failures.extend(unjudged)
    except Exception as exc:
        while isinstance(exc, ExceptionGroup):
            exc = exc.exceptions[0]
        status = "stopped" if budget.cancelled else "failed"
        summary = f"RUN ENDED EARLY: {type(exc).__name__}: {exc}"[:500]
        runtime.failures.append(summary)
    await finish_run(db, run_id, status, summary, None, {**meta, **budget.live()}, counts, [],
                     list(runtime.warnings), list(runtime.failures))
    return {"run_id": run_id, "status": status, "summary": summary, **counts}
