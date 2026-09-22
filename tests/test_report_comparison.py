"""Offline tests for report loading, alignment and the visual comparison."""

import json
import os

import pytest

from src.evaluation.comparison_view import fmt_ms, fmt_usd, pct, render_html, type_label
from src.evaluation.report_comparison import (
    INFERENCE_ERROR,
    build_comparison,
    compute_model_metrics,
    cross_experiment_deltas,
    discover_experiments,
    load_experiment,
    pairwise_agreements,
    read_json,
)


def _result(log_id, model, error_type, **overrides):
    row = {
        "status": "success",
        "log_id": log_id,
        "repository": f"org/{log_id}",
        "workflow": "CI",
        "model": model,
        "error_type": error_type,
        "root_cause": "because",
        "suggested_fix": "fix it",
        "confidence_score": 0.9,
        "failure_lines": [1, 2],
        "grounding_score": 0.8,
        "hallucination_detected": False,
        "total_tokens": 100,
        "cost_usd": 0.01,
        "execution_time_ms": 1000.0,
    }
    row.update(overrides)
    return row


def _write_experiment(root, name, per_model, ground_truth, stats=None, stats_text=None):
    """Create one experiment directory the way benchmark_models.py lays it out."""
    path = os.path.join(root, "studies", "unit_study", "experiments", name)
    os.makedirs(path, exist_ok=True)
    gt_path = os.path.join(root, "studies", "unit_study", "ground_truth", "ground_truth.json")
    os.makedirs(os.path.dirname(gt_path), exist_ok=True)
    with open(gt_path, "w") as handle:
        json.dump({"study_id": "unit_study", "annotations": ground_truth}, handle)
    with open(os.path.join(path, "run_metadata.json"), "w") as handle:
        json.dump(
            {
                "run_started_at_utc": "2026-01-01T00:00:00+00:00",
                "ground_truth_file": gt_path,
                "pilot": True,
                "reasoning_effort": "medium",
                "models_requested": list(per_model),
                "git_commit": {"returncode": 0, "output": "abc1234def"},
            },
            handle,
        )
    for model, rows in per_model.items():
        safe = model.replace("/", "_").replace(":", "_")
        with open(os.path.join(path, f"results_{safe}.json"), "w") as handle:
            json.dump(rows, handle)
    if stats is not None:
        with open(os.path.join(path, "statistical_tests.json"), "w") as handle:
            json.dump(stats, handle)
    elif stats_text is not None:
        with open(os.path.join(path, "statistical_tests.json"), "w") as handle:
            handle.write(stats_text)
    return path


def _annotation(log_id, error_type, lines):
    """A fully specified annotation: evidence-linked and independently verified."""
    return {
        "log_id": log_id,
        "actual_error_type": error_type,
        "actual_root_cause": f"The {error_type} was traced to the change reverted by the linked fix.",
        "failure_lines": lines,
        "evidence_method": "historical_fix",
        "fixing_reference": f"https://example.invalid/{log_id}/pull/1",
        "annotator": "reviewer-one",
        "verifier": "reviewer-two",
        "agreement": "agree",
    }


GROUND_TRUTH = [
    _annotation("a", "syntax_error", [1, 2, 3]),
    _annotation("b", "dependency_error", [2]),
    _annotation("c", "timeout", [3]),
]


@pytest.fixture
def experiment(tmp_path):
    """One two-condition experiment: one shared hit, one split, one shared miss."""
    return _write_experiment(
        str(tmp_path),
        "pilot_001",
        {
            "openai/model-a": [
                _result("a", "openai/model-a", "syntax_error"),
                _result("b", "openai/model-a", "network_error"),
                _result("c", "openai/model-a", "unknown"),
            ],
            "local/model-b": [
                _result("a", "local/model-b", "syntax_error"),
                _result("b", "local/model-b", "dependency_error", cost_usd=0.0, execution_time_ms=90_000.0),
                _result("c", "local/model-b", "network_error", hallucination_detected=True),
            ],
        },
        GROUND_TRUTH,
        stats={
            "models_compared": ["openai/model-a", "local/model-b"],
            "n_common_logs": 3,
            "mcnemar": {"n01": 1, "n10": 0, "chi2": 0.0, "p_value": 1.0, "verdict": "No difference"},
            "bootstrap_ci": {"openai/model-a": {"observed": 0.333, "ci_lower": 0.0, "ci_upper": 0.667}},
            "permutation_test": {"observed_accuracy_diff": -0.333, "p_value": 0.5},
        },
    )


