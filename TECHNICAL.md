# TECHNICAL.md — Opportunity Radar, Phase 1 checkpoint

**Status:** Phase 1 complete (Stages 0–6 per `CLAUDE.md`). Last verified clean run:
`qwen/qwen3-32b`, 32/50 tool calls, 4 opportunities saved, 0 rejected, 0 failed.

**Purpose of this document.** A single technical reference for the system as it
actually stands — every component, flow, contract, limit and known defect — written
so that Phase 2 can be planned against facts rather than impressions. Every claim
below is verified against the code at the commit this was written on; file and line
references are given so anything can be checked.

**Authority.** `CLAUDE.md` remains the spec. This document describes the
implementation of that spec, including the places where implementation and spec have
drifted. Where they disagree, that disagreement is called out explicitly.

---



## 1. What the system does

Given a business described in `BusinessProfile.md`, the pipeline:

1. plans web searches for awards and recognition programmes the business could enter,
2. searches, selects promising results, and fetches their pages,
3. identifies distinct opportunities on each site and decides whether to pursue them,
4. extracts a structured record per opportunity,
5. checks it is still actionable, stores it, and records the edition against a
  recurring-programme registry,
6. judges the stored eligibility conditions against the full business profile,
7. presents all of it on a single read-only page.

**It is decision support only.** Nothing submits an application, contacts an award
body, or writes to the business profile. The last action in the pipeline is always a
stored record.

**Scope note.** Grants, funding and fellowships are excluded from discovery — the
business wants recognition, not money. `"grant"` remains in the stored `category`
enum for backward compatibility with records already saved, but nothing new should
arrive with it.

---



## 2. Runtime topology

Docker Compose only; no cloud hosting in Phase 1. Seven containers.


| Service           | Image                        | Port                | Purpose                                                    |
| ----------------- | ---------------------------- | ------------------- | ---------------------------------------------------------- |
| `mongodb`         | `mongo:7`                    | 127.0.0.1:27017     | `opportunities`, `programs`, `runs`, `extraction_failures` |
| `langfuse-web`    | `langfuse/langfuse:4`        | 3000                | Trace UI                                                   |
| `langfuse-worker` | `langfuse/langfuse-worker:4` | 127.0.0.1:3030      | Trace ingestion                                            |
| `postgres`        | `postgres:17`                | 127.0.0.1:5432      | Langfuse metadata                                          |
| `clickhouse`      | `clickhouse-server:25.12`    | 127.0.0.1:8123/9000 | Langfuse trace store                                       |
| `redis`           | `redis:7`                    | 127.0.0.1:6379      | Langfuse queue                                             |
| `minio`           | `chainguard/minio`           | 127.0.0.1:9090/9091 | Langfuse blob store                                        |


Six of the seven exist because Langfuse v3+ requires them. That is upstream's design,
accepted knowingly (`CLAUDE.md` constraint).

The application itself is **not containerised** — FastAPI runs on the host via
`uvicorn`, and serves the built React SPA from `frontend/dist` as static files.

### External services


| Service    | Used for              | Configured by                            |
| ---------- | --------------------- | ---------------------------------------- |
| OpenRouter | every LLM call        | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` |
| Tavily     | web search            | `TAVILY_API_KEY`                         |
| Firecrawl  | page fetch → markdown | `FIRECRAWL_API_KEY`                      |




### Configuration contract

All configuration is environment-driven via `.env` (gitignored, never committed).
`config.py:require()` raises rather than defaulting, so a missing variable fails
loudly instead of running against the wrong model or an untraced endpoint.

**The model is never hardcoded anywhere.** `chat_model()` reads `OPENROUTER_MODEL`,
and a per-call `model` argument overrides it — that is how two models are compared in
one run.

Notable variables:

- `OPENROUTER_MODEL` — the one reasoning model used by **every** node and stage.
- `OPENROUTER_TEMPERATURE` — applies to **Discovery only**. Unset means provider
default. Extraction and eligibility deliberately do not read it
(`config.py:58-76`).
- `OPENROUTER_RERANK_MODEL=cohere/rerank-4-fast` — **declared in** `.env.example` **but
read by no code.** Left over from a deleted experiment (see §12).
- `MONGO_URI`, `MONGO_DB_NAME` — note the names; not `MONGODB_URI`.
- `BUSINESS_PROFILE_PATH` — optional, defaults to `BusinessProfile.md` at repo root.

---



## 3. Repository map

~5,200 lines of Python across 34 modules, plus a ~2,000-line React frontend.

```
src/opportunity_radar/
├── config.py            env contract; require() raises on missing
├── tracing.py           chat_model(), trace_handler(), stage_span()
├── profile.py           loads BusinessProfile.md
├── paths.py             repo-root anchored paths
│
├── discovery/           ← the agentic half
│   ├── agent.py         run_discovery() — public runner, run records, status
│   ├── workflow.py      the LangGraph graph, all 4 nodes, all 4 prompts  (1,084 ln)
│   ├── state.py         DiscoveryState, EvidenceBundle, CandidateVerdict, runtime
│   ├── budget.py        RunBudget — hard caps enforced in the tool wrapper
│   ├── providers.py     tavily_search(), firecrawl_fetch()
│   ├── link_resolver.py bounded same-site traversal, URL canonicalisation
│   ├── profile_seed.py  distils BusinessProfile.md for the planner
│   └── actionability.py date arithmetic + HTTP status; completeness checks
│
├── extraction/          ← plain functions, not an agent
│   ├── extract.py       extract() → record | typed failure            (520 ln)
│   ├── schema.py        OpportunityRecord, strict pydantic validation
│   ├── failures.py      FailureReason enum
│   ├── grounding.py     deadline_verified — string check, not model opinion
│   ├── base_title.py    edition/year stripping — 16 regexes (see §11)
│   └── golden.py        loads golden_set/extraction-examples.md
│
├── eligibility/         ← one LLM call per opportunity
│   ├── evaluate.py      evaluate() / evaluate_criteria()
│   ├── schema.py        CriterionResult, QualitativeNote, EligibilityResult
│   ├── scoring.py       confidence, score, classification audit — all plain fns
│   └── criteria_sets.py loads the 5 hand-written reference sets
│
├── storage/
│   ├── client.py        AsyncMongoClient; unique identity indexes
│   ├── identity.py      normalisation for the identity keys
│   ├── opportunities.py save_opportunity() atomic upsert; attach_eligibility()
│   ├── programs.py      record_edition(), due_soon(), known_orgs(), typical_window
│   ├── runs.py          run records + append-as-you-go journey
│   └── failures.py      extraction failure records
│
└── api/app.py           FastAPI — reads, run triggers, delta feed       (542 ln)

