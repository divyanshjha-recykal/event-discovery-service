# CLAUDE.md — Opportunity Radar

## Objective

Build a pipeline that discovers awards, grants, and events relevant to Recykal, evaluates eligibility against `BusinessProfile.md`, and stores the result. Current goal: prove the full loop works end to end against real, live sources. Nothing beyond that is in scope until it does.

## Constraints — do not violate

- Decision support only. No code submits anything, contacts an award body, or writes to the business profile file. The pipeline's last action is a stored record, never an outbound action to a third party.
- No AWS or other cloud hosting this phase. Docker Compose only.
- The reasoning model is configurable, read from an environment variable (`OPENROUTER_MODEL`), never hardcoded into agent or function logic. No specific model is finalized yet.
- No formal test suite is required this phase. Verify by running against the golden set described in Stage 0, not by writing a test framework first.
- Every LLM call, extraction, Discovery Agent, Eligibility Agent, is wrapped with Langfuse tracing via LangGraph's callback handler. This is in scope from Stage 0, not deferred. Self-hosted Langfuse (v3+) brings up Postgres, ClickHouse, Redis, and MinIO alongside it, seven containers total with MongoDB, not two. Known and accepted, not a surprise to rediscover mid-Stage 0.
- Mongo access uses PyMongo's native async API (`AsyncMongoClient`), not Motor. Motor is past end-of-life as of this writing; starting on it now would be adopting a deprecated dependency on day one.

## Architecture

Two LLM-driven components, everything else is a plain function:

