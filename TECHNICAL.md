# TECHNICAL.md — Opportunity Radar

**As of 27 October 2026.** Branch `@Phase2-improvements`. Last commit `789c9d3` ("Phase 2 Checkpoint:
working pipelines"), plus uncommitted demo-freeze changes in 9 files (component watch, its page,
email, workbook loader, AUDIT, ledger).

**What this document is for.** This document gives the full picture of the project in one place:
what it is, who it is for, how each pipeline works, what state each one is in, the rules the work
follows, and what comes next. It is written so it can be handed to Claude (or a new engineer) as
the whole context. It replaces the Phase 1 version of this file, which is still in git history at
`704d09b`.

**Where the detail lives:**
- `AUDIT.md` holds the change log (rows 1–105), the Phase 2 plan (workstreams W1–W9) and the
  Phase 1 audit.
- `reference/spend-ledger.md` records every live run that spent credits.
- `CLAUDE.md` is empty. The Phase 1 spec it held is out of date; rewriting it is a W8 task.

---

## 1. What it is

**Opportunity Radar** is an agentic research system built for **Retearn**, which makes reverse
vending machines (RVMs) and deposit-return system infrastructure. Retearn sits within the Recykal
group. The system is built for Retearn and can be adapted for Recykal later. Retearn buys only in
India.

It supports decisions and never acts on them. It never submits an application, contacts an
organiser or seller, or places an order. Every pipeline ends with stored records, a dashboard view
and an optional email to a fixed recipient list.

It has three pipelines (called "tracks" in the UI). They share one codebase, one database, one
dashboard and one mailer.

| Pipeline | Question it answers | Input | Output | State after the Phase 2 review |
|---|---|---|---|---|
| **Opportunity discovery** (Awards, Events, Research, Everything) | Which awards, events and research venues can Retearn enter now? | `BusinessProfile.v2.md` | Opportunity records with a verdict on each entry condition (or a research-fit table) | Works; proven on many runs. Review focus moved to the two watch pipelines |
| **Competitor watch** (the "news" pipeline) | What have competitors and the RVM / deposit-return market done since the last run? | `docs/Competitors.xlsx` + business profile | Signals grouped into 5 digest sections, plus an email digest | **The safest pipeline; nobody raised issues in the review.** Parked since baseline run 5b67df |
| **Component watch** | For each part in a machine's BOM: is the same part cheaper elsewhere, and is there a better or cheaper alternative? | `docs/products/<machine>/ProductProfile.<M>.xlsx` | A verdict per part and three decision sections, plus email and CSV | **Needs course correction.** It does not match what the teams need; see §9 |

---

## 2. Review outcome and what it means (27 Oct 2026)

- **Competitor watch (news):** accepted as it is. It is the safest pipeline. Next steps are
  scheduling and the newsletter (§12.2).
- **Component watch:** the biggest risk of something going wrong, and the build does not match
  the teams' requirements. It needs a course correction before any more tuning. §9.4 lists the
  gaps already known against the original W9 plan and engineers' feedback F23.
- **Opportunity discovery:** stable. Remaining work is measurement, caching and cataloguing
  (W1, W2, W5).

> The review's specific requirements for component watch are not yet written down in this repo.
> Add them to §9.4 when they arrive. Until then, §9.4 lists only the gaps that are documented.

---

## 3. Runtime and stack

**Runs on:** a Windows laptop. Docker Compose provides the services; there is no cloud hosting.

| Piece | Technology | Notes |
|---|---|---|
| Backend | Python ≥3.11, FastAPI + uvicorn, run on the host (not in a container) | `src/opportunity_radar/api/app.py`; also serves the built SPA from `frontend/dist` |
| Orchestration | LangGraph (`StateGraph`, `Send`, `Command`) for opportunity discovery; plain asyncio for both watch pipelines | Checkpoints stored in Mongo through `langgraph-checkpoint-mongodb` |
| LLM | OpenRouter (OpenAI-compatible) through `langchain-openai` `ChatOpenAI` | The model is never hardcoded: `OPENROUTER_MODEL` or a per-run override. Phase 2 runs use `deepseek/deepseek-v4.1-flash`; `qwen/qwen3-32b` was the Phase 1 default |
| Search | **Exa** by default (`/search` with summary, highlights and text); Tavily still selectable for discovery | Exa costs about $0.014 per search on a free monthly credit of $20 |
| Page fetch | Firecrawl, **opportunity discovery only** | Paced one request at a time (`FIRECRAWL_MIN_INTERVAL=7s`) for the free tier's per-minute cap; 1,000 per month, resetting on the 21st. **The watch pipelines never use Firecrawl.** |
| Database | MongoDB 7 (`docker-compose.yml`), PyMongo's native `AsyncMongoClient` | Bound to 127.0.0.1 |
| Tracing | Langfuse v3+ in a separate, on-demand stack (`docker-compose.langfuse.yml`) | Start with `up -d`; stop and wipe with `down -v`. The pipeline runs untraced while it is stopped. Moved out on 20 Oct after ClickHouse filled the disk (row 72) |
| Frontend | React 18 + react-router-dom 6 + Vite 6 | No UI framework or icon package; one stylesheet of CSS custom properties |
| Spreadsheets | `openpyxl` | Product workbook, competitor list |
| Mail | SMTP (Gmail app password) | Recipients come only from `SMTP_TO` |