frontend/src/
├── main.jsx             BrowserRouter mount
├── App.jsx              layout shell, routes, run lifecycle, config persistence
├── api.js               fetch helper, stage maps, config <-> request mapping
├── export.js            CSV builders, download, clipboard
├── icons.jsx            inline stroke icons (no icon dependency)
├── styles.css           design tokens, light/dark, all layout
└── components/
    ├── Sidebar.jsx      configurator, budget caps, run list, collapse rail
    ├── RunView.jsx      one run: header, meters, tabs, delta polling
    ├── Journey.jsx      stage passes, step cards, reasoning, final output
    ├── Opportunity.jsx  one stored record with its eligibility table
    ├── Overview.jsx     everything stored across all runs + programme registry
    └── ExportPanel.jsx  CSV preview, download and copy

golden_set/              Stage 0 reference data (extraction + eligibility)
retrieval_set/           207 hand-labelled search results (see §13)
scripts/                 run_discovery, run_eligibility, run_golden_set, smoke tests
```

Frontend dependencies are React, `react-router-dom` and Vite. No UI framework, no
icon package, no CSS framework — icons are inline SVG and styling is one stylesheet of
CSS custom properties. Geist and Geist Mono load from Google Fonts with a full system
fallback stack, so an offline first paint still renders correctly.

---



## 4. Data model



### `opportunities`

Identity key: `norm_organizing_body + norm_base_title + cycle_year`, **unique index**
(`storage/client.py:33-37`). "Never a duplicate" is enforced at the database, not in
application logic, so a bug in the upsert path surfaces as an error rather than a
silent duplicate.

```
title, organizing_body, base_title, cycle_year, category
eligibility_criteria: [str]        # individually stated conditions
submission_deadline: str|null      # ISO
deadline_note: str|null            # for rolling/relative deadlines
deadline_verified: bool            # grounding check, never the model's opinion
event_date: str|null
source_url, evidence_urls: [str]
actionability: "actionable"        # only actionable records are stored
extraction_completeness: {score, identity, open_state, deadline,
                          eligibility, source_coverage, gaps[]}
judging_criteria: [str]            # from analyze
application_requirements: [str]    # from analyze
confidence_note: str|null          # the extractor's own stated uncertainty
discovery_run_id                   # last run to write this record, not an owner
eligibility: {…}                   # attached later by the Eligibility Agent
```

Two fields deserve a note.

`confidence_note` is the model's one-sentence statement of what it was unsure about.
The extraction schema has always required it, but `_build_record()` never read it, so
it was generated and discarded on every extraction. It is now stored, traced and
displayed. **This field is not in `CLAUDE.md`'s schema** — it is an additive, optional
extension.

`discovery_run_id` records the **last** run to write the record, not the run that owns
it. Because records are upserted on their identity key, a later run that re-finds the
same opportunity overwrites it. Nothing should treat this field as "which run found
this" — the per-run views derive that from each run's own journey instead.



### `programs`

Identity key: `norm_organizing_body + norm_base_title` (no year), unique index. One
document per recurring programme; each year it runs is an edition.

```
organizing_body, base_title
editions: [{year, deadline}]
typical_window: {month_start, month_end} | null   # null until 2+ dated editions
```

`typical_window` is computed on a **12-month circle**, so a programme running Nov–Jan
yields `{11, 1}` rather than the nonsensical `{1, 11}` a naive min/max gives
(`storage/programs.py:26-49`).

`record_edition()` is wired inside `save_opportunity()` rather than at the call site,
so the registry cannot drift out of sync with what was actually stored
(`storage/opportunities.py:56-63`).

### `runs`

One document per run, with the journey appended **as it happens** so a crashed run
still leaves a readable trail.

```
run_id, model, status, started_at, finished_at
budget:   { tool_calls, max_searches, max_scrapes, max_llm_calls,
            wall_clock_seconds,            # the caps this run was configured with
            spent, searches, scrapes, llm_calls, elapsed,   # live counters
            stop_reason }
counts:   { searched, scraped, extracted, extraction_failed,
            saved, rejected, historical, failed }
queries:  [str]        # caller-supplied, empty when the planner wrote the plan
thinking: [str]        # each planned query with its rationale
warnings: [str]        # per-record caveats, accumulated
failures: [str]        # provider and model failures during the run
summary, trace_url
journey:  [ … ]        # one row per tool call
eligibility_done, eligibility_evaluated, eligibility_failures
```

`budget` carries both the caps and the live counters. `append_event()` `$set`s the
counters on every journey push, which is what lets the UI meter a run while it is still
going; `finish_run()` rewrites the whole field with `caps() | live()`. An earlier
version wrote only the counters at the end, silently dropping the caps.

`warnings` and `failures` were computed on every run and never persisted, so nothing
downstream could show that a stored record came with caveats.

**Journey rows** are `{seq, t, tool, node, outcome, …}` where `seq` is the 1-based
position. Because `_record()` swallows a failed Mongo write, `seq` can contain gaps
while positions stay contiguous — which is why the delta endpoint slices by position
rather than by `seq`.

A `scrape` row additionally carries `page_title`, `page_description`, `links_found`,
and `preview` — the first 20,000 characters of the fetched markdown, the same bound
extraction reads, so what the model actually saw is inspectable after the fact.

### `extraction_failures`

Typed failures keyed by source URL, cleared when a later run succeeds on the same URL.

### Identity normalisation

`storage/identity.py:26-41` — NFKD unaccent, lowercase, strip punctuation, collapse
whitespace, drop a leading article. `"  The  CII, Ltd. "` → `"cii ltd"`.

**Deliberately no alias table.** The system does not know that "CII" and
"Confederation of Indian Industry" are one body, and treats them as two programmes.
Known and accepted limit.

---



## 5. The discovery graph, in detail

### Why a graph rather than a free-form agent

The Discovery Agent is a **bounded LangGraph state machine**, not a model in a
tool-calling loop. The model makes every judgement that requires reading meaning —
what to search for, which results matter, which links to follow, what counts as an
opportunity, whether to pursue it — but it never decides *what happens next*. The
sequence of stages, the caps on each, and the single re-plan are fixed in code.

This matters for cost and for reproducibility. A free-form agent can spend an
unbounded number of calls deciding it needs one more search; this graph cannot. Every
run visits the same four nodes in the same order, and the only branch is a single
optional loop back to planning.

### The state object

`DiscoveryState` (`discovery/state.py`) is a `TypedDict` threaded through every node.
LangGraph merges each node's returned dict into it.

| Field | Written by | Carries |
| --- | --- | --- |
| `as_of_date` | runner | The run date, injected so "this year" is never the model's guess |
| `supplied_queries` | runner | Caller-supplied queries; non-empty disables planning **and** re-planning |
| `memory` | `plan_queries` | Distilled profile + known organising bodies + programmes due soon |
| `planned_queries` | `plan_queries` | `PlannedQuery(query, intent, geography, target_year, rationale)` |
| `search_hits` | `research` | Every `SearchHit` seen this run, deduplicated by canonical URL |
| `evidence_bundles` | `research` | `EvidenceBundle(seed_url, pages)` — the fetched pages per seed |
| `candidates` | `analyze` | `CandidateVerdict` — one per opportunity identified, pursue or skip |
| `analyzed_seeds` | `analyze` | Seeds already analysed, so a re-plan does not pay to analyse them twice |
| `analysis_errors` | `analyze` | Per-bundle failures, which also suppress the re-plan |
| `rejected` | `finalize` | Candidates that did not become records, with the stage that stopped them |
| `summary` | `finalize` | One-line account of the run |
| `replan_count` | `analyze` | Incremented only when a pass yielded nothing; caps the loop |

Alongside it, `WorkflowRuntime` is a plain dataclass holding the things that are *not*
graph state — the database handle, the `RunBudget`, the model id, the run id, and the
accumulating `journey`, `saved`, `failures`, `warnings` and `historical` lists. It is
bound into each node with `functools.partial`, so nodes stay pure functions of state
plus services.

### Graph shape

```
START → plan_queries → research → analyze ─┬─ something to pursue ──→ finalize → END
             ↑                             ├─ analysis errored ─────→ finalize → END
             └────────── replan ───────────┘   (at most once)
