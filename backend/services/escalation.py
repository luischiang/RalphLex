"""Escalation engine for determining and executing judicial level escalation."""

import logging
from datetime import UTC, datetime

from backend.models.case import Case, CaseStatus, CourtEvaluation, JudicialLevel
from backend.models.hierarchy import (
    JudicialHierarchy,
    JudicialLevelConfig,
    load_hierarchy,
)
from backend.services.case_folder import CaseFolderManager

logger = logging.getLogger(__name__)

# Mapping from court agent escalation_recommendation strings to criteria keys
RECOMMENDATION_TO_CRITERIA: dict[str, str] = {
    "escalate_constitutional": "constitutional_questions",
    "escalate_conflicting_precedents": "conflicting_precedents",
    "escalate_procedural_grounds": "procedural_irregularities",
}


class EscalationResult:
    """Result of an escalation check."""

    def __init__(
        self,
        *,
        should_escalate: bool,
        reason: str,
        current_level: JudicialLevel,
        next_level: JudicialLevel | None = None,
        triggers: list[str] | None = None,
    ) -> None:
        self.should_escalate = should_escalate
        self.reason = reason
        self.current_level = current_level
        self.next_level = next_level
        self.triggers = triggers or []

    def to_dict(self) -> dict[str, object]:
        return {
            "should_escalate": self.should_escalate,
            "reason": self.reason,
            "current_level": self.current_level.value,
            "next_level": self.next_level.value if self.next_level else None,
            "triggers": self.triggers,
        }