**Configuration** comes from `.env` (gitignored; `.env.example` lists the names).
`config.require()` raises an error when a value is missing; it never falls back to a default.
Main names: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`,
`SEARCH_PROVIDER`, `MONGO_URI`, `MONGO_DB_NAME`, `LANGFUSE_*`, `SMTP_*`.
`OPENROUTER_RERANK_MODEL` is declared but read by no code.

**Setup**
```bash
docker compose up -d                                   # MongoDB
docker compose -f docker-compose.langfuse.yml up -d    # optional tracing
uv sync
uv run uvicorn opportunity_radar.api.app:app           # API + built SPA
cd frontend && npm run build                           # (re)build the SPA
```

---

## 4. Repository map

About 10,500 lines of Python (about 1,700 of them in `scripts/`) and about 3,000 lines of React.

```
BusinessProfile.v2.md          the business profile every opportunity/competitor prompt reads (fixed sections)
BusinessProfile.md             older profile, kept; v2 is the one loaded
AUDIT.md                       change log rows 1–105, Phase 2 plan W1–W9, Phase 1 audit
docs/
  products/machines.json       product line: ACE, PRO, NEO, FastScan, Global RVM, Line
  products/ace/ProductProfile.ACE.xlsx   ACE parts workbook (gitignored; the only machine with one)
  Competitors.xlsx             watched competitors (gitignored)
  SourcingSites.xlsx           19 seller sites; NOT used by the pipeline (vendors are discovered, not listed)
  *BOM.xlsx                    source BOMs: ACE, Embedded ACE, FastScan, Embedded FastScan, Global RVM, Mini
  graph.md / solution-flow.md  diagrams of the discovery graph
reference/
  spend-ledger.md              every credit-spending run
  exa-pool-652ec9.json, search-tests/   saved search pools for offline re-ranking
src/opportunity_radar/
  config.py tracing.py paths.py        env contract, Langfuse + chat model, repo paths
  profile.py                           loads BusinessProfile.v2.md; profile_section / without_sections
  product_profile.py                   loads and validates the machine parts workbook
  reporting.py                         CSVs and HTML/plain emails for all three pipelines
  discovery/
    workflow.py      (2,289 ln)        opportunity graph: plan → search → rank → fetch → extract → evaluate → store
    types.py                           TypeSpec per opportunity type (any/award/event/research), tracks
    providers.py                       Exa + Tavily search, Firecrawl fetch (paced), link parsing
    link_resolver.py                   bounded same-site traversal, URL canonicalisation, content keys
    agent.py                           run_discovery(): runner, run records, status
    budget.py                          RunBudget: hard caps enforced in code
    state.py                           DiscoveryState, WorkflowRuntime, dataclasses
    actionability.py                   date arithmetic + HTTP status, completeness
    competitor_watch.py (383 ln)       competitor/market news pipeline
    component_watch.py  (642 ln)       BOM component pipeline
  extraction/                          record schema, base-title edition strip, deadline grounding, failures
  eligibility/                         condition-by-condition verdicts vs profile; scoring in code
  storage/                             Mongo client, identity keys, opportunities, programs, runs, failures, dead ends
  api/app.py          (795 ln)         FastAPI: run triggers, reads, delta feed, email, delete/clear
frontend/src/
  App.jsx api.js export.js
  components/ Sidebar RunView Journey Opportunity Overview ExportPanel Signals Components
scripts/
  run_discovery.py competitor_watch.py component_watch.py   CLI runners (component: --only, --all, --test-db)
  search_only.py rank_pool.py          plan+search with no scraping; re-rank a saved pool (one model call)
  email_report.py inspect_state.py show_*.py smoke_*.py verify_storage.py draw_*.py