```

Compiled in `build_discovery_graph()`. `recursion_limit` is 10: one optional re-plan
means at most seven node executions, so the limit can only be reached by a bug.

Every node is wrapped by `_traced_node`, which opens a Langfuse span named
`discovery.<node>` and attaches the budget before and after. That is why a trace shows
model calls nested under the stage that made them rather than as a flat list.

---

### Node 1 — `plan_queries`

**Reads** `as_of_date`, `supplied_queries`, `memory`.
**Writes** `memory`, `planned_queries`. **Costs** one model call (`plan`).

Three paths, in priority order:

1. **Caller supplied queries** — wrapped as `PlannedQuery` with
   `intent="mixed"`, no model call. This also disables re-planning, because the caller
   asked a specific question and a re-plan would silently change it.
2. **Dry run** — three fallback queries from the profile, no network.
3. **Normal** — one strict `json_schema` call returning exactly six queries.

Before the call, `_memory()` assembles what the planner is allowed to know:
`discovery_seed()` (five verbatim profile sections), `known_orgs()` (organising bodies
already in the registry) and `due_soon(lookahead_months=2)` (programmes whose typical
window is about to open). The planner is told what has already been found so it does
not spend the run rediscovering it.

The prompt's governing rule is query length:

> **KEEP EACH QUERY SHORT — three or four content words.** A search engine returns only
> pages matching every word you give it, so each extra word narrows the results.

It also bans quotation marks, unexplained acronyms, product and hardware category
names, and copying programme names out of the profile; and it directs variation across
the field named, whether a year appears, the kind of recognition, the kind of body that
runs it, and company stage. Four or five queries must name the primary market.

**Geography and sector are read from `BusinessProfile.md`, never from code.** An
earlier version hardcoded a region into the prompt and pointed an entire run at a
market the business has no presence in.

**On failure** `_fallback_queries()` builds one query per stated sector in the primary
market. It **raises** rather than inventing geography if the profile yields nothing —
a fallback that searches for the wrong company is worse than no fallback. The fallback
is recorded as `outcome="fallback"` and surfaces in the UI as a red banner, because a
silent fallback once cost a whole run.

---

### Node 2 — `research`

**Reads** `planned_queries`, `search_hits`, `evidence_bundles`, `memory`.
**Writes** `search_hits`, `evidence_bundles`.
**Costs** one search per query, one `shortlist` model call, one `select_links` model
call per seed, and one scrape per page fetched.

Four phases inside one node.

**a. Search.** `tavily_search(query, max_results=7,
search_depth="advanced", chunks_per_source=3)`, with social domains excluded.
Tavily's chunked content is retained separately from the display snippet. Queries
already seen this run are skipped, so a re-plan that repeats one costs nothing.

Tavily's `country` parameter is deliberately **not** used: measured against live
queries it never biased toward the named market, and combined with the market in the
query text it returned zero results. Geography belongs in the query text, which works.

**b. Ordering.** Hits are grouped by the query that found them and **round-robined**,
so one productive query cannot crowd out the rest. URLs are canonicalised — lowercase
host, `www.` stripped, tracking parameters removed, trailing slash normalised — and
deduplicated. There is **no keyword scoring**: a regex tuned for award-marketing words
scored "Sustainability Leadership Awards" at zero and dropped it from two runs.

**c. Shortlist.** Up to `SHORTLIST_POOL = 80` hits are presented as a numbered list
using up to 1,200 characters of Tavily evidence, the originating query and Tavily's
score. The model returns **indices**, not URLs — an index cannot resolve to a page the
model invented. It picks `MAX_RESEARCH_CANDIDATES = 4`.

The prompt reduces the decision to one question:

> **Does the organisation behind this page RUN the programme, or is it writing about
> someone else's?**

It states that a landing page is not worse than a deep one, since links are followed
from whatever is picked, and that the organisation and programme should be judged
rather than the domain name — newspapers, chambers of commerce and industry
associations run a large share of all awards. If the call fails, the fallback is
search-engine order: ranking is the fallback, never the gate.

**d. Traversal.** For each pick, `resolve_evidence_bundle()` builds an `EvidenceBundle`
under hard caps: `max_depth=2`, `max_pages=3`, `reserve_calls=3`.

- Fetch the seed through Firecrawl (`formats=["markdown","links"]`,
  `only_main_content=True`, 120s timeout, 200,000-character ceiling).
- If the result is low quality — non-2xx, under 500 characters, or no identifiable
  title — retry once with `only_main_content=False` and `wait_for=1500`, keeping
  whichever is longer.
- Collect same-site, non-binary links in page order. **No scoring** — only removal of
  what cannot be fetched. PDFs are deliberately retained: award guidelines are often
  PDFs and Firecrawl reads them.
- **At depth 0 only**, one `select_links` call picks at most `MAX_LINKS_PER_PAGE = 2`
  from up to 40 candidates. Firing it per page burned five calls where three sufficed.
- If that call is unavailable or fails, **follow nothing**. The seed page alone beats a
  keyword guess at which link matters.

Each fetched page is recorded to the journey with its status code, depth, link count,
page metadata and the **first 20,000 characters of its markdown** — the same bound
extraction reads, so what the model saw is inspectable afterwards.

---

### Node 3 — `analyze`

**Reads** `evidence_bundles`, `analyzed_seeds`, `memory`, `as_of_date`.
**Writes** `candidates`, `analyzed_seeds`, `analysis_errors`, `replan_count`.
**Costs** one model call per not-yet-analysed bundle.

Only bundles whose `seed_url` is absent from `analyzed_seeds` are processed, so a
re-plan never pays twice for the same site.

A bundle under `MIN_BUNDLE_CHARS = 400` is treated as a **failed fetch** — bot block,
error page or redirect — and is not sent to the model at all. The failure is attributed
to the scrape rather than to analysis, so the trace blames the stage that actually
broke.

Evidence is bounded at `ANALYSIS_PAGE_CHARS = 40_000` **per page, not per bundle**. A
single positional slice across the whole bundle meant a long seed page consumed the
entire window and the depth-1 pages the run had paid to fetch were never read.

The model returns at most three candidates per bundle, each carrying `decision`
(`pursue`/`skip`), `reason`, and three separate lists: `entry_eligibility`,
`judging_criteria`, `application_requirements`. The prompt states that entry
eligibility is the heart of the task — every stated condition as its own item, in the
page's own words, never summarised into one line and never invented. It prefers the
umbrella programme over one of its categories unless the category is entered
independently, and skips past editions, closed windows, individual/student/researcher-only
programmes, and grants.

Candidates are deduplicated on `(target_title.casefold(), source_url)`, so one entity
reached through several search hits is not extracted repeatedly.

`replan_count` increments **only** when a pass produced neither a pursued candidate nor
an error — that is, when the run genuinely found nothing and a different query plan
might help.

---

### Routing — `route_after_analyze`

The graph's only branch:

```python
if any(item.decision == "pursue" for item in state["candidates"]):
    return "finalize"          # something to extract — go do it
