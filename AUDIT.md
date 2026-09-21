# What is wrong with this project, and what to do about it

21 September 2026. Written against the running code.

## Progress

| # | Change | Status |
|---|---|---|
| 1 | Merge rules on the state (C4) | **Done** — 21 Sep |
| 2 | Saved progress (C5) | **Done** — 21 Sep, now stored in Mongo |
| 3 | Split the two big functions (C3) | planned — see below |
| 4 | Fix the contradictions in the focus lines (A1, A2) | not started |
| 5 | Pass focus to link-following (A4, A5) | not started |
| 6 | Cut to Awards only (A3) | not started |
| 7 | Quotes for every extracted field (B1) | not started |
| 8 | Require a date; fix what "ready" means (B2, B3) | not started |
| 9 | Ask each question once and pass the answer on (C1, C2) | not started |
| 10 | Pool check after ranking (C6) | not started |
| 11 | Delete dead code and stories (E1, E2) | not started |

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

**Left open:** saved progress survives a crash inside the running server, not a
restart of the server. Durable progress needs the
`langgraph-checkpoint-mongodb` package, which we have not installed. Nothing
yet *uses* the saved progress to resume — that is a small separate piece.

### 3 — splitting the big steps: what we have and what replaces it

**A note on "tools".** No step has a list of tools the model may choose from.
Every outside call is written into the step itself. The model never decides to
search or to fetch — it only fills in a form. So "calls" below means what that
piece of code reaches out to, not what the model can pick.

#### What we have now — 4 steps

| Step | Lines | Jobs it does | What it calls |
|---|---|---|---|
| `plan_queries` | 107 | write the opening searches | OpenRouter, Mongo (journey) |
| `research` | **204** | run the first searches · **write a second set of searches** · run those · build and de-duplicate the pool · look up sites earlier runs found empty · rank the pool · fetch each chosen site and follow its links | Tavily, OpenRouter ×3 kinds, Firecrawl, Mongo |
| `analyze` | 114 | read each site's pages in a loop, one after another | OpenRouter, Mongo (journey) |
| `finalize` | **283** | build a record · check it is complete · check it is still live · record a past edition · save it · mark or clear a dead end · judge it against the profile · attach the verdict · write the summary | OpenRouter, Mongo ×7 kinds |

The two problems this causes:

- `research` calls the **planner** inside itself. The picture says four steps;
  the code runs seven.
- `analyze` and `finalize` loop over sites and records inside one step, so a
  failure on the fourth site loses the first three, and the five analyze calls
  run one after another instead of together.

#### What replaces it — 8 steps

| Step | Its one job | Reads | Writes | Calls |
|---|---|---|---|---|
| `plan` | write search queries | profile, focus, what earlier searches returned | queries | OpenRouter |
| `search` | run queries not yet run | queries | search results | Tavily |
| `rank` | order the pool, decide what is worth fetching | search results, profile, focus | the chosen sites **and why** | OpenRouter, Mongo (sites known empty) |
| `fetch` | get the pages for **one** site | one chosen site | that site's pages | Firecrawl, OpenRouter (which links to follow) |
| `analyze` | read **one** site's pages, list what is on it | one site's pages, profile, **the reason rank chose it** | candidates | OpenRouter |
| `build` | turn a candidate into a record and check its fields against the page | candidates, pages | records, rejections | none — plain code |
| `store` | save records, past editions, dead ends | records | saved ids | Mongo |
| `judge` | decide if we qualify, condition by condition | records, profile | verdicts | OpenRouter, Mongo |

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

| Question | Asked in |
|---|---|
| Is this still open? | ranking prompt → analyze prompt → `assess_actionability` |
| Is this for a business like ours? | ranking prompt → analyze prompt → `evaluate()` |

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

| Function | Lines | Model calls inside | Separate jobs |
|---|---|---|---|
| `research_node` | 202 | 6 | 5 |
| `finalize_node` | 283 | 1 | 8 |

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

| # | Change | Touches prompts? | Needs a live run to check? |
|---|---|---|---|
| 1 | ~~Merge rules on the state (C4)~~ **done** | No | No |
| 2 | ~~Saved progress (C5)~~ **done** | No | No |
| 3 | Split the two big functions (C3) | No | No |
| 4 | Fix the contradictions in the focus lines (A1, A2) | Yes | Replay |
| 5 | Pass focus to link-following (A4, A5) | Yes | Replay |
| 6 | Cut to Awards only (A3) | Yes | No |
| 7 | Quotes for every extracted field (B1) | Yes | Live |
| 8 | Require a date; fix what "ready" means (B2, B3) | No | Live |
| 9 | Ask each question once and pass the answer on (C1, C2) | Yes | Live |
| 10 | Pool check after ranking (C6) | Yes | Live |
| 11 | Delete dead code and stories (E1, E2) | Yes | Replay |

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
