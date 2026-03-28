"""Tests for RalphLex data models."""

import pytest
from pydantic import ValidationError

from backend.models.case import (
    Argument,
    Case,
    CaseStatus,
    CourtEvaluation,
    JudicialLevel,
    MCDAResult,
)


class TestCase:
    def test_create_case_defaults(self):
        case = Case(title="Test Case", facts="Some facts")
        assert case.title == "Test Case"
        assert case.facts == "Some facts"
        assert case.status == CaseStatus.pending
        assert case.judicial_level == JudicialLevel.first_instance
        assert case.id  # UUID is generated
        assert case.created_at
        assert case.updated_at

    def test_case_with_all_fields(self):
        case = Case(
            title="Full Case",
            facts="Facts here",
            claimant_input="Claimant says...",
            respondent_input="Respondent says...",
            status=CaseStatus.running,
            judicial_level=JudicialLevel.appeals,
        )
        assert case.status == CaseStatus.running
        assert case.judicial_level == JudicialLevel.appeals
        assert case.claimant_input == "Claimant says..."

    def test_case_serialization_roundtrip(self):
        case = Case(title="Roundtrip", facts="Facts")
        json_str = case.model_dump_json()
        loaded = Case.model_validate_json(json_str)
        assert loaded.id == case.id
        assert loaded.title == case.title
        assert loaded.status == case.status

    def test_case_status_enum(self):
        for status in CaseStatus:
            case = Case(title="T", facts="F", status=status)
            assert case.status == status

    def test_judicial_level_enum(self):
        for level in JudicialLevel:
            case = Case(title="T", facts="F", judicial_level=level)
            assert case.judicial_level == level


class TestArgument:
    def test_create_argument(self):
        arg = Argument(role="claimant", iteration=0, content="Opening argument")
        assert arg.role == "claimant"
        assert arg.iteration == 0
        assert arg.content == "Opening argument"
        assert arg.legal_basis == []
        assert arg.timestamp

    def test_argument_with_all_fields(self):
        arg = Argument(
            role="respondent",
            iteration=2,
            content="Counter-argument",
            legal_basis=["Article 42"],
            factual_claims=["Claim A"],
            counterarguments=["Rebuttal B"],
            evidence_requests=["Request C"],
            references=["Ref D"],
        )
        assert arg.legal_basis == ["Article 42"]
        assert arg.factual_claims == ["Claim A"]

    def test_argument_negative_iteration_rejected(self):
        with pytest.raises(ValidationError):
            Argument(role="claimant", iteration=-1, content="Bad")


class TestCourtEvaluation:
    def test_create_empty(self):
        ev = CourtEvaluation()
        assert ev.consistency_scores == {}
        assert ev.compliance_assessment == {}
        assert ev.adversarial_review == {}
        assert ev.escalation_decision is None
        assert ev.reasoning_trace == []

    def test_create_with_data(self):
        ev = CourtEvaluation(
            consistency_scores={"claimant": 0.85, "respondent": 0.72},
            compliance_assessment={"tax_law": "compliant"},
            adversarial_review={"challenge": "Weak evidence on point 3"},
            escalation_decision="no_escalation",
            reasoning_trace=["Step 1", "Step 2"],
        )
        assert ev.consistency_scores["claimant"] == 0.85
        assert ev.escalation_decision == "no_escalation"


class TestMCDAResult:
    def test_create_empty(self):
        r = MCDAResult()
        assert r.criteria_scores == {}
        assert r.weighted_totals == {}
        assert r.predicted_winner is None
        assert r.confidence == 0.0

    def test_create_with_data(self):
        r = MCDAResult(
            criteria_scores={
                "evidentiary_strength": {"claimant": 8.0, "respondent": 6.0},
            },
            weighted_totals={"claimant": 0.75, "respondent": 0.55},
            predicted_winner="claimant",
            confidence=0.82,
        )
        assert r.predicted_winner == "claimant"
        assert r.confidence == 0.82

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            MCDAResult(confidence=1.5)
        with pytest.raises(ValidationError):
            MCDAResult(confidence=-0.1)
