"""Full case orchestrator implementing the Ralph Loop pattern.

Ties together: case intake -> argument iteration -> legal reference retrieval
-> court evaluation with adversarial review -> MCDA scoring -> escalation
check -> next judicial level loop or final resolution.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.agents.claimant import ClaimantAgent
from backend.agents.court import CourtAgent
from backend.agents.respondent import RespondentAgent
from backend.config import settings
from backend.evaluation.cost_estimator import CostEstimator
from backend.legal_db.store import (
    LegalStore,
    retrieve_laws_with_fallback,
    retrieve_precedents_with_fallback,
)
from backend.models.case import (
    Argument,
    Case,
    CaseStatus,
    CourtEvaluation,
    MCDAResult,
)
from backend.services.argument_loop import ArgumentLoop, ArgumentLoopResult
from backend.services.case_folder import CaseFolderManager
from backend.services.escalation import EscalationEngine

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorProgress:
    """Tracks the current phase and progress of orchestration."""

    phase: str = "pending"
    iteration: int = 0
    judicial_level: str = "First Instance"
    message: str = ""
    started_at: str = ""
    updated_at: str = ""


@dataclass
class OrchestratorResult:
    """Complete output from the orchestration pipeline."""

    judicial_stage: str = ""
    arguments_summary: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    referenced_precedents: list[str] = field(default_factory=list)
    referenced_laws: list[str] = field(default_factory=list)
    court_evaluation: dict[str, object] = field(default_factory=dict)
    escalation_decisions: list[dict[str, object]] = field(default_factory=list)
    mcda_scoring: dict[str, object] = field(default_factory=dict)
    predicted_winner: str | None = None
    confidence_estimate: float = 0.0
    full_reasoning_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "judicial_stage": self.judicial_stage,
            "arguments_summary": self.arguments_summary,
            "referenced_precedents": self.referenced_precedents,
            "referenced_laws": self.referenced_laws,
            "court_evaluation": self.court_evaluation,
            "escalation_decisions": self.escalation_decisions,
            "mcda_scoring": self.mcda_scoring,
            "predicted_winner": self.predicted_winner,
            "confidence_estimate": self.confidence_estimate,
            "full_reasoning_trace": self.full_reasoning_trace,
        }


# In-memory progress tracker for running cases
_progress: dict[str, OrchestratorProgress] = {}


def get_progress(case_id: str) -> OrchestratorProgress | None:
    """Get the current orchestration progress for a case."""
    return _progress.get(case_id)


def _update_progress(case_id: str, phase: str, message: str, **kwargs: object) -> None:
    """Update the progress tracker for a case."""
    prog = _progress.get(case_id)
    if prog is None:
        prog = OrchestratorProgress()
        _progress[case_id] = prog
    prog.phase = phase
    prog.message = message
    prog.updated_at = datetime.now(UTC).isoformat()
    for key, value in kwargs.items():
        if hasattr(prog, key):
            setattr(prog, key, value)


def _summarize_arguments(
    arguments: list[Argument],
) -> list[dict[str, object]]:
    """Summarize a list of arguments for the final output."""
    summaries: list[dict[str, object]] = []
    for arg in arguments:
        summaries.append(
            {
                "iteration": arg.iteration,
                "role": arg.role,
                "content": arg.content[:500],
                "legal_basis": arg.legal_basis,
                "factual_claims": arg.factual_claims,
            }
        )
    return summaries


class CaseOrchestrator:
    """Orchestrates the full Ralph Loop pipeline for a case.

    Pipeline: case intake -> argument iteration -> legal reference retrieval
    -> court evaluation -> MCDA scoring -> escalation check -> loop or resolve.
    """

    def __init__(
        self,
        folder_manager: CaseFolderManager | None = None,
        legal_store: LegalStore | None = None,
        escalation_engine: EscalationEngine | None = None,
        *,
        claimant_agent: ClaimantAgent | None = None,
        respondent_agent: RespondentAgent | None = None,
        court_agent: CourtAgent | None = None,
        max_iterations: int = 5,
        max_escalations: int = 3,
    ) -> None:
        self.folder_manager = folder_manager or CaseFolderManager()
        self.legal_store = legal_store
        self.max_iterations = max_iterations
        self.max_escalations = max_escalations

        self.claimant_agent = claimant_agent or ClaimantAgent()
        self.respondent_agent = respondent_agent or RespondentAgent()
        self.court_agent = court_agent or CourtAgent()
        self.escalation_engine = escalation_engine or EscalationEngine(
            folder_manager=self.folder_manager
        )

    async def run(self, case_id: str) -> OrchestratorResult:
        """Run the full orchestration pipeline for a case.

        Args:
            case_id: The case ID to orchestrate.

        Returns:
            OrchestratorResult with all output fields populated.
        """
        result = OrchestratorResult()
        escalation_count = 0
        total_argument_rounds = 0

        # Load case
        case = self.folder_manager.load(case_id)
        case.status = CaseStatus.running
        case.updated_at = datetime.now(UTC)
        self.folder_manager.update_case(case)

        _update_progress(
            case_id,
            "started",
            "Orchestration started",
            judicial_level=case.judicial_level.value,
            started_at=datetime.now(UTC).isoformat(),
        )

        try:
            while escalation_count <= self.max_escalations:
                level_label = case.judicial_level.value
                result.judicial_stage = level_label

                # Phase 1: Argument iteration
                _update_progress(
                    case_id,
                    "arguing",
                    f"Running argument loop at {level_label}",
                    judicial_level=level_label,
                )

                loop_result = await self._run_argument_loop(case)
                total_argument_rounds += loop_result.iterations_completed

                result.arguments_summary = {
                    "claimant": _summarize_arguments(loop_result.claimant_arguments),
                    "respondent": _summarize_arguments(loop_result.respondent_arguments),
                }

                # Phase 2: Legal reference retrieval
                _update_progress(
                    case_id,
                    "retrieving_references",
                    f"Retrieving legal references at {level_label}",
                )

                precedent_strs, law_strs = await self._retrieve_references(case)
                result.referenced_precedents = precedent_strs
                result.referenced_laws = law_strs

                # Phase 3: Court evaluation with adversarial review + MCDA
                _update_progress(
                    case_id,
                    "evaluating",
                    f"Court evaluation at {level_label}",
                )

                evaluation, mcda_result = await self._evaluate(
                    case,
                    loop_result,
                    precedent_strs,
                    law_strs,
                )

                result.court_evaluation = evaluation.model_dump(mode="json")
                result.mcda_scoring = mcda_result.model_dump(mode="json")
                result.predicted_winner = mcda_result.predicted_winner
                result.confidence_estimate = mcda_result.confidence
                result.full_reasoning_trace.extend(evaluation.reasoning_trace)

                # Phase 4: Escalation check
                _update_progress(
                    case_id,
                    "checking_escalation",
                    f"Checking escalation at {level_label}",
                )

                esc_result = self.escalation_engine.check_escalation(
                    evaluation, case.judicial_level
                )

                if esc_result.should_escalate:
                    result.escalation_decisions.append(esc_result.to_dict())

                    _update_progress(
                        case_id,
                        "escalating",
                        (
                            f"Escalating from {level_label} to "
                            f"{esc_result.next_level.value if esc_result.next_level else 'unknown'}"
                        ),
                    )

                    case = self.escalation_engine.execute_escalation(case, evaluation, esc_result)
                    escalation_count += 1
                    result.full_reasoning_trace.append(
                        f"Escalated to {case.judicial_level.value}: {esc_result.reason}"
                    )
                    continue

                # No escalation — resolve
                break

            # Finalize
            case.status = CaseStatus.completed
            case.updated_at = datetime.now(UTC)
            self.folder_manager.update_case(case)

            # Save final output
            self.folder_manager.save_output(case_id, "final_result.json", result.to_dict())

            # Compute and save litigation cost estimate
            cost_estimator = CostEstimator()
            cost_estimate = cost_estimator.estimate(
                final_judicial_level=case.judicial_level.value,
                escalation_decisions=result.escalation_decisions,
                argument_rounds=total_argument_rounds,
                created_at=case.created_at,
                completed_at=case.updated_at,
                llm_provider=settings.llm_provider,
            )
            self.folder_manager.save_output(
                case_id, "cost_estimate.json", cost_estimate.to_dict()
            )

            _update_progress(
                case_id,
                "completed",
                "Case resolved",
                judicial_level=case.judicial_level.value,
            )

            self.folder_manager.save_state(
                case_id,
                {
                    "status": case.status.value,
                    "judicial_level": case.judicial_level.value,
                    "phase": "completed",
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )

        except Exception:
            logger.exception("Orchestration failed for case %s", case_id)
            case.status = CaseStatus.pending
            case.updated_at = datetime.now(UTC)
            self.folder_manager.update_case(case)
            _update_progress(case_id, "failed", "Orchestration failed")
            raise

        return result

    async def _run_argument_loop(self, case: Case) -> ArgumentLoopResult:
        """Run the claimant/respondent argument iteration."""
        loop = ArgumentLoop(
            claimant_agent=self.claimant_agent,
            respondent_agent=self.respondent_agent,
            folder_manager=self.folder_manager,
            max_iterations=self.max_iterations,
        )
        return await loop.run(case.id, case.facts)

    async def _retrieve_references(self, case: Case) -> tuple[list[str], list[str]]:
        """Retrieve legal precedents and laws relevant to the case."""
        if not self.legal_store:
            return [], []

        query = case.facts[:500]

        precedents, web_precedents = await retrieve_precedents_with_fallback(
            self.legal_store, query
        )
        laws, web_laws = await retrieve_laws_with_fallback(self.legal_store, query)

        precedent_strs = [
            f"{p.case_name} ({p.year}, {p.jurisdiction}): {p.summary}" for p in precedents
        ]
        for wp in web_precedents:
            precedent_strs.append(f"[Web] {wp.get('title', '')}: {wp.get('snippet', '')}")

        law_strs = [
            f"{law.code} {law.article} ({law.jurisdiction}): {law.text[:200]}" for law in laws
        ]
        for wl in web_laws:
            law_strs.append(f"[Web] {wl.get('title', '')}: {wl.get('snippet', '')}")

        return precedent_strs, law_strs

    async def _evaluate(
        self,
        case: Case,
        loop_result: ArgumentLoopResult,
        precedent_strs: list[str],
        law_strs: list[str],
    ) -> tuple[CourtEvaluation, MCDAResult]:
        """Run court evaluation with adversarial review and MCDA."""
        return await self.court_agent.evaluate(
            case_facts=case.facts,
            claimant_arguments=loop_result.claimant_arguments,
            respondent_arguments=loop_result.respondent_arguments,
            precedents=precedent_strs,
            laws=law_strs,
            folder_manager=self.folder_manager,
            case_id=case.id,
        )
