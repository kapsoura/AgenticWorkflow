import json
from collections import Counter
from typing import Dict, List, Optional, Tuple

from src.agents.agent_tools import trend_tool_specs
from src.pipeline.schemas import TrendSummary
from src.utils.llm_client import AnthropicClient
from src.utils.prompt_store import render_prompt
from src.utils.tool_loop import AnthropicToolClient


class ArchiveTrendAnalyzer:
    """Per-code trend assessment routed through Anthropic.

    Preferred path: real Anthropic tool use — the model calls read-only tools
    (yearly counts, top problems) to inspect the archive, then commits to a trend
    DIRECTION and rationale. Falls back to the ``claude -p`` JSON path when no
    ANTHROPIC_API_KEY is set. There is **no heuristic fallback** — if neither
    backend is enabled or the model returns nothing usable, the summary is
    NOT_AVAILABLE so the report flags it for human review.
    """

    SOFTWARE_HINTS = ("software", "application", "algorithm", "image", "dicom")
    _VALID_DIRECTIONS = {"upward", "downward", "flat"}

    def __init__(self):
        self.llm = AnthropicClient()
        self.tool_client = AnthropicToolClient()
        self.last_tool_calls: List[str] = []
        self.last_fallback_reason: Optional[str] = None
        if self.tool_client.enabled:
            self.last_backend = "anthropic_tools"
        elif self.llm.enabled:
            self.last_backend = "anthropic"
        else:
            self.last_backend = "unavailable"
            self.last_fallback_reason = (
                "No Anthropic backend enabled (set ANTHROPIC_API_KEY for tools or "
                "CLAUDE_CLI_PATH for the CLI in .env)"
            )

    def summarize(self, product_code: str, events: List[dict]) -> TrendSummary:
        self.last_tool_calls = []

        if not events:
            self.last_backend = "unavailable"
            self.last_fallback_reason = "No events in working archive for this product code"
            return self._not_available_summary(product_code)

        # Preferred path: real Anthropic tool use (model inspects the aggregates
        # via tools, then commits to a direction). Falls back to the CLI JSON path.
        if self.tool_client.enabled:
            try:
                return self._summarize_with_tools(product_code, events)
            except Exception as exc:  # noqa: BLE001 — surface, then try the CLI path
                self.last_fallback_reason = f"Anthropic tool trend analysis failed: {exc}"

        if self.llm.enabled:
            try:
                return self._summarize_llm(product_code, events)
            except Exception as exc:  # noqa: BLE001 — surface the reason via the trace
                self.last_backend = "unavailable"
                self.last_fallback_reason = f"Anthropic trend analysis failed: {exc}"
                return self._not_available_summary(product_code)

        if not self.tool_client.enabled and not self.llm.enabled:
            self.last_backend = "unavailable"
            self.last_fallback_reason = (
                "No Anthropic backend enabled (set ANTHROPIC_API_KEY or CLAUDE_CLI_PATH in .env)"
            )
        return self._not_available_summary(product_code)

    def _summarize_with_tools(self, product_code: str, events: List[dict]) -> TrendSummary:
        software_problem_events, latest_count, previous_count = self._aggregate(events)
        result = self.tool_client.run(
            system_prompt=render_prompt("trend_tools_system"),
            user_prompt=render_prompt(
                "trend_tools_user",
                product_code=product_code,
                total_events=len(events),
                software_problem_events=software_problem_events,
                previous_year_events=previous_count,
                latest_year_events=latest_count,
            ),
            tools=trend_tool_specs(self, events),
            max_tokens=600,
        )
        self.last_tool_calls = [inv.name for inv in result.invocations]

        verdict = result.json_object()
        direction = str(verdict.get("trend_direction", "")).strip().lower()
        if direction not in self._VALID_DIRECTIONS:
            self.last_backend = "anthropic_tools"
            self.last_fallback_reason = "Anthropic tool model returned no usable trend direction"
            return self._not_available_summary(product_code)

        self.last_backend = "anthropic_tools"
        self.last_fallback_reason = None
        return TrendSummary(
            product_code=product_code,
            total_events=len(events),
            software_problem_events=software_problem_events,
            latest_year_events=latest_count,
            previous_year_events=previous_count,
            trend_direction=direction,
            trend_rationale=str(verdict.get("rationale", "")).strip(),
        )

    def _summarize_llm(self, product_code: str, events: List[dict]) -> TrendSummary:
        software_problem_events, latest_count, previous_count = self._aggregate(events)
        yearly = self.yearly_breakdown(events)
        problems = self.problem_breakdown(events)

        result = self.llm.complete_json(
            system_prompt=render_prompt("trend_system"),
            user_prompt=render_prompt(
                "trend_user",
                product_code=product_code,
                total_events=len(events),
                software_problem_events=software_problem_events,
                previous_year_events=previous_count,
                latest_year_events=latest_count,
                yearly_breakdown=json.dumps(yearly),
                top_problems=json.dumps(problems),
            ),
            fallback={},
        )

        direction = str(result.get("trend_direction", "")).strip().lower()
        if direction not in self._VALID_DIRECTIONS:
            # No heuristic fallback: without an agent verdict the trend is unknown.
            self.last_backend = "anthropic"
            self.last_fallback_reason = "Anthropic model returned no usable trend direction"
            return self._not_available_summary(product_code)

        self.last_backend = "anthropic"
        self.last_fallback_reason = None
        return TrendSummary(
            product_code=product_code,
            total_events=len(events),
            software_problem_events=software_problem_events,
            latest_year_events=latest_count,
            previous_year_events=previous_count,
            trend_direction=direction,
            # Capture the model's justification instead of discarding it.
            trend_rationale=str(result.get("rationale", "")).strip(),
        )

    def _aggregate(self, events: List[dict]) -> Tuple[int, int, int]:
        """Deterministic counts used purely as context for the agent's judgment."""
        year_counter: Counter = Counter()
        software_problem_events = 0
        for event in events:
            date_received = str(event.get("date_received", ""))
            if len(date_received) >= 4 and date_received[:4].isdigit():
                year_counter[date_received[:4]] += 1
            problems = " ".join(event.get("product_problems") or []).lower()
            if any(term in problems for term in self.SOFTWARE_HINTS):
                software_problem_events += 1

        if year_counter:
            years = sorted(year_counter.keys())
            latest_count = year_counter[years[-1]]
            previous_count = year_counter[years[-2]] if len(years) > 1 else year_counter[years[-1]]
        else:
            latest_count = 0
            previous_count = 0
        return software_problem_events, latest_count, previous_count

    @staticmethod
    def _not_available_summary(product_code: str) -> TrendSummary:
        return TrendSummary(
            product_code=product_code,
            total_events=0,
            software_problem_events=0,
            latest_year_events=0,
            previous_year_events=0,
            trend_direction="not_available",
        )

    def yearly_breakdown(self, events: List[dict]) -> List[Dict[str, int]]:
        """Return events-per-year, sorted ascending, for trend plotting."""
        year_counter: Counter = Counter()
        for event in events:
            date_received = event.get("date_received", "")
            if len(date_received) >= 4 and date_received[:4].isdigit():
                year_counter[date_received[:4]] += 1
        return [{"year": year, "count": year_counter[year]} for year in sorted(year_counter)]

    def problem_breakdown(self, events: List[dict], top_n: int = 8) -> List[Dict[str, int]]:
        """Return the most frequent reported product problems for plotting."""
        problem_counter: Counter = Counter()
        for event in events:
            for problem in event.get("product_problems") or []:
                label = str(problem).strip()
                if label:
                    problem_counter[label] += 1
        return [
            {"problem": label, "count": count}
            for label, count in problem_counter.most_common(top_n)
        ]