def test_read_json_reports_missing_and_truncated(tmp_path):
    missing = str(tmp_path / "nope.json")
    assert read_json(missing) == (None, "missing")

    truncated = tmp_path / "half.json"
    truncated.write_text('{"mcnemar": {"chi2": 0.5, "significant_at_005":')
    assert read_json(str(truncated)) == (None, "unreadable")


def test_metrics_count_inference_failures_as_incorrect():
    results = [
        _result("a", "m", "syntax_error"),
        {"status": "error", "log_id": "b", "model": "m", "execution_time_ms": 10.0, "error": "timeout"},
    ]
    metrics = compute_model_metrics(results, GROUND_TRUTH)
    assert metrics["total_logs"] == 2
    assert metrics["successful_logs"] == 1
    assert metrics["failed_logs"] == 1
    # One of two ground-truth-matched logs was right, so accuracy is 50% even
    # though the model answered only one of them.
    assert metrics["matched_gt_logs"] == 2
    assert metrics["error_type_accuracy"] == 0.5


def test_load_experiment_aligns_models_on_log_id(experiment):
    report = load_experiment(experiment)

    assert report.study_id == "unit_study"
    assert report.experiment_id == "pilot_001"
    assert sorted(report.model_labels) == ["local/model-b", "openai/model-a"]
    assert report.log_order == ["a", "b", "c"]
    assert report.run_context["reasoning_effort"] == "medium"

    assert report.outcome("openai/model-a", "a").correct is True
    assert report.outcome("openai/model-a", "b").correct is False
    assert report.outcome("local/model-b", "b").correct is True
    assert report.metrics["openai/model-a"]["error_type_accuracy"] == pytest.approx(0.333, abs=0.001)
    assert report.metrics["local/model-b"]["hallucination_rate"] == pytest.approx(0.333, abs=0.001)
    assert report.statistical_tests["n_common_logs"] == 3
    assert report.issues == []


def test_failed_diagnosis_becomes_an_explicit_no_diagnosis_outcome(tmp_path):
    path = _write_experiment(
        str(tmp_path),
        "pilot_001",
        {
            "openai/model-a": [
                _result("a", "openai/model-a", "syntax_error"),
                {
                    "status": "error",
                    "log_id": "b",
                    "model": "openai/model-a",
                    "execution_time_ms": 5.0,
                    "error": "boom",
                },
            ]
        },
        GROUND_TRUTH,
    )
    report = load_experiment(path)
    outcome = report.outcome("openai/model-a", "b")
    assert outcome.predicted_error_type == INFERENCE_ERROR
    assert outcome.correct is False
    assert type_label(INFERENCE_ERROR) == "no diagnosis"


def test_pairwise_agreement_splits_the_four_outcomes(experiment):
    pair = pairwise_agreements(load_experiment(experiment))[0]
    assert pair.n_common == 3
    assert pair.both_correct == 1
    assert pair.only_a_correct + pair.only_b_correct == 1
    assert pair.both_wrong == 1
    assert pair.same_prediction == 1
    assert pair.to_dict()["prediction_agreement_rate"] == pytest.approx(0.333, abs=0.001)


