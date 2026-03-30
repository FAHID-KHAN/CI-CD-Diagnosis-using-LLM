"""Quick smoke test for new statistical tests and cost tracking."""
from src.evaluation.evaluation import StatisticalTests, PredictionResult, Visualizer
import tempfile, os


def _make_preds(correct_mask):
    """Build PredictionResult list from a boolean mask."""
    types = ["dependency_error", "test_failure", "build_configuration",
             "timeout", "network_error"]
    preds = []
    for i, correct in enumerate(correct_mask):
        actual = types[i % len(types)]
        predicted = actual if correct else "unknown"
        preds.append(PredictionResult(
            log_id=f"log{i}",
            predicted_error_type=predicted,
            actual_error_type=actual,
            predicted_lines=[], actual_lines=[],
            confidence=0.8 if correct else 0.3,
            hallucination_detected=not correct,
            execution_time_ms=100 + i * 10,
            cost_usd=0.001 * (i + 1),
        ))
    return preds


def test_mcnemar():
    preds_a = _make_preds([True, True, False, True, False])
    preds_b = _make_preds([True, False, True, True, True])
    result = StatisticalTests.mcnemar_test(preds_a, preds_b)
    assert "p_value" in result
    assert "chi2" in result
    assert "verdict" in result
    assert 0 <= result["p_value"] <= 1


def test_bootstrap_ci():
    preds = _make_preds([True, True, False, True, False, True, True, False])
    result = StatisticalTests.bootstrap_confidence_interval(preds)
    assert result["ci_lower"] <= result["observed"] <= result["ci_upper"]
    assert result["confidence"] == 0.95


def test_permutation():
    preds_a = _make_preds([True, True, False, True, False])
    preds_b = _make_preds([True, False, True, True, True])
    result = StatisticalTests.paired_permutation_test(preds_a, preds_b)
    assert "p_value" in result
    assert 0 <= result["p_value"] <= 1


def test_cost_accuracy_chart():
    metrics = {
        "openai/gpt-4o-mini": {
            "accuracy": 0.85,
            "cost_per_diagnosis_usd": 0.002,
            "avg_execution_time_ms": 1500,
        },
        "local/llama3": {
            "accuracy": 0.72,
            "cost_per_diagnosis_usd": 0.0,
            "avg_execution_time_ms": 4000,
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "chart.png")
        Visualizer.plot_cost_accuracy_tradeoff(metrics, path)
        assert os.path.exists(path)


def test_prediction_result_cost_field():
    p = PredictionResult(
        log_id="x", predicted_error_type="unknown", actual_error_type="timeout",
        predicted_lines=[], actual_lines=[],
        confidence=0.5, hallucination_detected=False,
        execution_time_ms=100, cost_usd=0.0042,
    )
    assert p.cost_usd == 0.0042
