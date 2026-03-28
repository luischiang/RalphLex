"""Tests for claimant/respondent agents, convergence detection, and argument loop."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import anthropic
import pytest

from backend.agents.claimant import ClaimantAgent
from backend.agents.respondent import RespondentAgent
from backend.models.case import Argument
from backend.services.argument_loop import ArgumentLoop, ArgumentLoopResult
from backend.services.case_folder import CaseFolderManager
from backend.services.convergence import (
    _list_similarity,
    _text_similarity,
    compute_argument_similarity,
    has_converged,
)

# --- Helpers ---

SAMPLE_ARGUMENT_JSON = json.dumps(
    {
        "content": "The defendant breached the contract by failing to deliver goods.",
        "legal_basis": ["Contract Act Section 73", "UCC Article 2"],
        "factual_claims": ["Delivery was due on Jan 1", "No goods were delivered"],
        "counterarguments": ["Defendant claims force majeure is inapplicable"],
        "evidence_requests": ["Delivery receipts", "Communication records"],
        "strategy_notes": ["Focus on documented timeline"],
    }
)

SAMPLE_ARGUMENT_JSON_2 = json.dumps(
    {
        "content": (
            "The defendant had valid reasons for delayed delivery due to supply chain issues."
        ),
        "legal_basis": ["Force Majeure Clause", "UCC Section 2-615"],
        "factual_claims": ["Supply chain disrupted globally", "Defendant notified claimant"],
        "counterarguments": ["Claimant's timeline is disputed"],
        "evidence_requests": ["Supply chain documentation", "Notification records"],
        "strategy_notes": ["Emphasize notification compliance"],
    }
)

# Similar to SAMPLE_ARGUMENT_JSON (for convergence testing)
SAMPLE_ARGUMENT_JSON_CONVERGED = json.dumps(
    {
        "content": "The defendant breached the contract by failing to deliver goods on time.",
        "legal_basis": ["Contract Act Section 73", "UCC Article 2"],
        "factual_claims": ["Delivery was due on Jan 1", "No goods were delivered"],
        "counterarguments": ["Defendant claims force majeure is inapplicable"],
        "evidence_requests": ["Delivery receipts", "Communication records"],
        "strategy_notes": ["Focus on documented timeline"],
    }
)


def _make_mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic Messages response."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 200
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
    content: str = "Default argument content",
    legal_basis: list[str] | None = None,
    factual_claims: list[str] | None = None,
    counterarguments: list[str] | None = None,
    evidence_requests: list[str] | None = None,
) -> Argument:
    return Argument(
        role=role,
        iteration=iteration,
        content=content,
        legal_basis=legal_basis or [],
        factual_claims=factual_claims or [],
        counterarguments=counterarguments or [],
        evidence_requests=evidence_requests or [],
    )


# --- Text similarity tests ---


class TestTextSimilarity:
    def test_identical_strings(self) -> None:
        assert _text_similarity("hello", "hello") == 1.0

    def test_empty_strings(self) -> None:
        assert _text_similarity("", "") == 1.0

    def test_one_empty(self) -> None:
        assert _text_similarity("hello", "") == 0.0
        assert _text_similarity("", "hello") == 0.0

    def test_similar_strings(self) -> None:
        sim = _text_similarity("The contract was breached", "The contract was broken")
        assert 0.5 < sim < 1.0

    def test_different_strings(self) -> None:
        sim = _text_similarity("hello world", "completely unrelated text here")
        assert sim < 0.5


# --- List similarity tests ---


class TestListSimilarity:
    def test_identical_lists(self) -> None:
        a = ["Contract Act", "UCC Article 2"]
        assert _list_similarity(a, a) == 1.0

    def test_empty_lists(self) -> None:
        assert _list_similarity([], []) == 1.0

    def test_one_empty(self) -> None:
        assert _list_similarity(["hello"], []) == 0.0

    def test_similar_lists(self) -> None:
        a = ["Contract Act Section 73", "UCC Article 2"]
        b = ["Contract Act Section 73", "UCC Article 2-615"]
        sim = _list_similarity(a, b)
        assert 0.5 < sim < 1.0

    def test_different_lists(self) -> None:
        a = ["Contract law principles", "Breach of duty"]
        b = ["Quantum mechanics theory", "Thermodynamics"]
        sim = _list_similarity(a, b)
        assert sim < 0.5


# --- Argument similarity tests ---


class TestArgumentSimilarity:
    def test_identical_arguments(self) -> None:
        arg = _make_argument(
            content="Breach of contract",
            legal_basis=["Section 73"],
            factual_claims=["Late delivery"],
        )
        sim = compute_argument_similarity(arg, arg)
        assert sim == 1.0

    def test_different_arguments(self) -> None:
        arg1 = _make_argument(
            content="Breach of contract by defendant",
            legal_basis=["Contract Act"],
            factual_claims=["Late delivery"],
        )
        arg2 = _make_argument(
            content="Force majeure defense is applicable",
            legal_basis=["Force Majeure Clause"],
            factual_claims=["Supply chain disruption"],
        )
        sim = compute_argument_similarity(arg1, arg2)
        assert sim < 0.5

    def test_slightly_different_arguments(self) -> None:
        arg1 = _make_argument(
            content="The defendant breached the contract by failing to deliver goods.",
            legal_basis=["Contract Act Section 73", "UCC Article 2"],
            factual_claims=["Delivery was due on Jan 1", "No goods were delivered"],
        )
        arg2 = _make_argument(
            content="The defendant breached the contract by failing to deliver goods on time.",
            legal_basis=["Contract Act Section 73", "UCC Article 2"],
            factual_claims=["Delivery was due on Jan 1", "No goods were delivered"],
        )
        sim = compute_argument_similarity(arg1, arg2)
        assert sim > 0.85


# --- Convergence detection tests ---


class TestConvergence:
    def test_converged_when_similar(self) -> None:
        arg1 = _make_argument(
            content="Breach of contract occurred",
            legal_basis=["Section 73"],
            factual_claims=["Late delivery"],
            counterarguments=["Force majeure invalid"],
            evidence_requests=["Delivery logs"],
        )
        arg2 = _make_argument(
            content="Breach of contract occurred",
            legal_basis=["Section 73"],
            factual_claims=["Late delivery"],
            counterarguments=["Force majeure invalid"],
            evidence_requests=["Delivery logs"],
        )
        assert has_converged(arg1, arg2) is True

    def test_not_converged_when_different(self) -> None:
        arg1 = _make_argument(content="Position A", legal_basis=["Law A"])
        arg2 = _make_argument(content="Completely different position B", legal_basis=["Law B"])
        assert has_converged(arg1, arg2) is False

    def test_custom_threshold(self) -> None:
        arg1 = _make_argument(content="Some argument text here")
        arg2 = _make_argument(content="Some argument text here modified")
        # With a very low threshold, should converge
        assert has_converged(arg1, arg2, threshold=0.3) is True


# --- ClaimantAgent tests ---


class TestClaimantAgent:
    async def test_generate_opening_argument(self) -> None:
        client = _make_mock_client([SAMPLE_ARGUMENT_JSON])
        agent = ClaimantAgent(client=client)

        arg = await agent.generate_argument(
            case_facts="Defendant failed to deliver goods.",
            iteration=0,
        )

        assert isinstance(arg, Argument)
        assert arg.role == "claimant"
        assert arg.iteration == 0
        assert len(arg.content) > 0
        assert len(arg.legal_basis) > 0

    async def test_generate_response_to_opponent(self) -> None:
        client = _make_mock_client([SAMPLE_ARGUMENT_JSON])
        agent = ClaimantAgent(client=client)

        opponent = _make_argument(
            role="respondent",
            iteration=0,
            content="We had force majeure.",
            legal_basis=["Force Majeure Clause"],
        )

        arg = await agent.generate_argument(
            case_facts="Defendant failed to deliver goods.",
            iteration=1,
            opponent_argument=opponent,
        )

        assert arg.role == "claimant"
        assert arg.iteration == 1
        # Verify the prompt included opponent info
        call_kwargs = client.messages.create.call_args
        sent_prompt = call_kwargs.kwargs["messages"][-1]["content"]
        assert "Respondent's Argument" in sent_prompt
        assert "force majeure" in sent_prompt.lower()

    async def test_structured_output_fields(self) -> None:
        client = _make_mock_client([SAMPLE_ARGUMENT_JSON])
        agent = ClaimantAgent(client=client)

        arg = await agent.generate_argument(case_facts="Test facts", iteration=0)

        assert isinstance(arg.legal_basis, list)
        assert isinstance(arg.factual_claims, list)
        assert isinstance(arg.counterarguments, list)
        assert isinstance(arg.evidence_requests, list)
        assert isinstance(arg.strategy_notes, list)


# --- RespondentAgent tests ---


class TestRespondentAgent:
    async def test_generate_opening_defense(self) -> None:
        client = _make_mock_client([SAMPLE_ARGUMENT_JSON_2])
        agent = RespondentAgent(client=client)

        arg = await agent.generate_argument(
            case_facts="Defendant failed to deliver goods.",
            iteration=0,
        )

        assert isinstance(arg, Argument)
        assert arg.role == "respondent"
        assert arg.iteration == 0

    async def test_generate_response_to_claimant(self) -> None:
        client = _make_mock_client([SAMPLE_ARGUMENT_JSON_2])
        agent = RespondentAgent(client=client)

        opponent = _make_argument(
            role="claimant",
            iteration=0,
            content="Contract was breached.",
            legal_basis=["Contract Act"],
        )

        arg = await agent.generate_argument(
            case_facts="Defendant failed to deliver goods.",
            iteration=1,
            opponent_argument=opponent,
        )

        assert arg.role == "respondent"
        assert arg.iteration == 1
        call_kwargs = client.messages.create.call_args
        sent_prompt = call_kwargs.kwargs["messages"][-1]["content"]
        assert "Claimant's Argument" in sent_prompt


# --- ArgumentLoop tests ---


class TestArgumentLoop:
    @pytest.fixture
    def folder_manager(self, tmp_path: Path) -> CaseFolderManager:
        from backend.models.case import Case

        manager = CaseFolderManager(base_path=tmp_path)
        case = Case(id="test-case", title="Test", facts="Test facts")
        manager.create(case)
        return manager

    async def test_runs_iterations_and_persists(self, folder_manager: CaseFolderManager) -> None:
        """Verifies iterations run, arguments are persisted to case folder."""
        # 2 iterations = 4 LLM calls (claimant + respondent per iteration)
        responses = [
            SAMPLE_ARGUMENT_JSON,
            SAMPLE_ARGUMENT_JSON_2,
            SAMPLE_ARGUMENT_JSON,
            SAMPLE_ARGUMENT_JSON_2,
        ]
        claimant_client = _make_mock_client(responses[:2])
        respondent_client = _make_mock_client(responses[2:])

        loop = ArgumentLoop(
            claimant_agent=ClaimantAgent(client=claimant_client),
            respondent_agent=RespondentAgent(client=respondent_client),
            folder_manager=folder_manager,
            max_iterations=2,
        )

        result = await loop.run("test-case", "Contract dispute facts")

        assert isinstance(result, ArgumentLoopResult)
        assert result.iterations_completed == 2
        assert len(result.claimant_arguments) == 2
        assert len(result.respondent_arguments) == 2

        # Verify iteration files were saved
        iter_dir = folder_manager.case_dir("test-case") / "iterations"
        assert (iter_dir / "round_0_claimant.json").exists()
        assert (iter_dir / "round_0_respondent.json").exists()
        assert (iter_dir / "round_1_claimant.json").exists()
        assert (iter_dir / "round_1_respondent.json").exists()

    async def test_arguments_follow_schema(self, folder_manager: CaseFolderManager) -> None:
        """All generated arguments have the required fields."""
        responses = [SAMPLE_ARGUMENT_JSON, SAMPLE_ARGUMENT_JSON_2]
        claimant_client = _make_mock_client([responses[0]])
        respondent_client = _make_mock_client([responses[1]])

        loop = ArgumentLoop(
            claimant_agent=ClaimantAgent(client=claimant_client),
            respondent_agent=RespondentAgent(client=respondent_client),
            folder_manager=folder_manager,
            max_iterations=1,
        )

        result = await loop.run("test-case", "Facts")

        for arg in result.claimant_arguments + result.respondent_arguments:
            assert isinstance(arg, Argument)
            assert arg.content
            assert isinstance(arg.legal_basis, list)
            assert isinstance(arg.factual_claims, list)
            assert isinstance(arg.counterarguments, list)
            assert isinstance(arg.evidence_requests, list)
            assert isinstance(arg.strategy_notes, list)

    async def test_convergence_stops_loop(self, folder_manager: CaseFolderManager) -> None:
        """Loop stops early when both sides converge."""
        # Provide 3 rounds of responses but convergence should trigger after round 2
        # Round 0: different arguments, Round 1: same arguments as round 0 -> converge
        responses_claimant = [
            SAMPLE_ARGUMENT_JSON,
            SAMPLE_ARGUMENT_JSON_CONVERGED,  # very similar to round 0
            SAMPLE_ARGUMENT_JSON,  # should not be reached
        ]
        responses_respondent = [
            SAMPLE_ARGUMENT_JSON_2,
            SAMPLE_ARGUMENT_JSON_2,  # identical to round 0 -> converged
            SAMPLE_ARGUMENT_JSON_2,  # should not be reached
        ]

        claimant_client = _make_mock_client(responses_claimant)
        respondent_client = _make_mock_client(responses_respondent)

        loop = ArgumentLoop(
            claimant_agent=ClaimantAgent(client=claimant_client),
            respondent_agent=RespondentAgent(client=respondent_client),
            folder_manager=folder_manager,
            max_iterations=5,
            convergence_threshold=0.85,
        )

        result = await loop.run("test-case", "Facts")

        assert result.claimant_converged is True
        assert result.respondent_converged is True
        assert result.iterations_completed == 2  # stopped at iteration 2, not 5

    async def test_max_iterations_respected(self, folder_manager: CaseFolderManager) -> None:
        """Loop doesn't exceed max_iterations even without convergence."""
        # Very different arguments each time — no convergence
        diff_arg_1 = json.dumps(
            {
                "content": "Argument version A",
                "legal_basis": ["Law A"],
                "factual_claims": ["Fact A"],
                "counterarguments": ["Counter A"],
                "evidence_requests": ["Evidence A"],
                "strategy_notes": ["Strategy A"],
            }
        )
        diff_arg_2 = json.dumps(
            {
                "content": "Completely different argument B",
                "legal_basis": ["Law B"],
                "factual_claims": ["Fact B"],
                "counterarguments": ["Counter B"],
                "evidence_requests": ["Evidence B"],
                "strategy_notes": ["Strategy B"],
            }
        )
        diff_arg_3 = json.dumps(
            {
                "content": "Yet another argument C",
                "legal_basis": ["Law C"],
                "factual_claims": ["Fact C"],
                "counterarguments": ["Counter C"],
                "evidence_requests": ["Evidence C"],
                "strategy_notes": ["Strategy C"],
            }
        )

        claimant_client = _make_mock_client([diff_arg_1, diff_arg_2, diff_arg_3])
        respondent_client = _make_mock_client([diff_arg_2, diff_arg_3, diff_arg_1])

        loop = ArgumentLoop(
            claimant_agent=ClaimantAgent(client=claimant_client),
            respondent_agent=RespondentAgent(client=respondent_client),
            folder_manager=folder_manager,
            max_iterations=3,
        )

        result = await loop.run("test-case", "Facts")

        assert result.iterations_completed == 3
        assert not (result.claimant_converged and result.respondent_converged)

    async def test_persisted_iteration_content(self, folder_manager: CaseFolderManager) -> None:
        """Verify the persisted iteration files contain correct data."""
        claimant_client = _make_mock_client([SAMPLE_ARGUMENT_JSON])
        respondent_client = _make_mock_client([SAMPLE_ARGUMENT_JSON_2])

        loop = ArgumentLoop(
            claimant_agent=ClaimantAgent(client=claimant_client),
            respondent_agent=RespondentAgent(client=respondent_client),
            folder_manager=folder_manager,
            max_iterations=1,
        )

        await loop.run("test-case", "Facts")

        # Load and verify persisted iteration data
        claimant_data = folder_manager.load_iteration("test-case", 0, "claimant")
        assert claimant_data["role"] == "claimant"
        assert claimant_data["iteration"] == 0
        assert "content" in claimant_data

        respondent_data = folder_manager.load_iteration("test-case", 0, "respondent")
        assert respondent_data["role"] == "respondent"
        assert respondent_data["iteration"] == 0
