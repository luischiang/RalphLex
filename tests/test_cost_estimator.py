"""Tests for litigation cost and time estimation."""

from datetime import UTC, datetime, timedelta

from backend.evaluation.cost_estimator import (
    COMPLEXITY_MULTIPLIERS,
    LEVEL_COSTS,
    CostEstimate,
    CostEstimator,
    LevelCostBreakdown,
    _get_complexity,
)


class TestGetComplexity:
    """Test complexity category determination."""

    def test_simple_1_round(self) -> None:
        cat, mult = _get_complexity(1)
        assert cat == "simple"
        assert mult == 1.0

    def test_simple_2_rounds(self) -> None:
        cat, mult = _get_complexity(2)
        assert cat == "simple"
        assert mult == 1.0

    def test_moderate_3_rounds(self) -> None:
        cat, mult = _get_complexity(3)
        assert cat == "moderate"
        assert mult == 1.3

    def test_moderate_4_rounds(self) -> None:
        cat, mult = _get_complexity(4)
        assert cat == "moderate"
        assert mult == 1.3

    def test_complex_5_rounds(self) -> None:
        cat, mult = _get_complexity(5)
        assert cat == "complex"
        assert mult == 1.6

    def test_complex_high_rounds(self) -> None:
        cat, mult = _get_complexity(10)
        assert cat == "complex"
        assert mult == 1.6


class TestLevelCostBreakdown:
    """Test LevelCostBreakdown dataclass."""

    def test_to_dict(self) -> None:
        lb = LevelCostBreakdown(
            level="First Instance",
            attorney_fees_per_party_low=15_000,
            attorney_fees_per_party_high=75_000,
            court_costs_low=2_000,
            court_costs_high=5_000,
            expert_witness_fees_low=0,
            expert_witness_fees_high=5_000,
            duration_months_low=6,
            duration_months_high=18,
        )
        d = lb.to_dict()
        assert d["level"] == "First Instance"
        assert d["attorney_fees_per_party_low"] == 15_000
        assert d["duration_months_high"] == 18


class TestCostEstimate:
    """Test CostEstimate dataclass."""

    def test_to_dict_defaults(self) -> None:
        ce = CostEstimate()
        d = ce.to_dict()
        assert d["total_per_party_low"] == 0
        assert d["complexity_category"] == "simple"
        assert d["ralphlex_cost_estimate"] == "$0 (local LLM)"
        assert isinstance(d["level_breakdowns"], list)

    def test_to_dict_with_breakdowns(self) -> None:
        lb = LevelCostBreakdown(
            level="Test",
            attorney_fees_per_party_low=1,
            attorney_fees_per_party_high=2,
            court_costs_low=3,
            court_costs_high=4,
            expert_witness_fees_low=5,
            expert_witness_fees_high=6,
            duration_months_low=7,
            duration_months_high=8,
        )
        ce = CostEstimate(level_breakdowns=[lb])
        d = ce.to_dict()
        assert len(d["level_breakdowns"]) == 1
        breakdown = d["level_breakdowns"][0]  # type: ignore[index]
        assert breakdown["level"] == "Test"  # type: ignore[index]


