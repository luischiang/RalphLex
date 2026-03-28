"""Multi-Criteria Decision Analysis scoring for case evaluation."""

import json
import logging
from pathlib import Path
from typing import Any

from backend.models.case import MCDAResult
from backend.services.case_folder import CaseFolderManager

logger = logging.getLogger(__name__)

CRITERIA = [
    "evidentiary_strength",
    "legal_consistency",
    "procedural_validity",
    "precedent_alignment",
    "appeal_likelihood",
]

WEIGHTS_PATH = Path(__file__).parent / "weights.json"


def load_weights(path: Path | None = None) -> dict[str, float]:
    """Load MCDA criteria weights from a JSON file.

    Args:
        path: Path to weights JSON file. Defaults to weights.json in this dir.

    Returns:
        Mapping of criterion name to weight (should sum to ~1.0).
    """
    weights_file = path or WEIGHTS_PATH
    with open(weights_file) as f:
        weights: dict[str, float] = json.load(f)
    return weights


def compute_weighted_scores(
    criteria_scores: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> dict[str, float]:
    """Compute weighted total scores for each party.

    Args:
        criteria_scores: {criterion: {party: raw_score(1-10)}}
        weights: {criterion: weight}

    Returns:
        {party: weighted_total} normalized to 0-1 range.
    """
    # Collect all parties from the scores
    parties: set[str] = set()
    for party_scores in criteria_scores.values():
        parties.update(party_scores.keys())

    totals: dict[str, float] = {party: 0.0 for party in parties}

    for criterion, party_scores in criteria_scores.items():
        weight = weights.get(criterion, 0.0)
        for party, raw_score in party_scores.items():
            # Normalize raw score from 1-10 to 0-1, then apply weight
            normalized = (raw_score - 1.0) / 9.0 if raw_score > 1.0 else 0.0
            totals[party] += weight * normalized

    return totals


def determine_winner(
    weighted_totals: dict[str, float],
) -> tuple[str | None, float]:
    """Determine predicted winner and confidence from weighted totals.

    Confidence is based on the score differential and ranges from 0 to 1.
    A small differential yields low confidence; a large one yields high.

    Args:
        weighted_totals: {party: normalized_weighted_score}

    Returns:
        (predicted_winner, confidence) tuple.
    """
    if not weighted_totals:
        return None, 0.0

    sorted_parties = sorted(weighted_totals.items(), key=lambda x: x[1], reverse=True)

    if len(sorted_parties) < 2:
        return sorted_parties[0][0], 1.0

    top_score = sorted_parties[0][1]
    second_score = sorted_parties[1][1]
    winner = sorted_parties[0][0]

    # Differential-based confidence
    max_possible = 1.0
    if max_possible == 0:
        return winner, 0.5

    differential = top_score - second_score
    # Scale differential to confidence: 0 diff -> 0.5, max diff -> 1.0
    confidence = 0.5 + 0.5 * min(differential / max_possible, 1.0)

    return winner, round(confidence, 4)


def compute_criteria_agreement(
    criteria_scores: dict[str, dict[str, float]],
) -> float:
    """Compute how consistently the criteria agree on a winner.

    Returns a value 0-1 where 1 means all criteria favor the same party.
    """
    if not criteria_scores:
        return 0.0

    winners_per_criterion: list[str | None] = []
    for _criterion, party_scores in criteria_scores.items():
        if not party_scores:
            continue
        best = max(party_scores.items(), key=lambda x: x[1])
        winners_per_criterion.append(best[0])

    if not winners_per_criterion:
        return 0.0

    # Count the most common winner
    from collections import Counter

    counts = Counter(winners_per_criterion)
    most_common_count = counts.most_common(1)[0][1]
    return most_common_count / len(winners_per_criterion)


def evaluate_mcda(
    criteria_scores: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
    folder_manager: CaseFolderManager | None = None,
    case_id: str | None = None,
) -> MCDAResult:
    """Run full MCDA evaluation and optionally persist results.

    Args:
        criteria_scores: {criterion: {party: raw_score(1-10)}}
        weights: Optional custom weights. Loads from file if not provided.
        folder_manager: Optional, to persist output to case folder.
        case_id: Required if folder_manager is provided.

    Returns:
        MCDAResult with scores, winner, and confidence.
    """
    if weights is None:
        weights = load_weights()

    weighted_totals = compute_weighted_scores(criteria_scores, weights)
    winner, base_confidence = determine_winner(weighted_totals)

    # Adjust confidence by criteria agreement
    agreement = compute_criteria_agreement(criteria_scores)
    confidence = round(base_confidence * agreement, 4)

    result = MCDAResult(
        criteria_scores=criteria_scores,
        weighted_totals=weighted_totals,
        predicted_winner=winner,
        confidence=confidence,
    )

    if folder_manager and case_id:
        folder_manager.save_output(
            case_id,
            "mcda_scoring.json",
            result.model_dump(mode="json"),
        )

    return result


# JSON schema for LLM-generated MCDA ratings
MCDA_RATING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ratings": {
            "type": "object",
            "properties": {
                criterion: {
                    "type": "object",
                    "properties": {
                        "claimant": {
                            "type": "number",
                            "description": f"Claimant score for {criterion} (1-10)",
                        },
                        "respondent": {
                            "type": "number",
                            "description": (f"Respondent score for {criterion} (1-10)"),
                        },
                    },
                    "required": ["claimant", "respondent"],
                }
                for criterion in CRITERIA
            },
            "required": CRITERIA,
        },
        "rating_justification": {
            "type": "string",
            "description": "Brief justification for the assigned ratings",
        },
    },
    "required": ["ratings", "rating_justification"],
}
