"""Tests for CaseFolderManager."""

import json

import pytest

from backend.models.case import Case, CaseStatus
from backend.services.case_folder import CaseFolderManager


@pytest.fixture
def tmp_manager(tmp_path):
    return CaseFolderManager(base_path=tmp_path / "cases")


@pytest.fixture
def sample_case():
    return Case(title="Contract Breach", facts="Party A breached clause 5.")


class TestCaseFolderCreate:
    def test_creates_directory_structure(self, tmp_manager, sample_case):
        case_path = tmp_manager.create(sample_case)
        assert case_path.exists()
        for sub in ("config", "state", "iterations", "outputs"):
            assert (case_path / sub).is_dir()

    def test_persists_case_config(self, tmp_manager, sample_case):
        case_path = tmp_manager.create(sample_case)
        config_file = case_path / "config" / "case.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["title"] == "Contract Breach"
        assert data["status"] == "pending"

    def test_idempotent_create(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        tmp_manager.create(sample_case)  # Should not raise


class TestCaseFolderLoad:
    def test_load_existing_case(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        loaded = tmp_manager.load(sample_case.id)
        assert loaded.id == sample_case.id
        assert loaded.title == sample_case.title

    def test_load_missing_case_raises(self, tmp_manager):
        with pytest.raises(FileNotFoundError):
            tmp_manager.load("nonexistent-id")


class TestCaseFolderState:
    def test_save_and_load_state(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        tmp_manager.save_state(sample_case.id, {"phase": "arguing", "iteration": 2})
        state = tmp_manager.load_state(sample_case.id)
        assert state["phase"] == "arguing"
        assert state["iteration"] == 2

    def test_load_empty_state(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        state = tmp_manager.load_state(sample_case.id)
        assert state == {}


class TestCaseFolderIterations:
    def test_save_and_load_iteration(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        data = {"content": "Opening argument", "legal_basis": ["Art. 1"]}
        tmp_manager.save_iteration(sample_case.id, 1, "claimant", data)
        loaded = tmp_manager.load_iteration(sample_case.id, 1, "claimant")
        assert loaded["content"] == "Opening argument"

    def test_load_missing_iteration_raises(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        with pytest.raises(FileNotFoundError):
            tmp_manager.load_iteration(sample_case.id, 99, "claimant")


class TestCaseFolderOutputs:
    def test_save_output(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        tmp_manager.save_output(sample_case.id, "court_evaluation.json", {"result": "ok"})
        output_file = tmp_manager.case_dir(sample_case.id) / "outputs" / "court_evaluation.json"
        assert output_file.exists()
        assert json.loads(output_file.read_text())["result"] == "ok"


class TestCaseFolderListAndUpdate:
    def test_list_cases(self, tmp_manager):
        c1 = Case(title="Case 1", facts="F1")
        c2 = Case(title="Case 2", facts="F2")
        tmp_manager.create(c1)
        tmp_manager.create(c2)
        ids = tmp_manager.list_cases()
        assert set(ids) == {c1.id, c2.id}

    def test_list_cases_empty(self, tmp_manager):
        assert tmp_manager.list_cases() == []

    def test_update_case(self, tmp_manager, sample_case):
        tmp_manager.create(sample_case)
        sample_case.status = CaseStatus.running
        tmp_manager.update_case(sample_case)
        loaded = tmp_manager.load(sample_case.id)
        assert loaded.status == CaseStatus.running

    def test_update_missing_case_raises(self, tmp_manager, sample_case):
        with pytest.raises(FileNotFoundError):
            tmp_manager.update_case(sample_case)
