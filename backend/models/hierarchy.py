"""Judicial hierarchy model for configurable court levels and escalation criteria."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.models.case import JudicialLevel

# Mapping from config IDs to JudicialLevel enum values
LEVEL_ID_MAP: dict[str, JudicialLevel] = {
    "first_instance": JudicialLevel.first_instance,
    "appeals": JudicialLevel.appeals,
    "superior": JudicialLevel.superior,
    "supreme": JudicialLevel.supreme,
}

# Ordered list of judicial levels from lowest to highest
LEVEL_ORDER: list[JudicialLevel] = [
    JudicialLevel.first_instance,
    JudicialLevel.appeals,
    JudicialLevel.superior,
    JudicialLevel.supreme,
]

DEFAULT_HIERARCHY_PATH = Path(__file__).parent.parent / "config" / "judicial_hierarchy.json"


class EscalationCriteria(BaseModel):
    """Criteria that can trigger escalation at a given judicial level."""

    constitutional_questions: bool = False
    conflicting_precedents: bool = False
    procedural_irregularities: bool = False
    explicit_recommendation: bool = True


class JudicialLevelConfig(BaseModel):
    """Configuration for a single judicial level."""

    id: str
    name: str
    jurisdiction_scope: str
    escalation_criteria: EscalationCriteria = Field(
        default_factory=EscalationCriteria,
    )
    procedural_requirements: list[str] = Field(default_factory=list)


class JudicialHierarchy(BaseModel):
    """The full judicial hierarchy configuration."""

    levels: list[JudicialLevelConfig]

    def get_level_config(self, level: JudicialLevel) -> JudicialLevelConfig | None:
        """Get the config for a specific judicial level."""
        level_id = next(
            (k for k, v in LEVEL_ID_MAP.items() if v == level),
            None,
        )
        if level_id is None:
            return None
        for config in self.levels:
            if config.id == level_id:
                return config
        return None

    def get_next_level(self, current: JudicialLevel) -> JudicialLevel | None:
        """Get the next higher judicial level, or None if at highest."""
        try:
            idx = LEVEL_ORDER.index(current)
        except ValueError:
            return None
        if idx >= len(LEVEL_ORDER) - 1:
            return None
        return LEVEL_ORDER[idx + 1]

    def is_highest_level(self, level: JudicialLevel) -> bool:
        """Check if the given level is the highest in the hierarchy."""
        return level == LEVEL_ORDER[-1]


def load_hierarchy(path: Path | None = None) -> JudicialHierarchy:
    """Load the judicial hierarchy from a JSON config file."""
    config_path = path or DEFAULT_HIERARCHY_PATH
    data: dict[str, object] = json.loads(config_path.read_text())
    return JudicialHierarchy.model_validate(data)
