"""Pydantic models for RalphLex case data structures."""

from datetime import UTC, datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    escalated = "escalated"


class JudicialLevel(str, Enum):
    first_instance = "First Instance"
    appeals = "Appeals Court"
    superior = "Superior Court"
    supreme = "Supreme Court"


class Argument(BaseModel):
    role: str = Field(..., description="claimant or respondent")
    iteration: int = Field(..., ge=0)
    content: str
    legal_basis: list[str] = Field(default_factory=list)
    factual_claims: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    evidence_requests: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CourtEvaluation(BaseModel):
    consistency_scores: dict[str, float] = Field(default_factory=dict)
    compliance_assessment: dict[str, str] = Field(default_factory=dict)
    adversarial_review: dict[str, str] = Field(default_factory=dict)
    escalation_decision: Optional[str] = None
    reasoning_trace: list[str] = Field(default_factory=list)


class MCDAResult(BaseModel):
    criteria_scores: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Mapping of criterion -> {claimant: score, respondent: score}",
    )
    weighted_totals: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of party -> weighted total score",
    )
    predicted_winner: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class Case(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    facts: str
    claimant_input: Optional[str] = None
    respondent_input: Optional[str] = None
    status: CaseStatus = CaseStatus.pending
    judicial_level: JudicialLevel = JudicialLevel.first_instance
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
