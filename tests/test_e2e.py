"""End-to-end integration tests exercising the full RalphLex flow.

Submit a case via the API, trigger orchestration, poll until complete,
and verify all output fields are present and valid.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
from fastapi.testclient import TestClient

from backend.app import app
from backend.orchestrator import OrchestratorResult, _progress
from backend.services.case_folder import CaseFolderManager

# --- Mock LLM responses (same as test_orchestrator) ---

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


def _make_mock_response(text: str) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 200
    response.model = "claude-sonnet-4-20250514"
    response.stop_reason = "end_turn"
    return response


def _make_mock_client(responses: list[str]) -> MagicMock:
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.create.side_effect = [_make_mock_response(text) for text in responses]
    return client


def _build_all_responses(iterations: int = 1) -> list[str]:
    """Build the full sequence of mock LLM responses for one judicial level.

    Includes refinement rounds with high-confidence scores to satisfy
    the confidence threshold loop.
    """
    responses: list[str] = []
    for _ in range(iterations):
        responses.append(CLAIMANT_RESPONSE)
        responses.append(RESPONDENT_RESPONSE)
    responses.extend([PHASE1_RESPONSE, PHASE2_RESPONSE, PHASE3_RESPONSE, PHASE4_RESPONSE])
    # Add refinement rounds with high-confidence scores
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


# All 10 required output fields
REQUIRED_FIELDS = [
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


class TestEndToEnd:
    """Full end-to-end tests: API submission -> orchestration -> verification."""

    def _setup_mocks(
        self,
        tmp_path: Path,
        responses: list[str] | None = None,
    ) -> tuple[CaseFolderManager, MagicMock]:
        """Create a folder manager and mock client for e2e testing."""
        fm = CaseFolderManager(base_path=tmp_path / "cases")
        if responses is None:
            responses = _build_all_responses(iterations=1)
        client = _make_mock_client(responses)
        return fm, client

    def test_full_flow_submit_run_verify(self, tmp_path: Path) -> None:
        """Submit a case, run orchestration synchronously, verify output."""
        fm, client = self._setup_mocks(tmp_path)

        from backend.agents.claimant import ClaimantAgent
        from backend.agents.court import CourtAgent
        from backend.agents.respondent import RespondentAgent
        from backend.orchestrator import CaseOrchestrator

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        with (
            patch("backend.api.cases.folder_manager", fm),
            patch("backend.api.orchestration.folder_manager", fm),
            patch("backend.api.orchestration.orchestrator", orch),
        ):
            tc = TestClient(app)

            # Step 1: Submit a case
            resp = tc.post(
                "/api/cases",
                json={
                    "title": "E2E Contract Dispute",
                    "facts": "Defendant failed to deliver goods per contract terms.",
                    "party_role": "claimant",
                    "supporting_materials": "Invoice #12345, delivery schedule",
                },
            )
            assert resp.status_code == 201
            case_data: dict[str, object] = resp.json()
            case_id = str(case_data["id"])
            assert case_data["status"] == "pending"

            # Step 2: Verify case appears in list
            resp = tc.get("/api/cases")
            assert resp.status_code == 200
            cases = resp.json()
            assert any(c["id"] == case_id for c in cases)

            # Step 3: Get case details
            resp = tc.get(f"/api/cases/{case_id}")
            assert resp.status_code == 200
            detail: dict[str, object] = resp.json()
            assert detail["title"] == "E2E Contract Dispute"
            assert detail["status"] == "pending"

            # Step 4: Trigger orchestration (runs synchronously in TestClient)
            resp = tc.post(f"/api/cases/{case_id}/run")
            assert resp.status_code == 202

            # Step 5: Verify case is now completed
            resp = tc.get(f"/api/cases/{case_id}")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["status"] == "completed"

            # Step 6: Retrieve final result and verify all output fields
            resp = tc.get(f"/api/cases/{case_id}/outputs/final_result.json")
            assert resp.status_code == 200
            final: dict[str, object] = resp.json()
            for field in REQUIRED_FIELDS:
                assert field in final, f"Missing required field: {field}"

            # Verify field values are populated
            assert final["judicial_stage"] == "First Instance"
            assert isinstance(final["arguments_summary"], dict)
            assert "claimant" in final["arguments_summary"]  # type: ignore[operator]
            assert "respondent" in final["arguments_summary"]  # type: ignore[operator]
            assert isinstance(final["court_evaluation"], dict)
            assert isinstance(final["mcda_scoring"], dict)
            assert final["predicted_winner"] is not None
            assert isinstance(final["confidence_estimate"], float)
            assert final["confidence_estimate"] > 0  # type: ignore[operator]
            assert isinstance(final["full_reasoning_trace"], list)
            assert len(final["full_reasoning_trace"]) > 0  # type: ignore[arg-type]
            assert isinstance(final["escalation_decisions"], list)
            assert isinstance(final["referenced_precedents"], list)
            assert isinstance(final["referenced_laws"], list)

        # Clean up progress
        _progress.pop(case_id, None)

    def test_full_flow_with_escalation(self, tmp_path: Path) -> None:
        """Submit a case, run with escalation, verify higher judicial level."""
        phase3_escalate = json.dumps(
            {
                "reconciled_decision": "Case has constitutional questions.",
                "escalation_recommendation": "escalate_constitutional",
                "escalation_reasoning": "Constitutional issue raised.",
            }
        )

        # First level (escalates, high confidence to skip refinement)
        first_level = [
            CLAIMANT_RESPONSE,
            RESPONDENT_RESPONSE,
            PHASE1_RESPONSE,
            PHASE2_RESPONSE,
            phase3_escalate,
            PHASE4_HIGH_CONFIDENCE,
        ]
        second_level = _build_all_responses(iterations=1)
        all_responses = first_level + second_level

        fm, client = self._setup_mocks(tmp_path, responses=all_responses)

        from backend.agents.claimant import ClaimantAgent
        from backend.agents.court import CourtAgent
        from backend.agents.respondent import RespondentAgent
        from backend.orchestrator import CaseOrchestrator

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
            max_escalations=3,
        )

        with (
            patch("backend.api.cases.folder_manager", fm),
            patch("backend.api.orchestration.folder_manager", fm),
            patch("backend.api.orchestration.orchestrator", orch),
        ):
            tc = TestClient(app)

            # Submit case
            resp = tc.post(
                "/api/cases",
                json={
                    "title": "Constitutional Dispute",
                    "facts": "A dispute involving constitutional rights interpretation.",
                    "party_role": "claimant",
                },
            )
            assert resp.status_code == 201
            case_id = str(resp.json()["id"])

            # Run orchestration
            resp = tc.post(f"/api/cases/{case_id}/run")
            assert resp.status_code == 202

            # Verify completed
            resp = tc.get(f"/api/cases/{case_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"

            # Verify escalation in final result
            resp = tc.get(f"/api/cases/{case_id}/outputs/final_result.json")
            assert resp.status_code == 200
            final: dict[str, object] = resp.json()

            for field in REQUIRED_FIELDS:
                assert field in final, f"Missing required field: {field}"

            assert final["judicial_stage"] == "Appeals Court"
            esc = final["escalation_decisions"]
            assert isinstance(esc, list)
            assert len(esc) >= 1

        _progress.pop(case_id, None)

    def test_full_flow_iterations_and_court_eval(self, tmp_path: Path) -> None:
        """Verify iteration files and court evaluation are produced."""
        fm, client = self._setup_mocks(tmp_path)

        from backend.agents.claimant import ClaimantAgent
        from backend.agents.court import CourtAgent
        from backend.agents.respondent import RespondentAgent
        from backend.orchestrator import CaseOrchestrator

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        with (
            patch("backend.api.cases.folder_manager", fm),
            patch("backend.api.orchestration.folder_manager", fm),
            patch("backend.api.orchestration.orchestrator", orch),
        ):
            tc = TestClient(app)

            resp = tc.post(
                "/api/cases",
                json={
                    "title": "Iteration Verification",
                    "facts": "Testing iteration file creation.",
                    "party_role": "respondent",
                },
            )
            case_id = str(resp.json()["id"])

            tc.post(f"/api/cases/{case_id}/run")

            # Verify iterations are accessible
            resp = tc.get(f"/api/cases/{case_id}/iterations")
            assert resp.status_code == 200
            iterations = resp.json()
            assert len(iterations) >= 2  # claimant + respondent

            # Verify court evaluation
            resp = tc.get(f"/api/cases/{case_id}/outputs/court_evaluation.json")
            assert resp.status_code == 200
            court: dict[str, object] = resp.json()
            assert "consistency_scores" in court or "preliminary_opinion" in court

            # Verify MCDA scoring
            resp = tc.get(f"/api/cases/{case_id}/outputs/mcda_scoring.json")
            assert resp.status_code == 200
            mcda: dict[str, object] = resp.json()
            assert "predicted_winner" in mcda
            assert "confidence" in mcda

        _progress.pop(case_id, None)

    def test_full_flow_timeline(self, tmp_path: Path) -> None:
        """Verify the timeline endpoint reflects orchestration phases."""
        fm, client = self._setup_mocks(tmp_path)

        from backend.agents.claimant import ClaimantAgent
        from backend.agents.court import CourtAgent
        from backend.agents.respondent import RespondentAgent
        from backend.orchestrator import CaseOrchestrator

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        with (
            patch("backend.api.cases.folder_manager", fm),
            patch("backend.api.orchestration.folder_manager", fm),
            patch("backend.api.orchestration.orchestrator", orch),
        ):
            tc = TestClient(app)

            resp = tc.post(
                "/api/cases",
                json={
                    "title": "Timeline Test",
                    "facts": "Testing timeline endpoint.",
                    "party_role": "claimant",
                },
            )
            case_id = str(resp.json()["id"])

            tc.post(f"/api/cases/{case_id}/run")

            resp = tc.get(f"/api/cases/{case_id}/timeline")
            assert resp.status_code == 200
            timeline = resp.json()
            assert len(timeline) >= 1

            phases = [e["phase"] for e in timeline]
            assert "created" in phases
            # After orchestration, we expect arguing + evaluating + completed
            assert "arguing" in phases
            assert "completed" in phases

        _progress.pop(case_id, None)

    def test_full_flow_status_endpoint(self, tmp_path: Path) -> None:
        """Verify status endpoint reflects completed orchestration."""
        fm, client = self._setup_mocks(tmp_path)

        from backend.agents.claimant import ClaimantAgent
        from backend.agents.court import CourtAgent
        from backend.agents.respondent import RespondentAgent
        from backend.orchestrator import CaseOrchestrator

        orch = CaseOrchestrator(
            folder_manager=fm,
            claimant_agent=ClaimantAgent(client=client),
            respondent_agent=RespondentAgent(client=client),
            court_agent=CourtAgent(client=client),
            max_iterations=1,
        )

        with (
            patch("backend.api.cases.folder_manager", fm),
            patch("backend.api.orchestration.folder_manager", fm),
            patch("backend.api.orchestration.orchestrator", orch),
        ):
            tc = TestClient(app)

            resp = tc.post(
                "/api/cases",
                json={
                    "title": "Status Check",
                    "facts": "Testing status endpoint after orchestration.",
                    "party_role": "claimant",
                },
            )
            case_id = str(resp.json()["id"])

            # Before run: pending
            resp = tc.get(f"/api/cases/{case_id}/status")
            assert resp.status_code == 200
            assert resp.json()["phase"] == "pending"

            # Run orchestration
            tc.post(f"/api/cases/{case_id}/run")

            # After run: completed
            resp = tc.get(f"/api/cases/{case_id}/status")
            assert resp.status_code == 200
            assert resp.json()["phase"] == "completed"

        _progress.pop(case_id, None)

    def test_error_handling_missing_case(self) -> None:
        """Verify proper error responses for non-existent cases."""
        tc = TestClient(app)

        resp = tc.get("/api/cases/nonexistent-id")
        assert resp.status_code == 404

        resp = tc.post("/api/cases/nonexistent-id/run")
        assert resp.status_code == 404

        resp = tc.get("/api/cases/nonexistent-id/status")
        assert resp.status_code == 404

    def test_validation_error_on_bad_submission(self) -> None:
        """Verify 422 on invalid case submission."""
        tc = TestClient(app)

        # Missing required fields
        resp = tc.post("/api/cases", json={})
        assert resp.status_code == 422

        # Invalid party_role
        resp = tc.post(
            "/api/cases",
            json={
                "title": "Bad Case",
                "facts": "Some facts",
                "party_role": "invalid_role",
            },
        )
        assert resp.status_code == 422

    def test_sample_case_endpoint(self, tmp_path: Path) -> None:
        """Verify the sample case runner creates a case and triggers run."""
        fm = CaseFolderManager(base_path=tmp_path / "cases")
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(return_value=OrchestratorResult())

        with (
            patch("backend.api.cases.folder_manager", fm),
            patch("backend.api.tools.folder_manager", fm),
            patch("backend.api.orchestration.orchestrator", mock_orch),
        ):
            tc = TestClient(app)

            resp = tc.post("/api/tools/run-sample?template=contract")
            assert resp.status_code == 201
            data: dict[str, object] = resp.json()
            assert "case_id" in data
            assert data["template"] == "contract"
            assert data["status"] == "running"

            # Verify the case was actually created
            case_id = str(data["case_id"])
            resp = tc.get(f"/api/cases/{case_id}")
            assert resp.status_code == 200

    def test_openapi_docs_accessible(self) -> None:
        """Verify the /docs endpoint (Swagger UI) is accessible."""
        tc = TestClient(app)

        resp = tc.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_openapi_schema_has_endpoints(self) -> None:
        """Verify OpenAPI schema contains all expected API paths."""
        tc = TestClient(app)

        resp = tc.get("/openapi.json")
        assert resp.status_code == 200
        schema: dict[str, object] = resp.json()
        paths = schema.get("paths", {})
        assert isinstance(paths, dict)

        expected_paths = [
            "/api/health",
            "/api/cases",
            "/api/cases/{case_id}",
            "/api/cases/{case_id}/run",
            "/api/cases/{case_id}/status",
            "/api/cases/{case_id}/timeline",
            "/api/cases/{case_id}/iterations",
            "/api/tools/run-sample",
        ]
        for path in expected_paths:
            assert path in paths, f"Missing path in OpenAPI: {path}"
