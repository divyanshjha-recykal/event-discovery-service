# Pipeline audit

21 September 2026. Measured against the running code, not against intent.

## Method

```
workflow.py              1,772 lines — 29% of the codebase
prompt text              1,310 words across 5 prompts, all in that one file
fields verified          1 of 12 (deadline)
focus reaches            3 of 5 prompts
dead code                extract() + 384-word prompt + schema + retry ≈ 200 lines
```

---

## 1. The system does not know what it is looking for

This is the root failure. Everything below follows from it.

### 1.1 Two prompts contradict each other in the same call

`FOCUS_HINT["award"]` is injected into the ranking prompt:

> "THIS RUN WANTS AWARDS. Prizes, rankings, honours and **listings that name a winner**."

Fifteen lines later in the same prompt:

> "3. IS IT STILL AHEAD OF US? **A page reporting winners**, listing finalists, or naming a date already behind today is a finished edition — **rank it low**."

The focus line asks for exactly what question 3 rejects. A results page is the single most common piece of noise in every pool we have collected, and one half of the prompt instructs the model to find it.

### 1.2 A second contradiction, in the planner

`_QUERY_MECHANICS`, injected into both planning calls:

> "**Do not name a year.**"

`FOCUS_HINT["research"]`, injected into the same prompt:

> "Here a **year IS worth naming** in some queries."

Both present, neither qualified. The model resolves it arbitrarily.

### 1.3 Events cannot produce a usable record, by construction

`FOCUS_HINT["event"]` asks for things the business could "speak at, exhibit at or take part in." Everything downstream is built around **entry conditions**:

- `analyze` is told entry eligibility "is the heart of this"
- `ready = bool(result.eligibility_criteria)`
- `evaluate()` judges a company against stated conditions

An expo has no entry conditions. It has a stand price and a call for speakers. So an event run either stores nothing, or stores whatever prose looked condition-shaped — which is how a summit's *audience description* ("CXO, Head, Vice President of Sustainability") became an eligibility criterion.

### 1.4 The link chooser only knows about awards

It is run on every fetched page in every focus mode, and its instruction is fixed:

> "Pick at most N that most likely state **entry eligibility, who can enter, entry requirements, categories, fees, or the entry deadline**."

On a conference site the page we need is the call for papers. On an expo site it is the exhibitor prospectus. Neither matches those words, so the link chooser skips them and follows something else. `_focus_line` is never passed to this prompt.

### 1.5 The analyze prompt hardcodes the awards framing

> "These pages were fetched from one site while **researching recognition programmes**."

True for one of three focus modes.

**Conclusion of section 1.** This is an awards pipeline with two extra dropdown values bolted on. Events and research inherit awards vocabulary, awards link-hunting, awards record shape and awards eligibility logic. They were never going to work, and no amount of query tuning changes that.

---

## 2. Rules live in prose, where they are optional

Roughly forty behavioural rules are stated in paragraphs. A rule in prose is a suggestion the model weighs against every other sentence in the prompt. Current practice is the opposite:

> "By leveraging native constrained decoding and a rigorous, multi-layered inspection architecture, LLMs can be treated as reliable deterministic components; the industry has **transitioned from unreliable prompt engineering to deterministic structured output**."

Examples of ours that belong in code or schema and are instead prose:

| Rule, currently prose | Where it belongs |
|---|---|
| "never infer a deadline that is not written there" | grounding check (exists for deadline, nowhere else) |
| "if the page names no organiser, leave it empty" | grounding check |
| "return an empty list" when no conditions stated | schema cannot express it; a validator can |
| "skip grant, funding and fellowship programmes" | category filter in code |
| "do not name a year" | query post-check |

The deadline is the only rule we made deterministic, and it is the only field that has never silently fabricated.

---

## 3. The prompts contain narrative

The analyze prompt carries six lines recounting a past run:

> "A run once set aside a 25-category awards programme whose own page said anyone working toward sustainability may nominate, giving the reason 'one umbrella programme, not 25 opportunities' — that is this rule being read backwards."

That is paid for on every analyze call, in every run, forever. There are several of these. They are a changelog written into the working context.

---

## 4. Nodes do too many things

| Node | Lines | `await`s | Model-call sites | Distinct jobs |
|---|---|---|---|---|
| plan_queries | 107 | 3 | 1 | 1 |
| **research** | **202** | **15** | **6** | **5** — wave-1 search, wave-2 planning, wave-2 search, pool assembly + dead-end lookup, ranking, fetching with link traversal |
| analyze | 116 | 4 | 1 | 2 |
| **finalize** | **283** | **14** | **1** | **8** — build, validate, completeness, actionability, edition recording, save, eligibility, event recording |

`research` calls the *planner* inside itself. A node named for one phase runs another phase's model call. The graph says four stages; the code runs seven.