if state.get("analysis_errors"):
    return "finalize"          # errors are not fixed by new queries
if (not state["supplied_queries"]
        and state["replan_count"] <= 1
        and runtime.budget.remaining > MIN_CALLS_AFTER_RESEARCH):
    return "replan"            # nothing found, budget left, try a new plan
return "finalize"
```

Four guards, each for a distinct reason: a re-plan is pointless when there is already
something to extract; it cannot fix a provider error; it would override a caller who
asked a specific question; and it must not consume the budget that finalisation needs
to store what has already been paid for.

---

### Node 4 — `finalize`

**Reads** `candidates`, `evidence_bundles`, `as_of_date`, `rejected`.
**Writes** `rejected`, `summary`. **Costs** one `extract` call per pursued candidate.

`skip` candidates go straight to `rejected` with the analyser's reason. For each
`pursue` candidate, five steps run in order and any one of them can stop it.

**a. `extract()`** — a plain function, not an agent. Strict `json_schema`, one retry
that feeds the specific error back, then a **typed failure**: `insufficient_content`,
`opportunity_closed`, or `malformed_response`. It is contractually guaranteed never to
raise, because an exception escaping would take down the Discovery run around it.

Input is `bundle.extraction_text(per_page_chars=20_000)`, ordered so the canonical page
and its supporting URLs come first. Page title and meta description are passed as
evidence — some sites render their name only as a logo image.

Two things the model does not get the final word on: `deadline_verified` (a string
check) and `base_title` (a deterministic edition strip), because both feed the identity
key and must not drift between models or years.

**b. `verify_deadline()`** — the day and month of the extracted deadline must appear
**verbatim** in the source text, across five surface forms. The year may be inferred
from page context without failing the check; stating a day and month without repeating
an obvious year is normal. What this catches is the opposite case: a date the model
invented that appears nowhere on the page.

**c. `assess_completeness()`** — five booleans and their mean. See §9 for its defects.

**d. `assess_actionability()`** — date arithmetic and HTTP status **only**:

| Condition | Verdict |
| --- | --- |
| Target page returned non-2xx | `reject` |
| Submission deadline before today | `historical` |
| Event date before today | `historical` |
| `cycle_year` before this year | `historical` |
| No date and no deadline note | `actionable`, with "no date found — verify on the source page" |
| Otherwise | `actionable` |

**Nothing here reads the page's wording.** Closure and openness are meaning, and the
analyser and extractor — both of which read the whole page — already judge them. A
keyword regex here was a third and worse opinion: "Nominate Now" and "Express Interest"
failed it, so Greentech, CII and the ET Sustainability Awards were each discarded.

A `historical` verdict with a real deadline still calls `record_edition()`. A past
edition is worthless as an opportunity but valuable to the registry, which needs
edition history to compute `typical_window`.

**e. `save_opportunity()`** — atomic upsert on the identity key. A genuinely new
identity also records an edition against its programme. `record_warnings()` then
produces per-record caveats — past edition, ungrounded deadline, `base_title` residue,
no deadline at all — which are attached to the journey event *and* accumulated onto the
run record.

---

### Stage 5 — Eligibility, outside the graph

**Runs after `run_discovery()` returns and does not consume the run budget.** Verified:
`grep -rn "budget" src/opportunity_radar/eligibility/` returns nothing. The loop reads
`{"source_url": {"$in": discovery.saved}}`, so it judges only what this run accepted,
never stale records from earlier runs.

Input is the stored `eligibility_criteria` list and the **full business profile** —
unlike Discovery, which gets a distilled seed, because any profile field could decide
any criterion. It does **not** receive the source page; see §12.

Output is two buckets: `criteria_results` (`met` / `not_met` / `unclear`, each with
reasoning) for conditions a fact settles, and `qualitative_notes` for conditions no
fact can settle and for conditions belonging to a track this company would not enter.

The prompt is explicit in both directions on alternative categories: judge only the
track the company would realistically enter and name the others, but never move a
genuine requirement into `qualitative_notes` to avoid saying `not_met`.

`confidence` and `score` are computed by plain functions and never self-reported — a
model asked to rate its own certainty rates its own certainty, not the evidence.

This is the one model call in the system that uses `json_object` rather than strict
`json_schema`.

---

## 6. Model versus deterministic code

The design rule throughout: **code does arithmetic and parses formats we own; the
model does meaning.**


| Decision                           | Made by   | Where                                    |
| ---------------------------------- | --------- | ---------------------------------------- |
| What to search for                 | **Model** | `plan_queries`                           |
| Which results to fetch             | **Model** | `_shortlist`                             |
| Which links to follow              | **Model** | `_link_chooser`                          |
| What opportunities exist on a site | **Model** | `_analyze_bundle`                        |
| Pursue or skip                     | **Model** | `_analyze_bundle`                        |
| Whether a page is closed           | **Model** | `extract` (`status` field)               |
| Record fields                      | **Model** | `extract`                                |
| Whether a criterion is met         | **Model** | `evaluate`                               |
| Result ordering                    | Code      | round-robin, search-engine order         |
| URL canonicalisation               | Code      | `canonicalize_url`                       |
| Which links are fetchable          | Code      | binary-suffix filter, same-site          |
| Deadline grounding                 | Code      | `verify_deadline`                        |
| `base_title` edition strip         | Code      | `strip_edition`                          |
| Past/expired                       | Code      | `assess_actionability` — date arithmetic |
| HTTP rejection                     | Code      | `assess_actionability`                   |
| Identity + dedup                   | Code      | `identity.py` + unique index             |
| `typical_window`                   | Code      | `compute_typical_window`                 |
| Eligibility `confidence`/`score`   | Code      | `scoring.py`                             |
| Budget enforcement                 | Code      | `RunBudget`                              |


**Six prompts total.** Four live in `workflow.py` (plan, shortlist, select_links,
analyze), one in `extract.py`, one in `evaluate.py`. All are Python string literals.
There is no prompt registry, no versioning, and no A/B mechanism.

---



## 7. Budget and cost control

`RunBudget` (`discovery/budget.py`) is enforced in the tool wrapper — once spent,
every tool refuses and the agent physically cannot act. A prompt asking the model to
be frugal is not a budget.


| Limit                | Default | Why it exists                                                                       |
| -------------------- | ------- | ----------------------------------------------------------------------------------- |
| `tool_calls`         | 40      | headline cost control                                                               |
| `max_searches`       | 12      | stops one provider eating the run                                                   |
| `max_scrapes`        | 14      | as above                                                                            |
| `max_llm_calls`      | 16      | as above                                                                            |
| `wall_clock_seconds` | 900     | the one a call-count budget cannot catch — a hung request never decrements anything |


**Free tools:** `read_memory`, `save_opportunity`. Refusing a save would discard work
already paid for; a run once extracted three records and lost the best one because the
budget ran out on the save, one call after the expensive work was done.

**⚠️ The UI budget slider only sets** `tool_calls`**.** `api/app.py:212` constructs
`RunBudget(tool_calls=request.budget)` — every sub-cap keeps its default. So raising
the slider to 80 still caps the run at **12 searches, 14 scrapes and 16 LLM calls**.
`max_llm_calls = 16` is the real binding constraint on how much a run can do, and it
is not adjustable from the UI.

Per-call output-token budgets, sized from each call's own schema
(`workflow.py:46-49`):

```
TOKENS_PICK_LINKS =  1_024   # ≤4 ints + one sentence
TOKENS_SHORTLIST  =  3_000   # ≤8 picks, each an int + 300 chars
TOKENS_PLAN       =  3_000   # 10 queries with rationales
TOKENS_ANALYZE    = 16_000   # full condition lists; schema maxes near 10,400
extract           =  4_096
eligibility       =  4_096
```

One global ceiling meant a call returning four integers was allowed 16,000 tokens —
when a model looped it generated 16,000 tokens of garbage and burned 300 seconds doing
it. Three such calls cost one run 612 seconds.

Selection calls (`shortlist`, `select_links`) pass
`extra_body={"reasoning": {"effort": "low", "exclude": True}}`. Reasoning models spend
the output budget on hidden reasoning before emitting anything; one run died with
`reasoning_tokens=8453` against an 8,192 ceiling, having produced nothing.

Timeouts: 90s with one retry on Discovery calls (the wall clock is only checked
between calls, so 120s × 3 retries could sit for six minutes); 120s with three retries
on extraction and eligibility.

### Calls per run, observed

Reference run (`qwen/qwen3-32b`, budget 50): **32 tool calls**, 4 saved.

Typical composition: 1 plan + ~10 searches + 1 shortlist + ~4 select_links +
~10 scrapes + ~4 analyze + ~4 extract, then eligibility (free) per saved record.

---



## 8. Observability

Every LLM call goes through `chat_model()` and carries `trace_handler()`. An untraced
call is a bug, not an optimisation — a `CLAUDE.md` constraint in force from Stage 0.

`stage_span()` wraps each step in a named span with its decision attached — budget
remaining, typed failure reason, whether the deadline grounded, the confidence
verdict. LangChain's own spans are called `model`, `tools`, `ChatOpenAI` and
`LangGraph`: correctly nested, but you cannot tell which call is which without opening
every one.

Two complementary records:

- **Langfuse** — full prompts, responses, token counts, timings.
- `runs` **collection** — decisions and outcomes at one row per tool call, written as
the run proceeds. Each run carries its Langfuse trace URL so the UI can hand off
rather than restate.

`stage_span` carries a fixed bug worth remembering: a `@contextmanager` that yields
again after catching a thrown-in exception raises `RuntimeError: generator didn't stop after throw()`, **masking every real error underneath it**. Only tracing setup is
guarded now; the caller's body propagates unchanged (`tracing.py:60-79`).

