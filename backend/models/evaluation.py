from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.models.argument import Role
from backend.models.case import JudicialLevel


class ConsistencyScore(BaseModel):
    role: Role
    score: float = Field(ge=0, le=1)
    notes: str = ""


class ComplianceAssessment(BaseModel):
    compliant: bool
    violations: list[str] = Field(default_factory=list)
    notes: str = ""


class AdversarialReview(BaseModel):
    preliminary_opinion: str
    counter_opinion: str
    reconciled_opinion: str


class EscalationDecision(BaseModel):
    should_escalate: bool
    reasoning: str = ""
    target_level: JudicialLevel | None = None


class CourtEvaluation(BaseModel):
    case_id: str
    consistency_scores: list[ConsistencyScore] = Field(default_factory=list)
    compliance_assessment: ComplianceAssessment
    adversarial_review: AdversarialReview
    escalation_decision: EscalationDecision
    reasoning_trace: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
