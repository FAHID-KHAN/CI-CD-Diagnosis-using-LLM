"""Load, align and compare the JSON reports written by ``benchmark_models.py``.

An experiment directory holds one ``results_<model>.json`` per condition plus the
run-level ``comparison_report.json``, ``statistical_tests.json`` and
``run_metadata.json``. This module turns any number of those directories into a
single aligned structure -- the same logs, the same metric definitions and the
same ground truth for every model and every run -- so conditions can be read
against each other instead of one file at a time.

The per-log ``results_<model>.json`` files are the single source of truth for
every metric computed here. ``comparison_report.json`` only supplies run-level
context, because a run interrupted before its final write still has complete
per-log results but an incomplete or missing summary.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.evaluation.category_metrics import (
    aggregate_evidence_lines,
    category_scores,
    evidence_line_scores,
    macro_f1,
)
from src.evaluation.ground_truth_audit import GroundTruthAudit, audit_ground_truth_file

# Re-exported so existing callers keep importing the vocabulary and the tolerant
# readers from this module.
from src.evaluation.study_io import load_ground_truth, read_json  # noqa: F401
from src.evaluation.taxonomy import ERROR_TYPE_ORDER, INFERENCE_ERROR  # noqa: F401

RESULTS_PREFIX = "results_"
RESULTS_SUFFIX = ".json"


# ── Metrics ───────────────────────────────────────────────────────────────


def compute_model_metrics(results: List[dict], ground_truth: Optional[List[dict]] = None) -> dict:
    """Compute summary metrics for one model's results."""
    attempted = len(results)
    successful = [r for r in results if r.get("status", "success") == "success"]
    n = len(successful)
    if attempted == 0:
        return {
            "total_logs": 0,
            "successful_logs": 0,
            "failed_logs": 0,
            "avg_confidence": 0.0,
            "avg_execution_time_ms": 0.0,
            "mean_grounding_score": 0.0,
            "hallucination_rate": 0.0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "cost_per_diagnosis_usd": 0.0,
            "error_type_distribution": {},
        }

    avg_confidence = sum(r["confidence_score"] for r in successful) / n if n else 0.0
    avg_time = sum(r["execution_time_ms"] for r in successful) / n if n else 0.0
    error_dist = dict(Counter(r["error_type"] for r in successful))

    metrics = {
        "total_logs": attempted,
        "successful_logs": n,
        "failed_logs": attempted - n,
        "avg_confidence": round(avg_confidence, 3),
        "avg_execution_time_ms": round(avg_time, 1),
        "error_type_distribution": error_dist,
        "mean_grounding_score": round(sum(r.get("grounding_score", 0) for r in successful) / n, 3) if n else 0.0,
        "hallucination_rate": (
            round(sum(bool(r.get("hallucination_detected")) for r in successful) / n, 3) if n else 0.0
        ),
        "total_tokens": sum(r.get("total_tokens", 0) for r in successful),
        "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in successful), 6),
        "cost_per_diagnosis_usd": round(sum(r.get("cost_usd", 0) for r in successful) / n, 6) if n else 0.0,
    }

    # Inference failures count as incorrect so this measures the complete
    # diagnostic system, not only the subset of successful model calls.
    if ground_truth:
        gt_map = {a["log_id"]: a for a in ground_truth}
        matched_results = [result for result in results if result.get("log_id") in gt_map]
        type_correct = sum(
            result.get("status", "success") == "success"
            and result.get("error_type") == gt_map[result["log_id"]]["actual_error_type"]
            for result in matched_results
        )
        if matched_results:
            metrics["matched_gt_logs"] = len(matched_results)
            metrics["error_type_accuracy"] = round(type_correct / len(matched_results), 3)

    return metrics


# ── Aligned view of one experiment ────────────────────────────────────────