```

---

## 5. Shared machinery (all pipelines)

### 5.1 Model calls — `workflow._structured()`
- Every call returns **strict `json_schema`** output validated by Pydantic. `_strict_schema()` marks
  every property required, so OpenAI-strict providers accept it.
- Eligibility is the one exception: it still uses `json_object`.
- **Per-call output budgets:**

  | Call | Max output tokens |
  |---|---|
  | plan and search step | 20k |
  | rank | 24k |
  | analyze | 20k |
  | research fit | 20k |
  | competitor judge | 20k |
  | component plan | 20k |
  | component judge | **24k** (the user's ceiling; do not raise it) |

- **Reasoning:** each call asks for a reasoning cap of 40% of its budget, with reasoning excluded
  from the reply. The provider treats this cap as advisory, so the budget must hold both the
  reasoning and the answer. Hitting the cap is a known failure mode: replies get cut off (rows 89,
  103).
- **Timeouts:** 180 s per call, or 300 s for heavy calls, enforced by the caller with
  `asyncio.wait_for`. The HTTP client also has its own 90 s timeout and one retry.
- **When validation fails:** over-long strings and lists are trimmed and the reply is validated
  again. Discovery's per-site analysis can also keep the list items that validate.
  `_parse_json(strict=False)` accepts raw control characters copied from pages (row 87).
- **Tracing:** every call carries a Langfuse `trace_handler()`, and nodes are wrapped in
  `stage_span()`.

### 5.2 Budget — `RunBudget`
- Hard caps on tool calls, searches, scrapes, LLM calls and wall-clock time, enforced in code. A
  prompt asking the model to be frugal is not a budget.
- **Default caps:**

  | Pipeline | Tool calls | Searches | Scrapes | LLM calls | Wall clock |
  |---|---|---|---|---|---|
  | Discovery | 70 | 8 | 20 | 30 | 1,500 s |
  | Competitor | 80 | 40 | — | 15 | — |
  | Component | 240 | 150 | — | 80 | — |

- `POST /api/runs/{id}/stop` cancels a run. Stop uses an in-process registry, so it does not
  survive a server restart.

### 5.3 Runs and the journey
- Each run gets one document in `runs`: run_id, model, status, caps plus live counters, counts,
  warnings, failures, summary and journey.
- Journey rows are appended **as each step finishes**, so a crashed run still leaves a trail. The
  UI polls `/api/runs/{id}/events?after=N`, which returns only rows it has not seen.
- On startup, the server marks any run left `running` as failed (row 88).

### 5.4 Fail loudly
- A broken step stops the run with its error; there is no quiet fallback. Examples: a planning
  failure, a failed search, a bad sheet, a plan that leaves a part out.
- One planned exception: in component watch, a fault in **one part's judge reply** marks that part
  "Could not be judged" and the run goes on. A systemic fault (budget, timeout, rate limit, auth)
  still stops the run.
- Known leftover: the LangGraph progress saver falls back to in-memory storage when Mongo is
  unreachable (AUDIT item 26).

---

## 6. Opportunity discovery (Awards / Events / Research / Everything)

### 6.1 Graph
```
START → plan → search (opening searches + up to 3 ReAct steps) → rank ─┬→ fetch ×N (one per site, parallel) → extract ×N → evaluate → store → END
                                                                         ├→ plan   (nothing passed, once, budget left)
                                                                         └→ evaluate
