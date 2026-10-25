"""Component watch: for every BOM part, look for the same part from any seller and for alternatives.

Runs only when triggered. The model plans two searches per off-the-shelf part
(the current model from any seller, and other models that do the same job),
then judges each page against the part's brief, including how much effort a
switch would take. Code compares prices with the BOM rate, which never reaches
the model.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import httpx
from openai import ContentFilterFinishReasonError, LengthFinishReasonError
from pydantic import BaseModel, ConfigDict, Field

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
RESULTS_PER_SEARCH = 8
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
EFFORTS = ("drop-in", "minor changes", "major changes", "fit unclear")
PAGE_KINDS = ("seller listing", "manufacturer page", "other")


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
    index: int
    keep: bool
    product: str = Field(max_length=160)
    seller: str = Field(max_length=120)
    page_kind: Literal[PAGE_KINDS]
    relation: Literal["same part", "alternative"]
    effort: Literal[EFFORTS]
    changes: str = Field(max_length=300)
    offers: list[Literal[OFFER_KINDS]]
    why: str = Field(max_length=400)
    price: float | None
    price_before_gst: float | None
    price_unit: str = Field(max_length=60)
    units_per_part: float | None
    currency: str = Field(max_length=8)
    gst: Literal["included", "excluded", "not stated"]
    in_stock: Literal["yes", "no", "not stated"]
    checks: list[_Check]
    discontinued: bool
    concerns: str = Field(max_length=300)
    reason: str = Field(max_length=200)


class _Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[_Offer]


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
- `alternative_query`: a description of the page wanted: a product page for one model that
  does this part's job, with the specs that matter (from Why chosen and Must have, else the
  current model's own class and ratings), including newer models. Name no manufacturer or
  model the brief does not name. Empty when the part is not off the shelf.
- Write each as one plain sentence describing that page, about 15 to 25 words, not a list of
  keywords; the search engine matches pages to descriptions of them.

PARTS:
{listing}
"""
    runtime.budget.consume("plan")
    plan = (await w._structured(runtime, _Plan, "component_plan", w._PLAN_SYSTEM, prompt,
                                max_tokens=TOKENS_PLAN)).parts
    return [p for p in plan if p.part_id in {x.part_id for x in parts}]


async def _assess(runtime: WorkflowRuntime, part: Part, pages: list[dict]) -> list[_Offer]:
    listing = "\n\n".join(
        f"[{i}] {p['title']}\n    {p['url']}\n    found by: {p['lane']} search\n"
        f"    highlights: {p['highlights'][:HIGHLIGHT_CHARS]}\n    text: {p['text'][:JUDGE_TEXT_CHARS]}"
        for i, p in enumerate(pages)
    )
    prompt = f"""## Objective
These pages were found while looking for one part of a machine from other sellers, and for
models that could replace it. Return one item per page.

## Decide
- `page_kind`: "seller listing" (a shop or distributor page where this one product can be bought
  or quoted), "manufacturer page" (the maker's own page for this one product), or "other".
- `keep`: true only for a page about one specific product of the same kind as this part, made
  for the same use, and only when:
  for the same part, it is a seller listing from which the part can be bought in India (a
  rupee price, or an Indian seller that quotes on request);
  for an alternative, it is a seller listing or a manufacturer page.
  False for datasheets, manuals, user guides and other documentation; parts-broker pages that
  list a part number with stock or price placeholders; price-comparison sites; category or
  listing pages; articles; products of a different kind or meant for a different use (a
  household item for a machine part); and products that cannot do the job. `reason` says why.
- `product`: name and model as the page gives them. `seller`: who sells it on this page.
- `relation`: "same part" when it is the current model, whoever sells it; otherwise "alternative".
- `effort`: what switching to it would take in this machine.
  "drop-in": fits the current design as it is: same job, interfaces, size, mounting, ratings
  and software. Only when the page itself states the facts that matter for this part (size or
  dimensions, electrical ratings, interface, mounting, and any safety rating or certification)
  and they match the brief. A part with a safety function needs the same safety rating to be
  drop-in. The same part is always drop-in.
  "minor changes": only a cable, connector, bracket or setting changes, and the page shows the
  same interface and protocol, the same supply voltage, the same safety class and the same
  mounting otherwise. When the page shows that a new driver or protocol, a different supply
  voltage, a lower safety class or a new mount would be needed, it is "major changes"; when
  the page does not say, it is "fit unclear".
  "major changes": redesign, a different software stack or drivers, porting or retraining
  models, new mounting, or requalification.
  "fit unclear": the brief or the page lacks the facts needed to tell whether it would work
  in this machine (load, size, mounting, ratings, features the use needs).
  `changes` says what would have to change, or for "fit unclear" which facts are missing;
  empty for drop-in.
- `offers`: what an alternative offers over the current part, from: "newer model" (a later
  version or successor), "better spec" (a spec that matters to this part is better), "more
  efficient" (lower power or losses). Empty when none, and for the same part. `why` gives
  the page's facts behind each one, or what the page offers for the same part.
- `price`: the price for one unit exactly as the page states it, as a number; null when the page
  shows none or says price on request. `currency` as written (INR, USD…). `gst`: whether that
  price includes GST, as the page says. `price_before_gst`: the price before GST when the page
  states it, or states the GST amount; the same as `price` when the price excludes GST; null
  when the page gives no way to tell. `in_stock` as the page says.
- `price_unit`: what that price buys, as the page states it ("1 piece", "1 metre", "pack of
  100", "90 m coil"). `units_per_part`: how many of those make one unit of this part as the
  brief's "Qty per machine" counts it: 1 when they are the same; 0.01 for a pack of 100 when
  the part is counted in pieces; 1/90 for a 90 m coil when it is counted in metres. Null when
  it is not clear what one unit of this part is, or what the page's price buys.
- `checks`: one per Must have item in the brief, met / not met / unclear by the page's own specs;
  empty when the brief states no Must have.
- `discontinued`: true when the page says this product is discontinued, end of life or no
  longer made.
- `concerns`: anything else that may stop it replacing the current part (pack quantity,
  conflicting specs on the page, unclear seller, out of stock). Never repeat Must have results
  here, such as a compliance mark the page does not state; they belong in `checks` only.
For a dropped page, decide only `keep` and `reason`; fill every other field with an empty
value (empty text and lists, null numbers, "other", "fit unclear", "not stated", false).

PART:
{part.brief()}

PAGES:
{listing}
"""
    runtime.budget.consume("analyze")
    parsed = await w._structured(runtime, _Assessment, "component_assess",
                                 "Judge product pages for one part. Return JSON matching the supplied schema.",
                                 prompt, max_tokens=TOKENS_JUDGE)
    return [o for o in parsed.items if 0 <= o.index < len(pages)]


