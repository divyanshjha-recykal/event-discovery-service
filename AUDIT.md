# What is wrong with this project, and what to do about it

21 September 2026. Written against the running code. Updated 28 September 2026 at the end
of Phase 1; the Phase 2 plan is below the progress table.

## Progress


| #   | Change                                                                                                                                                                                                                                                                                                                           | Status                                                                                        |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1   | Merge rules on the state (C4)                                                                                                                                                                                                                                                                                                    | **Done** — 21 Sep                                                                             |
| 2   | Saved progress (C5)                                                                                                                                                                                                                                                                                                              | **Done** — 21 Sep, now stored in Mongo                                                        |
| 3   | Split the two big functions (C3)                                                                                                                                                                                                                                                                                                 | **Done** — 21 Sep, 7 steps                                                                    |
| 4   | Fix the contradictions in the focus lines (A1, A2)                                                                                                                                                                                                                                                                               | **Done** — 22 Sep                                                                             |
| 5   | Focus reaches link-following (A4) and analyze (A5)                                                                                                                                                                                                                                                                               | **A5 done** — A4 **deferred**                                                                 |
| 6   | Cut to Awards only (A3)                                                                                                                                                                                                                                                                                                          | **Replaced** by Phase 2 W6 (a record shape per opportunity type)                              |
| 7   | Quotes for every extracted field (B1)                                                                                                                                                                                                                                                                                            | **Partly** — 3 fields, measured                                                               |
| 8   | Require a date (B2); fix what "ready" means (B3)                                                                                                                                                                                                                                                                                 | **B3 done** — B2 **dropped**, see below                                                       |
| 9   | Ask each question once (C1); carry the answer on (C2)                                                                                                                                                                                                                                                                            | **C2 done** — C1 not started                                                                  |
| 10  | Pool check after ranking (C6)                                                                                                                                                                                                                                                                                                    | not started                                                                                   |
| 11  | Delete dead code and stories (E1, E2)                                                                                                                                                                                                                                                                                            | **E1 done**; E2 done for rank + extract, open for plan + link chooser                         |
| 12  | Resource contention exposed by the split                                                                                                                                                                                                                                                                                         | **Done** — 22 Sep                                                                             |
| 13  | Let the organiser be "not stated"                                                                                                                                                                                                                                                                                                | **Done** — 22 Sep                                                                             |
| 14  | Schemas valid under strict mode, so any provider runs                                                                                                                                                                                                                                                                            | **Done** — 22 Sep                                                                             |
| 15  | No fallbacks in planning; a failed step stops the run                                                                                                                                                                                                                                                                            | **Done** — 22 Sep                                                                             |
| 16  | Deterministic date signals into ranking                                                                                                                                                                                                                                                                                          | **Done** — 23 Sep                                                                             |
| 17  | Firecrawl paced per minute, never parallel                                                                                                                                                                                                                                                                                       | **Done** — 23 Sep                                                                             |
| 18  | Unknown organiser no longer splits a programme                                                                                                                                                                                                                                                                                   | **Done** — 23 Sep                                                                             |
| 19  | Partial dates kept as a note instead of failing the record                                                                                                                                                                                                                                                                       | **Done** — 23 Sep                                                                             |
| 20  | Eligibility given room for its answer                                                                                                                                                                                                                                                                                            | **Done** — 23 Sep                                                                             |
| 21  | Budget caps read from one place                                                                                                                                                                                                                                                                                                  | **Done** — 23 Sep                                                                             |
| 22  | Sites picked against the scrape budget, not tool calls                                                                                                                                                                                                                                                                           | **Done** — 23 Sep                                                                             |
| 23  | Drop duplicate pages: before ranking, and after the seed scrape                                                                                                                                                                                                                                                                  | **Done** — 23 Sep                                                                             |
| 24  | Reuse pages already fetched in an earlier run                                                                                                                                                                                                                                                                                    | not started — Phase 2 W2                                                                      |
| 25  | Test whether the search API can replace some scraping                                                                                                                                                                                                                                                                            | **Superseded** — Exa returns facts per result (item 33); scraping still needed for conditions |
| 26  | Remove the last two fallbacks (ranking, saved progress)                                                                                                                                                                                                                                                                          | **Ranking done** — 23 Sep; saved-progress fallback to memory remains                          |
| 27  | A repeatable way to measure a change (D1)                                                                                                                                                                                                                                                                                        | not started — Phase 2 W1                                                                      |
| 28  | Profile v2: fixed sections; constraints and angles read into prompts                                                                                                                                                                                                                                                             | **Done** — 23 Sep                                                                             |
| 29  | Restore ranking's entrant gate; planner re-asks a short query count                                                                                                                                                                                                                                                              | **Done** — 23 Sep                                                                             |
| 30  | Results and CSV show everything extracted (manager feedback)                                                                                                                                                                                                                                                                     | **Partly** — card done 28 Sep (item 43); one server-built CSV not started                     |
| 31  | Results list only the run's own records; one programme stored under two titles                                                                                                                                                                                                                                                   | not started — Phase 2 W2                                                                      |
| 32  | Ranking fails loudly; no fall back to search order                                                                                                                                                                                                                                                                               | **Done** — 23 Sep                                                                             |
| 33  | Exa as the default search provider, chosen per run from the dashboard                                                                                                                                                                                                                                                            | **Done** — 23 Sep                                                                             |
| 34  | Model no longer echoes the site URL; code drops nothing on a string mismatch                                                                                                                                                                                                                                                     | **Done** — 24 Sep (3 pursued expos had been silently dropped)                                 |
| 35  | Word-matching title swap in ranking deleted                                                                                                                                                                                                                                                                                      | **Done** — 24 Sep                                                                             |
| 36  | Date gate at search deleted; dates go to the ranker as data with their source sentence                                                                                                                                                                                                                                           | **Done** — 24 Sep                                                                             |
| 37  | Journey shows the pipeline's own hierarchy; full extracted listing and verdicts per step                                                                                                                                                                                                                                         | **Done** — 24 Sep                                                                             |
| 38  | Fetch errors say whether Firecrawl or our pipeline refused the page                                                                                                                                                                                                                                                              | **Done** — 24 Sep                                                                             |
| 39  | `summary` field on every extracted opportunity                                                                                                                                                                                                                                                                                   | **Done** — 24 Sep                                                                             |
| 40  | Email the run CSV from the dashboard, to SMTP_TO only                                                                                                                                                                                                                                                                            | **Done** — 25 Sep                                                                             |
| 41  | Extract: form fields and attendee lists are not conditions; month-only and key dates kept                                                                                                                                                                                                                                        | **Done** — 28 Sep                                                                             |
| 42  | Exa summary returns key dates and the entry-status sentence; highlights aimed at entry details                                                                                                                                                                                                                                   | **Done** — 28 Sep                                                                             |
| 43  | One standard opportunity card in Results and the Journey result                                                                                                                                                                                                                                                                  | **Done** — 28 Sep                                                                             |
| 44  | Ranking output cap 12k → 24k (provider ignores the reasoning cap; run 75bead failed on it)                                                                                                                                                                                                                                       | **Done** — 28 Sep                                                                             |
| 45  | Tavily-era datasets and the code that only read them removed: `retrieval_set/`, `golden_set/`, old `reference/` files, `run_golden_set.py`, `eval_retrieval.py`, `run_eligibility.py`, `replay.py`, `compare_*.py`, `extraction/golden.py`, `eligibility/criteria_sets.py`, `/api/reference-sets`. Recoverable from git history. | **Done** — 5 Oct                                                                              |
| 46  | Search records every result in full: all Exa fields, highlights, position, query intent | **Done** — 6 Oct |
| 47  | Exa `opportunity_type` label (award/event/research/other, else "unrecognised"); raw summary and parse status kept; on-type share per search; dashboard shows each result's type and exactly what the ranker read. Ranker does not use the label yet — baseline only | **Done** — 6 Oct |
| 48  | Research narrative rewritten: peer-reviewed venues, industry/applied tracks, workshops and challenge tracks hosted by established conferences; recognised scholarly bodies preferred (generic, no named list); standalone hackathons, student/individual and developer challenges and paper-mill series excluded. Exa research/other definitions sharpened; new `sponsor` field shown to the ranker; profile Seeking line updated. Baseline to beat: run ba3917 (5 of 34 results labelled research) | **Done** — 6 Oct |
| 49  | Profile: research topics and current in-house research added under Technology (manager's brief); Seeking split into awards / events / research lines; entrant exclusion reads "individuals entering in their own name". Research brief takes research topics first. Paper one-liners pending. aideadlines.org is a reference for expected output tier only, never a source | **Done** — 8 Oct |
| 50  | Wave-1 planning says "a kind of opportunity" (was "recognition"). Research runs use Exa's default query-guided highlights (`highlights: true`) instead of the fixed award-style instruction; each search step records `highlights: query/fixed`. Awards, Events, Everything unchanged | **Done** — 8 Oct |
| 51  | Batch 1: query rules rewritten as "describe the page you want" (Exa's documented practice) with one reasoned example per type, award phrase list removed; Research drops the country rule, Awards/Events/Everything keep it. Wave 2 replaced by a ReAct loop: up to 3 steps, each sees every search's results (counts by type, past dates, duplicates, titles), writes an assessment and gaps, then runs one search or stops; reasoning shown on the plan steps | **Done** — 8 Oct |
| 52  | Batch 2: first page of each site also requests `rawHtml`; code parses every `<a href>` (menus included) into the link candidates, main-content text unchanged. Up to 60 links offered (was 40). Link picker now reads the page's first 3,000 characters and states `covered` and `missing` before picking 0–2 links; shown on the page card. Firecrawl Map not used | **Done** — 8 Oct |
| 53  | Step A — type specs: new `discovery/types.py` holds each type's noun, brief, market rule, query examples, highlights mode, rank conditions and order, link checklist; `workflow.py` templates read them (old FOCUS_NOUN/FOCUS_HINT/_MARKET_RULE/_QUERY_EXAMPLES removed). Intended changes only: year required in queries; extract takes the last accepted date as the deadline (an early-bird date if it is the only one) with other dated steps in the note; ranking says ordering never removes a result. Verified by before/after prompt render for all 4 types | **Done** — 13 Oct |
| 54  | Step B — Research search: new brief (main-track, workshop and challenge calls at established venues by recognised scholarly bodies; search the technique, never the industry or product; student/college/individual events, hackathons and paper-mill series excluded). Two tracks (core technology; research topics and current work): opening wave writes one per track, each search step serves the track with fewer queries (3/2 at most); invalid track label stops planning. New `scripts/search_only.py` (plan + search, no scraping, nothing written to runs) | **Done** — 13 Oct |
| 55  | Step C part 1 — ranking: order is fit, then standing, then sooner deadline only as a tiebreak; dates decide only open/closed (passed deadline or winners announced = closed, no date = open). Per-type conditions: Awards = company award (no grants, accelerators, CSR, individual/student/NGO awards); Research = own paper call (not workshop-proposal pages), established body (paper mills fail), not student/individual-only. One seat per programme; each research track gets a seat in the fetched picks; ranker returns up to 8 `excluded` results with reasons (journey + Choose sites card). New `scripts/rank_pool.py` re-ranks a saved pool (one model call). Cohere approved for a future re-rank stage (re-rank only) | **Done** — 13 Oct |
| 56  | Step C part 2. Ranking: "Open" also closes passed event dates, stated closures and earlier editions; "Distinct" (one pick per programme; a workshop with its own call is its own) is now a numbered condition, as loose sentences were ignored in the part 1 test. Queries: research examples name a venue and edition (RECOMB 2027) or a subfield's call; research may name established venues, never "international conference on"; awards never ask for grants, CSR, individual/student/NGO awards; each query in a track takes a different line of work. Link picker: per-type checklist (research: dates, topics, submission guidelines, tracks; awards: deadline, who can enter, categories, fee, how to apply) and told CONSTRAINTS. Extract: per-type record guide; research fills topics / how to submit / review criteria, full-paper date as the deadline. Evaluate: research records get a "which of our work fits" verdict (fits / partly / no per line of work, the matching call topic, a venue note), stored as `fit`; card, journey, CSVs and email show it. Eval set (W1) on hold by decision; required before production | **Done** — 13 Oct |
| 57  | Regression fix after run 4d38cd (stopped after search): the row-56 rule "name an established venue you know" made every query a famous venue + year (CVPR/IROS/NeurIPS/MLSys 2027), returning proposal pages, past editions and tracker sites; Everything inherited it via the RECOMB example. Research now describes the call (subfield + kind of page), never names a conference or journal; examples are a workshop call and a journal special issue; the topics track searches each in-house line by its technique, never its product. Shared "Open" rule: a year in the URL no longer closes a result (it is usually a publish date); a past-year title closes only when no date on it is ahead. Known venues belong to the W2 catalogue, not search | **Done** — 13 Oct |
| 58  | Ranker fix after run 973845 (stopped before fetching; its six picks were niche workshops, two listing-site copies, RWS twice, an image-sensor design workshop; CVPR 2027 main, SenSys 2027 and WACV were not picked at all; ICFEC and T-ASE ranked 9–10). Research "Paper call" now requires the venue's own page; listing and tracker sites fail even when they copy a call (the earlier allowance let in visionbib and caused the RWS duplicate). Research ordering stays relevance first, now defined as the work the call asks for matching the TRACKS' methods, problems and systems, not shared words; then standing. No code enforcement of picks, by decision. Run 973845's pool exported to `reference/search-tests/20261013-run973845-research.json` for re-ranking | **Done** — 13 Oct |
| 59  | Parked batch from runs 6a68d9 (Research), 4c16b9 (Everything), 0d4823 (Awards): (1) research examples = main-track + workshop call; (2) fit rows = the profile's Research topics + Current research in house items only; (3) strict fit definitions; (4) TOKENS_PLAN and TOKENS_FIT 8k → 20k, fit on the 300s timeout — the model ignores the reasoning cap and truncates; (5) a failed search step stops the run as failed (Everything silently ran 2 of 5 searches); (6, optional) submission rules go to "How to apply", not entry conditions. Then Step E (Everything judges each result by its type's conditions; one event query) | **Parked** — resume 14 Oct |
| 60  | S1: TOKENS_PLAN and TOKENS_FIT 8k → 20k; research_fit on the 300s limit. S2: a failed search step stops the run as failed (was: searching quietly ended). S3: an unreadable dead-end list stops the run (was: silently ignored). A1: submission rules (entry limits, forms, fees, codes of conduct) go to application requirements, not entry conditions — awards, events, everything. Rules added: 1 (A1). Removed: 0 | **Done** — 15 Oct |
| 61  | After Awards run 4cba88 (S1, S2, A1 confirmed). X1: an early-bird date is no longer used as the deadline (ET AI Awards 2027 was set aside on 16 Oct because its 15 Oct early-bird became its deadline); it goes in the deadline note, and no final date means no deadline. X2: a run's Results show only records that run saved (an older record on the same page appeared as a fifth card); the "missing" note now says a later run may have updated them. Rules added: 0. Removed: 1 (X1) | **Done** — 16 Oct |
| 62  | Stored-programme lines removed from every prompt (commented out in `_memory`): "Known organizing bodies" (52 names from past records, incl. mills, duplicates, "Unknown") and "Programs due soon" (never fired: no programme has 2 editions). No data deleted. Evidence: 0 of 14 runs' queries and 0 of 81 pick reasons used the list; rank_pool A/B on 3 saved pools, same code with/without: fetched six overlap 5/6, 4/6, 4/6; all-picks overlap 6/10, 9/10, 10/10 — reshuffles of the same candidates, no quality change either way. Returns with the catalogue as explicit refresh data. Rules added: 0. Removed: 1 block | **Done** — 16 Oct |
| 63  | Final track shape. R0 (Exa paper index, 3 searches): papers, not calls; 15/30 with a venue, 0 conferences, pointed to applied journals — paper-first dropped. Research: examples = main-track call + workshop call (special issue removed); fit rows = the profile's Research topics + Current research in house items, strict fits/partly/no. Events: own conditions (event's own page; a company route to exhibit/speak/demo/apply, not visitor-only; open; distinct), order (relevance to what we sell and our buyers, standing, deadline tiebreak), link checklist, record guide (ways to take part; never the audience). Everything: three tracks (award, event, research) from the Seeking lines; one opening query per track (6 searches); each query carries its type's market and query rule; each result ranked by its type's conditions; link picking and extraction use the pick's type; highlights per query. Rules added: 0 net for Research/Awards; Events: its own 4 conditions replace the shared 3; Everything reuses existing type rules | **Done** — 16 Oct |
| 64  | ACE product profile, step 1 of component discovery: `docs/products/ace/ProductProfile.ACE.xlsx` (gitignored), drafted from the ACE BOM, the Embedded ACE BOM and the camera, lens and lighting selection. Sheets: Read me, Product, Parts (64 rows: 26 embedded, 19 electrical, 19 mechanical; BOM column names kept; dropdowns for subsystem, swappable, status, search), Requirements, Tooling (one-time), Open questions (12). Every value names its source; gaps are [to confirm]. Parts with a model number but no documented specs use the current part's datasheet as the baseline. Search = yes for the RVM camera, vision lighting (required, not in the BOM) and the 24 V supply. Flagged, not resolved: 17 parts priced >10% apart across the two BOMs (Jetson ₹29,500 vs ₹14,800); tooling totals that do not add up. `openpyxl` added | **Done** |
| 65  | ACE profile prices: per the BOM owners, the Embedded ACE BOM is the current price source (54 parts); the 10 parts it does not list keep their ACE BOM price (08-07-2026), marked per row in a new `Rate source` column; the old ACE BOM price is kept as `Previous rate`. Per-machine total computed from the Parts sheet: ₹2,39,976 before GST (was ₹2,69,180 on ACE BOM prices). Open: the Embedded BOM is undated; one quantity conflict (Arducam CSI-to-HDMI extension, 1 vs 2, item is a 'pack of 2') | **Done** |
| 66  | Step 2: product profile loader `product_profile.py` (+ `PRODUCTS_DIR` in paths, `scripts/show_product_profile.py`). Reads Product and Parts sheets; accepts extra columns and BOM header variants (Item Description, Revised price on…, Leadtime for deilvery); stops naming the column or row on a missing required column, an invalid Subsystem/Search value or a non-numeric rate. `Part.brief()` is the only text a prompt gets and carries no cost. Checked: synthetic workbook cases + the real ACE workbook (64 parts, 3 searchable) | **Done** |
| 67  | Watchlists as team-maintained spreadsheets (gitignored): `docs/Competitors.xlsx` (11 competitors from the team list; Zeleno's site is down, watched by name) and `docs/SourcingSites.xlsx` (19 sites: 3 international distributors, 9 Indian sellers and marketplaces, 7 brands). Addresses checked on the web: only verified ones are marked 'Use in search' (digikey.in, robu.in, evelta.com, probots.co.in, indiamart.com, thinkrobotics.com, in.misumi-ec.com); Mouser, element14, Sharvi, RoboSkull (robotskull.net — the current BOM vendor), RoboKits and the brands are unverified; RoboWays was not found | **Done** |
| 68  | Competitor watch v1 (`discovery/competitor_watch.py`, `scripts/competitor_watch.py`). Trigger-only (no schedule, no Exa Monitors: they require a public webhook, cost $15/1k runs and allow no news category or date filter). Three lanes per run, all Exa search published since the last successful watch run minus 2 days (first run: 90 days): each competitor's own site, ~8 model-planned market searches (half news, half general web), one name check per competitor ('Name check' column in Competitors.xlsx). Highlights + capped text from Exa, no Firecrawl. Code compares only exact links (`competitor_seen`) and dates; one model call per 20 new pages decides keep/drop, competitor or new entrant, kind, date from the text, same story as a recent signal, importance and why. Stored in `competitor_signals` (first-seen date, also-reported-by). A failed step fails the run and does not move the window. Checked on a throwaway database: two runs, skip-seen, merge into a known story, window advance, failure | **Done** (live test pending) |
| 69  | Competitor watch, after live test f165a8 (3 competitors, 14 searches: 53 signals; competitor lanes clean — Envipco's three UK/Romania RVM contracts, Tomra B3 compact RVM, Endlos UK launch; noise from market searches that drifted to general waste/recycling). Fixes: market searches must name this business's product category or a buyer programme; 'new entrant' only for companies newly offering products like this business's, others 'other company'; importance anchored (high = competitor or entrant move in the product category or a change in a market where the business operates); low-importance items stored as 'context' in competitor_seen, not as signals; headlines in English; print order high→low. Rules added: 3 (prompt). Removed: 0 | **Done** — retest pending |
| 70  | Competitor watch proven on live test 617d7f (same test DB, 90-day window): market searches stayed in the product space (bottle collection and refund machines, deposit refund rules, RVM tenders); 105 distinct pages, 49 skipped as judged in run 1, 56 new; 10 merged into known stories (4 into run-1 stories); 7 kept as context; 11 signals, all on-market, incl. two biddable RVM tenders (TASMAC statewide system operator ~₹50 cr; West Bengal ULB RVM EOI), Goa DRS deferral to 1 Apr 2027, Madras HC challenge to the TASMAC tender, Kerala Bevco withdrawal, Tomra Q2, Envipco Q2 (~5,400 UK RVMs). Open for polish: tender links point to tender-listing sites, not the official notice; Recykal (own group) labelled 'other company'; importance not fully consistent (Envipco Q2 medium vs Tomra Q2 high) | **Done** |
| 71  | Competitor watch in the main UI. Judge: new label 'own group: <company>' for this business or a company the profile names as its group (profile: 'operates within the Recykal group'); never a competitor move. API: POST /api/competitors/runs (checks Competitors.xlsx before starting; 400 with the column/row on a bad sheet) and GET /api/runs/{id}/signals (this run's signals by importance + earlier stories it added coverage to). UI: 'Competitors' option under Looking for; run buttons start a watch run (dry run refused, re-evaluate unaffected); run page header shows signal counts and the search window; Signals tab with cards (importance, company, kind, date, what happened, why it matters, also reported by); Journey shows lane per search, 'Skip seen pages' and 'Judge signals' (kept table + dropped with reasons). Checked: signals endpoint on test run 617d7f (11 signals, 7 updated stories); mocked two-run check | **Done** — first UI run pending |
| 72  | Disk full (C: 0 GB free): Docker's docker_data.vhdx had grown to 322 GB and its file system went emergency read-only; the Langfuse stack (ClickHouse above all) had run 24/7 under restart: always since Phase 1. Langfuse moved to its own on-demand stack `docker-compose.langfuse.yml` (project `radar-tracing`, no restart policy): start with `up -d`, stop and wipe with `down -v`, which cannot touch MongoDB. Main `docker-compose.yml` is MongoDB only. A fresh Langfuse re-provisions the same keys from .env (LANGFUSE_INIT_*); the pipeline runs untraced when it is stopped. README updated. Old Langfuse volumes to delete by hand, then compact the vhdx | **Done** — cleanup by user |
| 73  | Disk recovered. Measured before the reset: ClickHouse data 54.6 GB live, ClickHouse logs 2 GB, MinIO 265 MB, MongoDB 628 MB; the other ~260 GB of the 322 GB vhdx was ClickHouse churn the non-sparse file never returned. MongoDB backed up (`backups/radar-mongo-20261020.archive.gz`, 17.4 MB, gzip-verified, gitignored); docker_data.vhdx deleted (325 GB free); fresh Docker, MongoDB only; restore: 4,116 documents, 0 failed; counts match the backup (opportunities 64, programs 68, runs 14, dead_ends 10, extraction_failures 1, run_progress 571, run_progress_writes 3,140). Langfuse traces gone by decision; tracing now on demand only | **Done** — 20 Oct |
| 74  | Competitor-run view, after UI run 727121 (all 11 competitors, 30 searches, 170 new pages, 30 signals, 12 merged, 20 context, 108 dropped; Recykal labelled own group; Diebold ATM news kept out as context). The run page used the opportunity layout. Now, for competitor runs: stage bar plan → search → judge; no scrapes meter; stage descriptions worded for the watch; search tables show the published date instead of empty Type/Snippet; the closing block summarises signals and points to the Signals tab instead of '0 ready'. Open: a full run takes ~12 min (9 sequential judge batches) | **Done** |
| 75  | Run digest for competitor runs. The judge now also picks each signal's `section` from a fixed list (Act on this, Competitor moves, Market and policy, New entrants and other companies, Own group); `run_digest()` groups a run's signals by it, high to low, plus 'Following up' for earlier stories this run added coverage to. Each entry is the judge's own title, summary and link: no second model call, nothing reworded. Shown in the run's Result block (title, summary, link) and the Signals tab (full cards by section); the CLI prints the same; the newsletter will read `run_digest()`. A model-written digest was tried on run 727121 first and dropped: deepseek-v4.1-flash takes an effort level, not a reasoning token cap, so it spent the whole allowance thinking, and at low effort it joined two separate Envipco deals and left out three competitor signals. Run 727121 deleted with its 30 signals and 170 seen pages so the next run starts clean. Checked: mocked run_digest on a throwaway DB | **Done** — fresh UI run pending |
| 76  | After UI run cb25a6 (38 signals in 5 sections, all placed correctly, 297 s): the three Goa-deferral articles shared one judge batch and were all dropped as duplicates of each other, so the deferral was missing. Judge now gives each repeat in a batch `duplicate_of` (the page standing for the event) and keeps it; code stores the standing page first and adds repeats to its also-reported links; a repeat whose page did not become a signal is stored as its own signal with a run warning. Judge is told today's date; 'Act on this' only while a deadline is still ahead (a West Bengal EOI closed 6 Aug was listed). Checked: mocked run on a throwaway DB (3 pages → 1 signal + 2 links; orphan repeat kept + warning). Run cb25a6 deleted (38 signals, 161 seen) for a clean baseline | **Done** — baseline run pending |
| 77  | Email export. Demo sent nothing: SMTP was fine (Gmail login checked, nothing sent), but email handled opportunities only, so a competitor run's button was disabled and the endpoint refused it. Now every run mails a readable HTML body (inline styles, plain-text copy) with the CSV attached: competitor runs by section (linked title; importance · company · date; summary), opportunity runs by type (linked title; organiser · deadline or event date · fit; summary). `GET /api/runs/{id}/email` previews exactly what `POST` sends; Export panel has Signals CSV, Email preview and Run log for competitor runs, and an Email preview tab for opportunity runs. All page text HTML-escaped. Recipients still SMTP_TO only. Checked: bodies for mock signals (escaping, order, links) and real run 4cba88 (4/4 in body); MIME captured by a fake SMTP server (plain + HTML + CSV); preview endpoint 200 / 404 | **Done** — first real send by user |
| 78  | Component watch, backend. ACE profile cut to one Parts sheet (Part ID, Subsystem, Item, What it does, Manufacturer, Part number, Qty per machine, Rate before GST, Vendor, Why chosen, Must have (optional)) and a 7-line Questions sheet; earlier drafts in backups/. Loader rewritten to those columns; the rate never reaches a prompt. `component_watch.py`: the model plans every part (off the shelf or custom, with a reason; a same-model search on the 'Use in search' sourcing sites and an alternatives search on the open web), Exa returns page text with prices (probe: 6 searches, Indian sellers show prices), the model judges each page per part (product, seller, price as printed + GST basis, stock, offers: other vendor / newer model / better spec / more efficient with reasons, must-have checks, concerns), code computes the difference against the rate for rupee prices. Results by part plus custom and nothing-found lists; `POST /api/components/runs`, `GET /api/runs/{id}/components`, email + CSV; `scripts/component_watch.py` (--only, --test-db). Checked: mocked run on a throwaway DB (custom parts skipped, site-limited same-part search, rate absent from every prompt, price maths, email, a failed search stops the run, a part missing from the plan fails it) | **Done** — live run and UI pending |
| 79  | After test run 5cc679 (3 parts, 6 searches, 36 findings): cheaper boards needing a new software stack led the Jetson list (-52%, -36%), a carrier board without the module showed -65%, alternatives were tagged 'other vendor', and the same-part search was limited to the 7 sourcing sites. Now: the judge gives each finding an effort (drop-in / minor changes / major changes) and what would change; results run same part, then drop-in, minor, major, cheapest first; 'other vendor' removed (a same-part finding is another seller); same-part search on the open web, the sourcing-sites list no longer used by the pipeline; one code-computed summary line per part (lowest same-part price and whether ours is lowest, alternatives by effort, cheapest drop-in/minor); every finding stays in the email and CSV (+ Effort, What would change). Checked: mocked run on a throwaway DB | **Done** — rerun of the 3 parts pending |
| 80  | After test run 7e20ff (3 parts: Jetson same-part all +41% or more, so our rate is lowest; 24 V supply -9% at one seller; scanner same part only on request or in USD; cheap boards correctly major changes): prices are now compared on a like-for-like GST basis. The judge gives `price_before_gst` when the page states it or the GST amount; code compares our pre-GST rate with it, otherwise with the price as shown and labels it; no GST rate is assumed. `compared_on` stored; email, CSV and terminal show the pre-GST price and the basis. Open: confirm the Embedded BOM rates are before GST (Questions sheet) | **Done** — full ACE run pending |
| 81  | First full ACE run 15a5c8 (real DB, 627 s, 68 searches, 53 model calls): 15 custom parts correctly not searched (PCBs, harness, overlay, stand, enclosure, assembly, plastics); 364 findings on 48 of 49 searched parts (128 same part, 118 drop-in, 86 minor, 32 major). Leads: LRS-35-5 -27%, AC8265 -15%, LRS-200-24 -9%, LAN connector -57%; our rate lowest found for Jetson, camera, SD card, speaker, scanner, Sick sensor, MCB, RCCB, ribbon cable. Weak: vague parts (liners, mats, wires, bags) given generous drop-in labels (a baby mattress protector for the cradle liner); unit mismatches give false savings (wire per metre vs 5 m, LED tube -71%, liner -92%); a non-safety-rated door switch shown for the Keyence safety interlock. Email 257 KB, over Gmail's ~102 KB clip. UI: Components option, Findings tab (card per part with summary), Journey plan and judge tables, Export with Findings CSV and email | **Done** — judge strictness and unit fixes proposed |
| 82  | Component judging and pricing made explicit. Judge keeps only the same kind of product for the same use (no household items for machine parts); drop-in only when the page states the facts that matter (size, ratings, interface, mounting, safety rating or certification) and they match, else minor changes with what could not be confirmed; a safety part needs the same safety rating. Units: profile gains a Unit column (piece / metre, from the BOM's U.O.M.); the brief says 'Bought per: <unit>; <qty> per machine'; the judge gives what the listed price buys (`price_unit`) and how many make one of our units (`units_per_part`); code computes price per our unit, the difference, and per-machine cost (theirs vs ours), and compares nothing when units are unclear or the price is not in rupees. Email: a table per part (Type, Product · seller, Listed price, Per our unit vs ours, Per machine, Notes), top 5 findings with 'N more' and the full CSV; UI table has the same columns. Deleting a run now deletes its component findings. Checked: mocked run on a throwaway DB (pack of 100, metre-priced part, unclear unit, USD, GST bases, email rows, CSV) | **Done** — fresh full run pending |
| 83  | Unit column removed again at the user's direction: the workbook keeps exactly the team's 11 columns (Part ID, Subsystem, Item, What it does, Manufacturer, Part number, Qty per machine, Rate before GST, Vendor, Why chosen, Must Have). The brief says 'Qty per machine: N (our rate is for one of these)'; the judge infers how many of the page's price units make one such unit, and code compares nothing when that is unclear. Display reads 'per unit'. Checked: mocked run on a throwaway DB; loader reads all 64 parts | **Done** — fresh full run pending |
| 84  | Component runs made decision-first. (1) An old run's Result section returned 500 (findings stored before per-unit pricing); now a clear 409 'delete it and start a new run'. (2) Scope: the plan covers every part, then a priority run (default, weekly) searches only the off-the-shelf parts making up 80% of their cost per machine, from Qty × Rate in code (ACE: 13 of 49 parts); 'all' for a monthly sweep; --only for named parts; deferred parts are listed. (3) Per part, in code: verdict (cheaper seller / cheaper drop-in / changes needed to save / we pay the lowest / no comparable price / nothing found / low spend / custom), best like-for-like option and saving per machine; overview totals the saving. (4) Procurement can record per lead whether it held (PATCH /api/components/offers/{id}); the overview shows leads that held, the scorecard for this pipeline. (5) Run page for components: Decisions (KPIs, Act on, Worth a look), Parts (one row per BOM part, filter by verdict/subsystem, expands to every finding), How it ran (per-part trace: status, searches, kept, dropped with reasons); sidebar 'Parts to search' (Top 80% of spend / All parts). Email leads with the saving and the Act on / Worth a look tables. Honest read of 15a5c8: a lead list for procurement, savings small (~1% of the machine); the highest-cost parts gave least (stepper and Keyence on quote, display and interlock without a model number) | **Done** — fresh run pending |
| 85  | After run a28671 (default Top-80% scope: 13 of 49 off-the-shelf parts, 19 searches, 17 model calls, 409 s; 8 of the 13 top parts gave no comparable price): (1) verdict order fixed: a cheaper option needing changes no longer hides that we pay the lowest (Jetson); 'Worth a look' lists every part with such an option; (2) the judge flags a price far below other sellers' prices for the same product on the same pages (the Rs 3,305 'Jetson kit'); (3) live view: a component run opens on How it ran while running, built from the steps as they arrive (progress line, latest-steps feed, per-part status Planned / Queued / Searching / Judged), Decisions refetch after each judged part, and the page switches to Decisions when done; header shows the scope; (4) machine picker for Components: the product line comes from docs/products/machines.json (ACE, PRO, NEO, FastScan, Global RVM, Line); a machine is selectable once its workbook exists (today ACE); GET /api/components/machines; the run's product flag is the machine key. Open: the business profile's product line (Reklaim PRO, ACE, Mini, Neo, FastScan) differs from this list | **Done** |
| 86  | Feedback on run a28671: a nylon castor was offered for the Misumi wheels as 'minor changes' though it can never fit (chassis height, load, brake, levelling); results thin; no section for better or more efficient parts; the page switched view after the run. Now: (1) effort 'fit unclear' when the brief or the page lacks the facts needed to tell whether it works (what is missing goes in changes); fit-unclear options never count as savings or recommendations; (2) 'Better or newer options that fit': alternatives offering a newer model, better spec or more efficiency, drop-in or minor changes, no must-have not met, whatever their price, on the Decisions view, in the Result section and in the email; (3) a component run opens on How it ran and stays there, with a Result section under the trace like the other tracks; Decisions and Parts remain as tabs. Email for a28671 checked by preview (70 KB, nothing sent). The real fix for generic judgements is Why chosen and Must Have in the workbook, due this week | **Done** — full run pending |
| 87  | Run c4239b (All parts) failed after 378 s with JSONDecodeError 'Invalid control character': the judge copied a raw tab or newline from a product page into a JSON string, and the strict parser rejected the whole reply, stopping the run after 5 parts. The shared `_parse_json` now uses json.loads(strict=False), which reads such strings as meant and still fails on anything that is not JSON; this covers every track. The component page also kept showing parts as 'Searching…' after the run had ended, with no failure shown, so it looked like it was still running for an hour. Now an ended run that failed or was stopped says so at the top of every view with its reason, and parts left unjudged read 'Not judged: the run ended first' | **Done** — rerun pending |
| 88  | Code audit, Batch A (correctness only; no prompt or judging change): (1) a failed or duplicate fetch jumped straight to evaluate while other sites were still being read, so evaluate ran early, could start a paid re-plan, and store ran twice (reproduced: one duplicate + one slow site gave 3 evaluates, 2 stores, 1 needless re-plan). LangGraph's defer does not wait for Send branches, so such a fetch now goes through extract, which returns at once; every site fans in together. (2) _structured's keep-the-valid-candidates path sat under an unreachable except and returned None; it now runs after the try and raises the validation error when nothing validates (only discovery's per-site analysis uses it). (3) Clear database also wipes dead_ends, competitor_seen, competitor_signals, component_offers and run_progress; deleting a run also deletes its competitor pages and signals. (4) Clear requires the JSON body {confirm: 'delete everything'}, so a cross-site form post is refused (a text/plain forged body gets 422). (5) Server startup marks runs left 'running' as failed ('server restarted during the run'). (6) The run page polls with a timeout chain, so two polls never share the events cursor. Checked without credits: graph fan-in on the real fetch_node, _structured with a fake model, the API on a throwaway DB, and the component, competitor and email mock checks | **Done** |
| 89  | Run 89f045 (ACE, All parts) failed at 435 s after 12 of 47 parts: one judge reply hit the 20,000-token output limit with 16,683 tokens spent reasoning (this provider ignores the reasoning cap), and that one failure stopped the run. Now a fault in one part's judge reply (cut off, unreadable, wrong shape) marks that part 'Could not be judged' with the reason, on the page, in the email and in the script, and the run goes on; the run fails only if every judged part failed. Errors outside the reply (budget, timeout, rate limit, auth) still stop the run, so a systemic fault cannot spend searches on every part. Output limit left at 20,000 to hold cost; the parts that fail are the case for a stronger model in production | **Done** · rerun pending |
| 90  | From run 89f045's 107 findings: the judge kept datasheets, manuals, developer docs, manufacturer pages without a price, parts-broker stock pages ($0.00) and a price aggregator, because its rule kept any page that 'sells or specifies' one product; foreign sellers cluttered same-part results; alternative searches were keyword lists. Now: (1) the judge records each page's kind (seller listing, manufacturer page, other) and keeps a same-part page only when it is a seller listing buyable in India, an alternative only when it is a seller listing or manufacturer page, and drops documentation, broker and comparison pages; (2) searches are one-sentence descriptions of the page wanted; (3) Exa highlights are steered at price, pack size, GST, stock and specs (same searches, same pages, no extra calls), with page text trimmed so the prompt stays the same size; (4) the judge flags pages saying a product is discontinued; the summary counts same-part sellers. The email and the Decisions view now lead with three sections, one row per part: 1. Same part, cheaper seller; 2. Better or newer, fits; 3. Cheaper alternatives, fits as is first, then needs adaptation; everything else follows by part. Quote grounding was proposed for placement and rejected as string matching | **Done** · test run pending |
| 91  | After 5-part test 44e7d3: (1) the judge's note on the top saving row (ACE-013) gave invented numbers; the judge is no longer asked to compare prices across pages, and the email's number summary is gone: it opens on the three tables; (2) TF-Luna's Section 2 pick was 'minor changes' though its own text needed a new driver, mount and a lower laser class: minor now means only a cable, connector, bracket or setting with the same interface, protocol, supply, safety class and mounting shown; changes the page says are needed make it major, missing facts make it fit unclear; (3) ACE-008 cut off again (18,444 reasoning tokens): the judge fills only keep and reason for dropped pages, judge limit 20,000 → 24,000, item renamed microSD (team confirmed); (4) team: ACE-011 range is 5–7 mm metal detection (was 1 m), and CE, RoHS, UL, UK, EMI & EMC compliance is required for every Electrical and Embedded part, added to their Must Have as one check | **Done** · re-test pending |
| 92  | After re-test 68bd27 (TF-Luna alternatives correctly major, microSD judged with a ₹199 saving, Sick alternatives now 5–7 mm inductive): (1) the judge's notes no longer repeat Must Have results such as an unstated compliance mark; those stay in the checks; (2) a listed price with a lower before-GST figure is labelled 'GST included' in the email and on the page, and our side reads 'Ours, before GST: unit × qty = total' as in the Embedded ACE BOM, whose rates are before GST; (3) TF-Luna's Must Have filled from Benewake's own product page (range, interface, frame rate, power, size). Embedded ACE BOM checked line by line against the workbook: all 53 shared lines match on qty and rate except ACE-004 (BOM 2 × ₹620 = ₹1,240; workbook 1 × ₹620, item says 'pack of 2') | **Done** · ACE-004 to confirm |
| 93  | GST % column added to the ACE workbook at the user's request (18% for Electrical, Embedded and Mechanical parts; 5% for the two Forbo belts), as its last column; the loader requires it. A seller price marked GST included with no before-GST figure on the page is now brought to before GST at the part's own rate ('before GST at our 18% rate'), where it was compared as listed; a before-GST figure the page states is still used as is; 'GST not stated' is still compared as listed. Our side shows unit × qty = total before GST and the total with GST, as in the Embedded ACE BOM | **Done** |
| 94  | ACE-004 aligned with the Embedded ACE BOM on the user's say: qty 1 → 2, '(pack of 2)' dropped from the item; line ₹620 → ₹1,240, machine ₹2,40,596 before GST. Every Embedded BOM line now matches the workbook | **Done** · full run pending |
| 95  | From run a4ec6b and procurement's review: compliance marks were going into searches (pulling certificate PDFs and company profiles), a search named our own vendor, and 121 of 200 alternatives had no rupee price. Now the plan leaves certifications and the current vendor out of searches and asks for an equivalent from a different manufacturer, sold in India with a price (no makes named from model memory); the judge records each product's maker and the certifications the page itself states (never inferred; nothing dropped for lacking them); the summary counts makes found; Section 2 also lists better options needing major changes, after drop-in and minor ones, for procurement to weigh; a new Section 4 lists the certifications each option's page states, or 'none stated: ask the maker'; the part number shows under each part. Workbook (synthetic, user-approved, marked '(assumed)'): Jetson Nano's performance as its Must Have (472 GFLOPS FP16, 4 GB, CSI-2, ≤10 W, GbE and USB 3.0, production module), and closest-fit models for 9 parts without one (fan, display, interlock, light curtain, MCB, RCCB, SPD, inverter, battery) | **Done** · re-test pending |
| 96  | After 8-part test 8f5573 and feedback that prices were confusing: one price wording, built once per finding in code (`price_display`) and printed by both the email and the page: Ours before GST (each × qty = total, and incl. GST); As listed (incl. GST / + GST / GST not stated); Before GST, each, with how it was worked out (stated on the page / the listed price is before GST / listed price ÷ 1.18, our 18% GST / GST not stated: the listed price is used); vs ours. A same-part price more than 40% below the middle of at least 3 other sellers' prices is flagged 'far below… check before acting' and never counted (on 8f5573: the ₹8,599 display listing and an out-of-stock Jetson module). Options whose page names no maker stay out of sections 2 and 3; an unnamed shop shows as 'shop not named (<site>)'. GeM excluded as a seller (Recykal is not a government buyer). A price marked GST excluded counts as before GST even without a separate figure. Jetson item: Waveshare kit, module with carrier board (assumed) | **Done** · re-test pending |
| 97  | User's standard for prices: never change the seller's listed price. Code now puts OUR rate on the seller's GST basis instead (our rate + our GST % when their price includes GST; before GST when it excludes GST or does not say, labelled), then works out the difference and saving per machine on that basis; packs and lengths are the only conversion (× the judge's units per part). Removed: dividing seller prices by 1.18, the judge's before-GST figure, the 40% outlier rule (replaced by the judge's own `price_doubtful`, shown in red and never counted), and the last text check in component watch (rupee detection from the currency text, replaced by the judge's `rupee_price`). The page's rupee total of savings is gone, since rows may sit on different GST bases. Email, page and CSV print one wording from `price_display` | **Done** · re-test pending |
| 98  | Procurement feedback on run a4ec6b (the 8-part test runs had been deleted, so a4ec6b, judged before makers and certifications were recorded, was the one on screen): (1) certifications now sit beside each listing, under the product and seller, in the email, the page and every per-part table; the separate Certifications section is gone; (2) out-of-stock listings were reaching the top sections (6 findings had 'out of stock' in their notes with the stock field unset): the judge now marks stock 'no' for out of stock, sold out, unavailable, pre-order or back-order wherever the page says so, and such listings are shown with a red 'out of stock' tag but never counted; (3) the judge records whether the seller is the maker, an authorised distributor (only when the page says so) or another seller; the top sections take a maker or authorised distributor first when one qualifies, and the seller is labelled | **Done** · re-test pending |
| 99  | Out-of-stock listings are now dropped at the judge like any other unusable page (out of stock, sold out, unavailable, pre-order, back-order): never stored, shown or counted, and listed in the run trace with the reason 'out of stock'; a kept finding the judge marks stock 'no' is dropped the same way. The 'shown but never counted' tag from row 98 is removed | **Done** · re-test pending |
| 100 | User's decisions on what nobody can act on: listings priced outside rupees (the business buys only in India) and discontinued products are now dropped at the judge like out-of-stock ones, never stored, with the reason in the run trace ('Out of stock', 'Discontinued', 'Not sold in India'). 'Fit unclear' is renamed 'Needs verification' and is its own group, never an alternative (summary: 'Needs verification: N'; never in the three sections). 'Price doubtful' is renamed 'Price unclear'. Tags cut to one or two plain words: 'Price not available', 'Seller not named (site)', 'Certified: CE, RoHS', 'Certifications: not stated', 'Unit unclear', 'GST % missing', '+ GST (GST not stated)'. Quote-on-request listings kept. README and pyproject describe the tool for Retearn | **Done** · re-test pending |
| 101 | No tags for edge cases: 'GST % missing' removed (the workbook loader now refuses a blank GST %), 'Unit unclear' and 'Not in rupees' removed (the cell shows '—'; non-rupee listings are dropped), an unnamed seller shows as its website, certifications show only when the page lists some, and the comparison reads '+ GST' without a note. Kept: Price not available, Price unclear, Needs verification, and the listed price's incl. GST / + GST / GST not stated | **Done** · re-test pending |
| 102 | Run 345164: the judge answered 1 of 16 pages for ACE-028 and ACE-036 (30 of 126 pages never answered; 38 of 531 in full run a4ec6b), and code silently took what came back, because the reply was a list of any length. The reply is now one required slot per page (page_0 … page_N, built per call), so a reply that leaves a page out fails validation and the part shows 'Could not be judged: the reply left out page_4' instead of losing pages. Dropped-page reasons capped at a few words (80 characters). Certifications no longer decide fit: effort is judged on the stated specs (size, mounting, interface, electrical ratings, function); missing marks never make an option needs verification, minor or major (8 of 11 'needs verification' in 345164 cited missing marks); a safety part still needs its safety rating for drop-in. Makes counted regardless of capitals; the script prints the shared seller wording | **Done** · re-test pending |
| 103 | Run 49fef4: with every page required, 6 of 8 judge replies were cut off at the 24,000-token limit (21,000-24,000 spent reasoning): judging 16 pages in full does not fit one reply for this model, which is also why it had been answering 1 page. Results per search 8 → 5 (up to 10 pages per part, one call): in run a4ec6b, results 6-8 gave 77 of 273 findings but only 1 of 14 top-section rows | **Done** · re-test pending |
| 104 | Run ddc28b (every page answered, no cut-offs) showed: (1) Jetson's alternative search used the Nano's own spec (472 GFLOPS FP16…) and found Nano pages, and 'a different manufacturer than the current one' ruled out NVIDIA's own successors such as Orin: the alternative search now asks for another model that does the job, a newer one from the same maker or an equivalent from another maker, with the specs stated as needs; Jetson's Must Have now reads 'AI compute of 0.5 TOPS or more' (assumed, team's suggestion); (2) the same Elume page was 'incl. GST' in one run and 'not stated' in the next although the judge's own note said incl. GST: the judge now records the price, its GST basis, currency and unit before any notes, and incl. GST, inclusive of all taxes and an MRP count as included, + GST, excl. GST and ex-tax as excluded; (3) safety class was being asked of displays and inverters: minor changes needs the same safety class only for parts with a safety function; (4) a same-part listing with an unclear price still counts as found ('Same part from N seller(s), 1 with an unclear price') | **Done** · re-test pending |
| 105 | Full run 72fe64 against a4ec6b: more comparable prices (157 vs 122), more parts at the lowest price (14 vs 9), fewer with no comparable price (18 vs 29), no pages lost (38 before), but 5 parts cut off and the ₹649 5 V supply and the SPD saving missing. Jetson's alternative search there was 'an NVIDIA Jetson module with 0.5 TOPS, 4 GB RAM… 10 W', i.e. the Nano itself, so all five results were Nanos. Demo freeze changes: alternative searches now ask for a newer or more capable replacement for the named current model (its successor from the same maker, or another maker's equivalent) with needs as minimums, never the current model's exact figures; section 3 drops options that fail a Must Have, as section 2 already did (the 15.6-inch Acer); stock is read with the price and GST before any notes (the FlyRobo scanner showed 'Out Of Stock' beside its price yet was kept); Jetson Must Have power 10 W → 15 W (assumed, Orin Nano is 7-15 W). After the demo: a fixed, labelled reference set and saved page text, so every change is scored before it goes in | **Done** · freeze for demo |


## End of Phase 1 — where things stand, 28 September

Measured on runs 48d057, 5249ba and c6a554 (DeepSeek V4.1 Flash, Exa, caps 70/8/20/30, 6 sites).


| Measure                             | Value                                                  |
| ----------------------------------- | ------------------------------------------------------ |
| Model calls per run                 | 16–19                                                  |
| Tokens per run                      | ~75–90k in; ~7–9k answer; ~43–56k thinking             |
| Model cost per run                  | ~$0.045–0.050                                          |
| Exa per run                         | 4–5 searches × $0.014 = ~$0.06–0.07                    |
| Scrapes per run                     | 4–14 of 20                                             |
| Wall time                           | 5–15 min, most of it paced scraping and model thinking |
| Opportunities saved per run         | 1–6                                                    |
| Largest call against its output cap | extract 60%, plan wave 2 51%, evaluate 44%, rank 35%   |


**What limits results today**, in order of effect:

1. **Link discovery is starved.** Firecrawl runs with main content only, which strips site
  navigation — where "Key dates", "Nominate" and "Eligibility" links live. Seed pages yield
   0–29 links and the link picker is usually offered 1–3. SABERA was offered one link, back to
   itself, so its deadline page was never reached.
2. **Ranking passes fewer sites than there are seats.** In 4 of the last 5 runs everything
  that passed was fetched; order never mattered. It also passes weak pages (attendee and
   speaker lists) as "enterable".
3. **Budget goes unspent.** Runs use 4–5 of 8 searches; re-planning only happens when
  nothing at all is found.
4. **Extract's pursue decision is lenient.** Evaluation catches it (Zarabi: "early-stage only",
  not met), but the record is still stored as ready.

**Data already on hand for Phase 2**, reusable without new credits: 7 runs in Mongo with
233 search results (165 unique URLs), 39 ranked picks, 47 unique pages with stored text,
45 extracted candidates and 40 stored opportunities; plus `reference/exa-pool-652ec9.json`
(35 Exa results from a run no longer in Mongo). All of it is Exa; the Tavily-era sets were
removed on 5 Oct (item 45).

## Phase 2 — plan

### Feedback taken in

From the Phase 1 review:


| #   | Feedback                                                                                                              | Workstream                                 |
| --- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| F1  | No caching: the same searches and pages are paid for again                                                            | W2                                         |
| F2  | Cataloguing is convoluted; this is a cataloguing problem — know it once, store it structured, don't rediscover        | W2                                         |
| F3  | Sharpen domain-based search: get more from one search instead of many broad ones; explore component costs as a domain | W3                                         |
| F4  | Test a dedicated re-ranker on a small batched eval against the current ranking                                        | W4                                         |
| F5  | Define the confidence scoring: how aligned an opportunity is with the organisation                                    | W5                                         |
| F6  | Stay on free tiers; testing must not exhaust them                                                                     | Budget rules below                         |
| F7  | No confidence at the decision points (search, selection, pursue/skip)                                                 | W5                                         |
| F8  | Evaluation judges conditions without the source page                                                                  | W5                                         |
| F9  | Queries framed on product terms, not technology and demonstrated impact                                               | W3                                         |
| F10 | Uniform model across nodes                                                                                            | W8                                         |
| F11 | No repeatable measurement of quality                                                                                  | W1                                         |
| F12 | Default tool-call budget insufficient for a full cycle                                                                | W1, then re-size                           |
| F13 | Hand-labelled set for scoring retrieval with a re-ranker                                                              | W1, W4                                     |
| F14 | Classify by opportunity type; run per type                                                                            | W6                                         |
| F15 | Discovery window (e.g. next 6 months)                                                                                 | W7                                         |
| F16 | No outbound notification                                                                                              | W7                                         |
| F17 | Deeper and wider on paid tiers                                                                                        | Deferred until W1–W3 show where depth pays |
| F18 | The programmes registry should drive the search                                                                       | W2, W7                                     |
| F19 | Scheduled autonomous runs                                                                                             | W7                                         |
| F20 | Technical and research axis searched on the engineering                                                               | W3, W6                                     |
| F21 | Search specificity: is an Awards or Events run enforced, and is it cheaper than Everything?                           | W3 (specificity)                           |
| F22 | Search for cheaper or better components for the RVM product line                                                      | W9                                         |
| F23 | Engineers' feedback: a deliberate, on-demand search for one chosen component, instead of discovery running across every part | W9; register-level now, RAG / catalogue later |


Two review points need correcting against the code, not just accepting:

- **"No parallel execution."** Fetch and extract already run one lane per site in parallel.
Firecrawl scrapes are serialised on purpose, because the free tier caps requests per minute.
- **"Tool-call budget insufficient."** Recent runs use 17–33 of 70. The binding limit is how
few sites ranking passes, not the cap. Re-size only after W1 can measure the effect.

### Budget rules for Phase 2 (F6)

Balances at the start of Phase 2 (5 Oct): **Exa $20.00** (~1,400 searches at $0.014; resets
monthly), **Firecrawl 643 of 1,000** (resets 21 Oct). OpenRouter is paid, at cents per run.
Logged in `reference/spend-ledger.md`.

1. **Replay before live.** Every change to planning, ranking, extraction or evaluation is
  first checked against stored data (W1). No live run to test a prompt.
2. **One live run per milestone**, not per change. Each costs ~5 Exa searches and ~15 scrapes.
3. **A spend ledger** (`reference/spend-ledger.md`): date, what was tested, searches, scrapes,
  model cost, remaining balances. Updated after every live call.
4. **Cache first (W2)** so that repeated tests read stored pages instead of re-scraping.
5. **Credit-spending tests need an explicit yes**, as in Phase 1.

### Workstreams

**W1 — Measurement: labelled set and replay** (F11, F12, F13; item 27)

- Label the 165 unique search results already stored: is it the programme's own page, can
Retearn enter, is it current, which opportunity type. A small labelling page or a CSV.
- Label the 45 extracted candidates: correct pursue/skip, correct deadline, conditions real.
- A replay harness that runs ranking, extract and evaluation on stored inputs and scores
against the labels: precision of the top sites fetched, passed-good vs passed-bad, correct
dates, condition verdicts matching a human's.
- **Credits:** no search or scrape; about $0.01–0.05 of model per replay.
- **Done when:** a change can be scored in minutes and compared to the Phase 1 baseline.

**W2 — Cache and catalogue** (F1, F2, F18; items 24, 31)

Three stores, each with one job:


| Store        | Key              | Holds                                                                                                            | Used for                                                                                          |
| ------------ | ---------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Search cache | provider + query | results with Exa facts, fetched date                                                                             | re-running a query within its TTL costs nothing                                                   |
| Page cache   | canonical URL    | page text, links, content hash, fetched date, outcome                                                            | a page read in the last N days is not re-scraped; a changed hash marks the programme for re-check |
| Catalogue    | programme id     | names and aliases, organiser, known URLs, type, editions with dates, last verified, next expected window, status | "already known" is shown to ranking; known programmes are refreshed, not rediscovered             |


- **Two kinds of run:** a *refresh* re-checks catalogued programmes whose window is near (no
search, one scrape each); a *discovery* searches only for what the catalogue does not know.
- **Identity (item 31):** one programme under two titles is resolved in the catalogue. Same
site + same organiser + same year is not a safe rule (raceexpos.com holds two real
programmes), so a candidate match goes to a small model check or a merge in the dashboard.
- **Seeding:** the 47 stored pages and 40 stored opportunities seed the page cache and
catalogue, so W2 starts with data and no credits.
- **Model prompt caching:** put the stable part of each prompt (profile, rules) first so the
provider's prefix cache applies. Cached reads today are only a few thousand tokens a run.
- **Done when:** a second run on the same queries spends no search or scrape credits on
anything already known, and the Results page shows one record per programme.

**W3 — Search economy and domain sharpening** (F3, F9, F20)

- **More per search:** Exa bills up to 10 results in the base price; we ask for 7. Ask for 10.
Richer summary fields are free per page (item 42 did this for dates).
- **Listing pages become leads:** a directory page that names ten programmes is dropped today.
Extract the names into the catalogue as unverified leads for later refresh runs.
- **Fix link discovery** (limit 1 above): take links from the full page while keeping the
main-content text. Needs a 2-scrape test of Firecrawl's behaviour first.
- **Queries on technology and impact**, per opportunity type, taken from the profile's
Search angles; checked against the W1 labels, not by eye.
- **Component costs:** a separate objective (procurement, not recognition). Scope it as its
own profile section and record type once W1–W2 exist, not inside the opportunity flow.
- **Credits:** ~10–20 Exa searches and 2 scrapes of targeted tests.

*Search specificity (F21).* Today the focus is one prompt line in plan, rank, link picking
and extract. Nothing in code filters on it, and a focused run has the same path and caps as
Everything. Two focused runs stayed on type (223e14 awards, 8b7309 research) and used fewer
scrapes, but only because fewer results passed ranking. The change: **type becomes data
that code enforces.**

1. **Measure:** add type to the W1 labels; replay ranking per focus on stored pools. Metrics:
  on-type share of fetched sites; searches + scrapes per on-type record saved. No credits.
2. **Type on every result:** an `opportunity_type` field in Exa's summary (free, billed per
  page) and on each ranked pick. When a type is chosen, code does not fetch off-type picks
   (set aside, visible) and stores off-type records to the catalogue only, not the run's Results.
3. **A playbook per type**, in one config block: what the type is called on the web, what to
  pair it with (field and impact; technical subfield for research), what to avoid, and known
   source domains via Exa's domain filter.
4. **A budget per type** (start: awards 6 searches × 3 pages; events 4 × 2; research 4 × 2),
  with 10 results per search and catalogue-first refresh.
5. **Validate:** ~15 Exa searches (5 per type), on cached pages where possible.
  **Done when:** ≥90% of fetched sites match the chosen type, and searches and scrapes per
   on-type record fall below the Everything baseline.

**W4 — Re-ranker feasibility** (F4, F13)

- Compare on the W1 labelled pool, in small batches: (a) the current listwise model ranking,
(b) a dedicated re-ranker, (c) Exa's own order.
- Candidate re-ranker within the approved model families: **Qwen3-Reranker** (open weights,
runs locally, so no credits).
- Measure precision of the top 6, the good pages missed, cost and time per pool.
- **Decision gate:** adopt only if it beats (a) on the labels. It may also serve as a cheap
first pass that trims the pool before the model ranks it.

**W5 — Confidence and alignment, defined** (F5, F7, F8)

Written as a specification before code, then checked on the W1 labels. Two separate things,
never blended into one number:

- **Fit** — how aligned the opportunity is with the organisation: hard conditions met / not
met / unknown, and whether the type is one the profile seeks.
- **Certainty** — how sure we are of the facts: own page read, deadline found and quoted,
conditions found, date conflicts flagged.

Outputs are tiers with reasons (e.g. Eligible / Likely / Needs review / Not eligible), not a
decimal score. Every decision point records its own confidence and reason: rank per pick,
extract per pursue/skip, evaluation per condition. Evaluation also receives the page passage
each condition came from (F8), and code checks that every condition comes back exactly once.

**W6 — Opportunity types and their record shapes** (F14, A3, F20)

Types: award, event (exhibit), event (speak), research / call for papers, challenge. Each has
its own definition of a complete record: an award needs conditions and a deadline; an expo
needs dates, a way to take part and the cost; a call for papers needs scope and a submission
deadline. Runs can target one type. This removes attendee lists being judged as conditions.

**W7 — Time window, registry-driven runs, scheduling, notification** (F15, F16, F18, F19)

- A rolling window per run (default 6 months): applied at ranking where dates are known and at
storing, where out-of-window records go to the catalogue only.
- A weekly scheduled run: refresh what the catalogue says is due, then discovery with what
budget remains.
- An email digest after each scheduled run: new, changed, closing within 14 days. Reuses the
existing mailer and SMTP_TO.

**W8 — Model per call type and remaining clean-up** (F10; items 26, 30)

- Choose a model per call from W1 scores: strongest where a wrong call wastes scrapes
(ranking), cheaper for bulk reading. Turn reasoning off where it adds nothing (link picking).
- One server-built CSV for Download and Email (item 30); remove the memory fallback for saved
progress (item 26); delete `profile_seed.py`; rewrite `CLAUDE.md`; drop the digit/"must"
flag (E4).

**W9 — Component sourcing for the RVM line** (F22)

A second objective on the same pipeline: find cheaper or better components for the RVM
product line. Procurement, not recognition, so it has its own brief, record and evaluation,
and never mixes with opportunity runs.


| Step           | Opportunity runs                   | Component runs                                                                                                                                                                         |
| -------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input          | Business profile                   | **Component brief**, one per part: function, must-have specs, nice-to-have specs, current part and price, target (cheaper by X%, or better at Y)                                       |
| Plan           | Queries from the profile           | Queries from the function and specs, plus the current part number for drop-in alternatives                                                                                             |
| Search         | Exa                                | Exa to **discover** suppliers and alternatives; **distributor APIs** (e.g. Octopart/Nexar, DigiKey, Mouser) for price breaks, stock and lead time — terms and free tiers to be checked |
| Rank           | Programme page, enterable, current | Real product page, buyable in India, plausibly meets the must-have specs                                                                                                               |
| Extract        | Conditions, deadline               | Datasheet specs, price breaks, minimum order, lead time, certifications                                                                                                                |
| Evaluate       | Conditions vs profile              | **Specs vs the brief, same mechanism:** each must-have spec Met / Not met / Unclear; quality and reliability go to a person                                                            |
| Compare        | —                                  | **Price difference computed in code** against the BOM baseline, never by the model                                                                                                     |
| Catalogue (W2) | Programmes and editions            | Components → alternatives → last price, stock and date checked                                                                                                                         |


**Rules:**

- Price arithmetic happens in code from structured data. The model only judges spec fit.
- BOM costs stay local; only specs go to the model provider, unless approved otherwise.
- Prefer distributor APIs to scraping storefronts: structured, current, and within terms of use.

**Choosing what to search:** rank BOM lines by annual spend (unit cost × quantity per machine
× machines per year), then by risk (single source, long lead time, import dependence), then
by swappability (no redesign or requalification needed). Pilot on **3–5 parts** that are
high-spend and swappable. Refresh monthly through the catalogue. The baseline is cost per
part and per machine, so every alternative reads as "saves ₹X per machine at the same spec".

**Data to request from the inventory team** (start now; it takes time to collect):

- Per RVM model (Reklaim PRO, ACE, Mini, Neo, FastScan), the BOM with, per line: component
name and subsystem; manufacturer and part number (MPN); current supplier(s), imported or
sourced in India; unit cost with currency, duty and freight, and the date of that price;
quantity per machine; machines built per year, actual and planned; minimum order quantity;
lead time; history of stock-outs, price rises or quality failures.
- For the parts they most want improved: datasheet and the specs that matter (electrical,
interface, size, operating temperature, ingress rating); required certifications (BIS, CE,
RoHS…); swappable or locked by design, firmware or certification, and the requalification
effort; alternatives already tried and why rejected; the target (cheaper by how much, or
better at what).
- Constraints: approved vendor list; preference for Indian or local suppliers; which data may
go to an external AI provider and which must stay internal.

**Depends on:** W1 (labels and replay, extended to components), W2 (catalogue), W5 (fit and
certainty, reused for spec matching). **Credits:** pilot of ~3–5 searches per part plus API
calls on free tiers. **Done when:** for each pilot part, at least one alternative is found
with every must-have spec Met, a computed price difference, and its datasheet as the source.

### Order


| Stage           | Workstreams                          | Credits needed                         | Why this order                                                                           |
| --------------- | ------------------------------------ | -------------------------------------- | ---------------------------------------------------------------------------------------- |
| A — Foundations | W1, W2; W9 data request to inventory | None (stored data)                     | Everything after is measured by W1 and made cheaper by W2; the BOM takes time to collect |
| B — Definitions | W5, W6, W7 window                    | None (replay)                          | Changes what counts as good, so it comes before tuning                                   |
| C — Retrieval   | W3 including specificity, W4         | Small: ~35 searches, 2 scrapes         | Tuned against labels, on cached pages                                                    |
| C′ — Components | W9 pilot on 3–5 parts                | Small: ~15–25 searches, API free tiers | Reuses W1, W2 and W5 once they exist                                                     |
| D — Autonomy    | W7 schedule + digest, W8             | One live run per milestone             | Only worth scheduling once results are measured good                                     |
| Later           | Paid tiers (F17)                     | Paid                                   | Only where W1 shows depth is the limit                                                   |


Milestone live runs: end of A (baseline on the new catalogue), end of C, end of D.

### 31 — records shown under the wrong run, and one programme under two titles (28 Sep)

- **Display:** `/api/runs/{id}/results` finds records by source URL, so an older record at
the same URL shows under a newer run (22ff3a's "Circular Economy Awards" under 48d057).
Fix: match on URL and title from the run's `save_opportunity` events.
- **Storage:** identity is organiser + base title + cycle year, so "Circular Economy Awards"
and "Global Circular Economy Awards" are two records. Same URL + organiser + year is not
a safe merge rule: raceexpos.com legitimately holds an expo and its speaker programme.

### 30 — Results and CSV show everything extracted (manager feedback, 25 Sep)

Extract captures far more than the Results card and CSV show. The Zarabi award's
record notes the page contradicts itself on the closing date; the CSV drops it.

- **Store three more fields:** extract's pursue reason, the ranker's reason, the page's status.
- **Results card, ordered for the decision:** header with days to deadline; what it is;
why it's here; each condition with verdict and reason, then judgement calls; what to
submit and how it's judged; check before acting (uncertainty, gaps, unfound quotes,
flagged conditions); sources and the quoted sentences.
- **One CSV, built on the server,** for both Download and Email. Opportunities sheet
gains summary, days left, deadline note, reasons, uncertainty, gaps, and conditions
with verdicts; a second Conditions sheet has one row per condition.
- Today the dashboard CSV (`frontend/src/export.js`) and the emailed CSV
(`src/opportunity_radar/reporting.py`) are separate code and already differ.

### 14 to 22 — what changed, 22-23 September

**Strict schemas.** Every property is now marked required in the JSON schema we
send. Pydantic leaves defaulted fields out, which OpenAI rejects outright — so
GPT-4o-mini could not run at all and looked like a failing model when the
request was invalid. It now runs, and is the fastest of the four tested.

**No planning fallback.** A plan built in code from parsed profile fields fired
on a live run and searched on product names, which the planner's own rules
forbid, while hiding the real failure — a 180s timeout. The fallback is deleted,
planning raises, and the planning calls moved to the 300s ceiling.

**Date signals.** `published_date` is requested (free) and parsed from RFC 2822
rather than sliced, and years are read from the title and address. Both are
given to the ranker as facts. Coverage measured on a real pool: publish date on
25% of results, a year on 42%, at least one on 51%.

**Firecrawl pacing.** A semaphore capped concurrency, which does nothing to a
per-minute limit: one-at-a-time still fires ~20/min. Scrapes now hold a lock for
the whole request and wait out a 7s interval, giving 8.6/min against a ~10/min
cap.

**Identity.** Storing "not stated" inside the identity key made an unknown
organiser a different programme from the same award with a known one — the
A' Design award was stored twice, once with five conditions and a deadline and
once with neither. A named record now adopts the placeholder; an unnamed one
joins the record that exists.

**Eligibility budget.** 4,096 tokens with no reasoning reserve meant the richest
record was the one that failed: twelve conditions need the most output. Now
12,000 with 40% reserved, matching every discovery call.

**Seat sizing.** Ranking sized its picks on remaining tool calls rather than
remaining scrapes, so a re-plan picked five sites with no scrape budget left and
every one came back with zero pages. It now sizes on scrapes.

### 23 to 27 — found while documenting, not yet done

**Duplicate pages reach ranking.** The same page on two hosts —
`ecopreneur.timesofindia.com` and `timesofindia.indiatimes.com` — entered the
pool as two results with byte-identical content, ranked first and second, and
were both fetched. Six scrapes of a fifteen-scrape budget on one page. Dropping
a result whose content exactly matches one already held, before ranking, costs
nothing and frees a slot.

**A third of scraping is re-reading.** Across eight runs, 84 fetches covered 58
unique URLs: 26 credits spent re-reading pages already read, one of them a terms
and conditions page fetched four times. Good programmes rank well every run, so
they are fetched every run. A page cache keyed on canonical URL with a TTL would
cut it.

**The search API may already carry the content.** `include_raw_content` is free
and returns the cleaned full page; we pay Firecrawl separately for the same
text. Measured on real pages, the page opening holds the dates that the
query-matched extract misses — ICEF states 20-21 Aug 2026 at character 230 while
its extract contains no date at all. Unknown: how stale Tavily's index is,
whether consent banners survive its cleaning, and that it returns no link graph,
which link-following needs. One search settles it.

**Two fallbacks remain.** Ranking falls back to search-engine order, and saved
progress falls back to memory when Mongo is unreachable. Both keep a run alive
on a worse path, which is the pattern already removed from planning.

### B2 is dropped, not deferred

B2 proposed refusing a record with no date. The code already handles this
correctly and the comment in `actionability.py` names the case:

> a keyword regex here was a third and worse opinion: "Nominate Now" and
> "Express Interest" failed it, so Greentech, CII and the ET Sustainability
> Awards were each discarded.

A missing date is a gap in what we read, not evidence the programme is shut, so
it is stored and surfaced as "no date found — verify on the source page".
Proven live on 21 Sep: India Technology Awards had no deadline, was stored, and
was judged at score 1.0. **Implementing B2 would re-break exactly the case it
was meant to protect.** Removed from the list.

### A4 is deferred until after depth-3 testing

A4 proposed telling the link chooser what the run is looking for. The 21 Sep run
shows the chooser is not the failing part — its own reasons were "Brochure
contains full entry details; Eligibility states who can enter" and, on a page
offering one link, "only link is a winners announcement, which should be
skipped". It picked correctly and declined correctly.

What lost the conditions was depth: `max_pages_per_seed = 2` meant the seed page
plus exactly **one** followed link, so on CII the chooser picked the brochure
*and* the eligibility page and only one was ever fetched. Depth is now 3.
Revisit A4 only if depth-3 runs show the wrong pages being chosen.

### 12 — what the parallel fan-out exposed, 22 September

Splitting `fetch` into one instance per site changed *when* resources are spent,
not how many. Three things broke on the first live run:


| Problem                                 | Cause                                                                         | Fix                                                                                                   |
| --------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 4 scrapes lost to `Rate Limit Exceeded` | 8 sites fetching at once burst past Firecrawl's per-minute cap                | scrapes queue through one lane                                                                        |
| 3 sites scraped then never read         | all 8 link-picks ran before any analysis, exhausting the 16-call model cap    | `rank` now sizes its picks against the model-call budget too, and the caps were raised to fit 8 sites |
| `select_links` returned nothing         | `reasoning: {effort: "low"}` is advisory; nothing was reserved for the answer | an explicit `reasoning.max_tokens` reserve, same as every other call                                  |


The third was not caused by the split — `TOKENS_PICK_LINKS` and `light=True` are
unchanged since the "working pipeline" commit. It became *visible* because
failures are now attributed per-site instead of blending into one research step.

### 13 — the organiser may now be "not stated", 22 September

`organizing_body` was required with `min_length=1`, so a page that never says who
runs the programme forced the model to invent one. The Aegis Graham Bell record
was stored with `organizing_body: "mUni Campus"` — the page says only "POWERED BY
MUNI CAMPUS" and names no organiser at all. A grounding check would have *passed*
it, because that phrase really is on the page.

The field is now optional. Blank is stored as "not stated" with a warning, and the
prompt says the quote must be the sentence saying who runs it, never a sponsor,
partner, platform or "powered by" name. The identity key is unchanged until we see
how often this happens.

### 1 and 2 — what changed, 21 September

**Merge rules.** Six fields in `DiscoveryState` now say how to join new items to
what is already there, instead of replacing everything. Repeats are dropped by
whatever identifies that thing — a query by its text, a search result by its
address, a site by its seed address, a candidate by its title and address.

Each step now returns only what it added, rather than the whole list it was
given. That was the other half: with merge rules but whole-list returns,
everything would have been counted twice.

**Saved progress.** The graph now records the state after each step, keyed by
the run id. A run that dies part-way keeps the steps it finished.

Our own data types are listed by name in the saver's settings, so they come
back as themselves rather than as plain dictionaries — without that they
survived the trip but arrived as untyped data, which would have broken the step
that read them.

**Checked by:** a full dry run end to end. No duplicates in any of the six
fields, nothing lost, six steps recorded and restored with their real types.

**What this does on its own:** nothing visible. It is the change that makes
steps 3 and 9 possible — until now two steps could not write the same field, so
every "do this for each site" had to be a loop inside one step. That is the
actual reason `research_node` is 202 lines.

**Left open:** nothing yet *reads* the saved progress to resume a dead run —
the progress is written, but restarting a run still starts it from the top.
That is a small separate piece.

### 3 — the split, as built on 21 September

Seven steps, each with one job. `fetch` and `extract` run **once per site**,
started together, rather than as a loop inside one step.

```
plan → search → rank ─┬─(one per site)→ fetch → extract ─→ evaluate ─┬→ store → end
                      │                                              │
                      └── pool too thin ────→ plan ←─ nothing found ──┘
```


| Step       | Job                                                           | Reaches out to                    |
| ---------- | ------------------------------------------------------------- | --------------------------------- |
| `plan`     | write the search queries                                      | the model                         |
| `search`   | run the queries not yet run, in two waves                     | `tool_tavily_search`              |
| `rank`     | order the whole pool best-first, choose sites **and say why** | the model, Mongo                  |
| `fetch`    | get the pages for **one** site                                | `tool_firecrawl_fetch`, the model |
| `extract`  | read **one** site, build and check its records                | the model                         |
| `evaluate` | judge each record against the profile, condition by condition | the model                         |
| `store`    | write each record once, with its verdict                      | Mongo                             |


**What actually changed, beyond the names:**

- **The reason a site was chosen now reaches the step that reads it.** `rank`
worked out why each site was worth fetching, and the old code ended with the
line `_ = reason` — computed and thrown away. It is now carried to `extract`
and put in front of the model as something to confirm or contradict.
- **Judging happens before storing.** A record is written once, already
carrying its verdict. It used to be saved first and judged after, which is
why a run could report success before anything had been judged.
- **A failure names the step that broke.** One dead site fails its own `fetch`
and the other sites carry on; before, they shared a step with everything else.
- **One place decides whether to search again.** `evaluate` is the only point
where all sites have come back together, so the re-plan decision lives there.
Per-site counting would have counted four empty sites as four re-plans.
- **Every write to Mongo is in** `store`**.** Past editions used to be written from
the middle of the old finalize step; they are now handed to `store` with the
rejection that produced them.

**The grounding check, as agreed: a measurement, never a gate.** The model
returns the sentence it read a value from, and the code checks that its own
quote appears on the page. This is not word matching — that is what the deleted
`body_is_grounded` did, and it would pass "PRCA" against "practical" and fail
"Times Internet" against "TOI". Three fields carry a quote: who runs it, the
deadline, and whether it is open. The result is stored on the record and shown
as a warning. Nothing is rejected on it.

`ready` no longer depends on grounding either — it now means only what it says:
the page stated entry conditions.

**Checked by:** a dry run end to end. Seven steps ran in order, the site fanned
out to its own fetch and extract, one record was built, judged and stored, and
all three quotes were found on the page. The check also caught a real
inconsistency first time out — the fixture claimed a status sentence that was
not on its own page, which is exactly the failure this is meant to see.

**Left open:** `extract` still does three things in sequence — read the site,
validate each record, measure grounding. Only the first is a judgement; the
other two are plain checks over what it just produced, so they stay with it
rather than becoming steps of their own.

### 3 (original plan) — what we had and what replaces it

**A note on "tools".** No step has a list of tools the model may choose from.
Every outside call is written into the step itself. The model never decides to
search or to fetch — it only fills in a form. So "calls" below means what that
piece of code reaches out to, not what the model can pick.

#### What we have now — 4 steps


| Step           | Lines   | Jobs it does                                                                                                                                                                                                     | What it calls                                 |
| -------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `plan_queries` | 107     | write the opening searches                                                                                                                                                                                       | OpenRouter, Mongo (journey)                   |
| `research`     | **204** | run the first searches · **write a second set of searches** · run those · build and de-duplicate the pool · look up sites earlier runs found empty · rank the pool · fetch each chosen site and follow its links | Tavily, OpenRouter ×3 kinds, Firecrawl, Mongo |
| `analyze`      | 114     | read each site's pages in a loop, one after another                                                                                                                                                              | OpenRouter, Mongo (journey)                   |
| `finalize`     | **283** | build a record · check it is complete · check it is still live · record a past edition · save it · mark or clear a dead end · judge it against the profile · attach the verdict · write the summary              | OpenRouter, Mongo ×7 kinds                    |


The two problems this causes:

- `research` calls the **planner** inside itself. The picture says four steps;
the code runs seven.
- `analyze` and `finalize` loop over sites and records inside one step, so a
failure on the fourth site loses the first three, and the five analyze calls
run one after another instead of together.

#### What replaces it — 8 steps


| Step      | Its one job                                                          | Reads                                                   | Writes                       | Calls                                         |
| --------- | -------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------- | --------------------------------------------- |
| `plan`    | write search queries                                                 | profile, focus, what earlier searches returned          | queries                      | OpenRouter                                    |
| `search`  | run queries not yet run                                              | queries                                                 | search results               | Tavily                                        |
| `rank`    | order the pool, decide what is worth fetching                        | search results, profile, focus                          | the chosen sites **and why** | OpenRouter, Mongo (sites known empty)         |
| `fetch`   | get the pages for **one** site                                       | one chosen site                                         | that site's pages            | Firecrawl, OpenRouter (which links to follow) |
| `analyze` | read **one** site's pages, list what is on it                        | one site's pages, profile, **the reason rank chose it** | candidates                   | OpenRouter                                    |
| `build`   | turn a candidate into a record and check its fields against the page | candidates, pages                                       | records, rejections          | none — plain code                             |
| `store`   | save records, past editions, dead ends                               | records                                                 | saved ids                    | Mongo                                         |
| `judge`   | decide if we qualify, condition by condition                         | records, profile                                        | verdicts                     | OpenRouter, Mongo                             |


`fetch` and `analyze` run once **per site, at the same time**, which the merge
rules from step 1 now allow. `plan`, `search` and `rank` can each be visited
more than once when the pool comes back thin.

#### How they connect

```
        plan ── search ── rank
         ▲                 │
         │        pool too thin? go back and plan again
         └─────────────────┤
                           │ good enough
                     fetch ─┬─ one per site, together
                           │
                   analyze ─┴─ one per site, together
                           │
                     build ── store ── judge ── end
```

#### What this buys

- A failure lands in a named small step. Today a failure anywhere in fetching,
ranking or planning reports as "research failed".
- Five sites are read at the same time instead of one after another — on the
runs we have measured, about 300 seconds becomes about 60.
- With progress saved per step, a run that dies during `analyze` keeps its
searches and its fetches.
- `rank`'s reason for choosing a site can be handed to `analyze`, which today is
thrown away one line after it is produced.
- Two places that decide things get separated from the places that fetch, so
each can be checked on its own without a live run.

#### What it needs that we do not have yet

Two new things the steps pass between them: the chosen sites with rank's reason,
and the built records before they are stored. Both need merge rules, same as
step 1.

---

Every problem below is written the same way: what goes wrong, why it goes
wrong, what it does to the pipeline, what to do, why that fix and not another,
and what should change if we do it.

Measurements first, so nothing here is an opinion about size:

```
workflow.py            1,772 lines — 29% of all the code we have
prompt text            1,310 words, all five prompts, all in that one file
fields checked         1 of 12 (the deadline)
focus reaches          3 of the 5 prompts
dead code              about 200 lines the pipeline no longer calls
```

---

# Group A — The system does not know what it is looking for

## A1. One prompt asks for the exact thing another part of the same prompt rejects

**Problem.** When you pick "Awards", this sentence is added to the ranking
prompt:

> "THIS RUN WANTS AWARDS. Prizes, rankings, honours and **listings that name a
> winner**."

Fifteen lines further down, the same prompt says:

> "A page reporting winners, listing finalists... **rank it low**."

**Cause.** The focus sentences were written separately from the ranking
questions, months apart, and nobody read them together.

**Effect.** A results page — the commonest junk in every pool we have
collected — is asked for and rejected in one breath. The model picks one of
the two instructions and we cannot predict which.

**Fix.** Rewrite the three focus sentences to say what we want *found*, never
how to judge it. Judging belongs to the ranking questions alone.

**Why this fix.** The alternative is deleting the focus feature. But the focus
does useful work — an awards run and a research run should search differently.
The problem is that one line is doing two jobs. Split the jobs.

**Expected outcome.** No results page is ever asked for. The ranking questions
become the only place a page is judged, so there is one answer instead of two.

## A2. The same clash again, in the planner

**Problem.** The shared query rules say "Do not name a year." The research
focus sentence says "a year IS worth naming in some queries." Both go into the
same prompt.

**Cause.** I added the research exception without checking it against the rule
it contradicts.

**Effect.** For research runs the model gets two opposite instructions and
resolves it however it likes. For award runs the exception is not even
relevant, but it sits there confusing the instruction it follows.

**Fix.** State the year rule once, with its exception attached: "Do not name a
year, except when looking for conference calls, which publish next year's
dates early."

**Why this fix.** A rule and its exception in one sentence cannot contradict
each other. Two sentences in two places always can.

**Expected outcome.** One instruction about years instead of two.

## A3. Events cannot produce a usable result, no matter what we search for

**Problem.** Pick "Events" and the run can only end one of two ways: nothing
stored, or something stored with nonsense in it. The Sustainability Summit run
stored the event's *audience description* — "CXO, Head, Vice President of
Sustainability" — as an entry condition.

**Cause.** Everything after the search is built around entry conditions. The
analyze prompt calls them "the heart of this". Whether a record counts as
finished is literally `ready = does it have any entry conditions`. The
eligibility step judges the company against those conditions.

An expo does not have entry conditions. It has a stand price and a call for
speakers. So the pipeline looks for something that is not there, and the model
fills the gap with whatever text was nearest.

**Effect.** Every event run either produces nothing or produces a record nobody
should trust. Both outcomes look like a pipeline failure and neither is fixable
by better searching.

**Fix.** Two options, and I would take the first.

1. **Remove Events and Research for now.** Get Awards working end to end, then
  add the others back with their own record shape.
2. Give each kind its own definition of "what makes this finished" — an award
  needs entry conditions, an event needs a date and a way to take part, a
   research venue needs a topic scope and a submission deadline.

**Why this fix.** Option 2 is the right end state but it is a week of work
across four files. Option 1 costs an afternoon and makes the thing we
demonstrate honest. Three modes that produce nothing is worse than one that
produces something.

**Expected outcome.** No more records where the "conditions" are an audience
list. Awards runs stop competing for attention with two modes that cannot work.

## A4. The link-following step only knows about awards

**Problem.** After fetching a page, a model call picks which links to follow.
Its instruction never changes:

> "Pick the links that most likely state **entry eligibility, who can enter,
> entry requirements, categories, fees, or the entry deadline**."

**Cause.** The focus setting is passed to three of five prompts. This is one of
the two it is not passed to.

**Effect.** On a conference site the page we need is the call for papers. On an
expo site it is the exhibitor pack. Neither matches those words, so we walk
past them and follow something else. This is a large part of why research runs
find nothing.

**Fix.** Pass the focus to this call, and change what it hunts for per mode.

**Why this fix.** It is a two-line change and the information is already in the
runtime object. There is no reason it was ever missing except oversight.

**Expected outcome.** Research runs actually reach call-for-papers pages.
Events runs reach exhibitor pages.

## A5. The analyze step calls everything a "recognition programme"

**Problem.** It opens: "These pages were fetched while researching
**recognition programmes**."

**Cause.** Written when awards were the only mode.

**Effect.** Small on its own, but it sets the frame for a call that also
receives the "we want events" focus line. One more place where the model is
told two things.

**Fix.** Make that first line reflect the focus.

**Expected outcome.** The analyze call stops being told it is looking for
awards when it is looking for conferences.

---

# Group B — Almost nothing we store is checked

## B1. Only the deadline is verified. Everything else is taken on trust

**Problem.** We store an organiser, a year, a category, dates, a status and a
list of conditions. One of those — the deadline — is checked against the page.
The rest are whatever the model said.

Real example from run `2a3d29`. We stored:

```
organizing_body: "PRCA, mUni Campus"
```

Neither string appears anywhere on that page. The page names no organiser at
all. "PRCA" is the Plastic Recycling Conference Asia — a *different programme*
that happened to be in the same batch of search results.

**Cause.** There is a check for the deadline (`verify_deadline`) and no
equivalent for anything else. The model's answer goes straight into the
database.

**Effect.** This is why you do not trust any finding, and you are right not to.
The organiser is half of the key we use to recognise a programme again next
year, so an invented one creates a record that can never be matched or updated.

**Fix — citation-grounded extraction.** Make the model return, for every field
it fills in, the exact sentence it read that value from. Then check that the
quoted sentence appears in the page. If the quote is not there, the field is
not stored.

Roughly:

```
organizing_body: "Aegis School of Business"
organizing_body_quote: "organised by Aegis School of Business and Telecommunication"
```

The check is: does `organizing_body_quote` appear in the page text? That is a
plain substring test on **the model's own quote**, not a fuzzy comparison of
the value.

**Why this fix and not what I proposed before.** What I proposed earlier —
checking whether words of the organiser name appear in the page — is word
matching, and you were right to reject it. It would pass "PRCA" if the page
happened to contain "practical", and fail a correct answer where the page says
"TOI" and the model wrote "Times Internet".

Citation checking has neither problem, because the model supplies the string
being searched for. This is a documented, current technique:

> "Define a schema... where every value carries a citation to the exact span it
> came from, and fields the document doesn't contain come back null rather than
> a plausible guess. Forcing the extractor to emit the span rather than
> free-text prevents the model from rewriting or paraphrasing the source."

**Expected outcome.** A field the page does not state comes back empty instead
of invented. `"PRCA, mUni Campus"` is impossible, because there is no sentence
to quote.

## B2. A record with no date at all is called "actionable"

**Problem.** `assess_actionability` contains this:

```python
if deadline is None and event_date is None and not record.deadline_note:
    return ActionabilityVerdict(
        "actionable",
        ("no date found in the evidence — verify on the source page",),
    )
```

**Cause.** A deliberate choice, made to avoid throwing away real programmes
whose landing page happened not to show a date.

**Effect.** We store things nobody can act on and present them as results. An
opportunity with no date is a name, not an opportunity. This is your point
about date extraction, and it is not a bug — it is a decision we made.

**Fix.** No date and no note means not actionable. It becomes a *lead* — stored
so we know the programme exists, shown separately, not counted as a result.

**Why this fix.** The original worry was real: some landing pages genuinely
have no date. But the answer to that is to go looking for the date (follow the
link to the entry page), not to pretend the record is finished without one.

**Expected outcome.** The Results tab only contains things with a date you
could put in a calendar. Everything else appears as "found, needs a date".

## B3. "Ready" only checks that the conditions list is not empty

**Problem.** `ready = bool(result.eligibility_criteria)`. The Sustainability
Summit record had this as its first condition:

> "No explicit entrant eligibility conditions are stated on the page;
> registration is via Register Now."

That is a sentence saying there are no conditions. It is not empty, so the
record was marked Ready.

**Cause.** The check measures list length, not whether the contents are
conditions.

**Effect.** Records with no real conditions get promoted to results, and the
eligibility step then solemnly judges the company against a sentence that says
there is nothing to judge.

**Fix.** Two parts. Tell the analyze step to return an empty list when the page
states no conditions (already added today). And make "ready" mean: has a date,
has an organiser that survives the citation check, and has at least one
condition that is a requirement rather than a description.

**Why this fix.** The prompt half stops the sentence being produced. The check
half stops it mattering if it is produced anyway. Neither alone is enough.

**Expected outcome.** No record reaches Results without something real to judge.

## B4. A page that comes back thin silently costs a second fetch

**Problem.** When a fetched page looks poor, the code fetches it again with
different settings. That second fetch spends another Firecrawl credit and is
not announced anywhere.

**Cause.** Added to rescue pages that render by script. Reasonable in itself.

**Effect.** With a 15-scrape budget and 8 sites, a handful of retries quietly
eats the allowance. In one run, 11 scrapes covered 7 pages.

**Fix.** Keep the retry, but count it in the journey so it is visible, and cap
retries per run.

**Expected outcome.** You can see where the scrape budget went.

---

# Group C — The pipeline repeats itself and forgets what it decided

## C1. The same two questions are asked three times, and the answers disagree

**Problem.**


| Question                          | Asked in                                                 |
| --------------------------------- | -------------------------------------------------------- |
| Is this still open?               | ranking prompt → analyze prompt → `assess_actionability` |
| Is this for a business like ours? | ranking prompt → analyze prompt → `evaluate()`           |


They do not agree. Ranking says: anything with a date behind today gets ranked
low. Analyze says: pursue anything whose *next* edition is ahead, even with no
dates announced.

**Cause.** Each stage was written on its own, each needed the question
answered, so each asked it.

**Effect.** Two kinds of waste. Money — we pay for the same judgement three
times. And correctness — a programme whose 2026 edition has closed but which
runs every year is exactly what the programmes registry exists to track, and
ranking guarantees analyze never sees it.

**Fix.** Each question gets asked once, by the stage with the best information,
and the answer travels forward.

- Ranking decides *what kind of page this is* only. That is all it can tell
from a snippet.
- Analyze decides *is it open* and *is it for us*, because it has read the page.
- `assess_actionability` stops re-deciding and just enforces the dates analyze
extracted.

**Why this fix.** The stage with the most evidence should own the decision.
Ranking sees 200 characters; analyze sees the page. Asking ranking to judge
whether a programme is open is asking it to guess.

**Expected outcome.** One answer per question. Two fewer judgement calls per
candidate. Recurring programmes whose current edition has closed can reach the
registry instead of being sunk at ranking.

## C2. The ranker's reasoning is thrown away one line after it is produced

**Problem.** In `research_node`:

```python
for hit, reason in picks:
    ...
    _ = reason          # <- discarded
```

**Cause.** The ranking output was added for display. Nothing downstream was
wired to receive it.

**Effect.** Analyze re-derives "is this for a business like ours" from nothing,
unaware that the question was already answered with a stated reason. This is
the concrete form of "no shared progress between stages".

**Fix.** Carry the reason with the seed and include it in the analyze prompt as
context: "Ranking picked this page because: …".

**Why this fix.** It is free. The text already exists and is already paid for.

**Expected outcome.** Analyze starts from what ranking found rather than from
zero.

## C3. Two functions do the work of seven

**Problem.**


| Function        | Lines | Model calls inside | Separate jobs |
| --------------- | ----- | ------------------ | ------------- |
| `research_node` | 202   | 6                  | 5             |
| `finalize_node` | 283   | 1                  | 8             |


`research_node` runs the first searches, then calls the **planner** again for a
second round, runs those searches, assembles and de-duplicates the pool, calls
the ranker, then fetches every chosen page and follows links. The graph claims
four stages. The code runs seven.

**Cause.** Each new capability was added inside the function where the data
happened to be.

**Effect.** Changing a prompt means editing the file that defines the state
machine. Nothing can be tested on its own. When a run dies, it dies inside a
200-line function and restarts from nothing.

**Fix.** Split them. `research` becomes search / rank / fetch. `finalize`
becomes build / verify / store / judge. Each step checks its own output before
passing it on.

**Why this fix.** This is the standard guidance for this exact framework:

> "Design isolated worker nodes that handle specific tasks independently,
> communicating results back through graph state rather than calling each other
> directly."

> "An explicit gate sits between pipeline stages... because unvalidated
> chaining is just a pipeline that confidently propagates garbage."

**Expected outcome.** A failure lands in a named small step instead of
somewhere inside a long one. Each step becomes testable without a live run.

## C4. The state cannot merge, which is why the big functions exist

**Problem.** Every field in `DiscoveryState` is overwrite-only. If two steps
both wrote `candidates`, the second would erase the first.

**Cause.** The state was declared as a plain dictionary with no merge rules.
LangGraph supports them; we did not use them.

**Effect.** Because two steps cannot write the same field, every "do this for
each site" has to be a loop **inside one step**. That is the actual reason
`research_node` is 202 lines. It is not a style problem — the shape is forced.

It also means the five analyze calls run one after another. That is the slowest
part of every run.

**Fix.** Declare merge rules on the state fields that collect things, so
several steps can add to the same list.

**Why this fix.** It changes no prompt and no behaviour on its own, and it
unlocks everything structural that follows — splitting the big functions,
running analyze on several sites at once.

**Expected outcome.** Analyze on 5 sites goes from five calls in a row to five
at once. On the runs we have measured that is the difference between about 300
seconds and about 60.

## C5. A run that dies restarts from nothing

**Problem.** Several runs this week died part-way — a hung fetch, a call that
returned nothing. Every one started again from zero, re-paying for searches
already done.

**Cause.** LangGraph can save progress between steps. We do not switch it on.

**Fix.** Turn on saved progress.

**Why this fix.** It is a constructor argument. Given how many runs have died
mid-way and how tight the search budget is, it pays for itself the first time.

**Expected outcome.** A failed run resumes from the last completed step instead
of spending the search allowance twice.

## C6. There is no step where the run asks "was that enough?"

**Problem.** The run searches, ranks, fetches, extracts, stores. There is one
escape hatch: if analyze finds nothing at all, plan again. That is the only
moment the pipeline reconsiders anything.

**Cause.** It was built as a straight line with one exception.

**Effect.** If the pool is thin but not empty, we push on and produce one weak
record. Nothing notices that the search went badly.

**Fix.** After ranking, one short check: does this pool contain enough worth
fetching? If not, search again with different angles before spending scrapes.

**Why this fix.** Searching is cheap (2 credits). Fetching and analysing is
where the money and the time go. A check placed between them is the cheapest
possible place to catch a bad run.

**Expected outcome.** Bad pools cost one extra search instead of eight fetches
and five analyze calls.

---

# Group D — We cannot tell whether a change helped

## D1. Every change is judged by one live run

**Problem.** There is no way to test a prompt change except running the whole
pipeline and reading the output.

**Cause.** We never built one.

**Effect.** This is the reason for the whole month of back-and-forth. One run
is one sample with enormous variation, so a change that looks like an
improvement may be luck and a change that looks like a regression may be
noise. I removed the year rule on that basis and it cost a run to find out.

**Fix.** Two things, both cheap.

1. **Replay.** Feed a saved pool of search results back through the ranking and
  planning calls. No search cost, no fetch cost, about one cent. Already built
   (`scripts/replay.py`) and it works.
2. **A list of known-good and known-bad pages** to score against. Started
  (`reference/`), but the good ones are my judgement and you should mark them
   yourself before any number from them means anything. The bad ones — a tender
   directory, a press release, a page of past winners — need no judgement and
   can be trusted now.

**Why this fix.** Standard practice is a fixed set of examples re-run on every
change. The usual advice is 50 examples to catch big regressions. We have 28
and only the negative half is trustworthy.

**Expected outcome.** A change is checked in two minutes for a cent, instead of
eight minutes and a tenth of the monthly search budget.

---

# Group E — Dead weight and small traps

## E1. About 200 lines of the extraction module are no longer used

The `extract()` function, its 384-word prompt, its schema and its retry loop
are only called by `scripts/run_golden_set.py`. Analyze took over its job. It is
still imported and exported. **Fix:** move it into the script that uses it.
**Outcome:** the largest file after `workflow.py` loses a third of its size.

## E2. The prompts contain stories about past runs

Six lines in the analyze prompt recount something that went wrong once:

> "A run once set aside a 25-category awards programme whose own page said
> anyone working toward sustainability may nominate, giving the reason 'one
> umbrella programme, not 25 opportunities' — that is this rule being read
> backwards."

The rule is the sentence before it. The story is an explanation for whoever
reads the code. It is paid for on every analyze call in every run.
**Fix:** delete the stories, keep the rules. **Outcome:** shorter prompt, same
instructions.

## E3. The company profile is read with pattern matching over markdown

`profile_facts` finds sectors and markets by matching `- Label: value` lines.
If the profile is reformatted, they come back empty and the fallback plan
crashes. The Technology section is never read into facts at all — which is why
no query has ever searched on the technology.
**Fix:** read the sections we need explicitly, including Technology, and fail
loudly if one is missing rather than returning nothing.
**Outcome:** the capability angle becomes searchable; a profile edit cannot
silently empty the plan.

## E4. A quality warning fires on any number or the word "must"

`audit_classification` flags a condition as suspicious if it contains a digit or
"must". Nearly every real condition contains one.
**Fix:** drop it, or replace it with a short model check.
**Outcome:** less noise in the record detail.

## E5. We use five functions from the graph library

`StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`, `compile`. The
pieces that would fix C3, C4 and C5 — merge rules, running steps at once, saved
progress — are all in the version we already have installed.

---

# What is worth keeping

Not everything is broken, and a rewrite should not throw these away:

- Storing and matching records, so the same programme found twice becomes one
entry rather than two
- The programmes registry that learns when a yearly programme reopens
- The spending limits, which have held every single run
- Langfuse tracing
- The web interface and the run journey
- The deadline check — our one verified field, and the one that has never
invented anything
- `evaluate()`, the eligibility judgement. Its output on Aegis Graham Bell,
correctly refusing to fail Retearn on tracks it would not enter, is the best
thing the system has produced

---

# Order to do this in

Each step is only useful if the one before it is done.


| #   | Change                                                 | Touches prompts? | Needs a live run to check? |
| --- | ------------------------------------------------------ | ---------------- | -------------------------- |
| 1   | ~~Merge rules on the state (C4)~~ **done**             | No               | No                         |
| 2   | ~~Saved progress (C5)~~ **done**                       | No               | No                         |
| 3   | Split the two big functions (C3)                       | No               | No                         |
| 4   | Fix the contradictions in the focus lines (A1, A2)     | Yes              | Replay                     |
| 5   | Pass focus to link-following (A4, A5)                  | Yes              | Replay                     |
| 6   | Cut to Awards only (A3)                                | Yes              | No                         |
| 7   | Quotes for every extracted field (B1)                  | Yes              | Live                       |
| 8   | Require a date; fix what "ready" means (B2, B3)        | No               | Live                       |
| 9   | Ask each question once and pass the answer on (C1, C2) | Yes              | Live                       |
| 10  | Pool check after ranking (C6)                          | Yes              | Live                       |
| 11  | Delete dead code and stories (E1, E2)                  | Yes              | Replay                     |


Steps 1 to 3 change no behaviour at all — they only make the rest possible.
Nothing after step 3 should ship without a replay showing it did not make
things worse.

---

# Sources

- [Citation-grounded extraction — LlamaIndex](https://www.llamaindex.ai/glossary/citation-grounded-extraction)
- [Citation extraction: tying claims back to source spans — ZeroEntropy](https://zeroentropy.dev/concepts/citation-extraction/)
- [Structured extraction of legal reasoning with citation-hallucination control](https://arxiv.org/pdf/2607.03325)
- [Thinking in LangGraph — LangChain](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph)
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Progressive context disclosure — Thoughtworks Technology Radar](https://www.thoughtworks.com/radar/techniques/progressive-context-disclosure)
- [LLM workflows: patterns and production architecture — Morph](https://www.morphllm.com/llm-workflows)
- [Schema-guided extraction and validation](https://arxiv.org/abs/2604.06571)

