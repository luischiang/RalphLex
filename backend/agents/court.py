"""Court agent with adversarial internal review and consistency verification."""

import json
import logging
from typing import Any

import anthropic

from backend.agents.base import LLMAgent
from backend.evaluation.mcda import MCDA_RATING_SCHEMA, evaluate_mcda
from backend.models.case import Argument, CourtEvaluation, MCDAResult
from backend.services.case_folder import CaseFolderManager

logger = logging.getLogger(__name__)

COURT_SYSTEM_PROMPT = (
    "You are an impartial judicial agent presiding over a pre-trial "
    "dispute resolution proceeding.\n\n"
    "Your role is to evaluate both sides' arguments with rigorous "
    "legal analysis. You must NOT simply summarize the arguments. "
    "Instead, you must independently verify consistency, test "
    "compliance with applicable law, and form your own judicial "
    "opinion based on the evidence and legal principles presented.\n\n"
    "You must respond with ONLY valid JSON matching the required schema. "
    "Do not include any text outside the JSON object."
)

# Phase 1: Consistency analysis + compliance check + preliminary opinion
PHASE1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "consistency_analysis": {
            "type": "object",
            "properties": {
                "claimant_score": {
                    "type": "number",
                    "description": ("Internal consistency score for claimant (0-1)"),
                },
                "respondent_score": {
                    "type": "number",
                    "description": ("Internal consistency score for respondent (0-1)"),
                },
                "claimant_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Inconsistencies found in claimant arguments",
                },
                "respondent_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": ("Inconsistencies found in respondent arguments"),
                },
            },
            "required": [
                "claimant_score",
                "respondent_score",
                "claimant_issues",
                "respondent_issues",
            ],
        },
        "compliance_check": {
            "type": "object",
            "properties": {
                "claimant_compliance": {
                    "type": "string",
                    "description": ("Assessment of claimant's compliance with applicable law"),
                },
                "respondent_compliance": {
                    "type": "string",
                    "description": ("Assessment of respondent's compliance with applicable law"),
                },
                "violations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any legal violations identified",
                },
            },
            "required": [
                "claimant_compliance",
                "respondent_compliance",
                "violations",
            ],
        },
        "preliminary_opinion": {
            "type": "string",
            "description": (
                "The court's preliminary judicial conclusion based on the analysis so far"
            ),
        },
        "reasoning_trace": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Step-by-step reasoning leading to the opinion",
        },
    },
    "required": [
        "consistency_analysis",
        "compliance_check",
        "preliminary_opinion",
        "reasoning_trace",
    ],
}

# Phase 2: Adversarial challenge to the preliminary opinion
PHASE2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "adversarial_challenge": {
            "type": "string",
            "description": (
                "A rigorous counter-opinion challenging the preliminary "
                "conclusion. Must identify weaknesses, alternative "
                "interpretations, and potential errors in the "
                "preliminary opinion."
            ),
        },
        "challenge_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": ("Specific points of challenge against the preliminary opinion"),
        },
    },
    "required": ["adversarial_challenge", "challenge_points"],
}

# Phase 3: Reconciliation of preliminary opinion and adversarial challenge
PHASE3_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reconciled_decision": {
            "type": "string",
            "description": (
                "The final judicial decision after reconciling the "
                "preliminary opinion with the adversarial challenge"
            ),
        },
        "escalation_recommendation": {
            "type": "string",
            "description": (
                "Whether the case should escalate to a higher court. "
                "One of: 'no_escalation', 'escalate_constitutional', "
                "'escalate_conflicting_precedents', "
                "'escalate_procedural_grounds'"
            ),
        },
        "escalation_reasoning": {
            "type": "string",
            "description": "Reasoning for the escalation decision",
        },
    },
    "required": [
        "reconciled_decision",
        "escalation_recommendation",
        "escalation_reasoning",
    ],
}


def _format_arguments(arguments: list[Argument]) -> str:
    """Format a list of arguments for inclusion in a prompt."""
    parts: list[str] = []
    for arg in arguments:
        parts.append(
            f"### Iteration {arg.iteration} ({arg.role})\n"
            f"{arg.content}\n\n"
            f"Legal basis: {json.dumps(arg.legal_basis)}\n"
            f"Factual claims: {json.dumps(arg.factual_claims)}\n"
            f"Counterarguments: {json.dumps(arg.counterarguments)}\n"
            f"Evidence requests: {json.dumps(arg.evidence_requests)}"
        )
    return "\n\n".join(parts)


