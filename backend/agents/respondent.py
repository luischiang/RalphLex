"""Respondent agent for generating legal arguments from the respondent's perspective."""

import json
from typing import Any

import anthropic

from backend.agents.base import LLMAgent
from backend.models.case import Argument

RESPONDENT_SYSTEM_PROMPT = (
    "You are a legal advocate representing the RESPONDENT "
    "in a pre-trial dispute resolution proceeding.\n\n"
    "Your role is to construct the strongest possible legal defense "
    "against the claimant's claims. You must analyze the case facts, "
    "identify applicable legal principles, and build a persuasive defense.\n\n"
    "When responding to the opponent's arguments, you must:\n"
    "1. Address each argument directly with evidence and legal reasoning\n"
    "2. Identify weaknesses in the claimant's position\n"
    "3. Strengthen your own defense based on the exchange\n"
    "4. Request specific evidence that would support your position\n"
    "5. Reference applicable legal precedents and statutes\n\n"
    "You must respond with ONLY valid JSON matching the required schema. "
    "Do not include any text outside the JSON object."
)

ARGUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "Main argument narrative"},
        "legal_basis": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Legal principles, statutes, or precedents supporting the defense",
        },
        "factual_claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Factual assertions supporting the position",
        },
        "counterarguments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Responses to the claimant's arguments",
        },
        "evidence_requests": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Evidence that would strengthen the defense if available",
        },
        "strategy_notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Internal strategy observations for future iterations",
        },
    },
    "required": [
        "content",
        "legal_basis",
        "factual_claims",
        "counterarguments",
        "evidence_requests",
        "strategy_notes",
    ],
}


class RespondentAgent(LLMAgent):
    """Agent that argues from the respondent's perspective."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        super().__init__(
            system_prompt=RESPONDENT_SYSTEM_PROMPT,
            model=model,
            temperature=temperature,
            client=client,
        )

    async def generate_argument(
        self,
        case_facts: str,
        iteration: int,
        opponent_argument: Argument | None = None,
    ) -> Argument:
        """Generate a structured argument for the respondent.

        Args:
            case_facts: The facts of the case.
            iteration: Current iteration number.
            opponent_argument: The claimant's latest argument, if any.

        Returns:
            An Argument model with the respondent's position.
        """
        prompt_parts = [f"## Case Facts\n{case_facts}"]

        if opponent_argument:
            prompt_parts.append(
                f"\n## Claimant's Argument (Iteration {opponent_argument.iteration})\n"
                f"{opponent_argument.content}\n\n"
                f"Legal basis: {json.dumps(opponent_argument.legal_basis)}\n"
                f"Factual claims: {json.dumps(opponent_argument.factual_claims)}\n"
                f"Counterarguments: {json.dumps(opponent_argument.counterarguments)}"
            )
            prompt_parts.append(
                "\n## Your Task\n"
                "Construct your strongest defense responding to the claimant's arguments. "
                "Address their points directly and strengthen your defense."
            )
        else:
            prompt_parts.append(
                "\n## Your Task\n"
                "Construct your opening defense for the respondent. "
                "Present the strongest defense based on the facts provided."
            )

        prompt = "\n".join(prompt_parts)
        result = await self.call_structured(prompt, output_schema=ARGUMENT_SCHEMA)

        return Argument(
            role="respondent",
            iteration=iteration,
            content=result["content"],
            legal_basis=result.get("legal_basis", []),
            factual_claims=result.get("factual_claims", []),
            counterarguments=result.get("counterarguments", []),
            evidence_requests=result.get("evidence_requests", []),
            strategy_notes=result.get("strategy_notes", []),
        )
