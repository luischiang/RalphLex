import pytest

from backend.models.case import Case, CaseStatus, JudicialLevel
from backend.services.case_folder import CaseFolderManager, CaseNotFoundError


@pytest.fixture
def manager(tmp_path):
    return CaseFolderManager(base_dir=tmp_path / "cases")


def test_create_case_builds_subdirectories(manager):
    case = Case(title="Contract Dispute", facts="Goods not delivered on time.")
    manager.create_case(case)

    case_dir = manager.case_dir(case.id)
    assert case_dir.is_dir()
    for name in ("config", "state", "iterations", "outputs"):
        assert (case_dir / name).is_dir()
    assert (case_dir / "config" / "case.json").is_file()
    assert (case_dir / "state" / "case_state.json").is_file()


def test_load_case_round_trips(manager):
    case = Case(title="Employment Dispute", facts="Wrongful termination alleged.")
    manager.create_case(case)

    loaded = manager.load_case(case.id)
    assert loaded.id == case.id
    assert loaded.title == case.title
    assert loaded.facts == case.facts
    assert loaded.status == CaseStatus.PENDING


def test_load_case_missing_raises(manager):
    with pytest.raises(CaseNotFoundError):
        manager.load_case("does-not-exist")


def test_update_case_state_persists_changes(manager):
    case = Case(title="Property Damage", facts="Fence damaged by neighbor's tree.")
    manager.create_case(case)

    case.status = CaseStatus.RUNNING
    case.judicial_level = JudicialLevel.APPEALS_COURT
    manager.update_case_state(case)

    reloaded = manager.load_case(case.id)
    assert reloaded.status == CaseStatus.RUNNING
    assert reloaded.judicial_level == JudicialLevel.APPEALS_COURT
    # config snapshot (title/facts) is untouched by state updates
    assert reloaded.title == case.title


def test_update_case_state_missing_raises(manager):
    case = Case(title="Ghost Case", facts="Never created.")
    with pytest.raises(CaseNotFoundError):
        manager.update_case_state(case)


def test_list_case_ids_returns_created_cases(manager):
    case_a = Case(title="Case A", facts="Facts A")
    case_b = Case(title="Case B", facts="Facts B")
    manager.create_case(case_a)
    manager.create_case(case_b)

    ids = manager.list_case_ids()
    assert sorted(ids) == sorted([case_a.id, case_b.id])


def test_list_case_ids_empty_when_no_base_dir(tmp_path):
    manager = CaseFolderManager(base_dir=tmp_path / "nonexistent")
    assert manager.list_case_ids() == []


def test_write_and_read_artifact(manager):
    case = Case(title="Artifact Case", facts="Some facts")
    manager.create_case(case)

    manager.write_artifact(case.id, "iterations", "round_1_claimant.json", {"content": "hello"})
    data = manager.read_artifact(case.id, "iterations", "round_1_claimant.json")
    assert data == {"content": "hello"}
    assert manager.list_artifacts(case.id, "iterations") == ["round_1_claimant.json"]


def test_read_missing_artifact_raises(manager):
    case = Case(title="Case", facts="Facts")
    manager.create_case(case)
    with pytest.raises(FileNotFoundError):
        manager.read_artifact(case.id, "outputs", "missing.json")


def test_subdir_rejects_unknown_name(manager):
    with pytest.raises(ValueError):
        manager.subdir("some-id", "not-a-real-subdir")