evaluate → plan (nothing found anywhere, at most once)  |  evaluate → store
```
- A failed or duplicate fetch still passes through `extract` with `bundle=None`. LangGraph's
  `defer` does not wait for `Send` branches, so this is how every site fans in together
  (row 88).
- Saved progress lives in Mongo (`run_progress`, `run_progress_writes`).

### 6.2 Type specs — `discovery/types.py`
- Each type (`any`, `award`, `event`, `research`) is defined as data: its noun, brief, market
  rule, query examples, rank conditions and order, link checklist and record guide.
- **Research** has two tracks: core technology, and research topics / current work.
- **Everything** (`any`) has three tracks (award, event, research), and each track follows its own
  type's rules.
- Geography and sector come only from the profile's **Search constraints** and **Search angles**
  sections, never from code.

### 6.3 Nodes

**1. Plan**
- Writes the opening searches: at least 2, or one per track.
- Each query describes **the page wanted** (Exa's documented practice), for example "nominations
  page for a national award recognising … in …".
- Queries never name a venue or programme from the model's memory (row 57).

**2. Search**
- Runs on Exa with a per-result **structured summary**: programme name, organiser, entry deadline,
  event date, who can enter, country restriction, date quote, key dates, entry status, opportunity
  type and sponsor.
- Highlights are aimed at entry details; research queries use query-guided highlights instead.
- Results that are duplicates by content key or programme key are dropped and logged.
- After the opening searches comes a **ReAct loop** of up to 3 steps. Each step sees every search's
  results (counts by type, past dates, duplicates, titles), writes an assessment and its gaps, then
  runs one more search or stops.

**3. Rank**
- One model call orders the whole pool best-first against the type's numbered conditions:
  - its own page, not a listing or tracker
  - Retearn can enter (company, not individual or student)
  - open (dates decide only open or closed)
  - distinct (one seat per programme)
- It also returns up to 8 excluded results, each with a reason.
- The order is fit, then standing; a sooner deadline only breaks ties. Picks are sized to the
  scrape budget, and each research track gets a seat.
- Nothing is dropped by keyword or regex.

**4. Fetch** (one per site, in parallel)
- Firecrawl reads the seed page; the first page also requests `rawHtml`, so menu links count.
- A link picker reads the page's first 3,000 characters, states what is covered and what is
  missing, then picks 0–2 of up to 60 links.
- Limits: depth and pages per site are configurable.
- Dead ends (seen empty at least twice) are skipped.

**5. Extract** (one per site)
- Under 400 characters of evidence counts as a failed fetch.
- Otherwise one analysis call names the distinct opportunities on the site and decides pursue or
  skip for each. A record then carries:
  - entry conditions
  - judging criteria
  - application requirements
  - a summary
  - dated steps
- Quotes are checked for three fields: organiser, deadline and status. A failed check is recorded,
  and nothing is rejected on it.
- `base_title` (edition stripped in code) feeds the identity key.
- An early-bird date is never the deadline (row 61).

**6. Evaluate**
- Awards and events: `evaluate_criteria()` judges each condition met / not_met / unclear against
  the **full profile**, plus qualitative notes. `confidence` and `score` are computed in code,
  never self-reported.
- Research: `_research_fit()` writes fits / partly / no for each research topic and in-house work
  line, with the matching call topic and a venue note.

**7. Store**
- An atomic upsert on a **unique index** of normalised organiser + base title + cycle year, so
  duplicates are impossible at the database.
- Also records the edition in `programs` (typical window on a 12-month circle).

### 6.4 Measured (end of Phase 1, DeepSeek V4.1 Flash, Exa)

| Measure | Value |
|---|---|
| Model calls per run | 16–19 |
| Model cost per run | ~$0.05 |
| Exa searches per run | 4–5 (~$0.06–0.07) |
| Scrapes per run | 4–14 |
| Wall time | 5–15 min (paced scraping and model thinking) |
| Opportunities saved per run | 1–6 |

Main limits, in order:
1. Link discovery was starved (since partly fixed by `rawHtml` links).
2. Ranking passes fewer sites than there are seats.
3. Budget goes unspent.

---

## 7. Competitor watch (the "news" pipeline)

**File:** `discovery/competitor_watch.py`. It runs only when triggered (UI or `scripts/competitor_watch.py`).

**Three search lanes**, all on Exa, limited to pages published since the last successful run minus
2 days (the first run looks back 90 days):
1. **Site lane:** one search per competitor, limited to that competitor's own domain.
2. **Market lane:** about 8 searches written by the model, half with Exa's `news` category. Each
   must name Retearn's product category or a buyer programme; general waste or recycling news does
   not count.
3. **Name lane:** a name check per competitor (column "Name check").

**Processing:**
- Exact links seen before (`competitor_seen`) are skipped. Code compares only exact links and
  dates.
- The judge reads pages in batches of 20, with today's date and the last 30 days of signals. For
  each page it decides:
  - keep or drop
  - who the page is about: a competitor from the list, `own group: …` (Recykal is never a
    competitor), `new entrant: …`, `other company: …` or `market`
  - **section**: Act on this (only while a deadline is ahead), Competitor moves, Market and
    policy, New entrants and other companies, or Own group
  - kind, date (read from the text), importance (anchored: high / medium / low), why it matters
    and headline (in English)
  - `same_story_as` (an earlier signal) and `duplicate_of` (a repeat within the batch)
- **What code then does:**
  - repeats are merged into the story page's `also_reported_by`
  - low-importance pages are recorded as `context` (seen, not signals)
  - everything else is stored in `competitor_signals`

**Digest:** `run_digest()` groups a run's signals by section, high importance first, plus
"Following up" for earlier stories this run added coverage to. It uses the judge's own words, with
no second model call. A model-written digest was tried and dropped (row 75).

**Proven runs:**
- 617d7f: 11 on-market signals, including two biddable RVM tenders.
- cb25a6: 38 signals in 5 sections, 297 s.
- 5b67df: the current baseline.
- A full run (11 competitors) takes about 30 searches and about 10 model calls.

**Open polish:**
- Tender links point to listing sites, not the official notice.
- Importance is not fully consistent.
- A full run takes about 5–12 minutes because judge batches run one after another.

---

## 8. Data inputs

| File | Owner | Shape | Read by |
|---|---|---|---|
| `BusinessProfile.v2.md` | us + manager | Fixed `##` sections: Search constraints, Search angles, Identity, Business, Technology, Operations, Evidence, Recognition history, Known exclusions, Reading notes | Discovery (all prompts), competitor watch |
| `ProductProfile.<M>.xlsx`, sheet **Parts** | engineering teams | **Exactly these columns:** Part ID, Subsystem (Embedded / Electrical / Mechanical), Item, What it does, Manufacturer, Part number, Qty per machine, Rate (₹, before GST), Vendor, Why chosen, Must Have (`;`-separated), GST %. **No other columns may be added** (the team rejected extras) | Component watch |
| `Competitors.xlsx` | team | Competitor, Website, Watch (yes/no), Name check | Competitor watch |
| `machines.json` | us | name + key per machine; a machine can be selected once its workbook exists | Component machine picker |

