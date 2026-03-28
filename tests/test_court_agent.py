"""Tests for the CourtAgent with adversarial internal review."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import anthropic

from backend.agents.court import CourtAgent, _format_arguments
from backend.models.case import Argument, Case, CourtEvaluation
from backend.services.case_folder import CaseFolderManager

# --- Sample LLM responses for each phase ---

PHASE1_RESPONSE = json.dumps(
    {
        "consistency_analysis": {
            "claimant_score": 0.85,
            "respondent_score": 0.72,
            "claimant_issues": ["Minor timeline discrepancy between iterations"],
            "respondent_issues": [
                "Force majeure claim contradicts prior acknowledgment of delay",
                "Notification timeline is inconsistent",
            ],
        },
        "compliance_check": {
            "claimant_compliance": (
                "Claimant's arguments are consistent with Contract Act "
                "Section 73 and UCC Article 2 requirements"
            ),
            "respondent_compliance": (
                "Respondent's force majeure defense requires stricter "
                "documentation under UCC Section 2-615"
            ),
            "violations": ["Respondent failed to provide timely notice as required"],
        },
        "preliminary_opinion": (
            "Based on the evidence and legal analysis, the court finds "
            "that the claimant has established a prima facie case for "
            "breach of contract. The respondent's force majeure defense "
            "is weakened by inconsistent notification claims and "
            "insufficient documentation. The claimant is likely to "
            "prevail on the merits."
        ),
        "reasoning_trace": [
            "Reviewed claimant arguments for internal consistency",
            "Reviewed respondent arguments for internal consistency",
            "Assessed compliance with Contract Act and UCC provisions",
            "Weighed the strength of claimant's breach claim vs defense",
            "Concluded claimant has stronger position based on evidence",
        ],
    }
)

PHASE2_RESPONSE = json.dumps(
    {
        "adversarial_challenge": (
            "The preliminary opinion may overweight the claimant's "
            "position. The respondent's force majeure defense deserves "
            "more scrutiny — global supply chain disruptions in the "
            "relevant period are well-documented and courts have "
            "increasingly accepted broader force majeure interpretations. "
            "The notification inconsistency may be a factual dispute "
            "rather than a legal deficiency. Additionally, the "
            "preliminary opinion does not adequately address whether "
            "the claimant mitigated damages as required by law."
        ),
        "challenge_points": [
            "Force majeure interpretation may be too narrow",
            "Notification inconsistency is a factual dispute, not legal",
            "Claimant's duty to mitigate damages was not analyzed",
            "Recent precedent trends favor broader force majeure defenses",
        ],
    }
)

PHASE3_RESPONSE = json.dumps(
    {
        "reconciled_decision": (
            "After considering the adversarial challenge, the court "
            "maintains that the claimant has the stronger position but "
            "acknowledges the respondent's force majeure defense has "
            "more merit than initially assessed. The claimant's failure "
            "to demonstrate mitigation efforts is a valid concern that "
            "may affect damages. The court finds for the claimant on "
            "liability but recommends further proceedings on the "
            "damages question."
        ),
        "escalation_recommendation": "no_escalation",
        "escalation_reasoning": (
            "No constitutional questions are raised, precedents are "
            "not in conflict, and procedural requirements have been met. "
            "This case can be resolved at the current judicial level."
        ),
    }
)


# --- Helpers ---


def _make_mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic Messages response."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 500
    response.usage.output_tokens = 800
    response.model = "claude-sonnet-4-20250514"
    response.stop_reason = "end_turn"
    return response


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Create a mock client that returns a sequence of responses."""
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.create.side_effect = [_make_mock_response(text) for text in responses]
    return client


def _make_argument(
    role: str = "claimant",
    iteration: int = 0,
    content: str = "Default argument content for testing purposes",
) -> Argument:
    return Argument(
        role=role,
        iteration=iteration,
        content=content,
        legal_basis=["Contract Act Section 73"],
        factual_claims=["Delivery was due on Jan 1"],
        counterarguments=["Opponent's position is weak"],
        evidence_requests=["Delivery receipts"],
    )


# --- Format arguments tests ---


class TestFormatArguments:
    def test_formats_single_argument(self) -> None:
        arg = _make_argument(content="Test content")
        result = _format_arguments([arg])
        assert "Iteration 0 (claimant)" in result
        assert "Test content" in result
        assert "Contract Act Section 73" in result

    def test_formats_multiple_arguments(self) -> None:
        args = [
            _make_argument(iteration=0, content="First argument"),
            _make_argument(iteration=1, content="Second argument"),
        ]
        result = _format_arguments(args)
        assert "Iteration 0" in result
        assert "Iteration 1" in result
        assert "First argument" in result
        assert "Second argument" in result

    def test_empty_list(self) -> None:
        result = _format_arguments([])
        assert result == ""


# --- CourtAgent tests ---


