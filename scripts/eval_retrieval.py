"""Offline retrieval evaluation — does re-ranking beat Tavily's own order?

    uv run python scripts/eval_retrieval.py

Runs entirely against files already in the repo. No API calls, no cost, no
network: `retrieval_set/labels_done2.csv` holds 207 hand-labelled results with
Tavily's rank and score, and `retrieval_set/rerank_cache.json` holds cached
cross-encoder scores for the same rows.

This exists because the alternative is validating every selection change with a
live run — seven minutes, real money, one sample, huge variance. That is not a
development loop. An earlier version of this script was never committed and was
lost; the measurement had to be rebuilt from the surviving data.

Labels: 2 = strongly relevant, 1 = partially, 0 = irrelevant.
"""

from __future__ import annotations

import collections
import csv
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LABELS = REPO_ROOT / "retrieval_set" / "labels_done2.csv"
CACHE = REPO_ROOT / "retrieval_set" / "rerank_cache.json"

CUTOFFS = (3, 5)


def load() -> tuple[dict[str, list[dict]], dict[tuple[str, str], float]]:
    rows = list(csv.DictReader(LABELS.open(encoding="utf-8")))
    raw = json.loads(CACHE.read_text(encoding="utf-8"))

    # Cache keys are "model|query|url".
    scores: dict[tuple[str, str], float] = {}
    for key, value in raw.items():
        parts = key.split("|", 2)
        if len(parts) == 3:
            scores[(parts[1], parts[2])] = value

    by_query: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_query[row["query"]].append(row)
    return by_query, scores


def _score_for(scores, query: str, url: str) -> float | None:
    exact = scores.get((query, url))
    if exact is not None:
        return exact
    # URLs were cached before canonicalisation; fall back to a prefix match.
    return next(
        (v for (q, u), v in scores.items() if q == query and u.startswith(url[:60])),
        None,
    )


def dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg(order: list[dict], k: int) -> float | None:
    ideal = dcg(sorted((int(r["label"]) for r in order), reverse=True)[:k])
    return dcg([int(r["label"]) for r in order[:k]]) / ideal if ideal else None


def main() -> int:
    if not LABELS.exists() or not CACHE.exists():
        print(f"missing {LABELS} or {CACHE}", file=sys.stderr)
        return 1

    by_query, scores = load()
    stats: dict[str, list[float]] = collections.defaultdict(list)
    missing = 0

    for query, rows in by_query.items():
        for row in rows:
            score = _score_for(scores, query, row["url"])
            if score is None:
                missing += 1
            row["_rerank"] = score if score is not None else -1.0
            row["_tavily"] = float(row["tavily_score"] or 0)

        orders = {
            "tavily": sorted(rows, key=lambda r: -r["_tavily"]),
            "rerank": sorted(rows, key=lambda r: -r["_rerank"]),
        }
        for name, order in orders.items():
            for k in CUTOFFS:
                strong = sum(1 for r in order[:k] if int(r["label"]) == 2)
                stats[f"{name}|P@{k} strong"].append(strong / k)
                value = ndcg(order, k)
                if value is not None:
                    stats[f"{name}|NDCG@{k}"].append(value)
            rank = next(
                (i + 1 for i, r in enumerate(order) if int(r["label"]) == 2), None
            )
            stats[f"{name}|MRR"].append(1 / rank if rank else 0.0)

    total = sum(len(v) for v in by_query.values())
    print(f"{len(by_query)} queries · {total} labelled results · {missing} unscored\n")
    print(f"{'metric':<16}{'Tavily order':>14}{'Reranked':>11}{'change':>10}")
    print("-" * 51)
    metrics = [f"P@{k} strong" for k in CUTOFFS] + [f"NDCG@{k}" for k in CUTOFFS] + ["MRR"]
    for metric in metrics:
        base = stats[f"tavily|{metric}"]
        new = stats[f"rerank|{metric}"]
        t, r = sum(base) / len(base), sum(new) / len(new)
        change = (r - t) / t * 100 if t else 0.0
        print(f"{metric:<16}{t:>14.3f}{r:>11.3f}{change:>+9.1f}%")

    print(
        "\nMRR is the one to watch: it is how far down the list the first "
        "genuinely\nrelevant result sits, and the site-selection call only ever "
        "sees the top few."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
