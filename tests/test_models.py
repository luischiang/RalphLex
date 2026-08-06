import pytest
from pydantic import ValidationError

from backend.models.argument import Argument, Role
from backend.models.case import Case, CaseStatus, JudicialLevel
from backend.models.evaluation import (
    AdversarialReview,
    ComplianceAssessment,
    ConsistencyScore,
    CourtEvaluation,
    EscalationDecision,
)
from backend.models.mcda import CriterionScore, MCDAResult


def test_case_defaults():
    case = Case(title="Breach of Contract", facts="Party A failed to deliver goods.")
    assert case.id
    assert case.status == CaseStatus.PENDING
    assert case.judicial_level == JudicialLevel.FIRST_INSTANCE
    assert case.claimant_input is None
    assert case.created_at == case.updated_at or case.created_at <= case.updated_at


def test_case_requires_title_and_facts():
    with pytest.raises(ValidationError):
        Case(facts="missing title")


def test_argument_defaults_and_role():
    arg = Argument(role=Role.CLAIMANT, iteration=0, content="Initial position")
    assert arg.role == Role.CLAIMANT
    assert arg.legal_basis == []
    assert arg.timestamp is not None


def test_argument_iteration_must_be_non_negative():
    with pytest.raises(ValidationError):
        Argument(role=Role.RESPONDENT, iteration=-1, content="bad")


def test_court_evaluation_composition():
    evaluation = CourtEvaluation(
        case_id="case-1",
        consistency_scores=[
            ConsistencyScore(role=Role.CLAIMANT, score=0.8),
            ConsistencyScore(role=Role.RESPONDENT, score=0.6),
        ],
        compliance_assessment=ComplianceAssessment(compliant=True),
        adversarial_review=AdversarialReview(
            preliminary_opinion="A",
            counter_opinion="B",
            reconciled_opinion="C",
        ),
        escalation_decision=EscalationDecision(should_escalate=False),
        reasoning_trace=["step 1", "step 2"],
    )
    assert len(evaluation.consistency_scores) == 2
    assert evaluation.escalation_decision.target_level is None


def test_mcda_result_computation_inputs():
    result = MCDAResult(
        case_id="case-1",
        criteria_scores=[
            CriterionScore(
                criterion="evidentiary_strength", claimant_score=8, respondent_score=5, weight=0.3
            )
        ],
        weighted_totals={Role.CLAIMANT: 0.7, Role.RESPONDENT: 0.3},
        predicted_winner=Role.CLAIMANT,
        confidence=0.65,
    )
    assert result.predicted_winner == Role.CLAIMANT
    assert result.weighted_totals[Role.CLAIMANT] == 0.7


def test_mcda_criterion_score_bounds():
    with pytest.raises(ValidationError):
        CriterionScore(criterion="x", claimant_score=11, respondent_score=5, weight=0.2)
