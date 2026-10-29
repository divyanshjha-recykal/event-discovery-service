# Review prep — questions and answers

Short answers you can say out loud. The facts match `TECHNICAL.md` (27 Oct 2026). Where the honest
answer is "not yet", it says so, because a confident wrong answer costs more than an honest gap.

---

## 1. The project in one minute (non-technical)

**Q: What is Opportunity Radar, in one line?**
An AI research assistant for Retearn that searches the web and tells us three things: which awards,
events and research venues we can enter; what competitors and the market are doing; and where we
could buy machine parts cheaper or better.

**Q: Who is it for?**
Leadership and marketing (opportunities), strategy and business development (competitor news), and
procurement and engineering (components).

**Q: What problem does it solve?**
Today people find these things by hand, and only sometimes. The system does the searching, reading
and first-pass judging, then hands a person a short list with links and reasons. People decide.

**Q: Does it take any action on its own?**
No. It never applies, contacts anyone or buys anything. It stores results, shows them on a dashboard
and can email a fixed list of people.

**Q: What are the three pipelines?**
1. **Opportunity discovery**: awards, events, research venues, or all three ("Everything").
2. **Competitor watch**: news about competitors and the RVM / deposit-return market since the last run.
3. **Component watch**: for each part in a machine's bill of materials (ACE today), the same part
   from cheaper sellers, and better or cheaper alternatives.

**Q: What came out of the review?**
- Competitor watch (the news pipeline) is the safest; nobody raised issues.
- Component watch doesn't yet match what the teams need, and needs a course correction.
- Opportunity discovery is stable.

**Q: How much does it cost to run?**
It runs on free tiers plus a few cents of model cost:
- one discovery run: about $0.05 of model plus 4–5 Exa searches (~$0.07)
- a full ACE component run: about 68 searches (~$1) plus about 50 model calls
- Exa gives $20 of free credit a month; Firecrawl gives 1,000 pages a month

**Q: How long does a run take?**
- Discovery: 5–15 minutes. Most of that is waiting between page fetches to stay inside the free
  tier's limit, plus model thinking.
- Competitor watch: about 5–12 minutes.
- A full component run: about 10 minutes.

**Q: Can we trust the output?**
Each result comes with its source link and the reason it was kept, so a person checks before acting.
Prices are calculated in code, not by the AI. Honest gap: there's no labelled test set yet, so I
can't give you an accuracy percentage. Building that set is the next step.

**Q: What business value has it shown so far?**
- **Competitor watch:** real, usable signals, for example two RVM tenders we could bid for
  (TASMAC, a West Bengal ULB EOI), Goa's deposit-scheme deferral, and Tomra's and Envipco's
  results.
- **Discovery:** 1–6 opportunities we can act on per run.
- **Component watch on ACE:** small savings (₹300–800 on a ₹2.4 lakh machine) and 9–14 parts where
  we already pay the lowest price, which is useful to know too. The costliest parts (stepper,
  Keyence, light curtain, inverter, battery) mostly show no price online.

**Q: What's the biggest weakness?**
We can't measure quality automatically. Every change has been judged by eye on one live run, and in
component watch that led to cycles of fixes. The fix is a labelled reference set plus replay before
any change goes in.

**Q: What's next?**
1. Rework component watch around what the teams actually need, likely an on-demand search for one
   chosen part, with datasheets and distributor data.
2. Weekly scheduled runs and one combined newsletter email.
3. A measurement set for every pipeline.
4. A catalogue, so we stop paying to rediscover the same things.

**Q: Why not just use ChatGPT?**
ChatGPT answers one question at a time and doesn't remember results. This system:
- runs the same process every time, with hard cost limits
- reads Retearn's own profile and parts sheet
- stores results, skips what it has already seen, and compares prices against our real rates
- shows every step it took

---

## 2. Basic AI / LLM concepts

**Q: What is an LLM?**
A large language model: a neural network trained on large amounts of text to predict the next
token. Given instructions and text, it can read, classify, extract and write. Here it's used for
reading and judging, never for arithmetic.

