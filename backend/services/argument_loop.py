"""Argument loop orchestrator for iterative claimant/respondent exchanges.

Alternates between claimant and respondent agents until both converge
or max_iterations is reached.
"""

import logging
from dataclasses import dataclass, field

from backend.agents.claimant import ClaimantAgent
from backend.agents.respondent import RespondentAgent
from backend.models.case import Argument
from backend.services.case_folder import CaseFolderManager
from backend.services.convergence import has_converged

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 5
DEFAULT_CONVERGENCE_THRESHOLD = 0.85


@dataclass
class ArgumentLoopResult:
    """Result of running the argument loop."""

    claimant_arguments: list[Argument] = field(default_factory=list)
    respondent_arguments: list[Argument] = field(default_factory=list)
    claimant_converged: bool = False
    respondent_converged: bool = False
    iterations_completed: int = 0


class ArgumentLoop:
    """Orchestrates the iterative argument exchange between claimant and respondent."""

    def __init__(
        self,
        claimant_agent: ClaimantAgent,
        respondent_agent: RespondentAgent,
        folder_manager: CaseFolderManager,
        *,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        convergence_threshold: float = DEFAULT_CONVERGENCE_THRESHOLD,
    ) -> None:
        self.claimant_agent = claimant_agent
        self.respondent_agent = respondent_agent
        self.folder_manager = folder_manager
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

    async def run(self, case_id: str, case_facts: str) -> ArgumentLoopResult:
        """Run the argument loop for a case.

        Alternates between claimant and respondent, persisting each
        iteration to the case folder. Stops when both sides converge
        or max_iterations is reached.

        Args:
            case_id: The case identifier for folder persistence.
            case_facts: The facts of the case to argue about.

        Returns:
            ArgumentLoopResult with all arguments and convergence status.
        """
        result = ArgumentLoopResult()

        for iteration in range(self.max_iterations):
            logger.info("Case %s: Starting iteration %d", case_id, iteration)

            # Claimant argues (responds to latest respondent argument if any)
            opponent_arg = result.respondent_arguments[-1] if result.respondent_arguments else None
            claimant_arg = await self.claimant_agent.generate_argument(
                case_facts=case_facts,
                iteration=iteration,
                opponent_argument=opponent_arg,
            )
            result.claimant_arguments.append(claimant_arg)
            self.folder_manager.save_iteration(
                case_id, iteration, "claimant", claimant_arg.model_dump(mode="json")
            )

            # Check claimant convergence (need at least 2 arguments)
            if len(result.claimant_arguments) >= 2:
                result.claimant_converged = has_converged(
                    result.claimant_arguments[-1],
                    result.claimant_arguments[-2],
                    threshold=self.convergence_threshold,
                )

            # Respondent argues (responds to latest claimant argument)
            respondent_arg = await self.respondent_agent.generate_argument(
                case_facts=case_facts,
                iteration=iteration,
                opponent_argument=claimant_arg,
            )
            result.respondent_arguments.append(respondent_arg)
            self.folder_manager.save_iteration(
                case_id, iteration, "respondent", respondent_arg.model_dump(mode="json")
            )

            # Check respondent convergence
            if len(result.respondent_arguments) >= 2:
                result.respondent_converged = has_converged(
                    result.respondent_arguments[-1],
                    result.respondent_arguments[-2],
                    threshold=self.convergence_threshold,
                )

            result.iterations_completed = iteration + 1

            # Stop if both sides have converged
            if result.claimant_converged and result.respondent_converged:
                logger.info(
                    "Case %s: Both sides converged after %d iterations",
                    case_id,
                    result.iterations_completed,
                )
                break

        if not (result.claimant_converged and result.respondent_converged):
            logger.info(
                "Case %s: Max iterations (%d) reached without full convergence",
                case_id,
                self.max_iterations,
            )

        return result
