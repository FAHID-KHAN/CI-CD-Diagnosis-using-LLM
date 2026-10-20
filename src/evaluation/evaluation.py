"""Statistics and the single result chart used by the paired thesis experiment."""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from scipy import stats


@dataclass
class PredictionResult:
    log_id: str
    predicted_error_type: str
    actual_error_type: str
    predicted_lines: List[int]
    actual_lines: List[int]
    confidence: float
    hallucination_detected: bool
    execution_time_ms: float
    cost_usd: float = 0.0


class StatisticalTests:
    """Paired significance and uncertainty estimates for two model conditions."""

    @staticmethod
    def mcnemar_test(
        predictions_a: List[PredictionResult],
        predictions_b: List[PredictionResult],
    ) -> Dict[str, object]:
        if len(predictions_a) != len(predictions_b):
            raise ValueError("Both prediction lists must have the same length")

        n01 = 0
        n10 = 0
        for prediction_a, prediction_b in zip(predictions_a, predictions_b):
            a_correct = prediction_a.predicted_error_type == prediction_a.actual_error_type
            b_correct = prediction_b.predicted_error_type == prediction_b.actual_error_type
            if a_correct and not b_correct:
                n10 += 1
            elif not a_correct and b_correct:
                n01 += 1

        if n01 + n10 == 0:
            return {
                "n01": n01,
                "n10": n10,
                "chi2": 0.0,
                "p_value": 1.0,
                "significant_at_005": False,
                "verdict": "Models performed identically on all samples",
            }

        chi2 = (abs(n01 - n10) - 1) ** 2 / (n01 + n10)
        # scipy returns NumPy scalar types; normalize them so experiment
        # reports are always serializable by the standard json module.
        p_value = float(1 - stats.chi2.cdf(chi2, df=1))
        return {
            "n01": n01,
            "n10": n10,
            "chi2": round(chi2, 4),
            "p_value": round(p_value, 6),
            "significant_at_005": bool(p_value < 0.05),
            "verdict": (
                "Statistically significant difference (p < 0.05)"
                if p_value < 0.05
                else "No statistically significant difference (p >= 0.05)"
            ),
        }

    @staticmethod
    def paired_evidence_line_test(
        predictions_a: List[PredictionResult],
        predictions_b: List[PredictionResult],
    ) -> Dict[str, object]:
        """Wilcoxon signed-rank over per-case evidence-line F1.

        McNemar is computed on category accuracy, which cannot discriminate when
        the cohort carries one category: with every label the same, both models
        score 100%, there are no discordant pairs, and the verdict is forced to
        "performed identically". That happened on the first development run --
        eleven cases all labelled ``test_failure`` -- while the same eleven cases
        showed the hosted model ahead on evidence lines in all eleven, at
        p = 0.001. The category test was not wrong, it was answering a question
        the data could not distinguish.

        Evidence-line F1 varies case by case whatever the category distribution,
        so it is what SRQ1 can actually be tested on. Scores here come from
        ``evidence_line_scores`` rather than a second implementation, and cases
        with no annotated lines are unscorable and excluded rather than counted
        as zero.
        """
        from src.evaluation.category_metrics import evidence_line_scores

        by_id_b = {p.log_id: p for p in predictions_b}
        paired = []
        for item in predictions_a:
            other = by_id_b.get(item.log_id)
            if other is None:
                continue
            first = evidence_line_scores(predicted=item.predicted_lines, actual=item.actual_lines)
            second = evidence_line_scores(predicted=other.predicted_lines, actual=other.actual_lines)
            if not (first["scorable"] and second["scorable"]):
                continue
            paired.append((float(first["f1"]), float(second["f1"])))

        if len(paired) < 2:
            return {
                "scorable_pairs": len(paired),
                "verdict": "Too few scorable pairs for a paired test",
            }

        first_scores = [a for a, _ in paired]
        second_scores = [b for _, b in paired]
        a_wins = sum(1 for a, b in paired if a > b)
        b_wins = sum(1 for a, b in paired if b > a)
        ties = sum(1 for a, b in paired if a == b)
        mean_difference = float(np.mean(first_scores) - np.mean(second_scores))

        if a_wins + b_wins == 0:
            return {
                "scorable_pairs": len(paired),
                "a_better": 0,
                "b_better": 0,
                "ties": ties,
                "mean_f1_a": float(np.mean(first_scores)),
                "mean_f1_b": float(np.mean(second_scores)),
                "mean_f1_difference": 0.0,
                "verdict": "Identical evidence-line F1 on every case",
            }

        result = stats.wilcoxon(first_scores, second_scores)
        p_value = float(result.pvalue)
        return {
            "scorable_pairs": len(paired),
            "a_better": a_wins,
            "b_better": b_wins,
            "ties": ties,
            "mean_f1_a": float(np.mean(first_scores)),
            "mean_f1_b": float(np.mean(second_scores)),
            "mean_f1_difference": mean_difference,
            "statistic": float(result.statistic),
            "p_value": p_value,
            "significant_at_005": bool(p_value < 0.05),
            "verdict": (
                f"{'First' if mean_difference > 0 else 'Second'} model better on evidence lines "
                f"in {max(a_wins, b_wins)} of {len(paired)} cases"
                if p_value < 0.05
                else "No significant difference in evidence-line F1"
            ),
        }

    @staticmethod
    def bootstrap_confidence_interval(
        predictions: List[PredictionResult],
        metric_fn=None,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, float]:
        if not predictions:
            raise ValueError("At least one prediction is required")
        if metric_fn is None:

            def accuracy(values):
                return sum(item.predicted_error_type == item.actual_error_type for item in values) / len(values)

            metric_fn = accuracy

        rng = np.random.default_rng(seed)
        observed = metric_fn(predictions)
        count = len(predictions)
        samples = [
            metric_fn([predictions[index] for index in rng.integers(0, count, size=count)]) for _ in range(n_bootstrap)
        ]
        alpha = 1 - confidence
        return {
            "observed": round(float(observed), 4),
            "ci_lower": round(float(np.percentile(samples, 100 * alpha / 2)), 4),
            "ci_upper": round(float(np.percentile(samples, 100 * (1 - alpha / 2))), 4),
            "confidence": confidence,
            "n_bootstrap": n_bootstrap,
        }

    @staticmethod
    def paired_permutation_test(
        predictions_a: List[PredictionResult],
        predictions_b: List[PredictionResult],
        n_permutations: int = 10000,
        seed: int = 42,
    ) -> Dict[str, float]:
        if len(predictions_a) != len(predictions_b):
            raise ValueError("Both prediction lists must have the same length")
        if not predictions_a:
            raise ValueError("At least one paired prediction is required")

        a_correct = np.array([int(item.predicted_error_type == item.actual_error_type) for item in predictions_a])
        b_correct = np.array([int(item.predicted_error_type == item.actual_error_type) for item in predictions_b])
        observed = float(a_correct.mean() - b_correct.mean())
        differences = a_correct - b_correct
        rng = np.random.default_rng(seed)
        extreme = sum(
            abs(float((differences * rng.choice([-1, 1], size=len(differences))).mean())) >= abs(observed)
            for _ in range(n_permutations)
        )
        p_value = float(extreme / n_permutations)
        return {
            "observed_accuracy_diff": round(observed, 4),
            "p_value": round(p_value, 6),
            "significant_at_005": bool(p_value < 0.05),
            "n_permutations": n_permutations,
        }


class Visualizer:
    @staticmethod
    def plot_cost_accuracy_tradeoff(model_metrics: Dict[str, Dict], output_path: str):
        # Import lazily so collection, triage, and annotation do not initialize a
        # plotting backend or create a Matplotlib cache directory.
        import matplotlib.pyplot as plt

        fig, axis = plt.subplots(figsize=(8, 6))
        for label, metrics in model_metrics.items():
            cost = metrics.get("cost_per_diagnosis_usd", 0)
            accuracy = metrics.get("accuracy", metrics.get("error_type_accuracy", 0))
            axis.scatter(cost * 1000, accuracy * 100, s=100)
            axis.annotate(label, (cost * 1000, accuracy * 100), xytext=(8, 6), textcoords="offset points")
        axis.set_xlabel("Cost per diagnosis (× $0.001)")
        axis.set_ylabel("Error-type accuracy (%)")
        axis.set_title("Cost–accuracy trade-off by model")
        axis.set_ylim(0, 105)
        axis.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