@dataclass
class LogOutcome:
    """One model's answer for one log, paired against its ground truth."""

    log_id: str
    model: str
    status: str
    predicted_error_type: str
    actual_error_type: Optional[str]
    correct: Optional[bool]
    confidence: float
    grounding_score: float
    hallucination_detected: bool
    execution_time_ms: float
    cost_usd: float
    root_cause: str = ""
    suggested_fix: str = ""
    failure_lines: List[int] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "model": self.model,
            "status": self.status,
            "predicted_error_type": self.predicted_error_type,
            "actual_error_type": self.actual_error_type,
            "correct": self.correct,
            "confidence": self.confidence,
            "grounding_score": self.grounding_score,
            "hallucination_detected": self.hallucination_detected,
            "execution_time_ms": self.execution_time_ms,
            "cost_usd": self.cost_usd,
            "failure_lines": self.failure_lines,
        }


@dataclass
class ExperimentReport:
    """Every report file in one experiment directory, aligned by log id."""

    path: str
    study_id: str
    experiment_id: str
    model_labels: List[str] = field(default_factory=list)
    metrics: Dict[str, dict] = field(default_factory=dict)
    ground_truth_audit: Optional[GroundTruthAudit] = None
    outcomes: Dict[str, Dict[str, LogOutcome]] = field(default_factory=dict)
    log_order: List[str] = field(default_factory=list)
    log_info: Dict[str, dict] = field(default_factory=dict)
    ground_truth: Dict[str, dict] = field(default_factory=dict)
    statistical_tests: Optional[dict] = None
    run_context: Dict[str, object] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.study_id}/{self.experiment_id}"

    def outcome(self, model: str, log_id: str) -> Optional[LogOutcome]:
        return self.outcomes.get(model, {}).get(log_id)

    def category_report(self, model: str) -> dict:
        """Per-category precision/recall/F1 and macro F1 for one condition."""
        pairs = [
            (outcome.actual_error_type, outcome.predicted_error_type)
            for outcome in self.outcomes.get(model, {}).values()
            if outcome.actual_error_type
        ]
        scores = category_scores(pairs, ERROR_TYPE_ORDER)
        return {"categories": scores, "macro_f1": macro_f1(scores), "scored_cases": len(pairs)}

    def evidence_report(self, model: str) -> dict:
        """Evidence-line precision/recall/F1 for one condition, per case and mean."""
        per_case = []
        for log_id in self.log_order:
            outcome = self.outcome(model, log_id)
            truth = self.ground_truth.get(log_id)
            if outcome is None or truth is None:
                continue
            case = evidence_line_scores(outcome.failure_lines, truth.get("failure_lines", []))
            case["log_id"] = log_id
            per_case.append(case)
        return {"per_case": per_case, **aggregate_evidence_lines(per_case)}

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "study_id": self.study_id,
            "experiment_id": self.experiment_id,
            "label": self.label,
            "run_context": self.run_context,
            "model_labels": self.model_labels,
            "metrics": self.metrics,
            "log_order": self.log_order,
            "log_info": self.log_info,
            "ground_truth": {
                log_id: {
                    "actual_error_type": entry.get("actual_error_type"),
                    "failure_lines": entry.get("failure_lines", []),
                    "annotator": entry.get("annotator"),
                }
                for log_id, entry in self.ground_truth.items()
            },
            "outcomes": {
                model: {log_id: outcome.to_dict() for log_id, outcome in per_log.items()}
                for model, per_log in self.outcomes.items()
            },
            "statistical_tests": self.statistical_tests,
            "agreement": [pair.to_dict() for pair in pairwise_agreements(self)],
            "confusion": {model: confusion_rows(self, model) for model in self.model_labels},
            "category_metrics": {model: self.category_report(model) for model in self.model_labels},
            "evidence_line_metrics": {model: self.evidence_report(model) for model in self.model_labels},
            "ground_truth_audit": (self.ground_truth_audit.to_dict() if self.ground_truth_audit else None),
            "issues": self.issues,
        }


@dataclass
class PairAgreement:
    """How two conditions in one experiment relate, log by log."""

    model_a: str
    model_b: str
    n_common: int
    both_correct: int
    only_a_correct: int
    only_b_correct: int
    both_wrong: int
    same_prediction: int

    @property
    def scored(self) -> int:
        return self.both_correct + self.only_a_correct + self.only_b_correct + self.both_wrong

    def to_dict(self) -> dict:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "n_common": self.n_common,
            "both_correct": self.both_correct,
            "only_a_correct": self.only_a_correct,
            "only_b_correct": self.only_b_correct,
            "both_wrong": self.both_wrong,
            "same_prediction": self.same_prediction,
            "prediction_agreement_rate": (round(self.same_prediction / self.n_common, 3) if self.n_common else None),
        }