**ACE workbook status:**
- 64 parts: 15 custom, 49 off the shelf. Total ₹2,40,596 per machine before GST.
- Every line matches the Embedded ACE BOM.
- Some values are **demo assumptions marked "(assumed)"**, approved by the user:
  - the Jetson kit description and its Must Have (AI ≥0.5 TOPS, ≥4 GB, CSI-2, ≤15 W, GbE + USB 3.0,
    production module)
  - closest-fit model numbers for 9 parts that had none: Fan-4010-5V, TD1655, GS-11PC, GL-R series,
    A9F54263, EZ9R35225, DHSA2NAN40320, Exide Star 850VA, EP42-12
- **Open data items:** ACE-064 qty, ACE-025 wire unit, ACE-011 rate (₹550 vs a market price of about
  ₹1,238).

---

## 9. Component watch

**File:** `discovery/component_watch.py`. It runs only when triggered (UI or `scripts/component_watch.py`).

### 9.1 Flow
1. **Load** the workbook. The loader stops with the column or row at fault, and a blank GST % is
   refused. `Part.brief()` is the **only** text a prompt gets about a part: item, what it does, qty,
   current model, vendor, Why chosen and Must Have. **Our rate never reaches the model.**
2. **Plan** (one model call per 16 parts). For each part the model decides:
   - `off_the_shelf`, with a reason (custom parts are never searched)
   - `same_part_query`: one sentence describing an Indian seller's page for the exact current model
   - `alternative_query`: one sentence describing a page for a newer or more capable replacement,
     either the same maker's successor or another maker's equivalent. It names the current model as
     what is being replaced and states the needs as minimums ("at least …"), never the current
     model's exact figures.

   Both searches leave out certifications and the current vendor, and name no maker or model the
   brief does not name.
3. **Scope** (computed in code):
   - `priority` (default): the off-the-shelf parts making up 80% of off-the-shelf cost per machine
     (13 of 49 on ACE)
   - `all`: every off-the-shelf part
   - `--only`: the named parts
4. **Search** (Exa, 5 results per search, up to 10 pages per part):
   - highlights steered at price, pack size, GST, stock and specs
   - page text capped at 3,000 characters (1,400 reach the judge)
   - 4 parts run at a time, in an `asyncio.TaskGroup`, so a systemic failure cancels the rest
   - **There is no ranking step.** Exa's top 5 for each search go straight to the judge.
5. **Judge** (one call per part, 24k output tokens). Every page gets its own required slot
   (`page_0 … page_N`, a schema built per call), so a reply that leaves a page out fails instead of
   losing it silently. For each page the judge returns:
   - **page and seller:** page kind (seller listing / manufacturer page / other); product, maker,
     seller, seller kind (maker / authorised distributor, only when the page says so / other)
   - **price** (read before any notes): the price as printed, GST basis (included / excluded / not
     stated; MRP counts as included), currency and rupee flag, price unit and units per part (for
     packs and lengths), price unclear, stock
   - **fit:** relation (same part / alternative); effort (drop-in / minor changes / major changes /
     needs verification); what would change; offers (newer model / better spec / more efficient)
     with the reasons
   - **checks and notes:** Must Have checks (met / not met / unclear); certifications the page
     states (never inferred); discontinued; concerns
