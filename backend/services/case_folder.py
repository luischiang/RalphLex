import json
from pathlib import Path

from backend.models.case import Case

SUBDIRS = ("config", "state", "iterations", "outputs")


class CaseNotFoundError(Exception):
    def __init__(self, case_id: str):
        self.case_id = case_id
        super().__init__(f"Case not found: {case_id}")


class CaseFolderManager:
    """Creates and loads case working directories under `data/cases/{case_id}/`.

    Each case directory has four subdirectories (config/, state/, iterations/,
    outputs/), all storing JSON files. `config/case.json` holds the immutable
    intake snapshot; `state/case_state.json` holds the fields that change as
    the case progresses (status, judicial_level, updated_at).
    """

    def __init__(self, base_dir: Path | str = "data/cases"):
        self.base_dir = Path(base_dir)

    def case_dir(self, case_id: str) -> Path:
        return self.base_dir / case_id

    def subdir(self, case_id: str, subdir: str) -> Path:
        if subdir not in SUBDIRS:
            raise ValueError(f"Unknown case subdirectory: {subdir}")
        return self.case_dir(case_id) / subdir

    def exists(self, case_id: str) -> bool:
        return (self.subdir(case_id, "config") / "case.json").is_file()

    def create_case(self, case: Case) -> Case:
        for name in SUBDIRS:
            self.subdir(case.id, name).mkdir(parents=True, exist_ok=True)
        self._write_json(self.subdir(case.id, "config") / "case.json", case.model_dump(mode="json"))
        self._write_state(case)
        return case

    def load_case(self, case_id: str) -> Case:
        config_path = self.subdir(case_id, "config") / "case.json"
        if not config_path.is_file():
            raise CaseNotFoundError(case_id)
        data = self._read_json(config_path)
        state_path = self.subdir(case_id, "state") / "case_state.json"
        if state_path.is_file():
            data.update(self._read_json(state_path))
        return Case.model_validate(data)

    def update_case_state(self, case: Case) -> Case:
        if not self.exists(case.id):
            raise CaseNotFoundError(case.id)
        self._write_state(case)
        return case

    def list_case_ids(self) -> list[str]:
        if not self.base_dir.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.base_dir.iterdir()
            if entry.is_dir() and (entry / "config" / "case.json").is_file()
        )

    def write_artifact(self, case_id: str, subdir: str, filename: str, data: dict) -> Path:
        path = self.subdir(case_id, subdir) / filename
        self._write_json(path, data)
        return path

    def read_artifact(self, case_id: str, subdir: str, filename: str) -> dict:
        path = self.subdir(case_id, subdir) / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        return self._read_json(path)

    def list_artifacts(self, case_id: str, subdir: str) -> list[str]:
        directory = self.subdir(case_id, subdir)
        if not directory.is_dir():
            return []
        return sorted(entry.name for entry in directory.glob("*.json"))

    def _write_state(self, case: Case) -> None:
        state = {
            "status": case.status.value,
            "judicial_level": case.judicial_level.value,
            "updated_at": case.updated_at.isoformat(),
        }
        self._write_json(self.subdir(case.id, "state") / "case_state.json", state)

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2, default=str))

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text())
