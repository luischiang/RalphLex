"""Tests for MCDA scoring module."""

import json
from pathlib import Path

from backend.evaluation.mcda import (
    CRITERIA,
    compute_criteria_agreement,
    compute_weighted_scores,
    determine_winner,
    evaluate_mcda,
    load_weights,
)
from backend.models.case import Case, MCDAResult
from backend.services.case_folder import CaseFolderManager


class TestLoadWeights:
    def test_loads_default_weights(self) -> None:
        weights = load_weights()
        assert len(weights) == 5
        for criterion in CRITERIA:
            assert criterion in weights

    def test_weights_sum_approximately_to_one(self) -> None:
        weights = load_weights()
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_all_weights_positive(self) -> None:
        weights = load_weights()
        for w in weights.values():
            assert w > 0

    def test_loads_custom_weights(self, tmp_path: Path) -> None:
        custom = {"evidentiary_strength": 0.5, "legal_consistency": 0.5}
        weights_file = tmp_path / "custom_weights.json"
        weights_file.write_text(json.dumps(custom))

        result = load_weights(weights_file)
        assert result["evidentiary_strength"] == 0.5
        assert result["legal_consistency"] == 0.5


class TestComputeWeightedScores:
    def test_basic_computation(self) -> None:
        criteria_scores = {
            "evidentiary_strength": {"claimant": 8.0, "respondent": 6.0},
            "legal_consistency": {"claimant": 7.0, "respondent": 9.0},
        }
        weights = {
            "evidentiary_strength": 0.5,
            "legal_consistency": 0.5,
        }
        totals = compute_weighted_scores(criteria_scores, weights)

        assert "claimant" in totals
        assert "respondent" in totals
        # claimant: 0.5*(7/9) + 0.5*(6/9) = 0.5*0.778 + 0.5*0.667 = 0.722
        # respondent: 0.5*(5/9) + 0.5*(8/9) = 0.5*0.556 + 0.5*0.889 = 0.722
        assert 0 <= totals["claimant"] <= 1
        assert 0 <= totals["respondent"] <= 1

    def test_equal_scores_equal_totals(self) -> None:
        criteria_scores = {
            "evidentiary_strength": {"claimant": 5.0, "respondent": 5.0},
            "legal_consistency": {"claimant": 5.0, "respondent": 5.0},
        }
        weights = {
            "evidentiary_strength": 0.5,
            "legal_consistency": 0.5,
        }
        totals = compute_weighted_scores(criteria_scores, weights)
        assert abs(totals["claimant"] - totals["respondent"]) < 0.001

    def test_minimum_score(self) -> None:
        """Score of 1 should normalize to 0."""
        criteria_scores = {
            "evidentiary_strength": {"claimant": 1.0, "respondent": 1.0},
        }
        weights = {"evidentiary_strength": 1.0}
        totals = compute_weighted_scores(criteria_scores, weights)
        assert totals["claimant"] == 0.0
        assert totals["respondent"] == 0.0

    def test_maximum_score(self) -> None:
        """Score of 10 should normalize to weight value."""
        criteria_scores = {
            "evidentiary_strength": {"claimant": 10.0, "respondent": 10.0},
        }
        weights = {"evidentiary_strength": 1.0}
        totals = compute_weighted_scores(criteria_scores, weights)
        assert abs(totals["claimant"] - 1.0) < 0.001
        assert abs(totals["respondent"] - 1.0) < 0.001

    def test_missing_weight_treated_as_zero(self) -> None:
        criteria_scores = {
            "unknown_criterion": {"claimant": 10.0, "respondent": 1.0},
        }
        weights = {"evidentiary_strength": 1.0}
        totals = compute_weighted_scores(criteria_scores, weights)
        assert totals["claimant"] == 0.0
        assert totals["respondent"] == 0.0

    def test_empty_scores(self) -> None:
        totals = compute_weighted_scores({}, {"evidentiary_strength": 1.0})
        assert totals == {}


class TestDetermineWinner:
    def test_higher_score_wins(self) -> None:
        winner, confidence = determine_winner({"claimant": 0.8, "respondent": 0.3})
        assert winner == "claimant"
        assert confidence > 0.5

    def test_close_scores_low_confidence(self) -> None:
        winner, confidence = determine_winner({"claimant": 0.51, "respondent": 0.49})
        assert winner == "claimant"
        # Small differential should give lower confidence
        assert confidence < 0.7

    def test_large_gap_high_confidence(self) -> None:
        winner, confidence = determine_winner({"claimant": 0.95, "respondent": 0.05})
        assert winner == "claimant"
        assert confidence > 0.8

    def test_equal_scores(self) -> None:
        winner, confidence = determine_winner({"claimant": 0.5, "respondent": 0.5})
        assert winner is not None
        assert confidence == 0.5

    def test_empty_totals(self) -> None:
        winner, confidence = determine_winner({})
        assert winner is None
        assert confidence == 0.0

    def test_single_party(self) -> None:
        winner, confidence = determine_winner({"claimant": 0.7})
        assert winner == "claimant"
        assert confidence == 1.0