---



## 9. Scoring and confidence — complete inventory

**There is no confidence score at any search or selection stage.** This is the largest
single gap in the system.


| Stage                                | Confidence mechanism                       |
| ------------------------------------ | ------------------------------------------ |
| Search result relevance              | **none** — Tavily's own score is discarded |
| Which results to fetch               | **none** — a bare index + prose reason     |
| Which links to follow                | **none** — bare indices + one sentence     |
| Pursue/skip                          | **none** — a `Literal` + prose reason      |
| Opportunity relevance to the profile | **does not exist**                         |


Three numbers exist in the entire system:

**1.** `extraction_completeness.score` — fraction of five booleans passed
(`actionability.py:102-131`). Measures *how completely the form was filled*, not
whether the opportunity is any good. Two defects:

- `open_state` and `deadline` are the **same expression** — both
`bool(record.submission_deadline or record.deadline_note)` (lines 109–110). So it is
four real checks scored out of five, and having any deadline at all is worth 40% of
the score.
- The `source_coverage` regex `\b(eligib|who can apply|how to apply|nomination|application)\b`
— the trailing `\b` can never follow `eligib`, so that branch **matches nothing**.
Verified: `"Eligibility criteria"` → `False`, `"eligible companies"` → `False`. Only
`nomination` / `application` / `who can apply` still function.

This is also the number gating whether eligibility runs at all (`api/app.py:239`), so
the dead branch has real consequences.

**2. Eligibility** `score` — `met / (met + not_met)`, `unclear` excluded, `None` when
the denominator is zero (`scoring.py:24-36`). Sound arithmetic, misleading on
multi-track programmes (see §12). Deliberately **not displayed** in the UI.

**3. Eligibility** `confidence` — `"high"` only when there is at least one
fact-checkable criterion **and** none came back `unclear` (`scoring.py:39-56`). The
second half matters as much as the first: a record made entirely of qualitative
criteria has no `unclear` entries at all, and a rule that only looked for `unclear`
would report high confidence on a verdict where nothing was ever verified. This one is
correct.

