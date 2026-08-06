from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    CLAIMANT = "claimant"
    RESPONDENT = "respondent"


class Argument(BaseModel):
    role: Role
    iteration: int = Field(ge=0)
    content: str
    legal_basis: list[str] = Field(default_factory=list)
    factual_claims: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    evidence_requests: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