class TestComputeCriteriaAgreement:
    def test_full_agreement(self) -> None:
        scores = {
            "c1": {"claimant": 8.0, "respondent": 3.0},
            "c2": {"claimant": 7.0, "respondent": 4.0},
            "c3": {"claimant": 9.0, "respondent": 2.0},
        }
        agreement = compute_criteria_agreement(scores)
        assert agreement == 1.0

    def test_no_agreement(self) -> None:
        scores = {
            "c1": {"claimant": 8.0, "respondent": 3.0},
            "c2": {"claimant": 3.0, "respondent": 8.0},
        }
        agreement = compute_criteria_agreement(scores)
        assert agreement == 0.5

    def test_partial_agreement(self) -> None:
        scores = {
            "c1": {"claimant": 8.0, "respondent": 3.0},
            "c2": {"claimant": 7.0, "respondent": 4.0},
            "c3": {"claimant": 2.0, "respondent": 9.0},
        }
        agreement = compute_criteria_agreement(scores)
        # 2 out of 3 favor claimant
        assert abs(agreement - 2.0 / 3.0) < 0.01

    def test_empty_scores(self) -> None:
        assert compute_criteria_agreement({}) == 0.0


class TestEvaluateMcda:
    def test_returns_mcda_result(self) -> None:
        scores = {
            "evidentiary_strength": {"claimant": 8.0, "respondent": 5.0},
            "legal_consistency": {"claimant": 7.0, "respondent": 6.0},
            "procedural_validity": {"claimant": 6.0, "respondent": 7.0},
            "precedent_alignment": {"claimant": 8.0, "respondent": 4.0},
            "appeal_likelihood": {"claimant": 5.0, "respondent": 6.0},
        }
        result = evaluate_mcda(scores)

        assert isinstance(result, MCDAResult)
        assert result.predicted_winner in ("claimant", "respondent")
        assert 0.0 <= result.confidence <= 1.0
        assert "claimant" in result.weighted_totals
        assert "respondent" in result.weighted_totals

    def test_custom_weights(self) -> None:
        scores = {
            "evidentiary_strength": {"claimant": 10.0, "respondent": 1.0},
        }
        weights = {"evidentiary_strength": 1.0}
        result = evaluate_mcda(scores, weights=weights)
        assert result.predicted_winner == "claimant"

    def test_persists_to_case_folder(self, tmp_path: Path) -> None:
        manager = CaseFolderManager(base_path=tmp_path)
        case = Case(id="mcda-test", title="Test", facts="Facts")
        manager.create(case)

        scores = {
            "evidentiary_strength": {"claimant": 7.0, "respondent": 5.0},
            "legal_consistency": {"claimant": 6.0, "respondent": 8.0},
            "procedural_validity": {"claimant": 7.0, "respondent": 6.0},
            "precedent_alignment": {"claimant": 8.0, "respondent": 5.0},
            "appeal_likelihood": {"claimant": 5.0, "respondent": 6.0},
        }
        evaluate_mcda(scores, folder_manager=manager, case_id="mcda-test")

        output_file = tmp_path / "mcda-test" / "outputs" / "mcda_scoring.json"
        assert output_file.exists()

        data: dict[str, object] = json.loads(output_file.read_text())
        assert "criteria_scores" in data
        assert "weighted_totals" in data
        assert "predicted_winner" in data
        assert "confidence" in data

    def test_no_persist_without_folder_manager(self) -> None:
        scores = {
            "evidentiary_strength": {"claimant": 7.0, "respondent": 5.0},
        }
        weights = {"evidentiary_strength": 1.0}
        result = evaluate_mcda(scores, weights=weights)
        assert isinstance(result, MCDAResult)

    def test_confidence_with_full_agreement(self) -> None:
        """Full criteria agreement should not reduce confidence."""
        scores = {
            "evidentiary_strength": {"claimant": 10.0, "respondent": 1.0},
            "legal_consistency": {"claimant": 10.0, "respondent": 1.0},
            "procedural_validity": {"claimant": 10.0, "respondent": 1.0},
            "precedent_alignment": {"claimant": 10.0, "respondent": 1.0},
            "appeal_likelihood": {"claimant": 10.0, "respondent": 1.0},
        }
        result = evaluate_mcda(scores)
        # Full agreement + max differential = high confidence
        assert result.confidence > 0.8

    def test_confidence_with_disagreement(self) -> None:
        """Mixed criteria agreement should reduce confidence."""
        scores = {
            "evidentiary_strength": {"claimant": 8.0, "respondent": 3.0},
            "legal_consistency": {"claimant": 3.0, "respondent": 8.0},
            "procedural_validity": {"claimant": 8.0, "respondent": 3.0},
            "precedent_alignment": {"claimant": 3.0, "respondent": 8.0},
            "appeal_likelihood": {"claimant": 5.0, "respondent": 5.0},
        }
        result = evaluate_mcda(scores)
        # Mixed agreement should lower confidence
        assert result.confidence < 0.7