class CourtAgent(LLMAgent):
    """Judicial agent that evaluates both sides with adversarial self-review.

    The evaluation proceeds in three phases:
    1. Consistency analysis, compliance check, and preliminary opinion
    2. Adversarial self-challenge of the preliminary opinion
    3. Reconciliation into a final decision with escalation recommendation
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        super().__init__(
            system_prompt=COURT_SYSTEM_PROMPT,
            model=model,
            temperature=temperature,
            client=client,
        )

    async def evaluate(
        self,
        case_facts: str,
        claimant_arguments: list[Argument],
        respondent_arguments: list[Argument],
        precedents: list[str] | None = None,
        laws: list[str] | None = None,
        folder_manager: CaseFolderManager | None = None,
        case_id: str | None = None,
        refinement_instructions: str | None = None,
    ) -> tuple[CourtEvaluation, MCDAResult]:
        """Run the full three-phase adversarial evaluation.

        Args:
            case_facts: The facts of the case.
            claimant_arguments: Stable arguments from the claimant side.
            respondent_arguments: Stable arguments from the respondent side.
            precedents: Referenced legal precedents.
            laws: Applicable laws and statutes.
            folder_manager: Optional, to persist output to case folder.
            case_id: Required if folder_manager is provided.

        Returns:
            A CourtEvaluation with all sections populated.
        """
        # Reset history between phases to keep prompts focused
        self.reset_history()

        # --- Phase 1: Consistency + Compliance + Preliminary Opinion ---
        phase1_prompt = self._build_phase1_prompt(
            case_facts,
            claimant_arguments,
            respondent_arguments,
            precedents or [],
            laws or [],
            refinement_instructions=refinement_instructions,
        )
        phase1 = await self.call_structured(phase1_prompt, output_schema=PHASE1_SCHEMA)

        self.reset_history()

        # --- Phase 2: Adversarial Challenge ---
        phase2_prompt = self._build_phase2_prompt(
            phase1["preliminary_opinion"],
            phase1["reasoning_trace"],
        )
        phase2 = await self.call_structured(phase2_prompt, output_schema=PHASE2_SCHEMA)

        self.reset_history()

        # --- Phase 3: Reconciliation ---
        phase3_prompt = self._build_phase3_prompt(
            phase1["preliminary_opinion"],
            phase2["adversarial_challenge"],
            phase2.get("challenge_points", []),
        )
        phase3 = await self.call_structured(phase3_prompt, output_schema=PHASE3_SCHEMA)

        # --- Phase 4: MCDA Scoring ---
        self.reset_history()

        phase4_prompt = self._build_mcda_prompt(
            case_facts,
            claimant_arguments,
            respondent_arguments,
            phase3["reconciled_decision"],
        )
        phase4 = await self.call_structured(phase4_prompt, output_schema=MCDA_RATING_SCHEMA)

        # Extract MCDA criteria scores from LLM ratings
        ratings = phase4.get("ratings", {})
        criteria_scores: dict[str, dict[str, float]] = {}
        for criterion, party_scores in ratings.items():
            if isinstance(party_scores, dict):
                criteria_scores[criterion] = {
                    party: float(score) for party, score in party_scores.items()
                }

        mcda_result = evaluate_mcda(
            criteria_scores=criteria_scores,
            folder_manager=folder_manager,
            case_id=case_id,
        )

        # Build the CourtEvaluation
        consistency = phase1["consistency_analysis"]
        compliance = phase1["compliance_check"]

        evaluation = CourtEvaluation(
            consistency_scores={
                "claimant": float(consistency["claimant_score"]),
                "respondent": float(consistency["respondent_score"]),
            },
            compliance_assessment={
                "claimant": compliance["claimant_compliance"],
                "respondent": compliance["respondent_compliance"],
                "violations": "; ".join(compliance.get("violations", [])),
            },
            preliminary_opinion=phase1["preliminary_opinion"],
            adversarial_challenge=phase2["adversarial_challenge"],
            reconciled_decision=phase3["reconciled_decision"],
            escalation_recommendation=phase3["escalation_recommendation"],
            escalation_decision=phase3["escalation_recommendation"],
            adversarial_review={
                "challenge": phase2["adversarial_challenge"],
                "challenge_points": "; ".join(phase2.get("challenge_points", [])),
                "reconciliation": phase3["reconciled_decision"],
                "escalation_reasoning": phase3.get("escalation_reasoning", ""),
            },
            reasoning_trace=phase1.get("reasoning_trace", []),
        )

        # Persist to case folder if provided
        if folder_manager and case_id:
            folder_manager.save_output(
                case_id,
                "court_evaluation.json",
                evaluation.model_dump(mode="json"),
            )

        return evaluation, mcda_result

    def _build_phase1_prompt(
        self,
        case_facts: str,
        claimant_arguments: list[Argument],
        respondent_arguments: list[Argument],
        precedents: list[str],
        laws: list[str],
        refinement_instructions: str | None = None,
    ) -> str:
        parts = [
            "## Case Facts",
            case_facts,
            "\n## Claimant's Arguments",
            _format_arguments(claimant_arguments),
            "\n## Respondent's Arguments",
            _format_arguments(respondent_arguments),
        ]

        if precedents:
            parts.append("\n## Referenced Precedents")
            for p in precedents:
                parts.append(f"- {p}")

        if laws:
            parts.append("\n## Applicable Laws")
            for law in laws:
                parts.append(f"- {law}")

        if refinement_instructions:
            parts.append(f"\n## Refinement Context\n{refinement_instructions}")

        parts.append(
            "\n## Your Task\n"
            "Analyze both sides' arguments and produce:\n"
            "1. Consistency analysis: Score each side's internal "
            "consistency (0-1) and list any inconsistencies found.\n"
            "2. Compliance check: Assess each side's compliance with "
            "applicable law and flag any violations.\n"
            "3. Preliminary opinion: Form your initial judicial "
            "conclusion based on the evidence and analysis.\n"
            "4. Reasoning trace: Document your step-by-step reasoning."
        )

        return "\n".join(parts)

    def _build_phase2_prompt(
        self,
        preliminary_opinion: str,
        reasoning_trace: list[str],
    ) -> str:
        trace_str = "\n".join(f"- {step}" for step in reasoning_trace)
        return (
            "## Preliminary Opinion\n"
            f"{preliminary_opinion}\n\n"
            "## Reasoning Trace\n"
            f"{trace_str}\n\n"
            "## Your Task\n"
            "You must now act as an adversarial reviewer challenging "
            "the preliminary opinion above. Generate a rigorous "
            "counter-opinion that:\n"
            "1. Identifies weaknesses in the preliminary conclusion\n"
            "2. Proposes alternative interpretations of the evidence\n"
            "3. Highlights potential errors in legal reasoning\n"
            "4. Considers arguments that may have been underweighted\n"
            "5. Challenges any assumptions made\n\n"
            "Be thorough and critical — the goal is to stress-test "
            "the preliminary opinion, not to confirm it."
        )

    def _build_mcda_prompt(
        self,
        case_facts: str,
        claimant_arguments: list[Argument],
        respondent_arguments: list[Argument],
        reconciled_decision: str,
    ) -> str:
        return (
            "## Case Facts\n"
            f"{case_facts}\n\n"
            "## Claimant's Arguments\n"
            f"{_format_arguments(claimant_arguments)}\n\n"
            "## Respondent's Arguments\n"
            f"{_format_arguments(respondent_arguments)}\n\n"
            "## Reconciled Decision\n"
            f"{reconciled_decision}\n\n"
            "## Your Task\n"
            "Rate each party on the following criteria using a 1-10 scale "
            "(1 = very weak, 10 = very strong):\n\n"
            "1. **evidentiary_strength**: Quality and relevance of "
            "evidence presented\n"
            "2. **legal_consistency**: Internal consistency of legal "
            "arguments and reasoning\n"
            "3. **procedural_validity**: Adherence to procedural "
            "requirements and formalities\n"
            "4. **precedent_alignment**: Alignment with established "
            "legal precedents\n"
            "5. **appeal_likelihood**: Likelihood that an appeal would "
            "succeed (lower = less likely to be overturned)\n\n"
            "Provide ratings for both claimant and respondent on each "
            "criterion, along with a brief justification."
        )

    def _build_phase3_prompt(
        self,
        preliminary_opinion: str,
        adversarial_challenge: str,
        challenge_points: list[str],
    ) -> str:
        points_str = "\n".join(f"- {p}" for p in challenge_points)
        return (
            "## Preliminary Opinion\n"
            f"{preliminary_opinion}\n\n"
            "## Adversarial Challenge\n"
            f"{adversarial_challenge}\n\n"
            "## Challenge Points\n"
            f"{points_str}\n\n"
            "## Your Task\n"
            "Reconcile the preliminary opinion with the adversarial "
            "challenge to produce a final, balanced judicial decision. "
            "Address each challenge point and explain whether it "
            "changes the original conclusion. Also determine whether "
            "this case should escalate to a higher court based on:\n"
            "- Constitutional questions raised\n"
            "- Conflicting precedents detected\n"
            "- Procedural irregularities\n\n"
            "For escalation_recommendation, use one of: "
            "'no_escalation', 'escalate_constitutional', "
            "'escalate_conflicting_precedents', "
            "'escalate_procedural_grounds'"
        )
