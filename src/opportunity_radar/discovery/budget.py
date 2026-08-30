"""Run limits for the Discovery Agent.

The tool-call budget is a hard stop, not a suggestion: it is enforced in the
tool wrapper, so once it is spent every tool refuses and the agent physically
cannot do anything else. A prompt asking the model to be frugal is not a budget.

Three limits, because they fail differently:

- **tool-call budget** — the headline cost control.
- **per-provider caps** — a shared budget can be spent lopsidedly, e.g. entirely
  on Firecrawl scrapes with no searches. These stop one provider eating the run.
- **wall clock** — the one a call-count budget structurally cannot catch. A hung
  Firecrawl request or a stalled model never decrements anything, so without a
  clock an unattended run just sits there.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

DEFAULT_TOOL_CALLS = 25
DEFAULT_MAX_SEARCHES = 10
DEFAULT_MAX_SCRAPES = 12
DEFAULT_WALL_CLOCK_SECONDS = 600


class BudgetExhausted(RuntimeError):
    """Raised by the runner when a limit has stopped the run."""


@dataclass
class RunBudget:
    tool_calls: int = DEFAULT_TOOL_CALLS
    max_searches: int = DEFAULT_MAX_SEARCHES
    max_scrapes: int = DEFAULT_MAX_SCRAPES
    wall_clock_seconds: int = DEFAULT_WALL_CLOCK_SECONDS

    spent: int = 0
    searches: int = 0
    scrapes: int = 0
    started_at: float = field(default_factory=time.monotonic)
    stop_reason: str | None = None
    log: list[str] = field(default_factory=list)

    # -- queries ------------------------------------------------------------

    @property
    def remaining(self) -> int:
        return max(self.tool_calls - self.spent, 0)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def exhausted(self) -> bool:
        return self.stop_reason is not None or self.remaining <= 0 or self.timed_out

    @property
    def timed_out(self) -> bool:
        return self.elapsed >= self.wall_clock_seconds

    # -- enforcement --------------------------------------------------------

    def refusal(self, tool_name: str) -> str | None:
        """Why `tool_name` may not run, or None if it may.

        Returned to the model as the tool's result so it understands the run is
        over rather than retrying blindly.
        """
        # Storing a record and reading memory stay available even at zero budget:
        # refusing a save would discard work already paid for.
        if tool_name in self.FREE_TOOLS and not self.timed_out:
            return None

        if self.timed_out:
            self.stop_reason = self.stop_reason or (
                f"wall-clock limit of {self.wall_clock_seconds}s reached"
            )
            return f"STOP: {self.stop_reason}. No further tool calls are possible."

        if self.remaining <= 0:
            self.stop_reason = self.stop_reason or (
                f"tool-call budget of {self.tool_calls} exhausted"
            )
            return f"STOP: {self.stop_reason}. No further tool calls are possible."

        if tool_name == "search" and self.searches >= self.max_searches:
            return (
                f"STOP: per-provider cap reached — {self.max_searches} searches. "
                "Use what you already have; scrape or extract instead."
            )

        if tool_name == "scrape" and self.scrapes >= self.max_scrapes:
            return (
                f"STOP: per-provider cap reached — {self.max_scrapes} scrapes. "
                "Use pages you have already fetched."
            )

        return None

    # Tools that cost nothing external — a Mongo read and a Mongo write. The
    # budget exists to cap Tavily calls, Firecrawl calls and LLM tokens, so
    # charging it for these spends the cap on the one action that is free and is
    # the entire point of the run. A run once extracted three records and lost
    # the best one because the budget ran out on the save, one call after the
    # expensive work was already paid for.
    FREE_TOOLS = frozenset({"read_memory", "save_opportunity"})

    def consume(self, tool_name: str) -> None:
        if tool_name in self.FREE_TOOLS:
            self.log.append(f"  --. {tool_name}  (free, t+{self.elapsed:.0f}s)")
            return

        self.spent += 1
        if tool_name == "search":
            self.searches += 1
        elif tool_name == "scrape":
            self.scrapes += 1
        self.log.append(f"{self.spent:>3}. {tool_name}  (t+{self.elapsed:.0f}s)")

    # -- reporting ----------------------------------------------------------

    def summary(self) -> str:
        return (
            f"tool calls {self.spent}/{self.tool_calls} · "
            f"searches {self.searches}/{self.max_searches} · "
            f"scrapes {self.scrapes}/{self.max_scrapes} · "
            f"elapsed {self.elapsed:.0f}s/{self.wall_clock_seconds}s"
            + (f" · stopped: {self.stop_reason}" if self.stop_reason else "")
        )


def estimate_cost(budget: RunBudget, price_in: float, price_out: float,
                  avg_input_tokens: int = 6000, avg_output_tokens: int = 500) -> float:
    """Rough worst-case USD for a run, so an accidental --budget 500 is visible.

    Deliberately crude: every tool call implies roughly one model turn, and the
    context grows as results accumulate. Reported as an upper bound, not a quote.
    """
    turns = budget.tool_calls + 1
    tokens_in = turns * avg_input_tokens
    tokens_out = turns * avg_output_tokens
    return (tokens_in / 1e6) * price_in + (tokens_out / 1e6) * price_out