Also: `confidence_note` from extraction — one free-text sentence, not a number.

`SearchHit.score: float = 0.0` (`state.py:28`) is **dead**. Nothing writes it, nothing
reads it. A leftover from the deleted ranker.

---



## 10. Failure handling


| Failure                  | Handling                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------- |
| Search throws            | logged to journey as `outcome="failed"`, run continues                                |
| Firecrawl throws         | logged per URL, that page skipped, bundle continues                                   |
| Page is thin/bot-blocked | bundle under 400 chars → `insufficient`, attributed to **scrape**, no model call paid |
| Low-quality page         | one retry with full rendered page, keep the longer                                    |
| Planning throws          | deterministic fallback plan + red UI banner                                           |
| Shortlist throws         | falls back to search-engine order                                                     |
| `select_links` throws    | follows nothing                                                                       |
| Analyze throws           | that bundle errors, others continue                                                   |
| Extraction unusable      | typed failure, recorded to `extraction_failures`                                      |
| Eligibility unusable     | one retry, then raises; that record is skipped, loop continues                        |
| Budget exhausted         | tools refuse with a `STOP:` message; saves still go through                           |
| Operator stop            | `POST /api/runs/{id}/stop` → `budget.cancel()`                                        |


**Run status** is derived in `agent.py:106-111`: `failed` if there were failures and
nothing was saved; `completed_with_rejections` if anything was rejected or any failure
occurred; otherwise `completed`.

---



## 11. Regex inventory

Two populations, judged as one by outside readers. The distinction matters.

**Parsing formats we own — legitimate, not NLP.**


| File                           | Count | Purpose                                                |
| ------------------------------ | ----- | ------------------------------------------------------ |
| `discovery/profile_seed.py`    | 4     | split markdown on `^##` , read `- Label: value` lines  |
| `storage/identity.py`          | 3     | unaccent/lowercase/strip punctuation for the index key |
| `discovery/link_resolver.py`   | 3     | extract `[text](url)`, canonicalise URLs               |
| `extraction/extract.py`        | 1     | strip a code fence off a model reply                   |
| `eligibility/evaluate.py`      | 2     | strip a fence; strip a leading list number             |
| `eligibility/criteria_sets.py` | 3     | parse the hand-written golden-set markdown             |
| `extraction/golden.py`         | 10    | parse the golden-set markdown                          |
| `extraction/schema.py`         | 1     | ISO date shape check                                   |


Replacing any of these with a model would be slower, costlier and non-deterministic on
a task with exactly one correct answer.

**Regex doing semantic work — the real debt.**


| File                         | Count | Assessment                                                                                                                                                                                                                                                                                                         |
| ---------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `extraction/base_title.py`   | 16    | **The main debt.** Strips years and edition markers by *shape* rather than wording, which is the better version of a bad idea — but it feeds the **identity key**, so a miss creates a duplicate record. `edition_residue()` surfaces anything edition-shaped that survives, as a warning rather than a rejection. |
| `extraction/grounding.py`    | 5     | Defensible — an anti-hallucination string check with five surface forms. Brittle on unusual date formats.                                                                                                                                                                                                          |
| `eligibility/scoring.py`     | 2     | `_FACTUAL_MARKERS = \b\d+\b                                                                                                                                                                                                                                                                                        |
| `discovery/actionability.py` | 1     | The `source_coverage` check, with the dead `eligib` branch documented in §9.                                                                                                                                                                                                                                       |


**Six judgment regexes were deleted during Phase 1** after they were measured doing
harm: `rank_search_hit`, `score_link`, the
`_POSITIVE`/`_NEGATIVE`/`_DIRECTORY`/`_SECONDARY_SOURCE` keyword sets,
`has_open_signal`, `_CLOSED` phrase matching, `_year_conflict`, and
`_COUNTRY_ALIASES`/`_GLOBAL_TERMS`.

---



## 12. Known defects and debt

Verified, with evidence. Ordered by impact.

**Resolved since the first draft of this document**, listed so the history is not lost:

- `confidence_note` was generated on every extraction and discarded. Now stored,
  traced and displayed.
- Run `warnings` and `failures` were computed and never persisted. Now written by
  `finish_run()` and shown per run, with per-record caveats also attached to the
  `save_opportunity` journey row.
- `finish_run()` overwrote the `budget` field with counters only, dropping the caps, so
  a finished run had nothing to meter against. Now writes `caps() | live()`.
- Live budget counters were only written at start and finish. `append_event()` now
  `$set`s them on every journey push.
- Four of the five budget caps were accepted by the API and silently discarded.
- Fetched page content was never retained, so a failed extraction could not be
  diagnosed without re-running. The first 20,000 characters are now on the journey.
- A page that failed to load appeared in the journey and nowhere else; unreachable
  pages now surface in the run's set-aside list.

**1. Extraction splits the same sentence inconsistently.** Two records from the same
organiser, same boilerplate:

```
Industry Leaders Awards 2026 → 1 criterion:  "Open to entrepreneurs, startups,
                                              MSMEs, companies, professionals…"
India Innovation Awards 2026 → 7 fragments:  Entrepreneurs / Startups / MSMEs /
                                              Companies / Professionals / …