def _rupees(currency: str) -> bool:
    return currency.strip().upper() in ("INR", "₹", "RS", "RS.")


def price_difference(price: float | None, before_gst: float | None, currency: str, units_per_part: float | None,
                     rate: float | None, qty: float | None, gst: str = "not stated", gst_rate: float | None = None) -> dict:
    """The seller's price per our unit and per machine against the BOM rate (before GST), in code.

    Compared only for a rupee price, a known rate and a known unit conversion. On the seller's
    price before GST when the page gives it; otherwise on the price as shown, and `compared_on`
    says which, so a GST-included price is never read as like for like.
    """
    none = {"unit_price": None, "diff_pct": None, "machine_theirs": None, "machine_ours": None,
            "saving_per_machine": None, "compared_on": None}
    if price is None or not rate or not _rupees(currency) or not units_per_part:
        return none
    basis = "before GST"
    if before_gst is None and gst == "included" and gst_rate:
        # The page gives only a GST-included price: take our GST rate off it, and say so.
        before_gst, basis = price / (1 + gst_rate), f"before GST at our {gst_rate:.0%} rate"
    unit_price = (before_gst if before_gst is not None else price) * units_per_part
    per_machine = qty or 1
    return {"unit_price": round(unit_price, 2), "diff_pct": round((unit_price - rate) / rate * 100, 1),
            "machine_theirs": round(unit_price * per_machine, 2), "machine_ours": round(rate * per_machine, 2),
            "saving_per_machine": round((rate - unit_price) * per_machine, 2),
            "compared_on": basis if before_gst is not None else "price as shown"}


def part_summary(rate: float | None, offers: list[dict]) -> str:
    """One line per part from the stored findings: lowest same-part price, then alternatives by effort."""
    priced = sorted((o for o in offers if o["relation"] == "same part" and o["diff_pct"] is not None),
                    key=lambda o: o["diff_pct"])
    if priced:
        low = priced[0]
        line = (f"Lowest same-part price: {_shown(low)} at {low['seller']}, {low['diff_pct']:+.0f}% vs ours"
                + ("; our rate is the lowest found." if low["diff_pct"] >= 0 else "."))
    elif any(o["relation"] == "same part" for o in offers):
        line = "Same part found, but with no rupee price per our unit to compare."
    else:
        line = "Same part not found from another seller."
    sellers = {o["seller"] for o in offers if o["relation"] == "same part"}
    if sellers:
        line += f" Same part from {len(sellers)} seller(s)."
    alternatives = [o for o in offers if o["relation"] == "alternative"]
    if not alternatives:
        return line + " No alternatives."
    counts = ", ".join(f"{n} {e}" for e in EFFORTS if (n := sum(1 for o in alternatives if o["effort"] == e)))
    line += f" Alternatives: {counts}."
    for effort in ("drop-in", "minor changes"):
        cheaper = [o for o in alternatives if o["effort"] == effort and (o["diff_pct"] or 0) < 0]
        if cheaper:
            best = min(cheaper, key=lambda o: o["diff_pct"])
            line += f" Cheapest {effort}: {best['product']} at {_shown(best)} ({best['diff_pct']:+.0f}%)."
    return line