**Q: What is a token?**
A chunk of text, roughly ¾ of a word in English. Models are priced and limited by tokens: input
tokens (the prompt) and output tokens (the reply).

**Q: What is a context window?**
The most text (in tokens) a model can take in one call, prompt plus reply. That's why we cap page
text, for example 1,400 characters per page in the component judge.

**Q: What are reasoning (thinking) tokens?**
Reasoning models think in hidden tokens before they answer, and those tokens come out of the same
output budget. If the budget runs out mid-thought, the reply is empty or cut off. We hit this
several times (one judge call spent 21–24k of its 24k tokens thinking), so every call's budget
leaves room for both.

**Q: What is temperature?**
It controls randomness. Low means more consistent; high means more varied. Discovery reads it from
`OPENROUTER_TEMPERATURE`; the other calls use the provider's default.

**Q: What is hallucination, and how do you limit it?**
Hallucination is when the model states things that aren't true. We limit it in four ways:
1. **Structured output:** the model must fill fixed fields.
2. **Answering from the page only:** the prompts say "as the page states", and certifications are
   never inferred.
3. **Code does what code can:** dates, price maths, duplicate checks and identity are all done in
   code.
4. **Quote checks:** for discovery, the model must quote the sentence it read the organiser,
   deadline and status from, and code checks the quote is on the page. The result is recorded;
   nothing is rejected on it.

**Q: What is structured output / JSON schema?**
We send the model a JSON schema (made from a Pydantic class) with `strict: true`, so its reply must
match those fields and allowed values exactly. That turns free text into data the code can rely on.

**Q: What is Pydantic?**
A Python library that defines data models with types and validates data against them. We use it for
every model reply. Bad shapes raise errors instead of slipping through.

**Q: What is prompt engineering?**
Writing the instructions so the model does the job reliably. Ours follow a fixed layout (Objective,
Decide or Rules, then data), describe the page wanted rather than naming things, and keep rules
short. One lesson: adding a rule each time something breaks makes the rules compete with each other.

**Q: What is an AI agent? Is this one?**
An agent is a model that decides which actions to take, often by calling tools in a loop. Ours is a
**bounded agentic workflow**: the model makes every judgement that needs reading meaning (what to
search, what to keep, what to follow), but code fixes the order of steps and the limits. One part is
a true agent loop: the ReAct search steps.

**Q: What is ReAct?**
"Reason + Act". The model looks at results, reasons about what's missing, and takes one action
(another search), up to 3 times, or stops. In discovery, each step sees every search's results and
writes an assessment, the gaps, and the next search.

**Q: What is RAG? Do you use it?**
Retrieval-Augmented Generation: fetch relevant documents, then have the model answer using them. In
a loose sense, yes: we search, fetch pages and have the model judge using them. We don't use a
vector database, because the source is the live web through Exa, not a fixed document store. A
component or programme catalogue could later become a retrieval store.

**Q: What are embeddings / a vector database?**
An embedding is a list of numbers that represents a text's meaning; similar texts get nearby
vectors. A vector database stores them so you can search by similarity. We don't run our own. Exa
does neural (embedding-based) search on its side.

**Q: What is LLM-as-a-judge?**
Using a model to evaluate or label items. Our judges: the ranker, the competitor judge, the
component judge and the eligibility evaluator. Their weakness is that they need checking against
human labels. That's our W1 measurement gap.

**Q: What is a re-ranker?**
A model that re-orders search results by relevance to the query, usually a cross-encoder that reads
the query and each document together. Planned as test W4 (Qwen3-Reranker or Cohere), and adopted
only if it beats our current model-based ranking on labelled data.

**Q: Bi-encoder vs cross-encoder?**
- **Bi-encoder:** embeds the query and the document separately. Fast, and good for retrieval.
- **Cross-encoder:** reads both together. Slower, more accurate, and good for re-ranking a short
  list.

**Q: Precision, recall, NDCG?**
- **Precision:** of what we kept, how much was right.
- **Recall:** of everything right that existed, how much we found.
- **NDCG / MRR:** ranking metrics that reward putting the right items near the top.

We'd use these once the labelled set exists.

