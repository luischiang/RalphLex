"""Tests for the sample case runner tool and API endpoint."""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.case_folder import CaseFolderManager
from backend.tools.run_sample import (
    DEFAULT_TEMPLATE,
    SAMPLE_CASES_DIR,
    VALID_TEMPLATES,
    load_template,
)

# ---------------------------------------------------------------------------
# Template loading tests
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_load_contract_template(self) -> None:
        data = load_template("contract")
        assert "title" in data
        assert "facts" in data
        assert "party_role" in data
        assert data["party_role"] in ("claimant", "respondent")

    def test_load_employment_template(self) -> None:
        data = load_template("employment")
        assert "title" in data
        assert "facts" in data
        assert len(data["facts"]) > 100

    def test_load_property_template(self) -> None:
        data = load_template("property")
        assert "title" in data
        assert "facts" in data
        assert "supporting_materials" in data

    def test_load_first_amendment_template(self) -> None:
        data = load_template("first_amendment")
        assert "title" in data
        assert "facts" in data
        assert "party_role" in data
        assert data["party_role"] in ("claimant", "respondent")
        assert "First Amendment" in data["title"]

    def test_load_due_process_template(self) -> None:
        data = load_template("due_process")
        assert "title" in data
        assert "facts" in data
        assert "party_role" in data
        assert data["party_role"] in ("claimant", "respondent")
        assert "Due Process" in data["title"]

    def test_load_antitrust_template(self) -> None:
        data = load_template("antitrust")
        assert "title" in data
        assert "facts" in data
        assert "party_role" in data
        assert data["party_role"] in ("claimant", "respondent")
        assert "Antitrust" in data["title"]

    def test_load_invalid_template_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown template"):
            load_template("nonexistent")

    def test_all_templates_are_valid_json(self) -> None:
        for name in VALID_TEMPLATES:
            path = SAMPLE_CASES_DIR / f"{name}.json"
            assert path.exists(), f"Template file missing: {path}"
            data = json.loads(path.read_text())
            assert isinstance(data, dict)
            assert "title" in data
            assert "facts" in data
            assert "party_role" in data

    def test_default_template_is_valid(self) -> None:
        assert DEFAULT_TEMPLATE in VALID_TEMPLATES

    def test_templates_have_supporting_materials(self) -> None:
        for name in VALID_TEMPLATES:
            data = load_template(name)
            assert "supporting_materials" in data
            assert len(data["supporting_materials"]) > 50


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestRunSampleAPI:
    @pytest.fixture()
    def tmp_manager(self, tmp_path: Path) -> CaseFolderManager:
        return CaseFolderManager(base_path=tmp_path / "cases")

    @pytest.fixture()
    def client(self, tmp_manager: CaseFolderManager) -> Generator[TestClient]:
        with (
            patch("backend.api.tools.folder_manager", tmp_manager),
            patch("backend.api.cases.folder_manager", tmp_manager),
            patch(
                "backend.api.tools._run_orchestration",
                new_callable=AsyncMock,
            ),
        ):
            yield TestClient(app)

    def test_run_sample_default_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample")
        assert resp.status_code == 201
        data = resp.json()
        assert "case_id" in data
        assert data["template"] == "contract"
        assert data["status"] == "running"
        assert data["monitor_url"] == "/monitor"

    def test_run_sample_employment_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample?template=employment")
        assert resp.status_code == 201
        data = resp.json()
        assert data["template"] == "employment"
        assert "case_id" in data

    def test_run_sample_property_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample?template=property")
        assert resp.status_code == 201
        assert resp.json()["template"] == "property"

    def test_run_sample_first_amendment_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample?template=first_amendment")
        assert resp.status_code == 201
        data = resp.json()
        assert data["template"] == "first_amendment"
        assert "case_id" in data

    def test_run_sample_due_process_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample?template=due_process")
        assert resp.status_code == 201
        data = resp.json()
        assert data["template"] == "due_process"
        assert "case_id" in data

    def test_run_sample_antitrust_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample?template=antitrust")
        assert resp.status_code == 201
        data = resp.json()
        assert data["template"] == "antitrust"
        assert "case_id" in data

    def test_run_sample_invalid_template(self, client: TestClient) -> None:
        resp = client.post("/api/tools/run-sample?template=invalid")
        assert resp.status_code == 422

    def test_case_is_created_in_folder(
        self,
        client: TestClient,
        tmp_manager: CaseFolderManager,
    ) -> None:
        resp = client.post("/api/tools/run-sample?template=contract")
        assert resp.status_code == 201
        case_id = resp.json()["case_id"]
        # Verify the case exists in the folder manager
        case = tmp_manager.load(case_id)
        assert "TechVentures" in case.title
        assert case.claimant_input is not None

    def test_case_appears_in_list(
        self,
        client: TestClient,
    ) -> None:
        # Create a sample case
        resp = client.post("/api/tools/run-sample?template=employment")
        assert resp.status_code == 201
        case_id = resp.json()["case_id"]
        # Verify it appears in the case list
        list_resp = client.get("/api/cases")
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()]
        assert case_id in ids

    def test_orchestrator_is_triggered(self, tmp_path: Path) -> None:
        manager = CaseFolderManager(base_path=tmp_path / "cases")
        mock_run = AsyncMock()
        with (
            patch("backend.api.tools.folder_manager", manager),
            patch("backend.api.cases.folder_manager", manager),
            patch("backend.api.tools._run_orchestration", mock_run),
        ):
            client = TestClient(app)
            resp = client.post("/api/tools/run-sample")
            assert resp.status_code == 201
            case_id = resp.json()["case_id"]
            # Background task should have been called with the case_id
            mock_run.assert_called_once_with(case_id)

    def test_new_template_cases_created_in_folder(
        self,
        client: TestClient,
        tmp_manager: CaseFolderManager,
    ) -> None:
        for template in ("first_amendment", "due_process", "antitrust"):
            resp = client.post(f"/api/tools/run-sample?template={template}")
            assert resp.status_code == 201
            case_id = resp.json()["case_id"]
            case = tmp_manager.load(case_id)
            assert case.facts is not None
            assert len(case.facts) > 100
            assert case.claimant_input is not None

    def test_all_six_templates_via_api(self, client: TestClient) -> None:
        for template in VALID_TEMPLATES:
            resp = client.post(f"/api/tools/run-sample?template={template}")
            assert resp.status_code == 201
            data = resp.json()
            assert data["template"] == template
            assert data["status"] == "running"

    def test_multiple_samples_create_different_cases(
        self,
        client: TestClient,
    ) -> None:
        resp1 = client.post("/api/tools/run-sample?template=contract")
        resp2 = client.post("/api/tools/run-sample?template=contract")
        assert resp1.json()["case_id"] != resp2.json()["case_id"]
