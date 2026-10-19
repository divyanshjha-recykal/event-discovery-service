# Spend ledger

Every live call that spends credits, logged after it runs. Balances are as reported by
each provider's dashboard.

| Date | What was tested | Exa searches | Firecrawl scrapes | Model cost | Exa balance | Firecrawl balance |
|---|---|---|---|---|---|---|
| 2026-10-05 | Phase 2 start | — | — | — | $20.00 (resets next month) | 643 / 1,000 (resets 21 Oct) |
| 2026-10-08 | Run bbb0bf — Research, Batch 1+2 test | 5 | 6 pages (rawHtml on 3 first pages) | ~10 model calls | — | check dashboard |
| 2026-10-08 | Run 906ad0 — Awards, Batch 1+2 test | 5 | 10 pages (rawHtml on 4 first pages) | ~13 model calls | — | check dashboard |
| 2026-10-13 | Search-only test — Research (steps A+B) | 5 | 0 | 4 model calls | — | — |
| 2026-10-13 | Search-only test — Awards (steps A+B) | 5 | 0 | 4 model calls | — | — |
| 2026-10-13 | rank_pool re-ranks, Step C part 1 (research + awards pools) | 0 | 0 | 2 model calls | — | — |
| 2026-10-13 | Run 4d38cd — Research, Step C part 2; stopped after search | 4 | 0 | 3 model calls | — | — |
| 2026-10-13 | Run 973845 — Research, after the row-57 fix; stopped after search | 5 | 0 | 5 model calls | — | — |
| 2026-10-13 | rank_pool re-rank of run 973845's pool after row-58 fix | 0 | 0 | 1 model call | — | — |
| 2026-10-13 | Run 6a68d9 — Research, full run after row-58 fix | 5 | 9 pages | 13 model calls | — | check dashboard |
| 2026-10-13 | Run 4c16b9 — Everything (search step failed after 2 searches) | 2 | 11 pages | 11 model calls | — | check dashboard |
| 2026-10-13 | Run 0d4823 — Awards | 5 | 12 pages | 16 model calls | — | check dashboard |
| 2026-10-16 | rank_pool A/B: 3 saved pools × with/without the stored-programme lines in the prompt | 0 | 0 | 6 model calls | — | — |
| 2026-10-16 | R0: Exa publication-index test (3 paper sketches) | 3 (category publication, 10 results) | 0 | 1 model call | — | — |
