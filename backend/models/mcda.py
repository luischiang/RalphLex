from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.models.argument import Role


class CriterionScore(BaseModel):
    criterion: str
    claimant_score: float = Field(ge=0, le=10)
    respondent_score: float = Field(ge=0, le=10)
    weight: float = Field(ge=0, le=1)


class MCDAResult(BaseModel):
    case_id: str
    criteria_scores: list[CriterionScore] = Field(default_factory=list)
    weighted_totals: dict[Role, float] = Field(default_factory=dict)
    predicted_winner: Role | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