Industry guidance is explicit:

> "Design isolated worker nodes that handle specific tasks independently, communicating results back through graph state rather than calling each other directly."

> "A key gotcha is mandatory Pydantic output schema validation at each worker boundary to prevent worker cascade failures."

---

## 5. No decision is carried forward

`DiscoveryState` carries *data* — hits, bundles, candidates. It carries no *judgements*. The clearest case, in `research_node`:

```python
for hit, reason in picks:
    ...
    _ = reason          # the ranker's reason, explicitly discarded
```

The ranker decides *why* a page is worth fetching, and that reason is thrown away one line later. `analyze` then re-derives "is this for a business like ours" from scratch, with no knowledge that the question was already answered.

The same question is asked three times across the pipeline, by three prompts, with no reconciliation:

| Question | Asked at |
|---|---|
| Is it still open? | ranker Q3 → analyze Q1 → `assess_actionability` |
| Is this for us? | ranker Q2 → analyze Q2 → `evaluate()` |

And the three do not agree. The ranker sinks any page with a past date; analyze pursues anything whose *next* edition is ahead. A programme whose 2026 edition closed but which runs annually is exactly what `programs`/`typical_window` exists for — and the ranker guarantees analyze never sees it.

---

## 6. Verification is missing almost everywhere

Standard practice for schema-guided extraction is three checks:

> "missing attribute checks, **grounding verification**, and rule compliance checks that validate extracted values against schema constraints."

We have grounding for `deadline` (and, as of today, `organizing_body`). Not for `cycle_year`, `category`, `status`, `event_date`, `base_title`, or any eligibility condition. Everything else is the model's claim, written to Mongo.

Two consequences already observed:

- `organizing_body: "PRCA, mUni Campus"` — neither string on the page; PRCA belonged to a different programme in the same result set
- a record with **no deadline and no event date** declared `actionable`, because `assess_actionability` returns actionable with a note when both are missing

---

## 7. Prompt bloat, against current practice

The consensus pattern is **progressive disclosure**:

> "Most agents load all capabilities at once, every time, resulting in bloated system prompts, confused reasoning, and degrading performance as capabilities grow. Progressive disclosure lets agents load only the instructions they need per query."

> "Both Anthropic and OpenAI now recommend progressive disclosure as a core harness engineering technique."

| | Standard | Ours |
|---|---|---|
| Instruction loading | just-in-time, per task | all 307 words of `_QUERY_MECHANICS` on every planning call |
| Focus-specific rules | only the active one | award/event/research text all resident |
| Invariants | schema or code | prose, paragraph 19 |
| Growth | replace, with an eval gate | append, validated by one live run |

Our calls are single-shot structured extractions, not tool-choosing loops, so "skills" do not map directly. What maps is the principle: **load only what this call needs, and put anything that must always hold somewhere it cannot be ignored.**

---

## 8. What is actually sound

Worth stating so a rewrite does not discard it: storage and identity/upsert, the programs registry, budget enforcement, Langfuse tracing, the frontend and journey, `verify_deadline`, and `evaluate()` — whose per-criterion output with alternative-track handling is the strongest component in the system.

---

## 9. What to do

**Cut scope to awards.** Events and research are not features, they are two dropdown values pointed at an awards pipeline. Remove them until awards works end to end. One mode that produces trustworthy records beats three that produce none.

**One question per call.** Split the ranker's three questions and analyze's two into calls that each answer one thing, or accept that a call answering three questions will answer them in priority order and drop the third.

**Carry decisions, not just data.** The ranker's verdict travels with the seed into analyze. Analyze does not re-litigate what has been decided upstream on better evidence.

**Break the two god nodes.** `research` → search / rank / fetch. `finalize` → build / verify / store / judge. Validate at each boundary.

**Ground every field, or do not store it.** Apply the `deadline_verified` pattern to organiser, dates, year and status. A record that cannot be grounded is a typed failure, not a degraded record.

**Require a date.** No deadline and no event date is not actionable. Change `assess_actionability` to say so.

**Move the forty prose rules into schema, validators and post-checks**, and delete what remains. Target for `_QUERY_MECHANICS`: under 100 words.

**Delete the dead extraction path** or move it to the golden-set script that is its only caller.

---

## Sources

- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Progressive context disclosure — Thoughtworks Technology Radar](https://www.thoughtworks.com/radar/techniques/progressive-context-disclosure)
- [Context engineering in Deep Agents — LangChain](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- [Thinking in LangGraph — LangChain](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph)
- [LLM-based Schema-Guided Extraction and Validation](https://arxiv.org/abs/2604.06571)
- [PARSE: LLM-driven schema optimization for reliable entity extraction](https://arxiv.org/pdf/2510.08623)
- [Getting structured output from LLMs in 2026](https://projectsupply.in/blog/structured-output-llm-2026)