def model_label_from_filename(filename: str) -> str:
    """Recover ``provider/model`` from a ``results_<safe-name>.json`` filename.

    The writer flattens ``/`` and ``:``; the stored rows keep the real label, so
    this is only the fallback for a file whose rows are empty.
    """
    stem = filename[len(RESULTS_PREFIX) : -len(RESULTS_SUFFIX)]
    provider, _, rest = stem.partition("_")
    return f"{provider}/{rest}" if rest else stem


def _resolve_ground_truth_path(experiment_path: str, run_metadata: Optional[dict]) -> Optional[str]:
    """Prefer the path the run recorded, fall back to the study's own file."""
    if isinstance(run_metadata, dict):
        recorded = run_metadata.get("ground_truth_file")
        if isinstance(recorded, str) and os.path.exists(recorded):
            return recorded
    study_root = os.path.dirname(os.path.dirname(os.path.abspath(experiment_path)))
    fallback = os.path.join(study_root, "ground_truth", "ground_truth.json")
    return fallback if os.path.exists(fallback) else None


def load_experiment(experiment_path: str, ground_truth_path: Optional[str] = None) -> ExperimentReport:
    """Read one experiment directory into an aligned, comparable report."""
    experiment_path = os.path.abspath(experiment_path)
    if not os.path.isdir(experiment_path):
        raise FileNotFoundError(f"Experiment directory does not exist: {experiment_path}")

    experiment_id = os.path.basename(experiment_path)
    study_id = os.path.basename(os.path.dirname(os.path.dirname(experiment_path)))
    report = ExperimentReport(path=experiment_path, study_id=study_id, experiment_id=experiment_id)

    run_metadata, run_status = read_json(os.path.join(experiment_path, "run_metadata.json"))
    if run_status == "unreadable":
        report.issues.append("run_metadata.json could not be parsed; run context is unavailable.")
    if not isinstance(run_metadata, dict):
        run_metadata = {}

    summary, summary_status = read_json(os.path.join(experiment_path, "comparison_report.json"))
    if summary_status == "unreadable":
        report.issues.append(
            "comparison_report.json could not be parsed; metrics were recomputed from per-log results."
        )
    if not isinstance(summary, dict):
        summary = {}

    git_commit = run_metadata.get("git_commit")
    report.run_context = {
        "run_started_at_utc": run_metadata.get("run_started_at_utc"),
        "timestamp": summary.get("timestamp"),
        "pilot": summary.get("pilot", run_metadata.get("pilot")),
        "reasoning_effort": summary.get("reasoning_effort", run_metadata.get("reasoning_effort")),
        "models_requested": run_metadata.get("models_requested", []),
        "input_file": summary.get("input_file", run_metadata.get("input_file")),
        "git_commit": git_commit.get("output") if isinstance(git_commit, dict) else None,
        "prompt_sha256": run_metadata.get("prompt_sha256"),
        "log_filter": run_metadata.get("log_filter"),
        "platform": run_metadata.get("platform"),
        "python_version": run_metadata.get("python_version"),
    }

    gt_path = ground_truth_path or _resolve_ground_truth_path(experiment_path, run_metadata)
    annotations: List[dict] = []
    if gt_path:
        annotations, gt_status = load_ground_truth(gt_path)
        if gt_status != "ok":
            report.issues.append(f"Ground truth at {gt_path} is {gt_status}; accuracy cannot be computed.")
    else:
        report.issues.append("No ground-truth file was found; accuracy cannot be computed.")
    report.ground_truth = {item["log_id"]: item for item in annotations if item.get("log_id")}
    report.run_context["ground_truth_file"] = gt_path
    report.ground_truth_audit = audit_ground_truth_file(gt_path or "")
    # One note per distinct problem, not per case: the ground-truth panel carries
    # the per-case breakdown.
    if report.ground_truth_audit.blocking:
        for line in report.ground_truth_audit.summary_lines():
            if line.startswith("[blocking]"):
                report.issues.append(f"Ground truth {line}")

    result_files = sorted(
        name
        for name in os.listdir(experiment_path)
        if name.startswith(RESULTS_PREFIX) and name.endswith(RESULTS_SUFFIX)
    )
    if not result_files:
        report.issues.append("No results_<model>.json files were found in this experiment directory.")

    for filename in result_files:
        rows, status = read_json(os.path.join(experiment_path, filename))
        if status != "ok" or not isinstance(rows, list):
            report.issues.append(f"{filename} is {status}; that condition was skipped.")
            continue
        label = next((row.get("model") for row in rows if row.get("model")), model_label_from_filename(filename))
        report.model_labels.append(label)
        report.metrics[label] = compute_model_metrics(rows, annotations)
        per_log: Dict[str, LogOutcome] = {}
        for row in rows:
            log_id = row.get("log_id")
            if not log_id:
                continue
            if log_id not in report.log_info:
                report.log_order.append(log_id)
                report.log_info[log_id] = {
                    "repository": row.get("repository", ""),
                    "workflow": row.get("workflow", ""),
                }
            truth = report.ground_truth.get(log_id)
            actual = truth.get("actual_error_type") if truth else None
            succeeded = row.get("status", "success") == "success"
            predicted = row.get("error_type", INFERENCE_ERROR) if succeeded else INFERENCE_ERROR
            per_log[log_id] = LogOutcome(
                log_id=log_id,
                model=label,
                status=row.get("status", "success"),
                predicted_error_type=predicted,
                actual_error_type=actual,
                correct=(predicted == actual) if actual else None,
                confidence=float(row.get("confidence_score", 0.0) or 0.0),
                grounding_score=float(row.get("grounding_score", 0.0) or 0.0),
                hallucination_detected=bool(row.get("hallucination_detected")),
                execution_time_ms=float(row.get("execution_time_ms", 0.0) or 0.0),
                cost_usd=float(row.get("cost_usd", 0.0) or 0.0),
                root_cause=row.get("root_cause", ""),
                suggested_fix=row.get("suggested_fix", ""),
                failure_lines=row.get("failure_lines", []) or [],
                error=row.get("error", ""),
            )
        report.outcomes[label] = per_log

    stats, stats_status = read_json(os.path.join(experiment_path, "statistical_tests.json"))
    if stats_status == "ok" and isinstance(stats, dict):
        report.statistical_tests = stats
    elif stats_status == "unreadable":
        report.issues.append(
            "statistical_tests.json is truncated or malformed, so this run has no usable significance test. "
            "Re-run the benchmark to regenerate it."
        )
    elif len(report.model_labels) >= 2:
        report.issues.append("statistical_tests.json is missing, so this run has no paired significance test.")

    return report