```

Root cause is **not** model flakiness. `eligibility_criteria: [str]` is a flat list
where every consumer reads entries as AND, so a disjunctive sentence has **no
representable form** — the model must either fuse alternatives into one string or
split them into requirements, and both are wrong. It is a forced lossy encoding.

**2. The eligibility agent never sees the page it is judging.** It receives only the
extracted strings. `"Entrepreneurs"` is unjudgeable alone; `"Open to entrepreneurs, startups, MSMEs, companies…"` is trivially met. Same page, same fact, context
destroyed between the two calls. Eligibility is not budget-constrained, so passing the
source text costs nothing.

**3.** `entry_eligibility` **from** `analyze` **is computed and discarded.** `finalize_node`
copies only `judging_criteria` and `application_requirements` onto the record
(`workflow.py:996-1004`). The stored `eligibility_criteria` comes from `extract` — a
second, independent read of the same evidence. Analyze saw 40,000 chars per page;
extract saw 20,000. Two chances to split the sentence differently, one kept, for no
benefit.

**4. Extraction and eligibility run at provider-default temperature (~1.0).**
`discovery_temperature()` applies to Discovery only, by design — but the stated intent
was that extraction and eligibility be *reproducible*, and leaving them unset achieves
the opposite. This compounds defect 1.

**5. Alternative eligibility domains scored as joint requirements.** Documented in
`CLAUDE.md`. IISD-CMI National Sustainability Awards lists 13 alternative categories;
the business qualifies under one and scored 0.17, marked `not_met` on things like
"minimum age above 70" belonging to categories it was never entering. Per-criterion
reasoning is correct; only the aggregate misleads.

**6.** `extraction_completeness.score` **is structurally broken** — duplicate check plus a
dead regex branch. See §9. It is the number most likely to be quoted in a demo.

**7. Eligibility uses** `json_object`**, not strict** `json_schema`**.** An off-vocabulary
`status` would construct a `CriterionResult` that fails pydantic validation *outside*
the retry loop, crashing that evaluation.

**8. Nothing validates that the criterion list round-trips.** The prompt says every
condition must appear exactly once across the two buckets. Nothing checks it. A
dropped or reworded criterion is invisible.

**9. No dedup across organiser name variants.** `CII` and `Confederation of Indian Industry` are two programmes. Accepted limit — an alias table trades a rare collision
for curation overhead.

**10. Vocabulary sprawl.** Three subsystems leak three vocabularies onto one screen:

```
actionability : actionable | upcoming | historical | reject
journey       : ok | failed | fallback | insufficient | no_new_evidence | skipped | partial
run status    : completed | completed_with_rejections | failed | running
eligibility   : met | not_met | unclear | qualitative  → UI merges last two as "Your call"
```

`"upcoming"` is declared in the `ActionabilityVerdict` Literal but is **never
returned** — the code path that produced it was removed. A run reported as
`completed_with_rejections` reads as a qualified failure when it is a normal success.

**11. "Considered but not taken forward" shows journey rows, not records.**
`_skipped_pages()` (`api/app.py:141-181`) reconstructs skips by scanning every run's
journey for scraped URLs that never reached extraction. The same site legitimately
appears once per stage that touched it, across *all* runs — which reads as duplicated
opportunities. **The dedup is very likely fine; the view is misleading.** The
opportunity identity index makes true duplicates impossible. The one real dedup risk
is `base_title` regex drift (§11).

**12. Deleted evaluation harness.** `scripts/eval_retrieval.py`,
`scripts/check_rerank.py` and `discovery/ranking.py` exist only as `.pyc` files. They
were **never committed**. The data they produced survives — see §13 — but every tuning
decision since has been made by eyeballing single runs.

**13.** `OPENROUTER_RERANK_MODEL` **is configured and unused.** Declared in `.env.example`
with a comment describing behaviour that no longer exists.

**14. `/api/state` still returns every opportunity on every load.** Fine at the current
scale, but it has no pagination and no run filter, so it grows without bound as runs
accumulate. The per-run views do not use it.

---



## 13. Evaluation assets

**Already in the repo, currently unused by any code.**

`retrieval_set/` — **207 hand-labelled search results**:


| Field                              | Notes                                                              |
| ---------------------------------- | ------------------------------------------------------------------ |
| `label`                            | 2 = strongly relevant (46), 1 = partial (17), 0 = irrelevant (144) |
| `query`, `title`, `url`, `snippet` | as returned                                                        |
| `kind`                             | `planner` (111), `known` (65), `broad` (31)                        |
| `tavily_rank`, `tavily_score`      | Tavily's own ordering and score                                    |
| `notes`                            | hand-written justification                                         |


`retrieval_set/pool.jsonl` — 207 raw pooled results.
`retrieval_set/rerank_cache.json` — `cohere/rerank-4-fast` **scores for all 207**.

This is enough to compute, offline and at zero API cost, whether re-ranking beats
Tavily's ordering: precision@k, NDCG@k and MRR for both orderings. It has not been
computed since the scripts were lost.

`golden_set/extraction-examples.md` — Stage 0 reference data in two parts: extraction
examples, and **5 hand-written eligibility criteria sets** spanning `met`, `not_met`,
`not_met`-international, `unclear`, and one qualitative. Loaded by
`eligibility/criteria_sets.py` and exposed at `GET /api/reference-sets`.

---



## 14. API surface


| Endpoint              | Method | Purpose                                     |
| --------------------- | ------ | ------------------------------------------- |
| `/api/health`                | GET    | Mongo ping                                              |
| `/api/state`                 | GET    | global metrics, all opportunities, programmes, run list |
| `/api/pipeline`              | POST   | discovery **then** eligibility, one action              |
| `/api/runs`                  | POST   | discovery only                                          |
| `/api/runs/{id}`             | GET    | one run with its full journey                           |
| `/api/runs/{id}/events`      | GET    | `?after=N` — run metadata plus only newer journey rows  |
| `/api/runs/{id}/results`     | GET    | what that run saved, set aside and failed on            |
| `/api/runs/{id}/stop`        | POST   | cancel in flight; saves still go through                |
| `/api/runs/{id}`             | DELETE | remove one run record; stored opportunities are kept    |
| `/api/eligibility`           | POST   | evaluate stored records lacking a verdict               |
| `/api/reference-sets`        | GET    | the hand-written Stage 0 criteria sets                  |
| `/api/database/clear`        | POST   | wipe all four collections (demo reset)                  |
| `/{path}`                    | GET    | SPA fallback, so `/run/<id>` survives a refresh         |


Runs execute as FastAPI `BackgroundTasks`; the journey is written to Mongo step by
step and the page polls, rather than holding a connection open for the ~90s a run
takes. `_ACTIVE: dict[str, RunBudget]` is an in-process registry, so **stop does not
survive a server restart**.

`POST /api/runs` is a deliberate, agreed deviation from Stage 5's "read-only" rule. It
triggers work; it does not judge an opportunity or write to the business profile.

### Run configuration

Both run endpoints take the same `RunConfig` body. A blank `model` is coerced to
`None`, meaning "use `OPENROUTER_MODEL`", so any OpenRouter model id can be typed in
without a code change. All five budget caps are accepted and passed through
`to_budget()`; an earlier version passed only `tool_calls`, which left
`max_llm_calls=16` silently capping every run however high the headline budget was set.

### Incremental polling

`/api/runs/{id}/events?after=N` returns the run document minus its journey, plus a
positional slice of the journey after `N`. The whole-document poll it replaced re-sent
every search snippet every 1.5 seconds — about **6.2 MB over a 90-second run**, growing
with journey length; the delta feed transfers about **0.15 MB**, and each row exactly
once.

Positional slicing is deliberate. `_record()` wraps its Mongo write in
`try/except: pass`, so a dropped write leaves a gap in `seq` while positions stay
contiguous — a `seq`-based cursor would stall or skip across such a gap. Simulated over
40 poll cycles at a 5% write-failure rate, the positional cursor reconstructed the
stored journey exactly, with no gaps and no duplicates.

### Deleting a run

`DELETE /api/runs/{id}` removes the run record and its journey. It refuses with 409
while the run is in flight, and it deliberately **does not** touch `opportunities` or
`programs`: a record is upserted on its own identity and may have been confirmed by
later runs, so deleting a run must not delete findings that outlived it.

### Export

CSV generation is entirely client-side (`frontend/src/export.js`) — no endpoint, no
server round trip. Three sheets: one row per opportunity, one row per eligibility
condition, and one row per journey step. Quoting is RFC 4180, so commas, embedded
quotes and newlines inside reasoning survive; a UTF-8 BOM is prepended so Excel opens
non-ASCII correctly. Each sheet can be downloaded or copied to the clipboard.

---



## 15. Frontend architecture

A Vite + React single-page app, built to `frontend/dist` and served as static files by
FastAPI. Client-side routing means `/run/<id>` is a real URL — bookmarkable, shareable,
and survivable across a refresh thanks to the SPA fallback route.

### Layout

A two-column shell: a sticky configurator on the left, the active view on the right.
The sidebar collapses to a 56-pixel rail that keeps the run button and a status dot per
run; the state persists in `localStorage`, as do the model and budget settings.

### Two views

**Overview** (`/`) — everything stored across all runs, filterable by whether a date was
confirmed, plus the recurring programme registry, which is written on every save and
had never been displayed before.

**Run view** (`/run/<id>`) — one run, with its status, the four budget meters, the stage
strip, and three tabs: Journey, Opportunities, Set aside. Everything here is scoped to
that run, derived from its own journey rather than from `discovery_run_id`.

### The journey view

The centre of the application, and the part that has to make an agentic pipeline
legible to somebody who will not read a Langfuse trace.

Steps group into **stage passes** by graph node. Each pass states its purpose and shows
its step count, duration, and problem count; a re-plan appears as a second pass rather
than silently interleaving. Each step card shows its **intent** — what it was trying to
do, independent of the result — and then its **reasoning** in a bordered callout: why
this query, why this result was chosen, why these links, why pursue, why skip. The
model's stated reasoning is the visually dominant element on the card, and turns red on
failure.

Every step also carries a **Raw event** block containing the untouched JSON, so no
recorded field is unreachable from the interface, and `scrape` steps carry the fetched
page content itself.

A closing **Final output** card reports what the run produced — each stored
opportunity with its deadline and its met / not met / your-call tally — so a run ends
with an answer rather than trailing off after the last step.

While a run is live, new steps animate in, the active pass is highlighted, and a dashed
"working…" row sits at the end. That row deliberately does not name a step: a step is
recorded only once it completes, so what is executing at any instant is genuinely
unknown, and naming one would be a guess presented as fact.

### Vocabulary

The UI deliberately narrows the system's internal vocabularies. `unclear` and
`qualitative` both render as **"Your call"**, because to a reader they mean the same
thing. Eligibility `score` is computed and stored but **not** shown as a headline
number — it misleads on multi-track programmes — and appears only inside a diagnostics
disclosure with an explanation of why the per-condition verdicts are the thing to read.

This narrowing is presentation only. §12 item 10 records that the underlying vocabulary
sprawl across actionability, journey outcomes, run status and eligibility is still
unreconciled in the data.

---

## 16. Decisions that shaped the implementation

Each of these was a measured finding, not a preference.


| Decision                                                     | Evidence                                                                                                                                |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| No keyword scoring anywhere in selection                     | A ranker tuned for award-marketing words scored "Sustainability Leadership Awards" and RECEIC at 0.00, dropping them from multiple runs |
| No Tavily `country` parameter                                | Measured: never biased toward the named market; combined with the market in the query text it returned zero results                     |
| Short queries (3–4 content words)                            | Long queries returned the same small set of heavily-marketed pages every run                                                            |
| Sector lines only from the profile                           | Feeding PET/HDPE to the planner produced queries no award is named after                                                                |
| Per-call token budgets, not one ceiling                      | One global ceiling let a 4-integer call emit 16,000 tokens of garbage; three such calls cost 612 seconds                                |
| `reasoning: {effort: low, exclude: true}` on selection calls | A run died at `reasoning_tokens=8453` against an 8,192 ceiling, having emitted nothing                                                  |
| Schemas bounded so a maximal answer fits                     | `analyze`'s schema permitted ~41,000 tokens against a 16,000 cap; a legal reply truncated and became unparseable, losing two bundles    |
| `select_links` only at depth 0                               | Per-page firing burned 5 calls where 3 sufficed                                                                                         |
| Per-page truncation, not per-bundle                          | A long seed page consumed the whole window; L1 pages we paid for were never read                                                        |
| No `upcoming` downgrade                                      | "Nominate Now" and "Express Interest" failed the regex, discarding ET, Greentech and CII while an award mill won on a parseable date    |
| Missing date ≠ rejection                                     | ET Sustainability Awards — the best find of Phase 1 — has no parseable deadline on its landing page                                     |
| Closure is the model's `status` alone                        | A keyword backstop read wording, not meaning, and outvoted a model that had read the whole page                                         |
| Grounding dropped the "deadline language" proximity rule     | It caged a mechanical anti-hallucination check behind a keyword list; dates in tables failed despite being on the page                  |
| Fallback plan raises rather than inventing geography         | A hardcoded fallback once spent a whole run on Bhutan, Mauritius and grants                                                             |
| `qwen/qwen3-32b` as the working default                      | `google/gemma-4-31b-it` degenerates on strict `json_schema`; every gemma run that day failed or stalled                                 |


---



## 17. Open questions for Phase 2

Not proposals — the decisions that need making, with the facts that bear on them.

1. **Confidence: telemetry or gate?** Every scoring heuristic deleted in Phase 1 was
  deleted because it *gated*. A score that ranks and displays is safe; a score that
   cuts needs the labelled set behind it first.
2. **Does re-ranking actually help?** Should be measured before it is funded.
3. **Should the criteria schema become two-level?** Program-wide conditions plus named
  tracks where any one suffices. This is the root fix for defects 1 and 5, and it
   changes stored data.
4. **One model or per-node models?** Every call currently uses `OPENROUTER_MODEL`.
  `chat_model()` already takes a per-call override, so this is one env var per role.
5. **Should** `max_llm_calls` **be exposed?** It is the real binding constraint and is
  currently invisible from the UI.
6. **Typed opportunity kinds.** An award, a summit and a conference have different
  relevant fields and share one schema, which is why records look half-empty.
7. **Date policy.** Mandatory dates would have discarded the best find of Phase 1.
  `programs.due_soon()` and `typical_window` already exist and are unused — urgency
   ranking is a better answer than a search-time window filter.
8. **Bedrock migration.** `chat_model()` returns `ChatOpenAI` against OpenRouter's base
  URL. Moving to Bedrock means a provider abstraction, not just a new model id.

---

*Verified against the working tree at the time of writing. Every file and line
reference was checked; every measured claim comes from a live run or a direct test.*