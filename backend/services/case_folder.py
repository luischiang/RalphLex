"""Case folder management for RalphLex.

Each case gets its own directory under data/cases/{case_id}/ with subdirectories:
config/, state/, iterations/, outputs/ — each storing JSON files.
"""

import json
from pathlib import Path

from backend.models.case import Case

SUBDIRS = ("config", "state", "iterations", "outputs")


class CaseFolderManager:
    """Creates and manages case directories under a base path."""

    def __init__(self, base_path: str | Path = "data/cases") -> None:
        self.base_path = Path(base_path)

    def case_dir(self, case_id: str) -> Path:
        return self.base_path / case_id

    def create(self, case: Case) -> Path:
        """Create the case folder structure and persist initial case data."""
        case_path = self.case_dir(case.id)
        for sub in SUBDIRS:
            (case_path / sub).mkdir(parents=True, exist_ok=True)

        # Persist the case config
        config_file = case_path / "config" / "case.json"
        config_file.write_text(case.model_dump_json(indent=2))
        return case_path

    def load(self, case_id: str) -> Case:
        """Load a case from its folder."""
        config_file = self.case_dir(case_id) / "config" / "case.json"
        if not config_file.exists():
            raise FileNotFoundError(f"Case {case_id} not found at {config_file}")
        return Case.model_validate_json(config_file.read_text())

    def save_state(self, case_id: str, state: dict) -> None:
        """Save arbitrary state data for a case."""
        state_file = self.case_dir(case_id) / "state" / "current.json"
        state_file.write_text(json.dumps(state, indent=2, default=str))

    def load_state(self, case_id: str) -> dict[str, object]:
        """Load the current state for a case."""
        state_file = self.case_dir(case_id) / "state" / "current.json"
        if not state_file.exists():
            return {}
        result: dict[str, object] = json.loads(state_file.read_text())
        return result

    def save_iteration(self, case_id: str, round_num: int, role: str, data: dict) -> None:
        """Save an iteration file for a specific round and role."""
        filename = f"round_{round_num}_{role}.json"
        iter_file = self.case_dir(case_id) / "iterations" / filename
        iter_file.write_text(json.dumps(data, indent=2, default=str))

    def load_iteration(self, case_id: str, round_num: int, role: str) -> dict[str, object]:
        """Load an iteration file."""
        filename = f"round_{round_num}_{role}.json"
        iter_file = self.case_dir(case_id) / "iterations" / filename
        if not iter_file.exists():
            raise FileNotFoundError(f"Iteration file not found: {iter_file}")
        result: dict[str, object] = json.loads(iter_file.read_text())
        return result

    def save_output(self, case_id: str, name: str, data: dict) -> None:
        """Save an output file (e.g., court_evaluation.json, mcda_scoring.json)."""
        output_file = self.case_dir(case_id) / "outputs" / name
        output_file.write_text(json.dumps(data, indent=2, default=str))

    def list_cases(self) -> list[str]:
        """List all case IDs."""
        if not self.base_path.exists():
            return []
        return [
            d.name
            for d in self.base_path.iterdir()
            if d.is_dir() and (d / "config" / "case.json").exists()
        ]

    def update_case(self, case: Case) -> None:
        """Update the persisted case config."""
        config_file = self.case_dir(case.id) / "config" / "case.json"
        if not config_file.exists():
            raise FileNotFoundError(f"Case {case.id} not found")
        config_file.write_text(case.model_dump_json(indent=2))
