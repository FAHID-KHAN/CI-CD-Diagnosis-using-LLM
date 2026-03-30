# evaluation.py - Comprehensive evaluation framework for CI/CD diagnosis

import json
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import pandas as pd
from scipy import stats

@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics"""
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    hallucination_rate: float
    mean_confidence: float
    mean_execution_time_ms: float
    total_cost_usd: float = 0.0
    cost_per_diagnosis_usd: float = 0.0

@dataclass
class PredictionResult:
    """Single prediction result"""
    log_id: str
    predicted_error_type: str
    actual_error_type: str
    predicted_lines: List[int]
    actual_lines: List[int]
    confidence: float
    hallucination_detected: bool
    execution_time_ms: float
    cost_usd: float = 0.0

class BaselineEvaluator:
    """Baseline methods for comparison"""
    
    @staticmethod
    def regex_baseline(log_content: str) -> Tuple[str, List[int]]:
        """Simple regex-based error detection"""
        import re
        
        lines = log_content.split('\n')
        error_lines = []
        error_type = "unknown"
        
        # Error patterns
        patterns = {
            'dependency_error': [r'ModuleNotFoundError', r'ImportError', r'package.*not found'],
            'test_failure': [r'FAILED.*test', r'AssertionError', r'Test.*failed'],
            'build_configuration': [r'build.*failed', r'gradle.*error', r'maven.*error'],
            'timeout': [r'timeout', r'timed out'],
            'permission_denied': [r'permission denied', r'access denied']
        }
        
        # Detect error type
        for err_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, log_content, re.IGNORECASE):
                    error_type = err_type
                    break
            if error_type != "unknown":
                break
        
        # Find error lines
        for i, line in enumerate(lines):
            if re.search(r'(?i)(error|failed|exception|fatal)', line):
                error_lines.append(i + 1)
        
        return error_type, error_lines[:5]  # Return top 5 error lines
    
    @staticmethod
    def heuristic_baseline(log_content: str) -> Tuple[str, List[int]]:
        """Heuristic-based error detection"""
        lines = log_content.split('\n')
        error_lines = []
        error_counts = {
            'dependency_error': 0,
            'test_failure': 0,
            'build_configuration': 0,
            'timeout': 0,
            'permission_denied': 0,
            'syntax_error': 0,
            'network_error': 0
        }
        
        # Keywords for each error type
        keywords = {
            'dependency_error': ['module', 'import', 'package', 'dependency', 'requirements'],
            'test_failure': ['test', 'assertion', 'expected', 'actual', 'junit'],
            'build_configuration': ['gradle', 'maven', 'npm', 'build.gradle', 'pom.xml'],
            'timeout': ['timeout', 'timed out', 'time limit'],
            'permission_denied': ['permission', 'access denied', 'forbidden'],
            'syntax_error': ['syntax', 'parse', 'unexpected token'],
            'network_error': ['connection', 'network', 'dns', 'host']
        }
        
        # Count occurrences
        content_lower = log_content.lower()
        for err_type, words in keywords.items():
            for word in words:
                error_counts[err_type] += content_lower.count(word)
        
        # Determine error type
        error_type = max(error_counts, key=error_counts.get)
        if error_counts[error_type] == 0:
            error_type = "unknown"
        
        # Find error lines with scoring
        for i, line in enumerate(lines):
            line_lower = line.lower()
            score = 0
            
            if any(word in line_lower for word in ['error', 'failed', 'exception', 'fatal']):
                score += 3
            if any(word in line_lower for word in keywords.get(error_type, [])):
                score += 2
            if 'traceback' in line_lower or 'stack trace' in line_lower:
                score += 2
            
            if score >= 3:
                error_lines.append((i + 1, score))
        
        # Sort by score and return top lines
        error_lines.sort(key=lambda x: x[1], reverse=True)
        return error_type, [line_num for line_num, _ in error_lines[:5]]

class MetricsCalculator:
    """Calculate evaluation metrics"""
    
    @staticmethod
    def calculate_line_overlap(predicted: List[int], actual: List[int]) -> Tuple[float, float, float]:
        """Calculate precision, recall, F1 for line detection"""
        if not actual:
            return 0.0, 0.0, 0.0
        
        predicted_set = set(predicted)
        actual_set = set(actual)
        
        true_positives = len(predicted_set & actual_set)
        false_positives = len(predicted_set - actual_set)
        false_negatives = len(actual_set - predicted_set)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return precision, recall, f1
    
    @staticmethod
    def calculate_metrics(predictions: List[PredictionResult]) -> EvaluationMetrics:
        """Calculate overall metrics"""
        # Error type accuracy
        correct_types = sum(1 for p in predictions if p.predicted_error_type == p.actual_error_type)
        accuracy = correct_types / len(predictions) if predictions else 0.0
        
        # Line detection metrics
        precisions, recalls, f1s = [], [], []
        for pred in predictions:
            p, r, f = MetricsCalculator.calculate_line_overlap(pred.predicted_lines, pred.actual_lines)
            precisions.append(p)
            recalls.append(r)
            f1s.append(f)
        
        # Hallucination rate
        hallucination_rate = sum(1 for p in predictions if p.hallucination_detected) / len(predictions) if predictions else 0.0
        
        # Confidence and timing
        mean_confidence = np.mean([p.confidence for p in predictions]) if predictions else 0.0
        mean_execution_time = np.mean([p.execution_time_ms for p in predictions]) if predictions else 0.0
        
        return EvaluationMetrics(
            precision=np.mean(precisions) if precisions else 0.0,
            recall=np.mean(recalls) if recalls else 0.0,
            f1_score=np.mean(f1s) if f1s else 0.0,
            accuracy=accuracy,
            hallucination_rate=hallucination_rate,
            mean_confidence=mean_confidence,
            mean_execution_time_ms=mean_execution_time,
            total_cost_usd=sum(p.cost_usd for p in predictions),
            cost_per_diagnosis_usd=(
                sum(p.cost_usd for p in predictions) / len(predictions)
                if predictions else 0.0
            ),
        )
    
    @staticmethod
    def calculate_per_error_type_metrics(predictions: List[PredictionResult]) -> Dict[str, Dict]:
        """Calculate metrics broken down by error type"""
        error_types = set(p.actual_error_type for p in predictions)
        results = {}
        
        for err_type in error_types:
            type_predictions = [p for p in predictions if p.actual_error_type == err_type]
            metrics = MetricsCalculator.calculate_metrics(type_predictions)
            results[err_type] = {
                'precision': metrics.precision,
                'recall': metrics.recall,
                'f1_score': metrics.f1_score,
                'accuracy': metrics.accuracy,
                'count': len(type_predictions)
            }
        
        return results

class AblationStudy:
    """Framework for conducting ablation studies"""
    
    @staticmethod
    def evaluate_filtering_strategies(test_logs: List[Dict], 
                                     diagnostic_api) -> Dict[str, EvaluationMetrics]:
        """Compare different log filtering strategies"""
        strategies = {
            'no_filtering': {'use_filtering': False, 'max_context_lines': 10000},
            'smart_filtering_500': {'use_filtering': True, 'max_context_lines': 500},
            'smart_filtering_1000': {'use_filtering': True, 'max_context_lines': 1000},
            'smart_filtering_2000': {'use_filtering': True, 'max_context_lines': 2000}
        }
        
        results = {}
        
        for strategy_name, params in strategies.items():
            print(f"Evaluating strategy: {strategy_name}")
            predictions = []
            
            for log in test_logs:
                # Call diagnostic API with strategy params
                response = diagnostic_api.diagnose(
                    log_content=log['log_content'],
                    use_filtering=params['use_filtering'],
                    max_context_lines=params['max_context_lines']
                )
                
                predictions.append(PredictionResult(
                    log_id=log['log_id'],
                    predicted_error_type=response['error_type'],
                    actual_error_type=log['actual_error_type'],
                    predicted_lines=response['failure_lines'],
                    actual_lines=log['actual_failure_lines'],
                    confidence=response['confidence_score'],
                    hallucination_detected=response['hallucination_detected'],
                    execution_time_ms=response['execution_time_ms']
                ))
            
            results[strategy_name] = MetricsCalculator.calculate_metrics(predictions)
        
        return results
    
    @staticmethod
    def evaluate_temperature_settings(test_logs: List[Dict], 
                                     diagnostic_api) -> Dict[float, EvaluationMetrics]:
        """Compare different temperature settings"""
        temperatures = [0.0, 0.1, 0.3, 0.5, 0.7, 1.0]
        results = {}
        
        for temp in temperatures:
            print(f"Evaluating temperature: {temp}")
            predictions = []
            
            for log in test_logs:
                response = diagnostic_api.diagnose(
                    log_content=log['log_content'],
                    temperature=temp
                )
                
                predictions.append(PredictionResult(
                    log_id=log['log_id'],
                    predicted_error_type=response['error_type'],
                    actual_error_type=log['actual_error_type'],
                    predicted_lines=response['failure_lines'],
                    actual_lines=log['actual_failure_lines'],
                    confidence=response['confidence_score'],
                    hallucination_detected=response['hallucination_detected'],
                    execution_time_ms=response['execution_time_ms']
                ))
            
            results[temp] = MetricsCalculator.calculate_metrics(predictions)
        
        return results
    
    @staticmethod
    def evaluate_prompt_variations(test_logs: List[Dict],
                                   prompt_templates: Dict[str, str]) -> Dict[str, EvaluationMetrics]:
        """Compare different prompt engineering strategies"""
        results = {}
        
        for prompt_name, template in prompt_templates.items():
            print(f"Evaluating prompt: {prompt_name}")
            # Implementation would test each prompt variation
            # This is a placeholder for the actual evaluation logic
            pass
        
        return results

class Visualizer:
    """Visualization tools for results"""
    
    @staticmethod
    def plot_comparison(results: Dict[str, EvaluationMetrics], 
                       title: str, 
                       output_path: str):
        """Plot comparison of different approaches"""
        approaches = list(results.keys())
        metrics = ['precision', 'recall', 'f1_score', 'accuracy']
        
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle(title, fontsize=16)
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx // 2, idx % 2]
            values = [getattr(results[approach], metric) for approach in approaches]
            
            ax.bar(approaches, values, alpha=0.7)
            ax.set_ylabel(metric.replace('_', ' ').title())
            ax.set_ylim(0, 1)
            ax.tick_params(axis='x', rotation=45)
            ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Saved plot to {output_path}")
    
    @staticmethod
    def plot_confusion_matrix(predictions: List[PredictionResult], 
                             output_path: str):
        """Plot confusion matrix for error type classification"""
        actual = [p.actual_error_type for p in predictions]
        predicted = [p.predicted_error_type for p in predictions]
        
        labels = sorted(set(actual + predicted))
        cm = confusion_matrix(actual, predicted, labels=labels)
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                   xticklabels=labels, yticklabels=labels)
        plt.title('Error Type Classification Confusion Matrix')
        plt.ylabel('Actual')
        plt.xlabel('Predicted')
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Saved confusion matrix to {output_path}")
    
    @staticmethod
    def plot_hallucination_analysis(predictions: List[PredictionResult],
                                    output_path: str):
        """Analyze hallucination patterns"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        
        # Hallucination rate by error type
        error_types = {}
        for p in predictions:
            if p.actual_error_type not in error_types:
                error_types[p.actual_error_type] = {'total': 0, 'hallucinated': 0}
            error_types[p.actual_error_type]['total'] += 1
            if p.hallucination_detected:
                error_types[p.actual_error_type]['hallucinated'] += 1
        
        types = list(error_types.keys())
        rates = [error_types[t]['hallucinated'] / error_types[t]['total'] for t in types]
        
        ax1.bar(types, rates, alpha=0.7, color='red')
        ax1.set_ylabel('Hallucination Rate')
        ax1.set_title('Hallucination Rate by Error Type')
        ax1.tick_params(axis='x', rotation=45)
        ax1.set_ylim(0, 1)
        ax1.grid(axis='y', alpha=0.3)
        
        # Confidence vs Hallucination
        hallucinated = [p.confidence for p in predictions if p.hallucination_detected]
        not_hallucinated = [p.confidence for p in predictions if not p.hallucination_detected]
        
        ax2.hist([not_hallucinated, hallucinated], bins=20, label=['No Hallucination', 'Hallucination'], alpha=0.7)
        ax2.set_xlabel('Confidence Score')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Confidence Distribution by Hallucination Status')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Saved hallucination analysis to {output_path}")

    @staticmethod
    def plot_cost_accuracy_tradeoff(
        model_metrics: Dict[str, Dict],
        output_path: str,
    ):
        """Scatter plot: cost per diagnosis (x) vs accuracy (y) per model.

        ``model_metrics`` maps model labels to dicts that contain at least
        ``cost_per_diagnosis_usd`` and ``accuracy`` (or ``error_type_accuracy``).
        """
        fig, ax = plt.subplots(figsize=(8, 6))

        for label, m in model_metrics.items():
            cost = m.get("cost_per_diagnosis_usd", m.get("total_cost_usd", 0))
            acc = m.get("accuracy", m.get("error_type_accuracy", 0))
            time_ms = m.get("avg_execution_time_ms", m.get("mean_execution_time_ms", 0))

            # Bubble size proportional to speed (inverse: faster = bigger)
            size = max(60, 300 - time_ms / 10)
            ax.scatter(cost * 1000, acc * 100, s=size, alpha=0.8, zorder=5)
            ax.annotate(
                label,
                (cost * 1000, acc * 100),
                textcoords="offset points",
                xytext=(8, 6),
                fontsize=9,
            )

        ax.set_xlabel("Cost per Diagnosis (× $0.001)")
        ax.set_ylabel("Error-Type Accuracy (%)")
        ax.set_title("Cost–Accuracy Trade-off by Model")
        ax.grid(alpha=0.3)
        ax.set_ylim(0, 105)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved cost-accuracy trade-off chart to {output_path}")


