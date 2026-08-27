# Opportunity Radar

Discovers awards, grants and events relevant to Recykal, evaluates eligibility
against the business profile, and stores the result. Decision support only —
nothing here submits an application or contacts an award body.

`CLAUDE.md` is the source of truth for architecture, schemas, constraints and the
stage plan. Read it before changing anything.

## Setup

```bash
cp .env.example .env       # then fill it in — nothing runs without it
docker compose up -d       # MongoDB + self-hosted Langfuse
uv sync
```

Langfuse UI: http://localhost:3000 · MongoDB: `localhost:27017`

## Stage 0 acceptance checks

```bash
uv run python scripts/show_profile.py --summary   # loads BusinessProfile.md
uv run python scripts/smoke_openrouter.py \
    --model <slug-a> --model <slug-b>             # traced OpenRouter calls
```

## Layout

```
CLAUDE.md                      source of truth
BusinessProfile.md             what the Eligibility Agent reasons against
golden_set/                    hand-written correct answers for extract()
src/opportunity_radar/
  paths.py  config.py          repo paths, environment
  profile.py                   Stage 0 — loads the business profile
  tracing.py                   Stage 0 — Langfuse + OpenRouter chat model
  storage/ extraction/         Stages 1-2, empty
  discovery/ eligibility/      Stages 3-4, empty
scripts/                       acceptance checks, not a test suite
```
