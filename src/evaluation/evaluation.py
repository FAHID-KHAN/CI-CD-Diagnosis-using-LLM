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

        Evidence-line scores vary case by case whatever the category
        distribution, so they are what SRQ1 can actually be tested on. Scores
        come from ``evidence_line_scores`` rather than a second implementation,
        and cases with no annotated lines are unscorable and excluded rather
        than counted as zero.

        **F1 is the tested statistic; precision is reported, not tested.** The
        models cite a roughly constant number of lines -- 6 to 16 across the
        development and pilot runs -- however many the annotation marks, so a
        case annotated with 54 lines caps recall at about 11% whatever the model
        does. Measured over 22 cases, the correlation between annotated line
        count and F1 is -0.41. Recall and F1 therefore carry information about
        how broadly the annotation marks evidence, while precision -- of the
        lines a model cited, how many were evidence -- does not, and matches what
        the prompt asks for: point at the failure, not enumerate it.

        Within a case both conditions face the same annotation, so the breadth
        cancels in a paired contrast: it damages the absolute figure, not the
        comparison. F1 therefore carries the test and uses signal precision
        discards, while precision carries the absolute capability claim and is
        reported without a p-value. Two p-values over the same pairs would be
        multiple testing without a correction, and the claim precision supports
        is not a claim about a difference.

        The mean number of lines each condition cites is reported alongside,
        because precision alone would reward a model that cited one line and
        stopped.
        """
        from src.evaluation.category_metrics import evidence_line_scores

        by_id_b = {p.log_id: p for p in predictions_b}
        paired: List[tuple] = []
        secondary: List[tuple] = []
        citations: List[tuple] = []
        for item in predictions_a:
            other = by_id_b.get(item.log_id)
            if other is None:
                continue
            first = evidence_line_scores(predicted=item.predicted_lines, actual=item.actual_lines)
            second = evidence_line_scores(predicted=other.predicted_lines, actual=other.actual_lines)
            if not (first["scorable"] and second["scorable"]):
                continue
            paired.append((float(first["precision"]), float(second["precision"])))
            secondary.append((float(first["f1"]), float(second["f1"])))
            citations.append((len(item.predicted_lines or []), len(other.predicted_lines or [])))

        if len(paired) < 2:
            return {
                "scorable_pairs": len(paired),
                "verdict": "Too few scorable pairs for a paired test",
            }

        precision_a = [a for a, _ in paired]
        precision_b = [b for _, b in paired]
        f1_a = [a for a, _ in secondary]
        f1_b = [b for _, b in secondary]

        # One hypothesis test, on F1. Precision is reported as a descriptive
        # capability figure and is deliberately not tested: two p-values over
        # the same pairs would be multiple testing without a correction, and the
        # absolute claim precision supports is not a claim about a difference.
        a_wins = sum(1 for a, b in secondary if a > b)
        b_wins = sum(1 for a, b in secondary if b > a)
        ties = sum(1 for a, b in secondary if a == b)
        mean_difference = float(np.mean(f1_a) - np.mean(f1_b))

        described = {
            "primary_metric": "f1",
            "mean_f1_a": float(np.mean(f1_a)),
            "mean_f1_b": float(np.mean(f1_b)),
            "mean_f1_difference": mean_difference,
            # Descriptive only, no p-value. Precision answers "when the system
            # cites a line, is it evidence?", which must not depend on how
            # broadly the annotation marked -- and it does not, where F1 does.
            "mean_precision_a": float(np.mean(precision_a)),
            "mean_precision_b": float(np.mean(precision_b)),
            "mean_precision_difference": float(np.mean(precision_a) - np.mean(precision_b)),
            # Reported because precision is blind to a model that cites one
            # correct line and stops.
            "mean_lines_cited_a": float(np.mean([a for a, _ in citations])),
            "mean_lines_cited_b": float(np.mean([b for _, b in citations])),
        }

        if a_wins + b_wins == 0:
            return {
                "scorable_pairs": len(paired),
                "a_better": 0,
                "b_better": 0,
                "ties": ties,
                **described,
                "mean_f1_difference": 0.0,
                "p_value": 1.0,
                "significant_at_005": False,
                "verdict": "Identical evidence-line F1 on every case",
            }

        result = stats.wilcoxon(f1_a, f1_b)
        p_value = float(result.pvalue)
        return {
            "scorable_pairs": len(paired),
            "a_better": a_wins,
            "b_better": b_wins,
            "ties": ties,
            **described,
            "statistic": float(result.statistic),
            "p_value": p_value,
            "significant_at_005": bool(p_value < 0.05),
            "verdict": (
                f"{'First' if mean_difference > 0 else 'Second'} model better on evidence-line "
                f"F1 in {max(a_wins, b_wins)} of {len(paired)} cases"
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
        differences = a_correct - b_correct
        # Compute the observed statistic from the same array the permutations
        # are drawn from. Taking it as a.mean() - b.mean() instead put it one
        # ULP above the identical quantity -- 9/11 - 6/11 evaluates above 3/11 --
        # so no permutation ever counted as extreme and the pilot reported
        # p = 0.0 where the correct value was 0.25.
        observed = abs(float(differences.mean()))
        rng = np.random.default_rng(seed)
        tolerance = 1e-12
        extreme = sum(
            abs(float((differences * rng.choice([-1, 1], size=len(differences))).mean())) >= observed - tolerance
            for _ in range(n_permutations)
        )
        # The unbiased estimator. A permutation test cannot demonstrate p = 0:
        # the floor is set by how many permutations were drawn, and reporting a
        # bare zero overstates what the resampling can support.
        p_value = float((extreme + 1) / (n_permutations + 1))
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
