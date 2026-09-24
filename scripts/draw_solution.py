"""Render the presentation diagram of the pipeline to docs/.

    uv run python scripts/draw_solution.py

Deliberately not the LangGraph render (scripts/draw_graph.py does that). This
one is for a slide: what each step does and who does it, rather than node names.
"""

from __future__ import annotations

import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"

MERMAID = """flowchart LR
    P["<b>Business<br/>profile</b>"]:::src
    A1["<b>1 Plan</b><br/>write the<br/>search queries"]:::ai
    A2["<b>2 Search</b><br/>broad, then informed<br/>by the results"]:::tool
    A3["<b>3 Rank</b><br/>order the pool,<br/>pick what to fetch"]:::ai
    B1["<b>4 Fetch</b><br/>scrape pages,<br/>follow the best link"]:::tool
    B2["<b>5 Extract</b><br/>organiser, dates,<br/>entry conditions"]:::ai
    B3["<b>6 Evaluate</b><br/>condition by condition<br/>vs the profile"]:::ai
    B4["<b>7 Store</b><br/>saved once,<br/>with its verdict"]:::det
    O["<b>Dashboard<br/>or CSV</b>"]:::out

    P --> A1 --> A2 --> A3 --> B1 --> B2 --> B3 --> B4 --> O
    A3 -.->|"pool too thin"| A1
    B3 -.->|"nothing found"| A1

    classDef src fill:#1f2937,stroke:#111827,color:#fff
    classDef ai fill:#2563eb,stroke:#1e40af,color:#fff
    classDef tool fill:#0f766e,stroke:#115e59,color:#fff
    classDef det fill:#7c3aed,stroke:#5b21b6,color:#fff
    classDef out fill:#b91c1c,stroke:#7f1d1d,color:#fff
"""


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "solution-flow.mmd").write_text(MERMAID, encoding="utf-8")
    (DOCS / "solution-flow.md").write_text(
        f"# Proposed solution - pipeline flow\n\n```mermaid\n{MERMAID}```\n",
        encoding="utf-8",
    )
    print(f"wrote {DOCS / 'solution-flow.mmd'}")
    print(f"wrote {DOCS / 'solution-flow.md'}")

    try:
        from langchain_core.runnables.graph_mermaid import draw_mermaid_png

        (DOCS / "solution-flow.png").write_bytes(
            draw_mermaid_png(
                MERMAID, background_color="white", padding=20,
                max_retries=5, retry_delay=2.0,
            )
        )
    except Exception as exc:  # noqa: BLE001 - the text versions are the deliverable
        print(f"PNG skipped ({type(exc).__name__}: {exc}); the .md renders anywhere")
        return 0
    print(f"wrote {DOCS / 'solution-flow.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