class StatisticalTests:
    """Statistical significance tests for comparing two classifiers."""

    @staticmethod
    def mcnemar_test(
        predictions_a: List[PredictionResult],
        predictions_b: List[PredictionResult],
    ) -> Dict[str, float]:
        """McNemar's test comparing two models on the same data set.

        Both prediction lists must be aligned (same log_id order).
        Returns chi-squared statistic, p-value, and a human-readable verdict.
        """
        if len(predictions_a) != len(predictions_b):
            raise ValueError("Both prediction lists must have the same length")

        # Build the 2×2 contingency table
        # b = correct/incorrect for model A vs model B
        n01 = 0  # A wrong, B right
        n10 = 0  # A right, B wrong
        for pa, pb in zip(predictions_a, predictions_b):
            a_correct = pa.predicted_error_type == pa.actual_error_type
            b_correct = pb.predicted_error_type == pb.actual_error_type
            if a_correct and not b_correct:
                n10 += 1
            elif not a_correct and b_correct:
                n01 += 1

        # McNemar's test with continuity correction
        n_discordant = n01 + n10
        if n_discordant == 0:
            return {
                "n01": n01,
                "n10": n10,
                "chi2": 0.0,
                "p_value": 1.0,
                "significant_at_005": False,
                "verdict": "Models performed identically on all samples",
            }

        chi2 = (abs(n01 - n10) - 1) ** 2 / (n01 + n10)
        p_value = 1 - stats.chi2.cdf(chi2, df=1)

        return {
            "n01": n01,
            "n10": n10,
            "chi2": round(chi2, 4),
            "p_value": round(p_value, 6),
            "significant_at_005": p_value < 0.05,
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
        """Bootstrap confidence interval for accuracy (or a custom metric).

        ``metric_fn`` takes a list of PredictionResult and returns a float.
        Defaults to error-type accuracy.
        """
        rng = np.random.default_rng(seed)

        if metric_fn is None:
            def metric_fn(preds):
                correct = sum(
                    1 for p in preds if p.predicted_error_type == p.actual_error_type
                )
                return correct / len(preds) if preds else 0.0

        observed = metric_fn(predictions)
        n = len(predictions)
        boot_values = []

        for _ in range(n_bootstrap):
            sample = [predictions[i] for i in rng.integers(0, n, size=n)]
            boot_values.append(metric_fn(sample))

        boot_values = np.array(boot_values)
        alpha = 1 - confidence
        lower = float(np.percentile(boot_values, 100 * alpha / 2))
        upper = float(np.percentile(boot_values, 100 * (1 - alpha / 2)))

        return {
            "observed": round(observed, 4),
            "ci_lower": round(lower, 4),
            "ci_upper": round(upper, 4),
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
        """Two-sided paired permutation test on accuracy difference."""
        if len(predictions_a) != len(predictions_b):
            raise ValueError("Both prediction lists must have the same length")

        rng = np.random.default_rng(seed)
        n = len(predictions_a)

        a_correct = np.array([
            int(p.predicted_error_type == p.actual_error_type) for p in predictions_a
        ])
        b_correct = np.array([
            int(p.predicted_error_type == p.actual_error_type) for p in predictions_b
        ])

        observed_diff = float(a_correct.mean() - b_correct.mean())
        diffs = a_correct - b_correct

        count_extreme = 0
        for _ in range(n_permutations):
            signs = rng.choice([-1, 1], size=n)
            perm_diff = float((diffs * signs).mean())
            if abs(perm_diff) >= abs(observed_diff):
                count_extreme += 1

        p_value = count_extreme / n_permutations

        return {
            "observed_accuracy_diff": round(observed_diff, 4),
            "p_value": round(p_value, 6),
            "significant_at_005": p_value < 0.05,
            "n_permutations": n_permutations,
        }


class BenchmarkRunner:
    """Main benchmark runner"""
    
    def __init__(self, test_data_path: str, output_dir: str):
        self.test_data_path = test_data_path
        self.output_dir = output_dir
        self.test_logs = self._load_test_data()
    
    def _load_test_data(self) -> List[Dict]:
        """Load annotated test data"""
        with open(self.test_data_path, 'r') as f:
            return json.load(f)
    
    def run_baseline_comparison(self) -> Dict[str, EvaluationMetrics]:
        """Compare LLM against baselines"""
        results = {}
        
        # Regex baseline
        print("Running regex baseline...")
        regex_predictions = []
        for log in self.test_logs:
            error_type, error_lines = BaselineEvaluator.regex_baseline(log['log_content'])
            regex_predictions.append(PredictionResult(
                log_id=log['log_id'],
                predicted_error_type=error_type,
                actual_error_type=log['actual_error_type'],
                predicted_lines=error_lines,
                actual_lines=log['actual_failure_lines'],
                confidence=1.0,
                hallucination_detected=False,
                execution_time_ms=5.0
            ))
        results['regex_baseline'] = MetricsCalculator.calculate_metrics(regex_predictions)
        
        # Heuristic baseline
        print("Running heuristic baseline...")
        heuristic_predictions = []
        for log in self.test_logs:
            error_type, error_lines = BaselineEvaluator.heuristic_baseline(log['log_content'])
            heuristic_predictions.append(PredictionResult(
                log_id=log['log_id'],
                predicted_error_type=error_type,
                actual_error_type=log['actual_error_type'],
                predicted_lines=error_lines,
                actual_lines=log['actual_failure_lines'],
                confidence=1.0,
                hallucination_detected=False,
                execution_time_ms=8.0
            ))
        results['heuristic_baseline'] = MetricsCalculator.calculate_metrics(heuristic_predictions)
        
        return results
    
    def generate_report(self, all_results: Dict[str, Any], output_file: str):
        """Generate comprehensive evaluation report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'test_set_size': len(self.test_logs),
            'results': {}
        }
        
        for approach, metrics in all_results.items():
            if isinstance(metrics, EvaluationMetrics):
                report['results'][approach] = {
                    'precision': float(metrics.precision),
                    'recall': float(metrics.recall),
                    'f1_score': float(metrics.f1_score),
                    'accuracy': float(metrics.accuracy),
                    'hallucination_rate': float(metrics.hallucination_rate),
                    'mean_confidence': float(metrics.mean_confidence),
                    'mean_execution_time_ms': float(metrics.mean_execution_time_ms)
                }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Report saved to {output_file}")
        
        # Also create a summary table
        df = pd.DataFrame.from_dict(report['results'], orient='index')
        print("\n=== Evaluation Summary ===")
        print(df.to_string())
        
        return report

# Example usage
if __name__ == "__main__":
    # Initialize benchmark
    benchmark = BenchmarkRunner(
        test_data_path="data/annotated_test_set.json",
        output_dir="results/"
    )
    
    # Run baseline comparison
    baseline_results = benchmark.run_baseline_comparison()
    
    # Generate visualizations
    Visualizer.plot_comparison(
        baseline_results,
        "Baseline Comparison",
        "results/baseline_comparison.png"
    )
    
    # Generate report
    benchmark.generate_report(baseline_results, "results/evaluation_report.json")