"""Tests for the timeline API endpoint."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.case_folder import CaseFolderManager

VALID_SUBMISSION = {
    "title": "Timeline Test Case",
    "facts": "Facts for timeline testing purposes.",
    "party_role": "claimant",
}


@pytest.fixture()
def client_and_manager(tmp_path):
    manager = CaseFolderManager(base_path=tmp_path / "cases")
    with patch("backend.api.cases.folder_manager", manager):
        yield TestClient(app), manager


def _create_case(client):
    resp = client.post("/api/cases", json=VALID_SUBMISSION)
    return resp.json()["id"]


class TestTimeline:
    def test_timeline_not_found(self, client_and_manager):
        client, _ = client_and_manager
        resp = client.get("/api/cases/nonexistent/timeline")
        assert resp.status_code == 404

    def test_timeline_new_case_has_creation_event(self, client_and_manager):
        client, _ = client_and_manager
        case_id = _create_case(client)
        resp = client.get(f"/api/cases/{case_id}/timeline")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) >= 1
        assert entries[0]["phase"] == "created"
        assert entries[0]["event"].startswith("Case ")
        assert entries[0]["is_escalation"] is False

    def test_timeline_includes_iterations(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)
        # Add iteration files
        manager.save_iteration(
            case_id,
            1,
            "claimant",
            {
                "role": "claimant",
                "iteration": 1,
                "content": "Claimant argument for round 1",
                "timestamp": "2026-03-28T10:00:00",
            },
        )
        manager.save_iteration(
            case_id,
            1,
            "respondent",
            {
                "role": "respondent",
                "iteration": 1,
                "content": "Respondent argument for round 1",
                "timestamp": "2026-03-28T10:01:00",
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        arguing_entries = [e for e in entries if e["phase"] == "arguing"]
        assert len(arguing_entries) == 2
        assert arguing_entries[0]["event"] == "Round 1 - claimant argument"
        assert arguing_entries[1]["event"] == "Round 1 - respondent argument"
        assert "Claimant argument" in str(arguing_entries[0]["details"]["content_preview"])

    def test_timeline_includes_court_evaluation(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)
        manager.save_output(
            case_id,
            "court_evaluation.json",
            {
                "consistency_scores": {"claimant": 7, "respondent": 6},
                "compliance_assessment": {},
                "escalation_recommendation": "escalate_appeals",
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        eval_entries = [e for e in entries if e["phase"] == "evaluating"]
        assert len(eval_entries) == 1
        assert eval_entries[0]["event"] == "Court evaluation completed"
        assert eval_entries[0]["details"]["has_escalation_recommendation"] is True

    def test_timeline_includes_mcda_scoring(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)
        manager.save_output(
            case_id,
            "mcda_scoring.json",
            {
                "criteria_scores": {},
                "weighted_totals": {"claimant": 0.6, "respondent": 0.4},
                "predicted_winner": "claimant",
                "confidence": 0.75,
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        mcda_entries = [e for e in entries if e["phase"] == "scoring"]
        assert len(mcda_entries) == 1
        assert mcda_entries[0]["details"]["predicted_winner"] == "claimant"
        assert mcda_entries[0]["details"]["confidence"] == 0.75

    def test_timeline_includes_escalation_events(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)
        # Create an archived level directory
        outputs_dir = manager.case_dir(case_id) / "outputs"
        level_dir = outputs_dir / "level_first_instance"
        level_dir.mkdir(parents=True, exist_ok=True)

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        esc_entries = [e for e in entries if e["is_escalation"]]
        assert len(esc_entries) == 1
        assert "Escalated from" in esc_entries[0]["event"]
        assert esc_entries[0]["phase"] == "escalating"

    def test_timeline_includes_final_result(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)
        manager.save_output(
            case_id,
            "final_result.json",
            {
                "judicial_stage": "First Instance",
                "predicted_winner": "claimant",
                "confidence_estimate": 0.82,
                "escalation_decisions": [],
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        final_entries = [e for e in entries if e["phase"] == "completed"]
        assert len(final_entries) == 1
        assert final_entries[0]["details"]["predicted_winner"] == "claimant"
        assert final_entries[0]["details"]["confidence_estimate"] == 0.82
        assert final_entries[0]["details"]["escalation_count"] == 0

    def test_timeline_sorted_by_timestamp(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)
        manager.save_iteration(
            case_id,
            1,
            "claimant",
            {
                "role": "claimant",
                "iteration": 1,
                "content": "Argument",
                "timestamp": "2026-03-28T10:00:00",
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        timestamps = [e["timestamp"] for e in entries]
        assert timestamps == sorted(timestamps)

    def test_timeline_full_flow(self, client_and_manager):
        """Integration: full case with iterations, evaluation, MCDA, and result."""
        client, manager = client_and_manager
        case_id = _create_case(client)

        # Add iterations
        for i in range(1, 3):
            for role in ["claimant", "respondent"]:
                manager.save_iteration(
                    case_id,
                    i,
                    role,
                    {
                        "role": role,
                        "iteration": i,
                        "content": f"{role} argument round {i}",
                        "timestamp": f"2026-03-28T10:0{i}:00",
                    },
                )

        # Add outputs
        manager.save_output(
            case_id,
            "court_evaluation.json",
            {
                "consistency_scores": {},
                "escalation_recommendation": None,
            },
        )
        manager.save_output(
            case_id,
            "mcda_scoring.json",
            {
                "criteria_scores": {},
                "weighted_totals": {},
                "predicted_winner": "respondent",
                "confidence": 0.65,
            },
        )
        manager.save_output(
            case_id,
            "final_result.json",
            {
                "judicial_stage": "First Instance",
                "predicted_winner": "respondent",
                "confidence_estimate": 0.65,
                "escalation_decisions": [],
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        assert resp.status_code == 200
        entries = resp.json()

        phases = [e["phase"] for e in entries]
        assert "created" in phases
        assert "arguing" in phases
        assert "evaluating" in phases
        assert "scoring" in phases
        assert "completed" in phases

    def test_timeline_escalation_with_decisions(self, client_and_manager):
        client, manager = client_and_manager
        case_id = _create_case(client)

        # Archived level + final result with escalation decisions
        level_dir = manager.case_dir(case_id) / "outputs" / "level_first_instance"
        level_dir.mkdir(parents=True, exist_ok=True)
        # Write a dummy file in the archived directory
        (level_dir / "court_evaluation.json").write_text(json.dumps({"test": True}))

        manager.save_output(
            case_id,
            "final_result.json",
            {
                "judicial_stage": "Appeals Court",
                "predicted_winner": "claimant",
                "confidence_estimate": 0.9,
                "escalation_decisions": [
                    {
                        "reason": "constitutional_question",
                        "from": "First Instance",
                        "to": "Appeals Court",
                    },
                ],
            },
        )

        resp = client.get(f"/api/cases/{case_id}/timeline")
        entries = resp.json()
        esc = [e for e in entries if e["is_escalation"]]
        assert len(esc) == 1
        final = [e for e in entries if e["phase"] == "completed"]
        assert final[0]["details"]["escalation_count"] == 1
