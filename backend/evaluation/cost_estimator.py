"""Litigation cost and time estimation for case resolution.

Estimates real-world US litigation costs and timelines based on the judicial
level reached, case complexity (argument rounds), and escalation history.
Compares against the instant RalphLex resolution cost/time.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Realistic US litigation cost data per judicial level.
# Each entry: (attorney_fees_low, attorney_fees_high, court_costs_low,
#              court_costs_high, expert_fees_low, expert_fees_high,
#              duration_months_low, duration_months_high)
LEVEL_COSTS: dict[str, tuple[int, int, int, int, int, int, int, int]] = {
    "First Instance": (15_000, 75_000, 2_000, 5_000, 0, 5_000, 6, 18),
    "Appeals Court": (25_000, 100_000, 3_000, 7_000, 0, 3_000, 12, 24),
    "Superior Court": (50_000, 200_000, 5_000, 10_000, 2_000, 10_000, 12, 36),
    "Supreme Court": (200_000, 500_000, 10_000, 25_000, 5_000, 20_000, 12, 24),
}

# Complexity multipliers based on argument rounds
COMPLEXITY_MULTIPLIERS: dict[str, float] = {
    "simple": 1.0,    # 1-2 rounds
    "moderate": 1.3,   # 3-4 rounds
    "complex": 1.6,    # 5+ rounds
}


def _get_complexity(argument_rounds: int) -> tuple[str, float]:
    """Determine complexity category and multiplier from argument rounds."""
    if argument_rounds <= 2:
        return "simple", COMPLEXITY_MULTIPLIERS["simple"]
    elif argument_rounds <= 4:
        return "moderate", COMPLEXITY_MULTIPLIERS["moderate"]
    else:
        return "complex", COMPLEXITY_MULTIPLIERS["complex"]


@dataclass
class LevelCostBreakdown:
    """Cost breakdown for a single judicial level."""

    level: str
    attorney_fees_per_party_low: int
    attorney_fees_per_party_high: int
    court_costs_low: int
    court_costs_high: int
    expert_witness_fees_low: int
    expert_witness_fees_high: int
    duration_months_low: int
    duration_months_high: int

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "attorney_fees_per_party_low": self.attorney_fees_per_party_low,
            "attorney_fees_per_party_high": self.attorney_fees_per_party_high,
            "court_costs_low": self.court_costs_low,
            "court_costs_high": self.court_costs_high,
            "expert_witness_fees_low": self.expert_witness_fees_low,
            "expert_witness_fees_high": self.expert_witness_fees_high,
            "duration_months_low": self.duration_months_low,
            "duration_months_high": self.duration_months_high,
        }


@dataclass
class CostEstimate:
    """Complete litigation cost estimate comparing traditional vs RalphLex."""

    # Per-level breakdown (cumulative for escalated cases)
    level_breakdowns: list[LevelCostBreakdown] = field(default_factory=list)

    # Totals across all levels
    total_attorney_fees_per_party_low: int = 0
    total_attorney_fees_per_party_high: int = 0
    total_court_costs_low: int = 0
    total_court_costs_high: int = 0
    total_expert_fees_low: int = 0
    total_expert_fees_high: int = 0
    total_per_party_low: int = 0
    total_per_party_high: int = 0
    total_all_parties_low: int = 0
    total_all_parties_high: int = 0
    estimated_duration_months_low: int = 0
    estimated_duration_months_high: int = 0

    # Complexity info
    complexity_category: str = "simple"
    complexity_multiplier: float = 1.0
    argument_rounds: int = 0

    # RalphLex comparison
    ralphlex_processing_seconds: float = 0.0
    ralphlex_cost_estimate: str = "$0 (local LLM)"

    # Savings
    savings_low: int = 0
    savings_high: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "level_breakdowns": [lb.to_dict() for lb in self.level_breakdowns],
            "total_attorney_fees_per_party_low": self.total_attorney_fees_per_party_low,
            "total_attorney_fees_per_party_high": self.total_attorney_fees_per_party_high,
            "total_court_costs_low": self.total_court_costs_low,
            "total_court_costs_high": self.total_court_costs_high,
            "total_expert_fees_low": self.total_expert_fees_low,
            "total_expert_fees_high": self.total_expert_fees_high,
            "total_per_party_low": self.total_per_party_low,
            "total_per_party_high": self.total_per_party_high,
            "total_all_parties_low": self.total_all_parties_low,
            "total_all_parties_high": self.total_all_parties_high,
            "estimated_duration_months_low": self.estimated_duration_months_low,
            "estimated_duration_months_high": self.estimated_duration_months_high,
            "complexity_category": self.complexity_category,
            "complexity_multiplier": self.complexity_multiplier,
            "argument_rounds": self.argument_rounds,
            "ralphlex_processing_seconds": self.ralphlex_processing_seconds,
            "ralphlex_cost_estimate": self.ralphlex_cost_estimate,
            "savings_low": self.savings_low,
            "savings_high": self.savings_high,
        }


class CostEstimator:
    """Estimates real-world litigation costs vs RalphLex resolution."""

    def estimate(
        self,
        *,
        final_judicial_level: str,
        escalation_decisions: list[dict[str, object]],
        argument_rounds: int,
        created_at: datetime,
        completed_at: datetime,
        llm_provider: str = "ollama",
    ) -> CostEstimate:
        """Compute litigation cost estimate.

        Args:
            final_judicial_level: The judicial level at which the case resolved.
            escalation_decisions: List of escalation decision dicts from orchestrator.
            argument_rounds: Number of argument rounds (proxy for complexity).
            created_at: Case creation timestamp.
            completed_at: Case completion timestamp.
            llm_provider: "ollama" or "anthropic" — affects RalphLex cost display.

        Returns:
            CostEstimate with full breakdown and comparison.
        """
        result = CostEstimate()
        result.argument_rounds = argument_rounds

        # Determine complexity
        complexity_cat, multiplier = _get_complexity(argument_rounds)
        result.complexity_category = complexity_cat
        result.complexity_multiplier = multiplier

        # Build list of judicial levels traversed
        levels_traversed = self._get_levels_traversed(
            final_judicial_level, escalation_decisions
        )

        # Compute cumulative costs across all levels
        for level in levels_traversed:
            costs = LEVEL_COSTS.get(level)
            if costs is None:
                logger.warning("Unknown judicial level for cost: %s", level)
                continue

            (
                atty_low, atty_high,
                court_low, court_high,
                expert_low, expert_high,
                dur_low, dur_high,
            ) = costs

            # Apply complexity multiplier
            adj_atty_low = int(atty_low * multiplier)
            adj_atty_high = int(atty_high * multiplier)
            adj_court_low = int(court_low * multiplier)
            adj_court_high = int(court_high * multiplier)
            adj_expert_low = int(expert_low * multiplier)
            adj_expert_high = int(expert_high * multiplier)

            breakdown = LevelCostBreakdown(
                level=level,
                attorney_fees_per_party_low=adj_atty_low,
                attorney_fees_per_party_high=adj_atty_high,
                court_costs_low=adj_court_low,
                court_costs_high=adj_court_high,
                expert_witness_fees_low=adj_expert_low,
                expert_witness_fees_high=adj_expert_high,
                duration_months_low=dur_low,
                duration_months_high=dur_high,
            )
            result.level_breakdowns.append(breakdown)

            # Accumulate totals
            result.total_attorney_fees_per_party_low += adj_atty_low
            result.total_attorney_fees_per_party_high += adj_atty_high
            result.total_court_costs_low += adj_court_low
            result.total_court_costs_high += adj_court_high
            result.total_expert_fees_low += adj_expert_low
            result.total_expert_fees_high += adj_expert_high
            result.estimated_duration_months_low += dur_low
            result.estimated_duration_months_high += dur_high

        # Compute per-party and all-parties totals
        result.total_per_party_low = (
            result.total_attorney_fees_per_party_low
            + result.total_court_costs_low
            + result.total_expert_fees_low
        )
        result.total_per_party_high = (
            result.total_attorney_fees_per_party_high
            + result.total_court_costs_high
            + result.total_expert_fees_high
        )
        result.total_all_parties_low = result.total_per_party_low * 2
        result.total_all_parties_high = result.total_per_party_high * 2

        # RalphLex resolution time
        duration = completed_at - created_at
        result.ralphlex_processing_seconds = round(duration.total_seconds(), 1)

        # RalphLex cost
        if llm_provider == "anthropic":
            result.ralphlex_cost_estimate = "~$0.50-$5.00 (API usage)"
        else:
            result.ralphlex_cost_estimate = "$0 (local LLM)"

        # Savings (per party)
        result.savings_low = result.total_per_party_low
        result.savings_high = result.total_per_party_high

        return result

    def _get_levels_traversed(
        self,
        final_level: str,
        escalation_decisions: list[dict[str, object]],
    ) -> list[str]:
        """Get ordered list of judicial levels the case went through."""
        if not escalation_decisions:
            return [final_level]

        levels: list[str] = []
        for decision in escalation_decisions:
            current = str(decision.get("current_level", ""))
            if current and current not in levels:
                levels.append(current)

        # Add the final level
        if final_level not in levels:
            levels.append(final_level)

        return levels