**Q: What is fine-tuning? Did you fine-tune?**
Fine-tuning means training a model further on your own examples. We didn't. We use hosted models
through prompts plus structured output. Fine-tuning needs a labelled dataset we don't have yet, and
model choice is still changing.

**Q: Why do models fail on strict JSON sometimes?**
Some models degenerate under strict schemas. `google/gemma-4-31b-it` once produced 16,000 tokens of
garbage. Others copy raw control characters from pages into strings, which we now tolerate with
`json.loads(strict=False)`. That's why model choice matters: `qwen3-32b` and `deepseek-v4.1-flash`
work.

---

## 3. Pipeline questions

### Opportunity discovery

**Q: Walk me through the discovery pipeline.**
Seven steps, as a LangGraph graph:
1. **Plan:** the model writes opening searches from the business profile.
2. **Search:** runs them on Exa, then up to 3 ReAct steps that look at results and add searches.
3. **Rank:** the model orders all results against numbered conditions (the organiser's own page,
   Retearn can enter, open, one per programme) and picks the sites to read.
4. **Fetch:** one branch per site, in parallel. Firecrawl reads the page, and a link picker chooses
   0–2 more pages on that site.
5. **Extract:** reads the site, names each opportunity, decides pursue or skip, and builds a record.
6. **Evaluate:** awards and events get each entry condition judged met / not met / unclear against
   the profile; research calls get a "which of our work fits" table.
7. **Store:** saves once per opportunity, protected by a unique index.

**Q: What are "tracks" / type specs?**
Each opportunity type (award, event, research, any) is defined as data in `types.py`: what it is
called, its query examples, rank conditions, link checklist and record guide. The prompts are filled
in from that data, so adding or changing a type doesn't mean editing prompts in five places.

**Q: Why describe the page wanted in queries instead of keywords?**
Exa is a neural search engine; it matches pages to descriptions of pages. "Nominations page for a
national award recognising cleantech startups in India" works better than "cleantech award India
2026". It's Exa's own documented practice.

**Q: Why never name a venue or programme in a search?**
When the model named famous venues from memory (CVPR 2027, NeurIPS…), runs found proposal pages,
past editions and tracker sites, and nothing new. Known programmes belong in a catalogue, not in
search.

**Q: How do you avoid duplicates?**
At three levels:
1. **Search:** duplicates are dropped by content key and programme key.
2. **Rank:** one seat per programme.
3. **Database:** a **unique index** on organiser + base title (edition stripped) + year, so a true
   duplicate can't be stored.

Known gap: one programme under two different titles (catalogue work, item 31).

**Q: How does it decide whether an opportunity is still open?**
- **Code:** date arithmetic (deadline or event date before today means past) plus HTTP status.
- **Model:** the meaning-based status ("nominations open").
- No keyword rules: a regex once threw away "Nominate Now" pages.
- A missing date is not a rejection: the best find of Phase 1 had none on its landing page.

**Q: What is the business profile?**
`BusinessProfile.v2.md`, with fixed sections:
- **Search constraints:** who can enter, primary market India, what we do and don't seek
- **Search angles:** fields, technology, impact, stage
- identity, business, technology, operations, evidence and recognition history

Prompts read specific sections, and geography always comes from the profile, never from code.

**Q: What does evaluation output?**
- For each condition: met / not met / unclear, with reasoning, plus qualitative notes for things no
  fact can settle.
- Confidence and score are **computed in code**: a model asked to rate itself rates its own
  certainty, not the evidence.
- Research calls get fits / partly / no for each research line.

### Competitor watch