class TestCostEstimator:
    """Test CostEstimator.estimate()."""

    def _make_estimator(self) -> CostEstimator:
        return CostEstimator()

    def test_single_level_simple(self) -> None:
        """First Instance, 2 rounds, no escalation."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(minutes=5)

        result = est.estimate(
            final_judicial_level="First Instance",
            escalation_decisions=[],
            argument_rounds=2,
            created_at=created,
            completed_at=completed,
        )

        assert result.complexity_category == "simple"
        assert result.complexity_multiplier == 1.0
        assert len(result.level_breakdowns) == 1
        assert result.level_breakdowns[0].level == "First Instance"

        # Check totals match first instance costs (1.0x multiplier)
        fi = LEVEL_COSTS["First Instance"]
        assert result.total_attorney_fees_per_party_low == fi[0]
        assert result.total_attorney_fees_per_party_high == fi[1]
        assert result.total_per_party_low == fi[0] + fi[2] + fi[4]
        assert result.total_per_party_high == fi[1] + fi[3] + fi[5]
        assert result.total_all_parties_low == result.total_per_party_low * 2
        assert result.total_all_parties_high == result.total_per_party_high * 2

        # Duration
        assert result.estimated_duration_months_low == fi[6]
        assert result.estimated_duration_months_high == fi[7]

        # RalphLex
        assert result.ralphlex_processing_seconds == 300.0
        assert result.ralphlex_cost_estimate == "$0 (local LLM)"

        # Savings
        assert result.savings_low == result.total_per_party_low
        assert result.savings_high == result.total_per_party_high

    def test_moderate_complexity(self) -> None:
        """3 argument rounds = moderate complexity (1.3x)."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(minutes=10)

        result = est.estimate(
            final_judicial_level="First Instance",
            escalation_decisions=[],
            argument_rounds=3,
            created_at=created,
            completed_at=completed,
        )

        assert result.complexity_category == "moderate"
        assert result.complexity_multiplier == 1.3

        fi = LEVEL_COSTS["First Instance"]
        expected_atty_low = int(fi[0] * 1.3)
        assert result.total_attorney_fees_per_party_low == expected_atty_low

    def test_complex_high_rounds(self) -> None:
        """5+ rounds = complex (1.6x)."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(minutes=15)

        result = est.estimate(
            final_judicial_level="First Instance",
            escalation_decisions=[],
            argument_rounds=5,
            created_at=created,
            completed_at=completed,
        )

        assert result.complexity_category == "complex"
        assert result.complexity_multiplier == 1.6

    def test_escalation_cumulative_costs(self) -> None:
        """Escalated case: costs are cumulative across levels."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(hours=1)

        escalation_decisions = [
            {
                "should_escalate": True,
                "reason": "Constitutional question",
                "current_level": "First Instance",
                "next_level": "Appeals Court",
                "triggers": ["constitutional_question"],
            }
        ]

        result = est.estimate(
            final_judicial_level="Appeals Court",
            escalation_decisions=escalation_decisions,
            argument_rounds=4,
            created_at=created,
            completed_at=completed,
        )

        # Should have 2 level breakdowns
        assert len(result.level_breakdowns) == 2
        assert result.level_breakdowns[0].level == "First Instance"
        assert result.level_breakdowns[1].level == "Appeals Court"

        # Duration is cumulative
        fi = LEVEL_COSTS["First Instance"]
        ac = LEVEL_COSTS["Appeals Court"]
        assert result.estimated_duration_months_low == fi[6] + ac[6]
        assert result.estimated_duration_months_high == fi[7] + ac[7]

        # Attorney fees are cumulative (with 1.3x moderate multiplier)
        mult = COMPLEXITY_MULTIPLIERS["moderate"]
        expected_atty_low = int(fi[0] * mult) + int(ac[0] * mult)
        assert result.total_attorney_fees_per_party_low == expected_atty_low

    def test_multi_level_escalation(self) -> None:
        """Multi-level escalation through 3 courts."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(hours=2)

        escalation_decisions = [
            {
                "should_escalate": True,
                "reason": "Constitutional question",
                "current_level": "First Instance",
                "next_level": "Appeals Court",
                "triggers": ["constitutional_question"],
            },
            {
                "should_escalate": True,
                "reason": "Conflicting precedents",
                "current_level": "Appeals Court",
                "next_level": "Superior Court",
                "triggers": ["conflicting_precedents"],
            },
        ]

        result = est.estimate(
            final_judicial_level="Superior Court",
            escalation_decisions=escalation_decisions,
            argument_rounds=5,
            created_at=created,
            completed_at=completed,
        )

        assert len(result.level_breakdowns) == 3
        levels = [lb.level for lb in result.level_breakdowns]
        assert levels == ["First Instance", "Appeals Court", "Superior Court"]

        # All costs are cumulative
        assert result.total_per_party_low > 0
        assert result.total_all_parties_low == result.total_per_party_low * 2

    def test_anthropic_provider_cost(self) -> None:
        """Anthropic provider shows API cost."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(minutes=3)

        result = est.estimate(
            final_judicial_level="First Instance",
            escalation_decisions=[],
            argument_rounds=1,
            created_at=created,
            completed_at=completed,
            llm_provider="anthropic",
        )

        assert "API usage" in result.ralphlex_cost_estimate

    def test_processing_time_calculation(self) -> None:
        """RalphLex processing time is computed from timestamps."""
        est = self._make_estimator()
        created = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
        completed = datetime(2026, 3, 15, 10, 7, 30, tzinfo=UTC)

        result = est.estimate(
            final_judicial_level="First Instance",
            escalation_decisions=[],
            argument_rounds=2,
            created_at=created,
            completed_at=completed,
        )

        assert result.ralphlex_processing_seconds == 450.0

    def test_supreme_court_costs(self) -> None:
        """Supreme Court level has highest cost range."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(hours=3)

        escalation_decisions = [
            {"current_level": "First Instance", "next_level": "Appeals Court",
             "should_escalate": True, "reason": "test", "triggers": []},
            {"current_level": "Appeals Court", "next_level": "Superior Court",
             "should_escalate": True, "reason": "test", "triggers": []},
            {"current_level": "Superior Court", "next_level": "Supreme Court",
             "should_escalate": True, "reason": "test", "triggers": []},
        ]

        result = est.estimate(
            final_judicial_level="Supreme Court",
            escalation_decisions=escalation_decisions,
            argument_rounds=5,
            created_at=created,
            completed_at=completed,
        )

        assert len(result.level_breakdowns) == 4
        # Supreme Court atty fees should be the highest individual level
        sc_breakdown = result.level_breakdowns[3]
        assert sc_breakdown.level == "Supreme Court"
        assert sc_breakdown.attorney_fees_per_party_high > 300_000

    def test_no_escalation_single_level(self) -> None:
        """Empty escalation_decisions results in single level."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(minutes=1)

        result = est.estimate(
            final_judicial_level="Appeals Court",
            escalation_decisions=[],
            argument_rounds=1,
            created_at=created,
            completed_at=completed,
        )

        assert len(result.level_breakdowns) == 1
        assert result.level_breakdowns[0].level == "Appeals Court"

    def test_to_dict_roundtrip(self) -> None:
        """CostEstimate.to_dict() produces serializable dict."""
        est = self._make_estimator()
        created = datetime(2026, 1, 1, tzinfo=UTC)
        completed = created + timedelta(minutes=5)

        result = est.estimate(
            final_judicial_level="First Instance",
            escalation_decisions=[],
            argument_rounds=2,
            created_at=created,
            completed_at=completed,
        )

        d = result.to_dict()
        assert isinstance(d, dict)
        assert "level_breakdowns" in d
        assert "total_per_party_low" in d
        assert "savings_low" in d
        assert "ralphlex_processing_seconds" in d
