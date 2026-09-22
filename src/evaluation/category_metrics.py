"""Per-category and evidence-line scoring over stored benchmark results.

The benchmark stores one exact-match accuracy per model. Decision D5 asks which
kinds of CI/CD failure the models handle well or poorly, which needs precision,
recall, F1 and support per category, plus a macro F1 that does not let the
largest category dominate.

The annotation tool also records supporting line numbers for every case, and the
benchmark stores each model's ``failure_lines``, but nothing scored one against
the other -- so "grounding" measured only whether a model's cited lines existed
in the log it was given, never whether they were the *right* lines. The
evidence-line functions here close that gap.

Everything is computed from stored results, so no frozen artifact changes.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from src.evaluation.taxonomy import INFERENCE_ERROR


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def category_scores(pairs: Sequence[tuple], categories: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """Precision, recall, F1 and support per category from (actual, predicted) pairs.

    Support counts ground-truth occurrences, so a category the model never
    predicts still appears with recall 0 rather than dropping out of the table.
    """
    names: List[str] = []
    for name in list(categories or []) + [actual for actual, _ in pairs] + [pred for _, pred in pairs]:
        if name and name != INFERENCE_ERROR and name not in names:
            names.append(name)

    scores: Dict[str, dict] = {}
    for name in names:
        true_positive = sum(1 for actual, predicted in pairs if actual == name and predicted == name)
        false_positive = sum(1 for actual, predicted in pairs if actual != name and predicted == name)
        false_negative = sum(1 for actual, predicted in pairs if actual == name and predicted != name)
        support = sum(1 for actual, _ in pairs if actual == name)
        precision = _safe_divide(true_positive, true_positive + false_positive)
        recall = _safe_divide(true_positive, true_positive + false_negative)
        scores[name] = {
            "support": support,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_safe_divide(2 * precision * recall, precision + recall), 4),
        }
    return scores


def macro_f1(scores: Dict[str, dict]) -> Optional[float]:
    """Unweighted mean F1 over categories that occur in the ground truth.

    Categories with no support are excluded: a model cannot be credited or
    penalised for a category the held-out set never contains.
    """
    supported = [entry["f1"] for entry in scores.values() if entry["support"] > 0]
    return round(sum(supported) / len(supported), 4) if supported else None


def evidence_line_scores(predicted: Sequence[int], actual: Sequence[int]) -> dict:
    """Precision, recall, F1 and Jaccard overlap for one case's supporting lines.

    A case whose ground truth records no lines is reported as unscorable rather
    than as a zero, so missing annotation never reads as a model failure.
    """
    truth = set(actual or [])
    guess = set(predicted or [])
    if not truth:
        return {"scorable": False, "precision": None, "recall": None, "f1": None, "jaccard": None}
    hits = len(truth & guess)
    precision = _safe_divide(hits, len(guess))
    recall = _safe_divide(hits, len(truth))
    return {
        "scorable": True,
        "matched_lines": hits,
        "predicted_lines": len(guess),
        "actual_lines": len(truth),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(_safe_divide(2 * precision * recall, precision + recall), 4),
        "jaccard": round(_safe_divide(hits, len(truth | guess)), 4),
    }


def aggregate_evidence_lines(per_case: Sequence[dict]) -> dict:
    """Mean of the per-case evidence-line scores, over scorable cases only."""
    scorable = [case for case in per_case if case.get("scorable")]
    if not scorable:
        return {"scorable_cases": 0, "mean_precision": None, "mean_recall": None, "mean_f1": None, "mean_jaccard": None}
    return {
        "scorable_cases": len(scorable),
        "mean_precision": round(sum(case["precision"] for case in scorable) / len(scorable), 4),
        "mean_recall": round(sum(case["recall"] for case in scorable) / len(scorable), 4),
        "mean_f1": round(sum(case["f1"] for case in scorable) / len(scorable), 4),
        "mean_jaccard": round(sum(case["jaccard"] for case in scorable) / len(scorable), 4),
    }
