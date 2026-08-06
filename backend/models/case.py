from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class CaseStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ESCALATED = "escalated"


class JudicialLevel(StrEnum):
    FIRST_INSTANCE = "first_instance"
    APPEALS_COURT = "appeals_court"
    SUPERIOR_COURT = "superior_court"
    SUPREME_COURT = "supreme_court"


class Case(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    facts: str
    claimant_input: str | None = None
    respondent_input: str | None = None
    status: CaseStatus = CaseStatus.PENDING
    judicial_level: JudicialLevel = JudicialLevel.FIRST_INSTANCE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