def test_truncated_statistics_degrade_to_a_reported_issue(tmp_path):
    path = _write_experiment(
        str(tmp_path),
        "pilot_001",
        {
            "openai/model-a": [_result("a", "openai/model-a", "syntax_error")],
            "local/model-b": [_result("a", "local/model-b", "timeout")],
        },
        GROUND_TRUTH,
        stats_text='{"mcnemar": {"chi2": 0.5, "significant_at_005":',
    )
    report = load_experiment(path)
    assert report.statistical_tests is None
    assert any("statistical_tests.json is truncated" in issue for issue in report.issues)
    # The rest of the run is still fully comparable.
    assert report.metrics["openai/model-a"]["error_type_accuracy"] == 1.0
    assert report.metrics["local/model-b"]["error_type_accuracy"] == 0.0


def test_discovery_finds_only_directories_with_results(tmp_path):
    _write_experiment(
        str(tmp_path),
        "pilot_001",
        {"openai/model-a": [_result("a", "openai/model-a", "syntax_error")]},
        GROUND_TRUTH,
    )
    empty = os.path.join(str(tmp_path), "studies", "unit_study", "experiments", "pilot_002")
    os.makedirs(empty)
    found = discover_experiments(os.path.join(str(tmp_path), "studies"))
    assert [os.path.basename(path) for path in found] == ["pilot_001"]


def test_cross_experiment_deltas_measure_against_the_first_run(tmp_path):
    first = _write_experiment(
        str(tmp_path),
        "pilot_001",
        {
            "openai/model-a": [
                _result(log["log_id"], "openai/model-a", log["actual_error_type"]) for log in GROUND_TRUTH
            ]
        },
        GROUND_TRUTH,
    )
    second = _write_experiment(
        str(tmp_path),
        "pilot_002",
        {"openai/model-a": [_result(log["log_id"], "openai/model-a", "unknown") for log in GROUND_TRUTH]},
        GROUND_TRUTH,
    )
    rows = cross_experiment_deltas([load_experiment(first), load_experiment(second)])
    accuracy = next(row for row in rows if row["metric"] == "error_type_accuracy")
    assert accuracy["points"][0]["value"] == 1.0
    assert accuracy["points"][0]["is_baseline"] is True
    assert accuracy["points"][1]["delta"] == pytest.approx(-1.0)


def test_build_comparison_is_json_serialisable(experiment):
    payload = build_comparison([load_experiment(experiment)])
    restored = json.loads(json.dumps(payload))
    assert restored["schema_version"] == 1
    assert len(restored["experiments"]) == 1
    assert "syntax_error" in restored["error_types"]
    assert restored["experiments"][0]["agreement"][0]["n_common"] == 3


def test_render_html_is_self_contained_and_covers_every_log(experiment):
    page = render_html([load_experiment(experiment)])

    assert page.startswith("<!DOCTYPE html>")
    assert "<script" not in page
    assert "http://" not in page and "https://" not in page
    for model in ("openai/model-a", "local/model-b"):
        assert model in page
    for log_id in ("a", "b", "c"):
        assert f"org/{log_id}" in page
    assert "prefers-color-scheme: dark" in page
    # Identity is never colour-alone: the legend and per-cell glyphs are present.
    assert page.count("swatch") >= 2
    assert "✓" in page and "✗" in page


def test_render_html_escapes_untrusted_report_text(tmp_path):
    path = _write_experiment(
        str(tmp_path),
        "pilot_001",
        {
            "openai/model-a": [
                _result("a", "openai/model-a", "syntax_error", root_cause="<script>alert(1)</script>"),
            ]
        },
        GROUND_TRUTH,
    )
    page = render_html([load_experiment(path)])
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_render_html_requires_at_least_one_report():
    with pytest.raises(ValueError):
        render_html([])


def test_display_helpers_round_the_way_the_terminal_table_does():
    assert pct(0.4, 0) == "40%"
    assert pct(None) == "n/a"
    assert fmt_ms(500) == "500 ms"
    assert fmt_ms(19_400) == "19.4 s"
    assert fmt_ms(1_046_376) == "17.4 min"
    assert fmt_usd(0) == "$0.00"
    assert fmt_usd(0.038115) == "$0.0381"
    assert type_label("build_configuration") == "build configuration"