**Q: How does competitor watch work?**
1. Three search lanes on Exa, limited to pages published since the last successful run minus 2
   days (the first run looks back 90 days):
   - each competitor's own site
   - about 8 market searches written by the model (half with Exa's news filter)
   - a name check per competitor
2. Pages judged in earlier runs are skipped by exact link.
3. The judge reads 20 pages at a time and decides keep or drop, which company, the section, kind,
   date, importance and why it matters, and whether the page repeats a known story.
4. Code merges repeats, stores signals, and groups them into a digest.

**Q: What are the digest sections?**
- Act on this (only while a deadline is still ahead)
- Competitor moves
- Market and policy
- New entrants and other companies
- Own group (Recykal is never counted as a competitor)
- Following up (earlier stories this run added coverage to)

**Q: How do you avoid reporting the same news twice?**
`competitor_seen` stores every judged link, so it's never judged again. The judge sees the last 30
days of signals and marks `same_story_as`; repeats within a batch get `duplicate_of`. Code then adds
those links to the original story's "also reported by" list.

**Q: Why not use Exa Monitors or alerts?**
They need a public webhook, cost $15 per 1,000 runs, and don't support the news category or date
filter we need.

**Q: Why did you drop a model-written digest?**
It was tried: the model joined two separate Envipco deals into one and left out three signals. The
digest now uses the judge's own headline and summary, grouped by code, so nothing is reworded or
lost.

### Component watch

**Q: How does component watch work?**
1. Load the machine's parts workbook. **Our rate is never sent to the model.**
2. **Plan:** for each part, the model decides off the shelf or custom, and writes two searches: the
   exact model from any Indian seller, and a newer or more capable replacement.
3. **Scope:** by default, the parts making up 80% of off-the-shelf cost (13 of 49 on ACE), or all
   parts.
4. **Search:** Exa, 5 results per search.
5. **Judge:** one call per part, with one required answer per page. For each page it gives:
   - page kind, product, maker, seller and seller kind
   - price as printed, GST basis, stock, units per part
   - same part or alternative, and effort (drop-in / minor / major / needs verification)
   - Must Have checks and certifications
6. **Code:** drops out-of-stock, discontinued and non-rupee listings, does the price maths, gives
   each part a verdict, and builds three sections: same part from a cheaper seller; better or
   newer; cheaper alternatives.

**Q: How are prices compared fairly?**
- The seller's price is never changed.
- If their price includes GST, we add our GST % to our rate. If it excludes GST or doesn't say, we
  compare before GST and label it that way.
- Packs and lengths are converted with "units per part" (for example, a pack of 100 means 0.01).
- All arithmetic is in code.

**Q: Why is the rate kept away from the model?**
Two reasons. Cost data stays internal. And a model that knows our price could be anchored by it,
for example by judging pages relative to that number.

**Q: What does "effort" mean?**
How much work switching would take:
- **Drop-in:** same fit, interface, mounting and ratings, as stated on the page.
- **Minor changes:** only a cable, connector, bracket or setting changes.
- **Major changes:** redesign, new drivers or software, retraining, requalification.
- **Needs verification:** the page or brief lacks the facts.

A major change only pays off when the saving is big, and that trade-off is shown to a person, never
decided in code.

**Q: Why doesn't component watch meet the requirements?**
Known gaps:
1. Engineers asked for a **deliberate, on-demand search for one chosen part**; we built a sweep over
   the whole bill of materials.
2. The plan named **distributor APIs** (DigiKey, Mouser, Octopart) and **datasheets**; we read
   open-web snippets.
3. No lead time, price breaks, minimum order or risk data.
4. The input sheet is thin, and some values are assumptions.
5. No measurement, so each fix moved the problem somewhere else.
6. The judge sometimes runs out of output tokens.

**Q: How long will the course correction take?**
Answer honestly by phase, without inventing a date:
1. Write down the teams' requirements (days).
2. Build a small labelled set and save page text (about a week).
3. Rebuild the search around the agreed shape.

The plumbing (dashboard, email, storage, price maths) is reusable.

**Q: What did you learn from component watch?**
1. Measure before you tune.
2. Agree on the use case with the actual users first. An on-demand single-part search is a
   different product from a weekly sweep.
3. Structured sources beat scraped snippets for prices and stock.
4. Big judge calls hit output limits, so split them or use a stronger model.

---

## 4. Stack questions

**Q: What's the stack?**

| Layer | Choice |
|---|---|
| Language and backend | Python 3.11+, FastAPI on uvicorn |
| Orchestration | LangGraph (discovery); plain asyncio (both watch pipelines) |
| Models | OpenRouter (mostly DeepSeek V4.1 Flash) through LangChain's `ChatOpenAI` |
| Search | Exa (Tavily is an option) |
| Page fetch | Firecrawl (discovery only) |
| Database | MongoDB 7 |
| Tracing | Langfuse (self-hosted, on demand) |
| Frontend | React 18 + Vite |
| Infrastructure | Docker Compose, locally |

**Q: Why LangGraph and not a free-form agent loop?**
Cost and reproducibility. A free-form agent can keep deciding it needs "one more search". A graph
fixes the steps, the parallel branches and the single re-plan in code, while the model still makes
the judgement calls. LangGraph also gives us checkpoints (resume after a crash) and fan-out and
fan-in with `Send`.

**Q: Why not LangGraph for the watch pipelines?**
They're straight lines: plan, search, judge, store. No branching back. Plain asyncio is simpler and
easier to debug there.

**Q: Why OpenRouter?**
One API key and an OpenAI-compatible API in front of many models, so we can switch or compare
models by changing a model id, with no code change. The model is never hardcoded.

**Q: Why Exa over Google or Tavily?**
- Exa is a neural search engine built for AI: you describe the page you want.
- It can return a **structured summary per result** (we ask for organiser, deadline, who can enter,
  type…), plus highlights and page text, in one call.
- It supports date filters and a news category.
- Tavily was used in Phase 1; Exa gave better results and data for each result.

**Q: Why Firecrawl?**
It turns a web page (including JavaScript-heavy ones and PDFs) into clean markdown plus links.
Discovery needs whole pages for entry conditions. The watch pipelines get enough from Exa's text,
so they don't use it.

**Q: Why MongoDB and not Postgres?**
Records are nested and change shape often (journeys, findings, verdicts). A document store fits
that and needs no migrations. Uniqueness that matters is still enforced with unique indexes. The
LangGraph Mongo checkpointer also fits. Postgres would work too; this was a fit choice, not a
necessity.

**Q: Why FastAPI?**
It's async (fits our async Mongo client and concurrent calls), validates requests with Pydantic,
generates API docs automatically, and is lightweight.

**Q: What is Langfuse and why self-host?**
Langfuse is LLM observability: every prompt, reply, token count and timing as a trace. Self-hosted
keeps data local and free. It runs on demand only, because left running 24/7 its ClickHouse store
once grew a 322 GB Docker disk and filled the laptop.

**Q: Why React without a UI library?**
A small, focused dashboard. React + router + Vite, one stylesheet, inline icons. Fewer dependencies
to break.

**Q: What libraries does the backend use?**
langgraph, langchain-core, langchain-openai, langfuse, pymongo (native async), langgraph-checkpoint-mongodb,
pydantic, fastapi, uvicorn, httpx, openpyxl, python-dotenv, tavily-python, firecrawl-py. Managed with
`uv`.

---

## 5. Backend-specific questions

**Q: How do runs execute without blocking the API?**
`POST` starts the run as a FastAPI background task and returns a `run_id` right away. Each step
appends a row to that run's journey in Mongo as it finishes. The UI polls.

**Q: Why polling and not WebSockets?**
It's simpler and survives a refresh or reconnect. The poll is a **delta feed**
(`/events?after=N`), so each row is sent once. That cut traffic from about 6.2 MB to about 0.15 MB
per run.

**Q: How is cost controlled?**
`RunBudget` sets hard caps on tool calls, searches, scrapes, model calls and wall-clock time,
enforced in code before every call. Once a cap is spent, the tools refuse. A prompt asking the
model to be frugal is not a budget.

**Q: How do you handle concurrency?**
- **Discovery:** one fetch-and-extract branch per site, in parallel. Firecrawl calls are serialised
  behind a lock with a 7-second gap, for the free tier's rate limit.
- **Component watch:** up to 4 parts at once (a semaphore) inside an `asyncio.TaskGroup`, so one
  systemic failure cancels the rest instead of spending more credits.

**Q: What is fan-out / fan-in? Any bug there?**
- **Fan-out:** rank sends one `Send` per site to fetch.
- **Fan-in:** evaluate waits for all of them.
- **Bug found:** LangGraph's `defer` doesn't wait for `Send` branches, so a failed fetch that jumped
  straight to evaluate made evaluate run early, twice, and trigger a needless re-plan. Fix: every
  site goes through extract (an empty bundle returns at once), so all sites fan in together.

**Q: What is checkpointing and why?**
LangGraph saves state after each step (`MongoDBSaver`, collections `run_progress*`), so a crashed
run can resume. Known leftover: if Mongo is unreachable, it falls back to memory.

**Q: How do you handle errors?**
Fail loudly. A broken step stops the run with its reason, shown in the UI. There are no quiet
fallbacks, because a silent fallback once wasted a whole run searching the wrong countries. One
planned exception: in component watch, one part's bad judge reply marks just that part "Could not
be judged", and the run goes on.

**Q: How do you make sure the judge doesn't skip pages?**
The reply schema is built per call with **one required field per page** (`page_0 … page_N`),
using Pydantic's `create_model`. A reply that leaves a page out fails validation instead of
silently losing it. Before this fix, 38 of 531 pages in one run were never judged.

**Q: What happens if a model reply is too long or slightly malformed?**
- Over-long text fields are trimmed and the reply is validated again (we paid for that call).
- Discovery's analysis can keep the valid items from a list.
- A reply cut off at the token limit raises a clear error naming the cause.

**Q: Timeouts and retries?**
Each call has a ceiling enforced by the caller (180 s, or 300 s for heavy calls), because the HTTP
client's own timeout didn't hold: one call ran 364 s. The client also gets one retry.

**Q: How is data idempotent / safe to re-run?**
- Opportunities: an upsert on the identity key with a unique index.
- Competitor pages: a unique index on URL in `competitor_seen`.
- Re-running doesn't create duplicates.
- Deleting a run removes its own signals and findings, but never opportunities (later runs may have
  confirmed them).

**Q: What are the Mongo collections?**

| Collection | Holds |
|---|---|
| `opportunities` | opportunity records |
| `programs` | editions per programme |
| `runs` | every run of every pipeline, with its journey |
| `run_progress`, `run_progress_writes` | discovery checkpoints |
| `extraction_failures` | typed extraction failures |
| `dead_ends` | pages fetched that gave nothing |
| `competitor_signals`, `competitor_seen` | competitor watch |
| `component_offers` | component findings |

**Q: What indexes matter?**
- Unique: opportunity identity, programme identity, `competitor_seen.url`,
  `competitor_signals.signal_id`, `dead_ends.url`.
- `first_seen_at`, for fetching recent signals.

**Q: How do you validate input files?**
Loaders for the parts workbook and competitor list check every required column and value, and stop
with the exact column or row at fault (for example "row 12: GST % is blank"). The API checks them
before starting a run, so a bad sheet fails at once, not mid-run.

**Q: Security?**
- Local, single-user tool: **no authentication yet** (needed before any shared deployment).
- Mongo is bound to localhost.
- Secrets live only in `.env`, which is gitignored.
- "Clear database" needs a JSON confirm body, so a forged cross-site form post is refused.
- Email goes only to `SMTP_TO`, and all page text in emails is HTML-escaped.
- Our cost data never goes to the model provider.

**Q: How do you test?**
Mock checks with fake models and a throwaway database (graph fan-in, judge slots, price maths,
email rendering), acceptance and smoke scripts in `scripts/`, plus one live run per milestone logged
in the spend ledger. Honest gap: no formal unit-test suite and no labelled evaluation set yet.

**Q: How is the email built?**
Server-side HTML with inline styles (email clients strip stylesheets), a plain-text copy, and the
CSV attached, sent over SMTP. There's a preview endpoint that returns exactly what would be sent.
The component email is trimmed because Gmail clips messages over about 102 KB.

**Q: How would you scale this?**
1. Containerise the API.
2. Move background tasks to a job queue (for example Celery or RQ, or a cloud scheduler) with a
   weekly cron.
3. Add authentication.
4. Cache search results and pages (W2).
5. Paginate the overview endpoint.
6. Choose a model per call type.

Mongo itself is far from its limits at this scale.

---

## 6. Data and evaluation

**Q: How do you know a change improved things?**
Today, by comparing live runs by eye, and that's the main weakness. The plan (W1):
- label stored search results and findings
- save page text
- replay ranking, judging and evaluation offline and score them against the labels
- every change must beat the baseline before it ships

**Q: Why not build that from the start?**
The priority was a working end-to-end system for the demos. In hindsight, component watch needed it
earlier. It's now the first step of the course correction.

**Q: Where does the data come from?**
- The business profile (markdown, kept by us and the manager)
- Engineering's parts workbook (12 fixed columns)
- The competitor list spreadsheet
- The live web through Exa and Firecrawl

**Q: Is any data sent outside?**
Prompts go to the model provider through OpenRouter: the profile text, page text and part
descriptions. Our rates and costs are never sent. Searches go to Exa.

---

## 7. Hard or tricky questions — answer honestly

**Q: Isn't this just a wrapper around an LLM?**
No. The model makes the judgement calls, but most of the system is engineering around it:
- hard budgets and parallel orchestration with checkpoints
- de-duplication with database guarantees
- price maths and dates in code
- skipping pages already seen across runs
- failure handling, observability, a dashboard and an email digest

**Q: Why did component watch need so many fixes?**
Each fix was judged on one live run without a reference set, and the use case wasn't nailed down
with the teams first. Both are being fixed: requirements first, then measurement.

**Q: Why not use regex or keyword rules — wouldn't that be more reliable?**
We tried, and measured the harm: keyword ranking scored a real awards page at zero; a closure regex
discarded "Nominate Now" pages; word matching dropped valid results. Rule of thumb: code does
arithmetic and formats we own, and the model does meaning.

**Q: What if the model gives different answers on different runs?**
It can, and search results drift too. That's why decisions go through fixed schemas, code computes
the numbers, and the plan is to measure consistency on a fixed set.

**Q: What if a website blocks scraping or the search API goes down?**
That step fails with its reason recorded. A failed site doesn't stop the other sites. A failed
search stops the run, so we never report "nothing found" when the truth is "couldn't look".

**Q: Why not distributor APIs from the start?**
We started with open-web search to discover sellers no list would include (the user's rule: vendors
are discovered, not listed). For price, stock and lead time, distributor APIs are the better
source, and they're part of the course correction.

**Q: What would you do differently?**
1. Agree on the use case with the end users before building.
2. Build a small labelled set before tuning prompts.
3. Store raw page text from day one.

**Q: Is it production-ready?**
- Competitor watch: close. It needs scheduling and the newsletter.
- Discovery: usable as a lead generator.
- Component watch: a pilot, not production.
- Platform: needs authentication, hosting and a scheduler before shared use.

---

## 8. Numbers to remember

| Item | Value |
|---|---|
| Pipelines | 3 (discovery has 4 modes) |
| Discovery steps | 7: plan, search, rank, fetch, extract, evaluate, store; up to 3 ReAct search steps |
| Discovery run | ~16–19 model calls, ~$0.05 model + ~$0.07 Exa, 5–15 min, 1–6 opportunities |
| Default discovery caps | 70 tool calls, 8 searches, 20 scrapes, 30 model calls, 25 min |
| Competitor run | 11 competitors, ~30 searches, ~10 model calls; best run 38 signals in 5 sections |
| ACE workbook | 64 parts (49 off the shelf, 15 custom), ₹2,40,596 per machine before GST |
| Component priority scope | parts making up 80% of off-the-shelf cost (13 of 49) |
| Component full run | ~68 searches (~$1), ~50 model calls, ~10 min |
| Best component run vs earlier | 157 vs 122 comparable prices, 14 vs 9 parts at lowest |
| Judge limits | 5 results per search, up to 10 pages per part, 24k output tokens |
| Exa | ~$0.014 per search, $20 free per month |
| Firecrawl | 1,000 pages per month, 1 page every 7 s |
| Code size | ~10,500 lines Python, ~3,000 lines React |
| Change log | 105 rows in AUDIT.md |