- **Discovery Agent** — tools: `search(query)`, `scrape(url)`, `read_memory()`, `save_opportunity(record)`. Given a tool-call budget per run, decides what to search and what's worth pursuing, calls `extract()` on genuine finds.
- **Eligibility Agent** — one call, `evaluate(opportunity, business_profile)`. Reasons per criterion, not one overall verdict.
- **`extract(scraped_text, source_url)`** — plain function. Returns a valid record or a typed failure. Typed failure reasons: `insufficient_content` (page itself is too thin to build a record from), `opportunity_closed` (page makes clear the opportunity is no longer open — Discovery should have caught this already, this is the second line of defense, not the primary one), or `malformed_response` (the page was fine, the model's reply wasn't — unparseable JSON after retry, a base_title that won't normalise, or a record that fails schema validation). JSON mode, one retry, then fail named, never guess.
- **`save_opportunity(record)`** — plain function, atomic upsert. See schema below for the identity key.
- **Program registry** — `due_soon(lookahead_months=1)`, `record_edition()`, `known_orgs()`, plain functions over one collection, `programs`, never `opportunities`. `due_soon()` returns programs whose `typical_window` is currently active or opens within `lookahead_months`; a null `typical_window` (fewer than two recorded editions) never qualifies.

## Data schemas

**Opportunity record** (`opportunities` collection):

```
{
  title: str,
  organizing_body: str,
  base_title: str,          # title with year/edition stripped
  cycle_year: int,
  category: "award" | "grant" | "event" | "conference",
  eligibility_criteria: [str],   # individually stated conditions, never one paragraph
  submission_deadline: str | null,   # ISO date
  deadline_note: str | null,         # set when deadline is relative/rolling
  deadline_verified: bool,           # see grounding rule below
  event_date: str | null,
  source_url: str
}
```

Identity key: `organizing_body + base_title + cycle_year`. Same identity on write → update existing record. New identity → insert. Never a duplicate.

**Program record** (`programs` collection):

```
{
  organizing_body: str,
  base_title: str,
  editions: [ { year: int, deadline: str } ],
  typical_window: { month_start: int, month_end: int } | null   # null until 2+ editions exist
}
```

Identity key: `organizing_body + base_title` (no year). New edition for an existing identity appends to `editions` and recomputes `typical_window`. Identity matching normalizes (unaccent, lowercase, strip punctuation/leading articles) before comparing, not exact string match. Known limit: acronym punctuation drift, `C.I.I.` and `CII` normalize to different strings and won't match. Accepted for Phase 1, an alias table would fix it but trades this rare collision for curation overhead with no clean punctuation rule that doesn't break some other case.

**Eligibility result**, attached to the opportunity record after `evaluate()` runs:

```
{
  criteria_results: [
    { criterion: str, status: "met" | "not_met" | "unclear", reasoning: str }
  ],
  qualitative_notes: [ { criterion: str, note: str } ],   # never scored, shown as context only
  confidence: "high" | "low",   # derived from criteria_results, never self-reported by the model
  score: float | null           # met / (met + not_met), unclear excluded, null if no fact-checkable criteria
}
```

## Development stages

**Stage 0 — Environment and reference data.** Docker Compose running MongoDB and self-hosted Langfuse. OpenRouter key working with at least two models via `OPENROUTER_MODEL`. `BusinessProfile.md` present and loaded by the code, not hand-copied into prompts. Collect 5-8 real award pages (save the raw HTML or a rendered copy, not just the URL, sites change) covering a spread of organizing bodies and at least one with an eligibility list, one with a relative deadline, one clearly closed/past. Write 3-5 reference eligibility criteria sets by hand, spanning all three verdict paths (met, not_met, unclear) plus at least one qualitative criterion. Done when: a script can load the business profile and print it, the golden set + reference criteria sets exist as files in the repo, and a test LLM call shows up as a trace in Langfuse.

**Stage 1 — Storage and identity.** Implement the two Mongo collections and `save_opportunity()`'s upsert logic exactly per the identity key above. Implement `due_soon()`, `record_edition()`, `known_orgs()` against the `programs` collection; wire `record_edition()` to run automatically whenever `save_opportunity()` inserts a genuinely new identity. Done when: feeding the same opportunity twice (identical identity, different deadline the second time) results in one document, updated, not two; feeding a new `cycle_year` for a known `organizing_body + base_title` produces both a new opportunity and a new entry in that program's `editions`.

**Stage 2 — Extraction.** Implement `extract()` against the Stage 0 golden set. Implement the `deadline_verified` grounding check: the day and month of the extracted deadline must match verbatim near deadline language in the source text; the year may be inferred from page context (title, publish date) without failing the check, that's reasonable inference, not hallucination. `opportunity_closed` typed failures are a second line of defense behind Discovery's own relevance judgment, not the primary check, don't rely on this catching everything Discovery should have filtered. Run the golden set through more than one `OPENROUTER_MODEL` value and compare schema-compliance rate and `deadline_verified` accuracy before Stage 3 starts. Done when: every golden set page produces either a schema-valid record or a named typed failure (`insufficient_content`, `opportunity_closed`, or `malformed_response`), never a malformed or partial record; Example 2 in the golden set produces `opportunity_closed`, not a valid record.

**Stage 3 — Discovery Agent.** Wire `search`, `scrape`, `read_memory`, `save_opportunity` as real tools around a reasoning loop. Enforce the tool-call budget as a hard stop, not a suggestion. Run at least one full live run against real Tavily/Firecrawl calls, across at least two `OPENROUTER_MODEL` values, before picking a default. Done when: a live run, unattended, produces at least one real opportunity that was not in the golden set, correctly deduplicates on a second run of the same query set, stays within budget, and the full run is visible as a trace in Langfuse, tool call by tool call.

**Stage 4 — Eligibility Agent.** Implement `evaluate()` per the eligibility result schema above. Run it against the Stage 0 reference criteria sets before running it against anything Stage 3 discovered. Done when: every reference criteria set produces the expected verdict path (met/not_met/unclear) as written by hand in Stage 0, and the qualitative criterion never appears inside `score`.

**Stage 5 — Metrics view.** One page or one script output, reading directly from Mongo: count of opportunities discovered, extraction success/failure counts, verdict breakdown, and the full list with each opportunity's verdicts and cited reasoning visible. No approve/reject actions, this is read-only. Done when: it reflects a real Stage 3 + Stage 4 run with no manual data entry.

**Stage 6 — End-to-end run.** Run Stages 3 through 5 back to back, unattended, against live sources. Fix whatever breaks. This is the state to be in for the September 7th presentation.

## Not building this phase

Auto-submission, multi-recipient notification routing, embedding-based matching, queue-based parallel scraping, an approve/reject review UI, a local Ollama fallback. Do not scaffold these preemptively, build only what the current stage requires.