class TestCourtAgent:
    async def test_evaluate_returns_court_evaluation(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        claimant_args = [_make_argument("claimant", 0, "Breach claim")]
        respondent_args = [
            _make_argument("respondent", 0, "Force majeure defense"),
        ]

        result = await agent.evaluate(
            case_facts="Contract dispute over delivery failure.",
            claimant_arguments=claimant_args,
            respondent_arguments=respondent_args,
        )

        assert isinstance(result, CourtEvaluation)

    async def test_consistency_scores_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert "claimant" in result.consistency_scores
        assert "respondent" in result.consistency_scores
        assert result.consistency_scores["claimant"] == 0.85
        assert result.consistency_scores["respondent"] == 0.72

    async def test_compliance_assessment_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert "claimant" in result.compliance_assessment
        assert "respondent" in result.compliance_assessment
        assert "violations" in result.compliance_assessment

    async def test_preliminary_opinion_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert len(result.preliminary_opinion) > 0
        assert "prima facie" in result.preliminary_opinion

    async def test_adversarial_challenge_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert len(result.adversarial_challenge) > 0
        assert "overweight" in result.adversarial_challenge

    async def test_adversarial_challenge_contains_challenges(self) -> None:
        """The adversarial review must contain actual challenges."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        # adversarial_review dict should have challenge points
        assert "challenge_points" in result.adversarial_review
        assert len(result.adversarial_review["challenge_points"]) > 0

    async def test_reconciled_decision_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert len(result.reconciled_decision) > 0
        assert "maintains" in result.reconciled_decision

    async def test_escalation_recommendation_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert result.escalation_recommendation == "no_escalation"

    async def test_reasoning_trace_populated(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert len(result.reasoning_trace) > 0

    async def test_three_llm_calls_made(self) -> None:
        """Verify exactly 3 LLM calls are made (one per phase)."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert client.messages.create.call_count == 3

    async def test_phase2_prompt_includes_preliminary_opinion(self) -> None:
        """Phase 2 prompt must reference the preliminary opinion."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        # Second call is phase 2
        phase2_call = client.messages.create.call_args_list[1]
        phase2_prompt = phase2_call.kwargs["messages"][-1]["content"]
        assert "Preliminary Opinion" in phase2_prompt
        assert "adversarial reviewer" in phase2_prompt.lower()

    async def test_phase3_prompt_includes_both_opinions(self) -> None:
        """Phase 3 prompt must include both preliminary and challenge."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        phase3_call = client.messages.create.call_args_list[2]
        phase3_prompt = phase3_call.kwargs["messages"][-1]["content"]
        assert "Preliminary Opinion" in phase3_prompt
        assert "Adversarial Challenge" in phase3_prompt
        assert "Reconcile" in phase3_prompt or "reconcile" in phase3_prompt

    async def test_precedents_included_in_phase1_prompt(self) -> None:
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
            precedents=["Hadley v Baxendale (1854)"],
            laws=["UCC Article 2"],
        )

        phase1_call = client.messages.create.call_args_list[0]
        phase1_prompt = phase1_call.kwargs["messages"][-1]["content"]
        assert "Hadley v Baxendale" in phase1_prompt
        assert "UCC Article 2" in phase1_prompt

    async def test_persists_to_case_folder(self, tmp_path: Path) -> None:
        """Evaluation output is saved to outputs/court_evaluation.json."""
        manager = CaseFolderManager(base_path=tmp_path)
        case = Case(id="court-test", title="Test", facts="Test facts")
        manager.create(case)

        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
            folder_manager=manager,
            case_id="court-test",
        )

        output_file = tmp_path / "court-test" / "outputs" / "court_evaluation.json"
        assert output_file.exists()

        data: dict[str, object] = json.loads(output_file.read_text())
        assert "consistency_scores" in data
        assert "compliance_assessment" in data
        assert "preliminary_opinion" in data
        assert "adversarial_challenge" in data
        assert "reconciled_decision" in data
        assert "escalation_recommendation" in data
        assert "reasoning_trace" in data

    async def test_no_persist_without_folder_manager(self) -> None:
        """No file I/O when folder_manager is not provided."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        # Should not raise
        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )
        assert isinstance(result, CourtEvaluation)

    async def test_all_sections_non_empty(self) -> None:
        """All required sections must be populated (not a simple summary)."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert len(result.consistency_scores) > 0
        assert len(result.compliance_assessment) > 0
        assert len(result.preliminary_opinion) > 0
        assert len(result.adversarial_challenge) > 0
        assert len(result.reconciled_decision) > 0
        assert result.escalation_recommendation is not None
        assert len(result.adversarial_review) > 0
        assert len(result.reasoning_trace) > 0


class TestCourtAgentEscalation:
    """Tests for escalation recommendation scenarios."""

    async def test_escalation_recommendation_value(self) -> None:
        """Escalation recommendation matches phase 3 response."""
        phase3_escalate = json.dumps(
            {
                "reconciled_decision": "Case requires higher court review.",
                "escalation_recommendation": "escalate_constitutional",
                "escalation_reasoning": ("Constitutional question regarding due process rights."),
            }
        )
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                phase3_escalate,
            ]
        )
        agent = CourtAgent(client=client)

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=[_make_argument("claimant")],
            respondent_arguments=[_make_argument("respondent")],
        )

        assert result.escalation_recommendation == "escalate_constitutional"
        assert result.escalation_decision == "escalate_constitutional"

    async def test_multiple_arguments_per_side(self) -> None:
        """Works correctly with multiple iteration arguments per side."""
        client = _make_mock_client(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
            ]
        )
        agent = CourtAgent(client=client)

        claimant_args = [
            _make_argument("claimant", 0, "Opening argument"),
            _make_argument("claimant", 1, "Follow-up argument"),
        ]
        respondent_args = [
            _make_argument("respondent", 0, "Opening defense"),
            _make_argument("respondent", 1, "Follow-up defense"),
        ]

        result = await agent.evaluate(
            case_facts="Facts",
            claimant_arguments=claimant_args,
            respondent_arguments=respondent_args,
        )

        assert isinstance(result, CourtEvaluation)

        # Verify all arguments were included in phase 1 prompt
        phase1_call = client.messages.create.call_args_list[0]
        phase1_prompt = phase1_call.kwargs["messages"][-1]["content"]
        assert "Opening argument" in phase1_prompt
        assert "Follow-up argument" in phase1_prompt
        assert "Opening defense" in phase1_prompt
        assert "Follow-up defense" in phase1_prompt