class EscalationEngine:
    """Determines and executes escalation of cases through the judicial hierarchy."""

    def __init__(
        self,
        hierarchy: JudicialHierarchy | None = None,
        folder_manager: CaseFolderManager | None = None,
    ) -> None:
        self.hierarchy = hierarchy or load_hierarchy()
        self.folder_manager = folder_manager

    def check_escalation(
        self,
        evaluation: CourtEvaluation,
        current_level: JudicialLevel,
    ) -> EscalationResult:
        """Determine if escalation is warranted based on the court evaluation.

        Checks:
        1. Whether the case is already at the highest level
        2. Whether the court agent explicitly recommended escalation
        3. Whether any escalation criteria are met for the current level
        """
        # Already at highest level — no escalation possible
        if self.hierarchy.is_highest_level(current_level):
            return EscalationResult(
                should_escalate=False,
                reason="Case is already at the highest judicial level",
                current_level=current_level,
            )

        next_level = self.hierarchy.get_next_level(current_level)
        level_config = self.hierarchy.get_level_config(current_level)

        triggers: list[str] = []

        # Check explicit escalation recommendation from court agent
        recommendation = evaluation.escalation_recommendation or "no_escalation"
        if recommendation != "no_escalation":
            criteria_key = RECOMMENDATION_TO_CRITERIA.get(recommendation)
            if criteria_key:
                triggers.append(
                    f"Court agent recommended escalation: {recommendation}"
                )

            # Verify the recommendation matches allowed criteria at this level
            if level_config and criteria_key:
                criteria = level_config.escalation_criteria
                if getattr(criteria, criteria_key, False):
                    triggers.append(
                        f"Escalation criterion '{criteria_key}' is active "
                        f"at {current_level.value} level"
                    )

        # Check for escalation signals in the evaluation content
        content_triggers = self._detect_content_triggers(evaluation, level_config)
        triggers.extend(content_triggers)

        should_escalate = len(triggers) > 0

        if should_escalate:
            reason = "; ".join(triggers)
            return EscalationResult(
                should_escalate=True,
                reason=reason,
                current_level=current_level,
                next_level=next_level,
                triggers=triggers,
            )

        return EscalationResult(
            should_escalate=False,
            reason="No escalation criteria met",
            current_level=current_level,
        )

    def _detect_content_triggers(
        self,
        evaluation: CourtEvaluation,
        level_config: JudicialLevelConfig | None,
    ) -> list[str]:
        """Detect escalation triggers from the evaluation content."""
        triggers: list[str] = []
        if not level_config:
            return triggers

        criteria = level_config.escalation_criteria

        # Check reasoning trace and adversarial review for trigger keywords
        all_text = " ".join(evaluation.reasoning_trace)
        all_text += " " + evaluation.adversarial_challenge
        all_text += " " + evaluation.reconciled_decision
        all_text_lower = all_text.lower()

        if criteria.constitutional_questions and (
            "constitutional" in all_text_lower
            and ("question" in all_text_lower or "issue" in all_text_lower)
        ):
            triggers.append("Constitutional question detected in evaluation")

        if criteria.conflicting_precedents and (
            "conflicting precedent" in all_text_lower
            or "contradictory precedent" in all_text_lower
        ):
            triggers.append("Conflicting precedents detected in evaluation")

        if criteria.procedural_irregularities and (
            "procedural irregularit" in all_text_lower
            or "procedural violation" in all_text_lower
        ):
            triggers.append("Procedural irregularity detected in evaluation")

        return triggers

    def execute_escalation(
        self,
        case: Case,
        evaluation: CourtEvaluation,
        escalation_result: EscalationResult,
    ) -> Case:
        """Execute the escalation: archive results, update case level.

        Args:
            case: The case to escalate.
            evaluation: The current court evaluation.
            escalation_result: The escalation check result.

        Returns:
            The updated case with new judicial level and escalated status.
        """
        if not escalation_result.should_escalate or not escalation_result.next_level:
            return case

        old_level = case.judicial_level

        # Archive current level results
        if self.folder_manager:
            self._archive_level_results(case.id, old_level)

        # Update case
        case.judicial_level = escalation_result.next_level
        case.status = CaseStatus.escalated
        case.updated_at = datetime.now(UTC)

        # Save escalation record
        if self.folder_manager:
            escalation_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "from_level": old_level.value,
                "to_level": escalation_result.next_level.value,
                "reason": escalation_result.reason,
                "triggers": escalation_result.triggers,
            }
            self.folder_manager.save_output(
                case.id,
                f"escalation_{old_level.value.lower().replace(' ', '_')}.json",
                escalation_record,
            )
            self.folder_manager.update_case(case)

        logger.info(
            "Case %s escalated from %s to %s: %s",
            case.id,
            old_level.value,
            escalation_result.next_level.value,
            escalation_result.reason,
        )

        return case

    def _archive_level_results(self, case_id: str, level: JudicialLevel) -> None:
        """Archive current level outputs before escalation."""
        if not self.folder_manager:
            return

        case_dir = self.folder_manager.case_dir(case_id)
        outputs_dir = case_dir / "outputs"
        level_slug = level.value.lower().replace(" ", "_")
        archive_dir = outputs_dir / f"level_{level_slug}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Move current output files to the archive directory
        for output_file in outputs_dir.iterdir():
            if output_file.is_file() and output_file.suffix == ".json":
                dest = archive_dir / output_file.name
                output_file.rename(dest)

    def prepare_escalation_context(
        self,
        case: Case,
        previous_evaluation: CourtEvaluation,
        escalation_result: EscalationResult,
    ) -> dict[str, object]:
        """Prepare context for re-running the argument loop at the next level.

        Returns a dict with additional prompt context reflecting the higher
        court's standards and scope.
        """
        next_level = escalation_result.next_level
        if not next_level:
            return {}

        level_config = self.hierarchy.get_level_config(next_level)
        if not level_config:
            return {}

        # Load archived evaluation if available
        previous_decision = previous_evaluation.reconciled_decision

        context: dict[str, object] = {
            "judicial_level": next_level.value,
            "jurisdiction_scope": level_config.jurisdiction_scope,
            "procedural_requirements": level_config.procedural_requirements,
            "escalation_reason": escalation_result.reason,
            "escalation_triggers": escalation_result.triggers,
            "previous_level": escalation_result.current_level.value,
            "previous_decision": previous_decision,
            "higher_court_instructions": (
                f"You are now operating at the {next_level.value} level. "
                f"Scope: {level_config.jurisdiction_scope}. "
                f"The case was escalated from {escalation_result.current_level.value} "
                f"because: {escalation_result.reason}. "
                f"Focus your analysis on the specific grounds for escalation. "
                f"Requirements: {', '.join(level_config.procedural_requirements)}."
            ),
        }

        return context
