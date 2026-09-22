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
