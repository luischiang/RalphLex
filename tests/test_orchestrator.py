"""Tests for the CaseOrchestrator and orchestration API endpoints."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from backend.agents.claimant import ClaimantAgent
from backend.agents.court import CourtAgent
from backend.agents.respondent import RespondentAgent
from backend.models.case import Argument, Case, CaseStatus
from backend.orchestrator import (
    CaseOrchestrator,
    OrchestratorProgress,
    OrchestratorResult,
    _progress,
    _summarize_arguments,
    _update_progress,
    get_progress,
)
from backend.services.case_folder import CaseFolderManager

# --- Low/high confidence MCDA responses for refinement tests ---

# Scores very close => low confidence
PHASE4_LOW_CONFIDENCE = json.dumps(
    {
        "ratings": {
            "evidentiary_strength": {"claimant": 5, "respondent": 5},
            "legal_consistency": {"claimant": 6, "respondent": 5},
            "procedural_validity": {"claimant": 5, "respondent": 5},
            "precedent_alignment": {"claimant": 5, "respondent": 5},
            "appeal_likelihood": {"claimant": 5, "respondent": 6},
        },
        "rating_justification": "Parties are very close.",
    }
)

# Scores with clear differentiation => high confidence
PHASE4_HIGH_CONFIDENCE = json.dumps(
    {
        "ratings": {
            "evidentiary_strength": {"claimant": 9, "respondent": 3},
            "legal_consistency": {"claimant": 9, "respondent": 3},
            "procedural_validity": {"claimant": 9, "respondent": 3},
            "precedent_alignment": {"claimant": 9, "respondent": 3},
            "appeal_likelihood": {"claimant": 9, "respondent": 3},
        },
        "rating_justification": "Claimant clearly stronger after refinement.",
    }
)

# Medium confidence (still below 0.80)
PHASE4_MEDIUM_CONFIDENCE = json.dumps(
    {
        "ratings": {
            "evidentiary_strength": {"claimant": 7, "respondent": 5},
            "legal_consistency": {"claimant": 6, "respondent": 5},
            "procedural_validity": {"claimant": 6, "respondent": 5},
            "precedent_alignment": {"claimant": 6, "respondent": 5},
            "appeal_likelihood": {"claimant": 5, "respondent": 6},
        },
        "rating_justification": "Claimant slightly stronger.",
    }
)

# --- Mock LLM responses ---

CLAIMANT_RESPONSE = json.dumps(
    {
        "content": "The defendant breached the contract by failing to deliver goods.",
        "legal_basis": ["Contract Act Section 73", "UCC Article 2"],
        "factual_claims": ["Delivery was due on Jan 1", "No goods were delivered"],
        "counterarguments": ["Defendant claims force majeure is inapplicable"],
        "evidence_requests": ["Delivery receipts"],
        "strategy_notes": ["Focus on timeline"],
    }
)

RESPONDENT_RESPONSE = json.dumps(
    {
        "content": "The defendant had valid reasons for delayed delivery.",
        "legal_basis": ["Force Majeure Clause"],
        "factual_claims": ["Supply chain disrupted globally"],
        "counterarguments": ["Claimant's timeline is disputed"],
        "evidence_requests": ["Supply chain documentation"],
        "strategy_notes": ["Emphasize notification compliance"],
    }
)

PHASE1_RESPONSE = json.dumps(
    {
        "consistency_analysis": {
            "claimant_score": 0.85,
            "respondent_score": 0.72,
            "claimant_issues": ["Minor timeline discrepancy"],
            "respondent_issues": ["Notification timeline inconsistent"],
        },
        "compliance_check": {
            "claimant_compliance": "Compliant with Contract Act",
            "respondent_compliance": "Requires stricter documentation",
            "violations": ["Late notice"],
        },
        "preliminary_opinion": "Claimant has stronger position.",
        "reasoning_trace": [
            "Reviewed claimant consistency",
            "Reviewed respondent consistency",
            "Weighed evidence",
        ],
    }
)

PHASE2_RESPONSE = json.dumps(
    {
        "adversarial_challenge": ("The preliminary opinion may overweight claimant's position."),
        "challenge_points": [
            "Force majeure interpretation too narrow",
            "Mitigation duty not analyzed",
        ],
    }
)

PHASE3_RESPONSE = json.dumps(
    {
        "reconciled_decision": (
            "Court finds for claimant on liability but acknowledges respondent's defense has merit."
        ),
        "escalation_recommendation": "no_escalation",
        "escalation_reasoning": "No grounds for escalation.",
    }
)

PHASE4_RESPONSE = json.dumps(
    {
        "ratings": {
            "evidentiary_strength": {"claimant": 7, "respondent": 5},
            "legal_consistency": {"claimant": 8, "respondent": 6},
            "procedural_validity": {"claimant": 7, "respondent": 7},
            "precedent_alignment": {"claimant": 7, "respondent": 5},
            "appeal_likelihood": {"claimant": 4, "respondent": 6},
        },
        "rating_justification": "Claimant stronger overall.",
    }
)


# --- Helpers ---


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
) -> Argument:
    return Argument(
        role=role,
        iteration=iteration,
        content=content,
        legal_basis=["Contract Act Section 73"],
        factual_claims=["Delivery was due on Jan 1"],
        counterarguments=["Opponent's position is weak"],
        evidence_requests=["Delivery receipts"],
        strategy_notes=["Focus on timeline"],
    )


def _create_test_case(folder_manager: CaseFolderManager) -> Case:
    """Create and persist a test case."""
    case = Case(
        title="Contract Breach Dispute",
        facts="Defendant failed to deliver goods as per the contract.",
    )
    folder_manager.create(case)
    return case


def _build_all_responses(iterations: int = 1) -> list[str]:
    """Build the full sequence of mock LLM responses.

    For each iteration: 1 claimant + 1 respondent response.
    After convergence (or max_iterations): 4 court phases.
    Includes extra high-confidence refinement rounds to satisfy the
    confidence threshold refinement loop (default PHASE4_RESPONSE
    produces confidence below 0.80).
    """
    responses: list[str] = []
    for _ in range(iterations):
        responses.append(CLAIMANT_RESPONSE)
        responses.append(RESPONDENT_RESPONSE)
    # Court evaluation: 4 phases (initial — may trigger refinement)
    responses.extend([PHASE1_RESPONSE, PHASE2_RESPONSE, PHASE3_RESPONSE, PHASE4_RESPONSE])
    # Add refinement rounds with high-confidence scores to exit loop
    for _ in range(3):
        responses.extend(
            [
                PHASE1_RESPONSE,
                PHASE2_RESPONSE,
                PHASE3_RESPONSE,
                PHASE4_HIGH_CONFIDENCE,
            ]
        )
    return responses


# --- OrchestratorProgress tests ---


class TestOrchestratorProgress:
    def test_default_progress(self) -> None:
        prog = OrchestratorProgress()
        assert prog.phase == "pending"
        assert prog.iteration == 0
        assert prog.message == ""

    def test_update_progress(self) -> None:
        case_id = "test-progress-1"
        _progress.pop(case_id, None)

        _update_progress(case_id, "arguing", "Running argument loop")
        prog = get_progress(case_id)
        assert prog is not None
        assert prog.phase == "arguing"
        assert prog.message == "Running argument loop"
        assert prog.updated_at != ""

        _progress.pop(case_id, None)

    def test_get_progress_missing(self) -> None:
        assert get_progress("nonexistent-case") is None

    def test_update_progress_with_kwargs(self) -> None:
        case_id = "test-progress-2"
        _progress.pop(case_id, None)

        _update_progress(
            case_id,
            "evaluating",
            "Court evaluation",
            judicial_level="Appeals Court",
            iteration=3,
        )
        prog = get_progress(case_id)
        assert prog is not None
        assert prog.judicial_level == "Appeals Court"
        assert prog.iteration == 3

        _progress.pop(case_id, None)


# --- OrchestratorResult tests ---


class TestOrchestratorResult:
    def test_default_result(self) -> None:
        result = OrchestratorResult()
        assert result.judicial_stage == ""
        assert result.predicted_winner is None
        assert result.confidence_estimate == 0.0
        assert result.arguments_summary == {}
        assert result.escalation_decisions == []

    def test_to_dict(self) -> None:
        result = OrchestratorResult(
            judicial_stage="First Instance",
            predicted_winner="claimant",
            confidence_estimate=0.75,
        )
        d = result.to_dict()
        assert d["judicial_stage"] == "First Instance"
        assert d["predicted_winner"] == "claimant"
        assert d["confidence_estimate"] == 0.75
        assert "arguments_summary" in d
        assert "full_reasoning_trace" in d


# --- Summarize arguments tests ---


class TestSummarizeArguments:
    def test_summarize_empty(self) -> None:
        assert _summarize_arguments([]) == []

    def test_summarize_single(self) -> None:
        arg = _make_argument(content="Test argument content here")
        summaries = _summarize_arguments([arg])
        assert len(summaries) == 1
        assert summaries[0]["role"] == "claimant"
        assert summaries[0]["iteration"] == 0
        assert "Test argument content here" in str(summaries[0]["content"])

    def test_summarize_truncates_long_content(self) -> None:
        arg = _make_argument(content="x" * 1000)
        summaries = _summarize_arguments([arg])
        assert len(str(summaries[0]["content"])) <= 500


# --- CaseOrchestrator tests ---


class TestCaseOrchestrator:
    def test_init_defaults(self, tmp_path: Path) -> None:
        fm = CaseFolderManager(base_path=tmp_path)
        orch = CaseOrchestrator(folder_manager=fm)
        assert orch.folder_manager is fm
        assert orch.max_iterations == 5
        assert orch.max_escalations == 3

    def test_init_custom(self, tmp_path: Path) -> None:
        fm = CaseFolderManager(base_path=tmp_path)
        claimant = ClaimantAgent(client=MagicMock(spec=anthropic.Anthropic))
        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=claimant,
            max_iterations=3,
            max_escalations=1,
        )
        assert orch.claimant_agent is claimant
        assert orch.max_iterations == 3
        assert orch.max_escalations == 1

    @pytest.mark.asyncio
    async def test_run_full_pipeline(self, tmp_path: Path) -> None:
        """Run the full orchestration pipeline with mocked LLM calls."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # Build mock responses: 1 iteration (claimant + respondent) + 4 court phases
        # Since max_iterations=1, we get exactly 1 round + court eval
        all_responses = _build_all_responses(iterations=1)

        # All agents share one mock client with sequential responses
        client = _make_mock_client(all_responses)
        claimant = ClaimantAgent(client=client)
        respondent = RespondentAgent(client=client)
        court = CourtAgent(client=client)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=claimant,
            respondent_agent=respondent,
            court_agent=court,
            max_iterations=1,
        )

        result = await orch.run(case.id)

        # Verify all required output fields
        assert result.judicial_stage == "First Instance"
        assert "claimant" in result.arguments_summary
        assert "respondent" in result.arguments_summary
        assert len(result.arguments_summary["claimant"]) >= 1
        assert len(result.arguments_summary["respondent"]) >= 1
        assert result.court_evaluation != {}
        assert result.mcda_scoring != {}
        assert result.predicted_winner is not None
        assert result.confidence_estimate > 0
        assert len(result.full_reasoning_trace) > 0

        # Verify case status updated
        updated_case = fm.load(case.id)
        assert updated_case.status == CaseStatus.completed

    @pytest.mark.asyncio
    async def test_run_saves_final_output(self, tmp_path: Path) -> None:
        """Verify final_result.json is saved to the case folder."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        await orch.run(case.id)

        # Check final_result.json exists
        output_path = fm.case_dir(case.id) / "outputs" / "final_result.json"
        assert output_path.exists()

        with open(output_path) as f:
            data: dict[str, object] = json.load(f)
        assert "judicial_stage" in data
        assert "predicted_winner" in data
        assert "mcda_scoring" in data
        assert "court_evaluation" in data

    @pytest.mark.asyncio
    async def test_run_updates_progress(self, tmp_path: Path) -> None:
        """Verify progress is tracked during orchestration."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        await orch.run(case.id)

        progress = get_progress(case.id)
        assert progress is not None
        assert progress.phase == "completed"
        assert progress.message == "Case resolved"

        _progress.pop(case.id, None)

    @pytest.mark.asyncio
    async def test_run_case_set_to_running(self, tmp_path: Path) -> None:
        """Case status is set to running at start of orchestration."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        # Track status changes
        statuses: list[str] = []
        original_update = fm.update_case

        def tracking_update(c: Case) -> None:
            statuses.append(c.status.value)
            original_update(c)

        fm.update_case = tracking_update  # type: ignore[assignment]

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        await orch.run(case.id)
        assert "running" in statuses
        assert "completed" in statuses

    @pytest.mark.asyncio
    async def test_run_no_escalation(self, tmp_path: Path) -> None:
        """No escalation when court recommends no_escalation."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        result = await orch.run(case.id)
        assert result.escalation_decisions == []
        assert result.judicial_stage == "First Instance"

    @pytest.mark.asyncio
    async def test_run_with_escalation(self, tmp_path: Path) -> None:
        """Test escalation triggers a second loop at a higher level."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # First round: escalation recommended
        phase3_escalate = json.dumps(
            {
                "reconciled_decision": "Case has constitutional questions.",
                "escalation_recommendation": "escalate_constitutional",
                "escalation_reasoning": "Constitutional issue raised.",
            }
        )

        # First level responses (with escalation, high confidence to skip refinement)
        first_level = [
            CLAIMANT_RESPONSE,
            RESPONDENT_RESPONSE,
            PHASE1_RESPONSE,
            PHASE2_RESPONSE,
            phase3_escalate,
            PHASE4_HIGH_CONFIDENCE,
        ]
        # Second level responses (no escalation, high confidence to skip refinement)
        second_level = [
            CLAIMANT_RESPONSE,
            RESPONDENT_RESPONSE,
            PHASE1_RESPONSE,
            PHASE2_RESPONSE,
            PHASE3_RESPONSE,
            PHASE4_HIGH_CONFIDENCE,
        ]
        all_responses = first_level + second_level
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
            max_escalations=3,
        )

        result = await orch.run(case.id)

        assert len(result.escalation_decisions) >= 1
        assert result.judicial_stage == "Appeals Court"
        updated = fm.load(case.id)
        assert updated.status == CaseStatus.completed

    @pytest.mark.asyncio
    async def test_run_error_resets_status(self, tmp_path: Path) -> None:
        """On orchestration failure, case status resets to pending."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # Client that raises an error on first call
        client = MagicMock(spec=anthropic.Anthropic)
        client.messages.create.side_effect = Exception("LLM error")

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        with pytest.raises(Exception, match="LLM error"):
            await orch.run(case.id)

        failed_case = fm.load(case.id)
        assert failed_case.status == CaseStatus.pending

    @pytest.mark.asyncio
    async def test_run_saves_iterations(self, tmp_path: Path) -> None:
        """Verify argument iterations are saved to the case folder."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        await orch.run(case.id)

        iterations_dir = fm.case_dir(case.id) / "iterations"
        iteration_files = list(iterations_dir.glob("*.json"))
        assert len(iteration_files) >= 2  # at least 1 claimant + 1 respondent

    @pytest.mark.asyncio
    async def test_run_saves_court_evaluation(self, tmp_path: Path) -> None:
        """Verify court_evaluation.json is saved."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        await orch.run(case.id)

        eval_path = fm.case_dir(case.id) / "outputs" / "court_evaluation.json"
        assert eval_path.exists()

    @pytest.mark.asyncio
    async def test_result_has_all_required_fields(self, tmp_path: Path) -> None:
        """Verify the final result contains all required output fields."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        all_responses = _build_all_responses(iterations=1)
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        result = await orch.run(case.id)
        d = result.to_dict()

        required_fields = [
            "judicial_stage",
            "arguments_summary",
            "referenced_precedents",
            "referenced_laws",
            "court_evaluation",
            "escalation_decisions",
            "mcda_scoring",
            "predicted_winner",
            "confidence_estimate",
            "full_reasoning_trace",
        ]
        for field in required_fields:
            assert field in d, f"Missing required field: {field}"


# --- API endpoint tests ---


class TestOrchestrationAPI:
    def test_run_case_accepted(self, tmp_path: Path) -> None:
        """POST /api/cases/{case_id}/run returns 202."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from backend.app import app

        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(return_value=OrchestratorResult())

        with (
            _patch("backend.api.orchestration.folder_manager", fm),
            _patch("backend.api.orchestration.orchestrator", mock_orch),
        ):
            client = TestClient(app)
            resp = client.post(f"/api/cases/{case.id}/run")

        assert resp.status_code == 202
        data: dict[str, object] = resp.json()
        assert data["case_id"] == case.id
        assert data["status"] == "accepted"

    def test_run_case_not_found(self, tmp_path: Path) -> None:
        """POST /api/cases/{case_id}/run returns 404 for missing case."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from backend.app import app

        fm = CaseFolderManager(base_path=tmp_path)

        with _patch("backend.api.orchestration.folder_manager", fm):
            client = TestClient(app)
            resp = client.post("/api/cases/nonexistent/run")

        assert resp.status_code == 404

    def test_run_case_already_running(self, tmp_path: Path) -> None:
        """POST /api/cases/{case_id}/run returns 409 if case is running."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from backend.app import app

        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)
        case.status = CaseStatus.running
        fm.update_case(case)

        with _patch("backend.api.orchestration.folder_manager", fm):
            client = TestClient(app)
            resp = client.post(f"/api/cases/{case.id}/run")

        assert resp.status_code == 409

    def test_get_status_pending(self, tmp_path: Path) -> None:
        """GET /api/cases/{case_id}/status returns pending for new case."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from backend.app import app

        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        with _patch("backend.api.orchestration.folder_manager", fm):
            client = TestClient(app)
            resp = client.get(f"/api/cases/{case.id}/status")

        assert resp.status_code == 200
        data: dict[str, object] = resp.json()
        assert data["case_id"] == case.id
        assert data["phase"] == "pending"

    def test_get_status_with_progress(self, tmp_path: Path) -> None:
        """GET /api/cases/{case_id}/status returns current progress."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from backend.app import app

        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        _update_progress(case.id, "arguing", "Running argument loop")

        with _patch("backend.api.orchestration.folder_manager", fm):
            client = TestClient(app)
            resp = client.get(f"/api/cases/{case.id}/status")

        assert resp.status_code == 200
        data: dict[str, object] = resp.json()
        assert data["phase"] == "arguing"
        assert data["message"] == "Running argument loop"

        _progress.pop(case.id, None)

    def test_get_status_not_found(self, tmp_path: Path) -> None:
        """GET /api/cases/{case_id}/status returns 404 for missing case."""
        from unittest.mock import patch as _patch

        from fastapi.testclient import TestClient

        from backend.app import app

        fm = CaseFolderManager(base_path=tmp_path)

        with _patch("backend.api.orchestration.folder_manager", fm):
            client = TestClient(app)
            resp = client.get("/api/cases/nonexistent/status")

        assert resp.status_code == 404