def pairwise_agreements(report: ExperimentReport) -> List[PairAgreement]:
    """Compare every ordered pair of conditions in one experiment."""
    pairs: List[PairAgreement] = []
    labels = report.model_labels
    for index, label_a in enumerate(labels):
        for label_b in labels[index + 1 :]:
            outcomes_a = report.outcomes.get(label_a, {})
            outcomes_b = report.outcomes.get(label_b, {})
            common = [log_id for log_id in report.log_order if log_id in outcomes_a and log_id in outcomes_b]
            both_correct = only_a = only_b = both_wrong = same_prediction = 0
            for log_id in common:
                first, second = outcomes_a[log_id], outcomes_b[log_id]
                if first.predicted_error_type == second.predicted_error_type:
                    same_prediction += 1
                if first.correct is None or second.correct is None:
                    continue
                if first.correct and second.correct:
                    both_correct += 1
                elif first.correct:
                    only_a += 1
                elif second.correct:
                    only_b += 1
                else:
                    both_wrong += 1
            pairs.append(
                PairAgreement(
                    model_a=label_a,
                    model_b=label_b,
                    n_common=len(common),
                    both_correct=both_correct,
                    only_a_correct=only_a,
                    only_b_correct=only_b,
                    both_wrong=both_wrong,
                    same_prediction=same_prediction,
                )
            )
    return pairs


