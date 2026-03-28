"""Integration tests for the case intake REST API."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.case_folder import CaseFolderManager


@pytest.fixture()
def client_and_manager(tmp_path):
    manager = CaseFolderManager(base_path=tmp_path / "cases")
    with patch("backend.api.cases.folder_manager", manager):
        yield TestClient(app), manager


VALID_SUBMISSION = {
    "title": "Contract Breach - ABC vs XYZ",
    "facts": "ABC Corp entered a contract with XYZ Ltd on 2025-01-15 for software delivery.",
    "party_role": "claimant",
    "supporting_materials": "Contract document and email correspondence attached.",
}


class TestCreateCase:
    def test_create_case_returns_201(self, client_and_manager):
        client, _ = client_and_manager
        response = client.post("/api/cases", json=VALID_SUBMISSION)
        assert response.status_code == 201

    def test_create_case_returns_case_data(self, client_and_manager):
        client, _ = client_and_manager
        response = client.post("/api/cases", json=VALID_SUBMISSION)
        data = response.json()
        assert data["title"] == VALID_SUBMISSION["title"]
        assert data["facts"] == VALID_SUBMISSION["facts"]
        assert data["status"] == "pending"
        assert data["judicial_level"] == "First Instance"
        assert data["id"]  # UUID assigned
        assert data["claimant_input"] == VALID_SUBMISSION["supporting_materials"]
        assert data["respondent_input"] is None

    def test_create_case_as_respondent(self, client_and_manager):
        client, _ = client_and_manager
        submission = {**VALID_SUBMISSION, "party_role": "respondent"}
        response = client.post("/api/cases", json=submission)
        data = response.json()
        assert data["respondent_input"] == VALID_SUBMISSION["supporting_materials"]
        assert data["claimant_input"] is None

    def test_create_case_creates_folder(self, client_and_manager):
        client, manager = client_and_manager
        response = client.post("/api/cases", json=VALID_SUBMISSION)
        case_id = response.json()["id"]
        case_dir = manager.case_dir(case_id)
        assert case_dir.exists()
        assert (case_dir / "config" / "case.json").exists()
        assert (case_dir / "state").is_dir()
        assert (case_dir / "iterations").is_dir()
        assert (case_dir / "outputs").is_dir()

    def test_create_case_invalid_role_returns_422(self, client_and_manager):
        client, _ = client_and_manager
        submission = {**VALID_SUBMISSION, "party_role": "judge"}
        response = client.post("/api/cases", json=submission)
        assert response.status_code == 422

    def test_create_case_missing_title_returns_422(self, client_and_manager):
        client, _ = client_and_manager
        submission = {**VALID_SUBMISSION}
        del submission["title"]
        response = client.post("/api/cases", json=submission)
        assert response.status_code == 422

    def test_create_case_empty_facts_returns_422(self, client_and_manager):
        client, _ = client_and_manager
        submission = {**VALID_SUBMISSION, "facts": ""}
        response = client.post("/api/cases", json=submission)
        assert response.status_code == 422

    def test_create_case_no_supporting_materials(self, client_and_manager):
        client, _ = client_and_manager
        submission = {
            "title": "Test Case",
            "facts": "Some facts",
            "party_role": "claimant",
        }
        response = client.post("/api/cases", json=submission)
        assert response.status_code == 201
        data = response.json()
        assert data["claimant_input"] is None


class TestGetCase:
    def test_get_case_returns_data(self, client_and_manager):
        client, _ = client_and_manager
        create_response = client.post("/api/cases", json=VALID_SUBMISSION)
        case_id = create_response.json()["id"]

        response = client.get(f"/api/cases/{case_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == case_id
        assert data["title"] == VALID_SUBMISSION["title"]

    def test_get_case_not_found_returns_404(self, client_and_manager):
        client, _ = client_and_manager
        response = client.get("/api/cases/nonexistent-id")
        assert response.status_code == 404


class TestListCases:
    def test_list_cases_empty(self, client_and_manager):
        client, _ = client_and_manager
        response = client.get("/api/cases")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_cases_after_creation(self, client_and_manager):
        client, _ = client_and_manager
        client.post("/api/cases", json=VALID_SUBMISSION)
        client.post(
            "/api/cases",
            json={**VALID_SUBMISSION, "title": "Second Case"},
        )

        response = client.get("/api/cases")
        assert response.status_code == 200
        cases = response.json()
        assert len(cases) == 2
        titles = {c["title"] for c in cases}
        assert VALID_SUBMISSION["title"] in titles
        assert "Second Case" in titles

    def test_list_cases_has_correct_fields(self, client_and_manager):
        client, _ = client_and_manager
        client.post("/api/cases", json=VALID_SUBMISSION)

        response = client.get("/api/cases")
        item = response.json()[0]
        assert "id" in item
        assert "title" in item
        assert "status" in item
        assert "judicial_level" in item
        assert "created_at" in item
        # List items should not have full details
        assert "facts" not in item
        assert "claimant_input" not in item


class TestOutputsNestedPath:
    def test_nested_path_output(self, client_and_manager):
        """Outputs endpoint supports nested paths for archived levels."""
        client, manager = client_and_manager
        resp = client.post("/api/cases", json=VALID_SUBMISSION)
        case_id = resp.json()["id"]
        # Create a nested output file
        nested_dir = manager.case_dir(case_id) / "outputs" / "level_first_instance"
        nested_dir.mkdir(parents=True, exist_ok=True)
        import json

        (nested_dir / "court_evaluation.json").write_text(
            json.dumps({"test": "nested_value"})
        )
        resp = client.get(
            f"/api/cases/{case_id}/outputs/level_first_instance/court_evaluation.json"
        )
        assert resp.status_code == 200
        assert resp.json()["test"] == "nested_value"

    def test_flat_path_still_works(self, client_and_manager):
        """Flat (non-nested) output paths still work."""
        client, manager = client_and_manager
        resp = client.post("/api/cases", json=VALID_SUBMISSION)
        case_id = resp.json()["id"]
        import json

        out_dir = manager.case_dir(case_id) / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final_result.json").write_text(json.dumps({"ok": True}))
        resp = client.get(f"/api/cases/{case_id}/outputs/final_result.json")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_path_traversal_blocked(self, client_and_manager):
        """Path traversal attempts are rejected."""
        client, _ = client_and_manager
        resp = client.post("/api/cases", json=VALID_SUBMISSION)
        case_id = resp.json()["id"]
        resp = client.get(f"/api/cases/{case_id}/outputs/../../config/case.json")
        assert resp.status_code in (400, 404)


class TestFullFlow:
    def test_submit_retrieve_list(self, client_and_manager):
        """Integration: submit a case, retrieve it, verify it appears in list."""
        client, manager = client_and_manager

        # Submit
        create_resp = client.post("/api/cases", json=VALID_SUBMISSION)
        assert create_resp.status_code == 201
        case_id = create_resp.json()["id"]

        # Retrieve
        get_resp = client.get(f"/api/cases/{case_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == case_id

        # List
        list_resp = client.get("/api/cases")
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()]
        assert case_id in ids

        # Folder exists
        case_dir = manager.case_dir(case_id)
        assert case_dir.exists()
        loaded = manager.load(case_id)
        assert loaded.title == VALID_SUBMISSION["title"]
