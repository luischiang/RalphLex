"""Convergence detection for iterative argument loops.

Compares consecutive argument versions using structured field diff
and similarity scoring to detect when arguments stabilize.
"""

from difflib import SequenceMatcher

from backend.models.case import Argument


def _text_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two strings using SequenceMatcher."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _list_similarity(a: list[str], b: list[str]) -> float:
    """Compute similarity between two lists of strings.

    Uses the Jaccard index (intersection over union) for set-level similarity,
    combined with text similarity for best-match pairs.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    # Compute best-match similarity for each item in a against items in b
    total_sim = 0.0
    for item_a in a:
        best = max(_text_similarity(item_a, item_b) for item_b in b)
        total_sim += best

    # Average over the larger list to penalize additions/removals
    return total_sim / max(len(a), len(b))


def compute_argument_similarity(arg1: Argument, arg2: Argument) -> float:
    """Compute overall similarity between two arguments.

    Returns a score between 0.0 (completely different) and 1.0 (identical).
    Weights the different fields by their importance for convergence detection.
    """
    weights = {
        "content": 0.30,
        "legal_basis": 0.25,
        "factual_claims": 0.20,
        "counterarguments": 0.15,
        "evidence_requests": 0.10,
    }

    scores = {
        "content": _text_similarity(arg1.content, arg2.content),
        "legal_basis": _list_similarity(arg1.legal_basis, arg2.legal_basis),
        "factual_claims": _list_similarity(arg1.factual_claims, arg2.factual_claims),
        "counterarguments": _list_similarity(arg1.counterarguments, arg2.counterarguments),
        "evidence_requests": _list_similarity(arg1.evidence_requests, arg2.evidence_requests),
    }

    weighted_sum = sum(scores[field] * weights[field] for field in weights)
    return weighted_sum


def has_converged(
    current: Argument,
    previous: Argument,
    threshold: float = 0.85,
) -> bool:
    """Determine if arguments have converged.

    Args:
        current: The latest argument.
        previous: The previous argument from the same role.
        threshold: Similarity threshold above which convergence is detected.

    Returns:
        True if the similarity exceeds the threshold.
    """
    similarity = compute_argument_similarity(current, previous)
    return similarity >= threshold