6. **Drop** (in code, from the judge's labels):
   - not kept: documentation, broker pages, comparison sites, category pages, wrong kind of product
   - out of stock, discontinued, or priced in a currency other than rupees

   These are never stored; the run trace lists each one with its reason.
7. **Price maths** (code only, `price_difference`):
   - **The seller's price is never changed.**
   - When their price includes GST, **our** rate is grossed up: `rate × (1 + GST %)`. Otherwise
     ours is compared before GST.
   - The only conversion is × units per part.
   - Outputs: per-unit difference %, per-machine theirs and ours, and saving per machine.
8. **Decide per part** (`part_decision`, in code). The verdict is one of:

   | Verdict |
   |---|
   | Cheaper seller found |
   | Cheaper drop-in found |
   | Changes needed to save |
   | We pay the lowest found |
   | No comparable price |
   | Could not be judged |
   | Nothing found |
   | Low spend, not searched this run |
   | Custom, not searched |

   Rules that apply across sections:
   - "Price unclear" findings are shown but never counted.
   - "Needs verification" is never an alternative.
   - Options whose page names no maker, or that fail a Must Have, are kept out of sections 2 and 3.
   - Makers and authorised distributors are preferred in the top sections.
9. **Present** — email, dashboard and CSV share one wording from `price_display`. Each starts with
   three sections:
   1. **Same part, cheaper seller**
   2. **Better or newer** (drop-in, then minor changes, then major changes)
   3. **Cheaper alternatives** (fits as is first, then needs adaptation)

   Then "everything else found, by part". Certifications sit beside each listing. Tags are one or
   two plain words.
10. **Procurement check:** `PATCH /api/components/offers/{id}` records whether a finding held up
    (holds / does not hold) when procurement asked the seller. This feedback loop is built; nobody
    uses it yet.

### 9.2 Runs, numbers and what was learned

| Run | Scope | Result |
|---|---|---|
| 15a5c8 (21 Oct) | full ACE | 364 findings; leads were small (~1% of the machine); vague parts got generous drop-in labels; unit mismatches gave false savings |
| a4ec6b (23 Oct) | full ACE, 49 off the shelf, 67 searches, 53 calls | 4 same-part savings (₹764 per machine), 2 better or newer, 2 cheaper alternatives, 9 parts where we already pay the lowest. Accepted for the review; 38 of 531 pages had been silently skipped by the judge |
| 345164 / 49fef4 / ddc28b (26 Oct) | 8-part tests | showed the judge skipping pages, then being cut off at 24k tokens, then fixed at 5 results per search |
| 72fe64 (26 Oct) | full ACE, 46 off the shelf | 157 comparable prices (vs 122), 14 parts at lowest (vs 9), 0 pages lost; but 5 parts cut off, and Jetson's alternative search described the Nano itself |

**Running cost:** a full ACE run is about 67–69 Exa searches (about $1) and about 50 model calls,
taking about 10 minutes.

**What a scrutiny of the record shows:** about 30 rows of the change log (rows 78–105) were
prompt or rule fixes, each tested by eye on one live run. Every fix moved the problem somewhere
else. There is **no fixed, labelled reference set**, so nobody can say whether a change helped.

### 9.3 Design rules for this pipeline (from the user; keep them)
- Vendors are **discovered on the open web**. No vendor list limits the search or decides a label.
  `SourcingSites.xlsx` is not used.
- No string-matching, regex or grounding gates decide what is shown or dropped. The judge's labels
  decide, and code does the comparison and the percentage.
- Our rate stays local and never goes into a prompt.
- The model never compares prices across pages; code does the price arithmetic.
- Out of stock, discontinued and non-rupee listings never get past the judge.
- No Firecrawl here.
- The workbook keeps exactly the team's columns. When something more is needed, infer it from the
  data and pages; don't add a column.
- Decisions about what is shown, dropped or counted go to the user first.

### 9.4 Course correction — gaps known so far

These are documented gaps between the build and its requirements. The review's own list should be
added here.

1. **The wrong shape of search.** Engineers asked (F23) for a **deliberate, on-demand search for
   one chosen component**. What was built sweeps every part of a machine on a schedule-like scope
   (priority 80% / all).
2. **Sources.** The W9 plan named **distributor APIs** (Octopart/Nexar, DigiKey, Mouser) for price
   breaks, stock and lead time, which are structured, current and within terms of use. The build
   instead reads open-web pages through Exa. Exa's top 5 are unranked and often not the best seller
   pages, and stock and price are read from page snippets of at most 1,400 characters.
3. **Missing data the plan asked for.** Datasheet specs as the source of Must Have checks, price
   breaks and minimum order, lead time, single-source or import risk, annual volume, and
   requalification effort. None of these are captured.
4. **The input brief is thin.** Several parts lack Why chosen or Must Have, and 9 model numbers
   and the Jetson spec are assumptions. The judge's effort labels are only as good as the brief.
5. **No measurement.** There is no labelled set, no saved page text, and no replay. Each run is a
   fresh, non-reproducible sample (Exa results drift between runs).
6. **Judge capacity.** One reply per part, judging up to 10 pages, sits close to the 24k cap.
   Parts get cut off (5 of 46 in 72fe64).
7. **Value framing.** Savings found are small (about ₹300–800 on a ₹2.4 lakh machine). The parts
   that cost the most (stepper, Keyence interlocks, light curtain, inverter, battery; about ₹60k)
   gave no comparable price, because they are sold on quote or have no model number.
8. **Only one machine.** ACE is the only machine with a workbook. The business profile's product
   line (Reklaim PRO, ACE, Mini, Neo, FastScan) differs from `machines.json`.

Fixes already agreed for after the demo:
- save page text per run
- build a fixed, labelled reference set and score every change against it before it goes in
- clean up tags ("drop-in" vs "fits as is"; how page kind is displayed)

---

## 10. Storage — Mongo collections

| Collection | Key / index | Holds |
|---|---|---|
| `opportunities` | unique: normalised organiser + base title + cycle year | opportunity records with eligibility or fit, record_state, evidence URLs, grounding, discovery_run_id (the last run that wrote it) |
| `programs` | unique: organiser + base title | editions and typical window |
| `runs` | run_id | every run of every pipeline (`budget.focus` = award/event/research/any/competitors/components), journey, counts, warnings, failures |
| `run_progress`, `run_progress_writes` | LangGraph | discovery checkpoints, so a run can resume |
| `extraction_failures` | source URL | typed extraction failures; cleared on a later success |
| `dead_ends` | url (unique) | pages fetched that gave nothing; skipped after being seen empty twice |
| `competitor_signals` | signal_id (unique), first_seen_at | signals with section, importance, also_reported_by |
| `competitor_seen` | url (unique) | every judged page: kept / merged / context / dropped, with a reason |
| `component_offers` | offer_id | one kept finding per page per part, with judge fields, price maths and procurement check |

- Deleting a run also deletes its signals, seen pages and component findings.
- Deleting a run never deletes opportunities, because a record may have been confirmed by later
  runs.
- "Clear database" wipes every collection and needs the JSON body `{confirm: "delete everything"}`.
- Backup: `backups/radar-mongo-20261020.archive.gz` (gitignored).

---

## 11. API and UI

### 11.1 Endpoints (`api/app.py`)

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Mongo ping |
| `GET /api/state` | overview: stored opportunities, programmes, run list |
| `POST /api/pipeline` · `POST /api/runs` | discovery run; body `RunConfig` (model, 5 caps, reach limits, focus, provider, queries, dry_run) |
| `POST /api/competitors/runs` | competitor run; 400 when the sheet is bad |
| `POST /api/components/runs` | component run (product, scope, only); 400 when the workbook is bad |
| `GET /api/components/machines` | the product line and which machines have a workbook |
| `GET /api/runs/{id}` · `/events?after=N` · `/results` · `/signals` · `/components` | run detail, delta feed, opportunity results, competitor digest, component decisions (409 for runs stored before per-unit pricing) |
| `PATCH /api/components/offers/{id}` | procurement's holds / does-not-hold check |
| `GET /api/mail` · `GET/POST /api/runs/{id}/email` | recipients, email preview, send (SMTP_TO only) |
| `POST /api/runs/{id}/stop` · `DELETE /api/runs/{id}` · `POST /api/database/clear` | stop, delete, wipe |

**No authentication.** It is a local, single-user tool. Runs execute as FastAPI background tasks.

### 11.2 Dashboard (React SPA)
- **Sidebar:**
  - "Looking for": Awards / Events / Research / Everything / Competitors / Components
  - machine picker and "Parts to search" (Top 80% / All) for Components
  - search provider, budget caps, reach limits
  - the run list
- **Run view** (`/run/<id>`): the journey is the pipeline's own steps, with each step's reasoning,
  the raw event and the fetched page text.
  - Opportunity runs: Results and Set aside tabs.
  - Competitor runs: a Signals tab (cards by section).
  - Component runs: How it ran (live per-part status), Decisions (the three sections) and Parts
    (one row per BOM part, filterable, expanding to every finding).
  - Every run: an Export panel (CSV, email preview, run log).
- **Overview** (`/`): every stored opportunity and the programme registry.

### 11.3 Email (`reporting.py`)
- Every run mails a readable HTML body (inline styles, with a plain-text copy) and attaches the CSV.
  - Opportunity runs: grouped by type.
  - Competitor runs: grouped by digest section.
  - Component runs: the three sections, then each part's top 5 findings with "N more".
- All page text is HTML-escaped. Gmail clips messages over about 102 KB, which is why the
  component email is trimmed.

---

## 12. Future scope

### 12.1 Component watch — course correction (first priority)
1. **Capture the teams' requirements** in writing (§9.4) and agree on the target shape before
   writing any code.
2. **Likely target shape**, to confirm with the teams:
   - an **on-demand search for one chosen component**, as engineers asked (F23), as well as or
     instead of a whole-BOM sweep
   - each must-have spec checked against the **datasheet**
   - **distributor APIs** for price breaks, stock and lead time
   - effort and requalification shown to a person, never decided in code
3. **Measurement before tuning:**
   - save the page text for each run
   - build a labelled reference set (correct same part, correct effort, correct price and GST
     basis, correct drop)
   - a replay harness that re-judges saved pages and scores each change against the labels before
     it ships
4. **A component catalogue (W2):** component → alternatives → last price, stock and date checked,
   so a part is re-checked rather than rediscovered every run.
5. **Choosing what to search:** by annual spend (rate × qty × machines per year), then risk (single
   source, lead time, import), then swappability. This needs data from the inventory team (W9 data
   request).
6. **Other machines' workbooks:** PRO, NEO, FastScan, Global RVM, Line. The source BOMs are already
   in `docs/`.
7. **Model capacity:** a stronger or larger-context model for the judge, or a reply split into more
   than one call per part, instead of raising the output cap.

### 12.2 Competitor watch → newsletter
- **Scheduled weekly runs** (no Exa Monitors: they need a public webhook and have no news or date
  filter).
- **Newsletter:** run the pipelines in parallel and send one email digest of new competitor
  signals, new or closing opportunities, and component leads. It reuses `run_digest()`, the mailer
  and `SMTP_TO`. This is the manager's "parallel newsletter" item.
- Polish: link to official tender notices, make importance consistent, run judge batches in
  parallel.

### 12.3 Opportunity discovery (Phase 2 plan, AUDIT W1–W8)
- **W1 measurement:** label the stored Exa results and candidates; replay ranking, extract and
  evaluate offline; score each change in minutes. This was never started. It is the same gap as in
  component watch.
- **W2 cache and catalogue:** a search cache, a page cache, and a programme catalogue (names and
  aliases, editions, next window). Two kinds of run: refresh what is known, and discover what is
  not. It fixes "one programme under two titles" (item 31). The manager paused it on 14 Oct; the
  design was liked.
- **W3 search economy:** 10 results per search, directory pages become leads, type enforced as
  data, a budget per type.
- **W4 re-ranker test** (Qwen3-Reranker or Cohere) against the labels, adopted only if it beats the
  current ranking.
- **W5 confidence:** fit and certainty kept as separate tiers with reasons, never one number;
  evaluation sees the source passage for each condition; code checks that every condition comes
  back exactly once.
- **W6 record shape per type**, partly done through type specs.
- **W7** a rolling window (e.g. 6 months), scheduled runs, and an email digest of what is new,
  changed or closing within 14 days.
- **W8** a model per call type; one server-built CSV; delete `profile_seed.py`; rewrite `CLAUDE.md`.

### 12.4 Platform
- **Deployment:** containerise the app; hosting; authentication before any shared use; a scheduler.
- **Provider abstraction**, if moving off OpenRouter (for example to Bedrock): today `chat_model()`
  returns `ChatOpenAI` pointed at OpenRouter.
- **Adapting for Recykal:** the profile and workbooks are already data; the prompts read
  "this business" from the profile.
- **Audit stage 3**, still open:
  - fail loudly in 4 more places
  - an eligibility count check
  - a guard against formulas in the CSV
  - refuse a duplicate run

---

## 13. Rules that govern how this project is built (for Claude)

These come from the user. Follow them in any future session.

1. **The user runs commands.** Hand over command blocks. Never run live runs that spend credits;
   any spend needs an explicit yes. Never read `.env`.
2. **Propose before implementing.** State the plan (exact file, before and after text, which runs
   it affects), wait for agreement, then write the code. Say when a check is manual.
3. **Root cause, not patches.** Diagnose why the mechanism is wrong and measure before claiming a
   fix. The user's main criticism of component watch was cycles of patches with no measurement.
4. **Fail loudly.** No fallbacks that degrade quietly.
5. **No string-matching gates.** Never drop model output on URL, word or date string checks. The
   model judges meaning; code does arithmetic and parses formats we own.
6. **Searches describe the page wanted and never name things.** No venue, programme or vendor names
   from model memory. Check every track a shared prompt change reaches.
7. **Ask what is shown, dropped and counted.** Product decisions go to the user. Drop what nobody
   can act on.
8. **Verify library APIs** against the installed version before writing code.
9. **Comments** are one or two lines, with no stories about past bugs, in code and in prompts.
10. **Call the organisation Retearn.** Tags are one or two plain words.
11. **Explain the flow first, then the details.** Present the simplest chunked flow first, then the
    specifics of each step.
12. **Budget:** free tiers. Replay before going live; one live run per milestone; log every spend in
    `reference/spend-ledger.md`.
13. **Model choice:** `qwen/qwen3-32b` and `deepseek/deepseek-v4.1-flash` work with strict JSON.
    `google/gemma-4-31b-it` degenerates on `json_schema`.

---

## 14. Timeline

| Date | Milestone |
|---|---|
| Sep 2026 | Stages 0–6: storage, extraction, eligibility, discovery graph, UI (commits 51b0f20 → 97b093c) |
| 21–28 Sep | Phase 1 audit (AUDIT Groups A–E); graph split into 7 nodes with per-site fan-out; Exa replaces Tavily; email export |
| 28 Sep | **Phase 1 presented** |
| 5–16 Oct | Phase 2: type specs, ReAct search, Research track (two tracks, fit table), Events conditions, Everything as three tracks; stored-programme lines removed from prompts after an A/B test |
| 14–15 Oct | Manager: catalogue paused; priorities set as (1) the main tracks reliable, (2) competitor and component watch, (3) parallel newsletter plan |
| 19 Oct | Presentation |
| 20–21 Oct | Competitor watch built, live-tested and put in the UI; disk recovery; Langfuse made on-demand |
| 21–26 Oct | Component watch on ACE: about 10 live runs, rows 78–105 |
| 26 Oct | Demo freeze |
| 27 Oct | **Phase 2 review:** the news pipeline is safe; component watch needs course correction |