# --- Refinement loop tests ---


def _build_responses_with_refinement(
    initial_mcda: str,
    refinement_mcdas: list[str],
    iterations: int = 1,
) -> list[str]:
    """Build mock responses for orchestration with refinement rounds.

    Each refinement round adds 4 court phases (phase1-3 + MCDA).
    """
    responses: list[str] = []
    # Argument iterations
    for _ in range(iterations):
        responses.append(CLAIMANT_RESPONSE)
        responses.append(RESPONDENT_RESPONSE)
    # Initial court evaluation: 4 phases
    responses.extend([PHASE1_RESPONSE, PHASE2_RESPONSE, PHASE3_RESPONSE, initial_mcda])
    # Refinement rounds: each is a full court eval (4 phases)
    for mcda_resp in refinement_mcdas:
        responses.extend([PHASE1_RESPONSE, PHASE2_RESPONSE, PHASE3_RESPONSE, mcda_resp])
    return responses


class TestRefinementLoop:
    """Tests for the confidence threshold refinement loop."""

    @pytest.mark.asyncio
    async def test_high_confidence_no_refinement(self, tmp_path: Path) -> None:
        """Confidence above threshold resolves immediately with refinement_rounds=0."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # High confidence initial MCDA — no refinement needed
        all_responses = _build_responses_with_refinement(
            initial_mcda=PHASE4_HIGH_CONFIDENCE,
            refinement_mcdas=[],
            iterations=1,
        )
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        result = await orch.run(case.id)
        assert result.refinement_rounds == 0
        assert result.confidence_estimate >= 0.80

        # No refinement files should exist
        outputs_dir = fm.case_dir(case.id) / "outputs"
        refinement_files = list(outputs_dir.glob("refinement_round_*"))
        assert len(refinement_files) == 0

        _progress.pop(case.id, None)

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_refinement(self, tmp_path: Path) -> None:
        """Low confidence triggers refinement and re-evaluation."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # Low initial confidence, then high after 1 refinement round
        all_responses = _build_responses_with_refinement(
            initial_mcda=PHASE4_LOW_CONFIDENCE,
            refinement_mcdas=[PHASE4_HIGH_CONFIDENCE],
            iterations=1,
        )
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        result = await orch.run(case.id)
        assert result.refinement_rounds == 1
        assert result.confidence_estimate >= 0.80

        # Refinement trace in reasoning
        assert any("Refinement round 1" in t for t in result.full_reasoning_trace)

        _progress.pop(case.id, None)

    @pytest.mark.asyncio
    async def test_max_refinement_rounds_respected(self, tmp_path: Path) -> None:
        """Max refinement rounds is respected even if confidence stays low."""
        from unittest.mock import patch as _patch

        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # All rounds produce low confidence — 3 refinement rounds (max)
        all_responses = _build_responses_with_refinement(
            initial_mcda=PHASE4_LOW_CONFIDENCE,
            refinement_mcdas=[
                PHASE4_LOW_CONFIDENCE,
                PHASE4_LOW_CONFIDENCE,
                PHASE4_LOW_CONFIDENCE,
            ],
            iterations=1,
        )
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        with _patch("backend.orchestrator.settings") as mock_settings:
            mock_settings.confidence_threshold = 0.80
            mock_settings.max_refinement_rounds = 3
            mock_settings.llm_provider = "ollama"
            result = await orch.run(case.id)

        assert result.refinement_rounds == 3
        # Should have warning about threshold not met
        assert any("Manual review recommended" in t for t in result.full_reasoning_trace)

        _progress.pop(case.id, None)

    @pytest.mark.asyncio
    async def test_refinement_files_saved(self, tmp_path: Path) -> None:
        """Verify refinement round files are saved to outputs."""
        fm = CaseFolderManager(base_path=tmp_path)
        case = _create_test_case(fm)

        # Low then medium then high confidence
        all_responses = _build_responses_with_refinement(
            initial_mcda=PHASE4_LOW_CONFIDENCE,
            refinement_mcdas=[PHASE4_MEDIUM_CONFIDENCE, PHASE4_HIGH_CONFIDENCE],
            iterations=1,
        )
        client = _make_mock_client(all_responses)

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        result = await orch.run(case.id)

        outputs_dir = fm.case_dir(case.id) / "outputs"

        # Check refinement round files exist
        for n in range(1, result.refinement_rounds + 1):
            assert (outputs_dir / f"refinement_round_{n}_court_evaluation.json").exists()
            assert (outputs_dir / f"refinement_round_{n}_mcda_scoring.json").exists()

        # Final result should include refinement_rounds
        with open(outputs_dir / "final_result.json") as f:
            final: dict[str, object] = json.load(f)
        assert final["refinement_rounds"] == result.refinement_rounds

        _progress.pop(case.id, None)