def _shown(o: dict) -> str:
    """The seller's price per our unit, with its GST basis."""
    basis = o["compared_on"] if o["compared_on"].startswith("before GST") else f"GST {o['gst']}"
    return f"₹{o['unit_price']:,.0f} per unit ({basis})"


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
    return f"{type(exc).__name__}: {exc}"[:300]


def part_decision(offers: list[dict]) -> dict:
    """What one part's findings mean, in code: the best like-for-like option, or why there is none."""
    like = [o for o in offers if o["diff_pct"] is not None and (o["relation"] == "same part" or o["effort"] == "drop-in")]
    best = min(like, key=lambda o: o["diff_pct"], default=None)
    same = min((o for o in offers if o["relation"] == "same part" and o["diff_pct"] is not None and o["diff_pct"] < 0),
               key=lambda o: o["diff_pct"], default=None)
    cheaper = [o for o in offers if o["diff_pct"] is not None and o["diff_pct"] < 0
               and o["relation"] == "alternative" and o["effort"] in ("drop-in", "minor changes", "major changes")]
    alternative = min(cheaper, key=lambda o: (EFFORTS.index(o["effort"]), o["diff_pct"]), default=None)
    # Better, newer or more efficient, and shown to fit: drop-in or minor changes, no must-have failed.
    upgrades = [o for o in offers if o["relation"] == "alternative" and o["offers"]
                and o["effort"] in ("drop-in", "minor changes") and all(c["status"] != "not met" for c in o["checks"])]
    upgrade = min(upgrades, key=lambda o: (o["effort"] != "drop-in", -len(o["offers"]),
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
        if "unit_price" not in o:
            raise OutdatedRunError(f"run {run_id[:6]} was stored before per-unit pricing; delete it and start a new run")
        by_part.setdefault(o["part_id"], []).append(o)
    order = {"same part": 0, **{e: i + 1 for i, e in enumerate(EFFORTS)}}
    parts, rows = [], []
    for p in planned:
        found = sorted(by_part.get(p["part_id"], []), key=lambda o: (
            order["same part"] if o["relation"] == "same part" else order[o["effort"]],
            o["diff_pct"] if o["diff_pct"] is not None else float("inf")))
        base = {k: p.get(k) for k in ("part_id", "item", "subsystem", "rate", "qty", "gst")}
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
                           key=lambda r: (r["best_upgrade"]["effort"] != "drop-in", -r["line_cost"])),
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
                 "off_the_shelf": plans[x.part_id].off_the_shelf, "reason": plans[x.part_id].reason,
                 "queries": [q for q in (plans[x.part_id].same_part_query, plans[x.part_id].alternative_query) if q]}
                for x in batch if x.part_id in plans])
        unplanned = [x.part_id for x in parts if x.part_id not in plans]
        if unplanned:
            runtime.failures.append(f"the plan left out {len(unplanned)} part(s): {', '.join(unplanned)}")

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
            for o in verdicts:
                page = found[o.index]
                if not o.keep:
                    counts["dropped"] += 1
                    continue
                kept.append({
                    "offer_id": uuid4().hex[:10], "run_id": run_id, "product": profile.product,
                    "part_id": part.part_id, "item": part.item, "rate": part.rate, "qty": part.qty,
                    "url": page["url"], "title": page["title"], "lane": page["lane"], "query": page["query"],
                    "found_at": now, **o.model_dump(exclude={"index", "keep", "reason"}),
                    **price_difference(o.price, o.price_before_gst, o.currency, o.units_per_part, part.rate, part.qty,
                                       o.gst, part.gst),
                })
            if kept:
                await db[OFFERS].insert_many([dict(k) for k in kept])
            counts["offers"] += len(kept)
            await w._record(runtime, "assess", node="evaluate", outcome="ok", part_id=part.part_id, item=part.item,
                            considered=len(found),
                            kept=[{k: o[k] for k in ("product", "seller", "relation", "effort", "offers", "price",
                                                     "currency", "diff_pct", "url")} for o in kept],
                            excluded=[{"title": found[o.index]["title"], "url": found[o.index]["url"], "reason": o.reason}
                                      for o in verdicts if not o.keep])

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