def confusion_rows(report: ExperimentReport, model: str) -> List[dict]:
    """Ground-truth type against predicted type for one condition."""
    counts: Counter = Counter()
    for outcome in report.outcomes.get(model, {}).values():
        if outcome.actual_error_type:
            counts[(outcome.actual_error_type, outcome.predicted_error_type)] += 1
    return [
        {"actual": actual, "predicted": predicted, "count": count}
        for (actual, predicted), count in sorted(counts.items())
    ]


def active_error_types(reports: List[ExperimentReport]) -> List[str]:
    """Declared types that actually occur, declared order first, extras after."""
    seen: set = set()
    for report in reports:
        seen.update(entry.get("actual_error_type") for entry in report.ground_truth.values())
        for per_log in report.outcomes.values():
            seen.update(outcome.predicted_error_type for outcome in per_log.values())
    seen.discard(None)
    ordered = [name for name in ERROR_TYPE_ORDER if name in seen]
    ordered.extend(sorted(name for name in seen if name not in ERROR_TYPE_ORDER))
    return ordered


# ── Cross-run comparison ──────────────────────────────────────────────────

# Metrics compared across runs; ``higher_is_better`` drives the delta colouring.
TRACKED_METRICS = (
    ("error_type_accuracy", "Error-type accuracy", "ratio", True),
    ("mean_grounding_score", "Mean grounding score", "ratio", True),
    ("hallucination_rate", "Hallucination rate", "ratio", False),
    ("avg_confidence", "Avg confidence", "ratio", True),
    ("avg_execution_time_ms", "Avg latency", "ms", False),
    ("cost_per_diagnosis_usd", "Cost per diagnosis", "usd", False),
    ("successful_logs", "Successful diagnoses", "count", True),
)


def cross_experiment_deltas(reports: List[ExperimentReport]) -> List[dict]:
    """Track each model's metrics across runs, relative to its earliest run."""
    if len(reports) < 2:
        return []
    rows = []
    all_models = []
    for report in reports:
        for label in report.model_labels:
            if label not in all_models:
                all_models.append(label)
    for label in all_models:
        present = [report for report in reports if label in report.metrics]
        if len(present) < 2:
            continue
        baseline = present[0]
        for key, title, unit, higher_is_better in TRACKED_METRICS:
            base_value = baseline.metrics[label].get(key)
            if base_value is None:
                continue
            points = []
            for report in present:
                value = report.metrics[label].get(key)
                delta = None if value is None else round(value - base_value, 6)
                points.append(
                    {
                        "experiment": report.label,
                        "value": value,
                        "delta": delta,
                        "is_baseline": report is baseline,
                    }
                )
            rows.append(
                {
                    "model": label,
                    "metric": key,
                    "title": title,
                    "unit": unit,
                    "higher_is_better": higher_is_better,
                    "points": points,
                }
            )
    return rows


# ── Discovery ─────────────────────────────────────────────────────────────


def discover_experiments(studies_root: str = "data/studies") -> List[str]:
    """Find every experiment directory that holds at least one results file."""
    found: List[str] = []
    if not os.path.isdir(studies_root):
        return found
    for study in sorted(os.listdir(studies_root)):
        experiments_dir = os.path.join(studies_root, study, "experiments")
        if not os.path.isdir(experiments_dir):
            continue
        for experiment in sorted(os.listdir(experiments_dir)):
            path = os.path.join(experiments_dir, experiment)
            if not os.path.isdir(path):
                continue
            if any(name.startswith(RESULTS_PREFIX) and name.endswith(RESULTS_SUFFIX) for name in os.listdir(path)):
                found.append(path)
    return found


def build_comparison(reports: List[ExperimentReport]) -> dict:
    """Assemble the serialisable structure the viewer and the JSON export share."""
    return {
        "schema_version": 1,
        "experiments": [report.to_dict() for report in reports],
        "error_types": active_error_types(reports),
        "cross_experiment": cross_experiment_deltas(reports),
    }
