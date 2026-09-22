"""Offline tests for the kickoff-decision guards: partitions, evidence, metrics."""

import json
import os

import pytest

from src.evaluation.case_partitions import describe_overlap, find_overlap, load_exclusions
from src.evaluation.category_metrics import (
    aggregate_evidence_lines,
    category_scores,
    evidence_line_scores,
    macro_f1,
)
from src.evaluation.ground_truth_audit import audit_annotations, audit_ground_truth_file, root_cause_problem

# ── D4: development and pilot cases must not reach the held-out set ────────


def _write_smoke_manifest(root, cohort, case_ids, cohort_file="cohort.json", exclude=True):
    study_dir = os.path.join(root, "studies", cohort)
    os.makedirs(study_dir, exist_ok=True)
    cohort_path = os.path.join(study_dir, cohort_file)
    with open(cohort_path, "w") as handle:
        json.dump([{"log_id": case_id} for case_id in case_ids], handle)
    with open(os.path.join(study_dir, "smoke_manifest.json"), "w") as handle:
        json.dump(
            {
                "cohort_id": cohort,
                "purpose": "engineering_smoke_test",
                "usable_as_final_thesis_evidence": False,
                "exclude_from_future_held_out_evaluation": exclude,
                "output": {"file": cohort_path},
                "selected_cases": [{"log_id": case_id} for case_id in case_ids],
            },
            handle,
        )
    return cohort_path


def test_exploratory_cases_are_detected_in_a_later_cohort(tmp_path):
    _write_smoke_manifest(str(tmp_path), "smoke_001", ["a", "b"])
    excluded, problems = load_exclusions(os.path.join(str(tmp_path), "studies"))

    assert problems == []
    assert sorted(excluded) == ["a", "b"]

    final_logs = [{"log_id": "a"}, {"log_id": "c"}, {"log_id": "b"}]
    hits = find_overlap(final_logs, excluded)
    assert [hit.case_id for hit in hits] == ["a", "b"]
    assert "smoke_001" in describe_overlap(hits)


def test_a_cohort_does_not_exclude_its_own_cases(tmp_path):
    """Running the smoke cohort over its own cases is the point of that cohort."""
    cohort_path = _write_smoke_manifest(str(tmp_path), "smoke_001", ["a", "b"])
    excluded, _ = load_exclusions(os.path.join(str(tmp_path), "studies"), current_input=cohort_path)
    assert excluded == {}


def test_a_cohort_that_does_not_declare_itself_exploratory_excludes_nothing(tmp_path):
    _write_smoke_manifest(str(tmp_path), "smoke_001", ["a"], exclude=False)
    excluded, _ = load_exclusions(os.path.join(str(tmp_path), "studies"))
    assert excluded == {}


def test_an_unreadable_manifest_is_reported_rather_than_skipped_silently(tmp_path):
    study_dir = os.path.join(str(tmp_path), "studies", "smoke_001")
    os.makedirs(study_dir)
    with open(os.path.join(study_dir, "smoke_manifest.json"), "w") as handle:
        handle.write('{"cohort_id": "smoke_001",')
    excluded, problems = load_exclusions(os.path.join(str(tmp_path), "studies"))
    assert excluded == {}
    assert len(problems) == 1 and "could not be read" in problems[0]


# ── D3: ground truth needs evidence and independent verification ──────────


def _annotation(**overrides):
    record = {
        "log_id": "a",
        "actual_error_type": "syntax_error",
        "actual_root_cause": "A trailing comma in the generated error-code map broke JSON parsing.",
        "failure_lines": [12, 13],
        "evidence_method": "historical_fix",
        "fixing_reference": "https://example.invalid/pull/9",
        "annotator": "reviewer-one",
        "verifier": "reviewer-two",
    }
    record.update(overrides)
    return record


def test_a_bare_menu_digit_is_rejected_as_a_root_cause():
    # The recorded smoke ground truth held "6": the category index, typed one
    # prompt too late, which the old tool accepted as a root cause.
    assert "menu index" in root_cause_problem("6")
    assert "repeats the category name" in root_cause_problem("syntax_error")
    assert "too short" in root_cause_problem("broken build")
    assert root_cause_problem("") == "is empty"
    assert root_cause_problem(None) == "is empty"
    assert root_cause_problem("A trailing comma in codes.json broke Jest's setup module.") is None


def test_a_complete_annotation_passes_every_requirement():
    audit = audit_annotations([_annotation(), _annotation(log_id="b")])
    assert audit.is_defensible
    assert audit.findings == []
    assert audit.verified_cases == 2
    assert audit.evidence_methods == {"historical_fix": 2}


def test_unlinked_human_judgement_blocks_accuracy_claims():
    audit = audit_annotations([{"log_id": "a", "actual_error_type": "syntax_error", "actual_root_cause": "6"}])
    codes = {finding.code for finding in audit.findings}
    assert not audit.is_defensible
    assert "no_evidence_method" in codes
    assert "no_independent_verification" in codes
    assert "unusable_root_cause" in codes
    assert "no_supporting_lines" in codes


def test_a_verifier_who_is_the_annotator_does_not_count():
    audit = audit_annotations([_annotation(verifier="reviewer-one")])
    assert not audit.is_defensible
    assert audit.verified_cases == 0
    assert any(finding.code == "no_independent_verification" for finding in audit.findings)


def test_one_annotator_is_acceptable_once_every_case_is_verified():
    audit = audit_annotations([_annotation(), _annotation(log_id="b")])
    assert audit.annotators == ["reviewer-one"]
    assert not any(finding.code == "single_annotator" for finding in audit.findings)


def test_a_historical_fix_without_its_reference_is_blocked():
    audit = audit_annotations([_annotation(fixing_reference="")])
    assert any(finding.code == "missing_fix_reference" for finding in audit.findings)


def test_a_seeded_defect_without_its_seed_id_is_blocked():
    audit = audit_annotations([_annotation(evidence_method="seeded_defect", fixing_reference=None, seed_reference="")])
    assert any(finding.code == "missing_seed_reference" for finding in audit.findings)


def test_a_missing_ground_truth_file_is_blocking_not_an_exception(tmp_path):
    audit = audit_ground_truth_file(str(tmp_path / "absent.json"))
    assert not audit.exists
    assert not audit.is_defensible
    assert audit.findings[0].code == "missing_ground_truth"


def test_a_truncated_ground_truth_file_is_reported(tmp_path):
    path = tmp_path / "gt.json"
    path.write_text('{"annotations": [')
    audit = audit_ground_truth_file(str(path))
    assert audit.findings[0].code == "unreadable_ground_truth"


# ── D5: category-level results, and the unused evidence-line fields ───────


def test_category_scores_keep_a_category_the_model_never_predicts():
    pairs = [
        ("syntax_error", "syntax_error"),
        ("syntax_error", "unknown"),
        ("timeout", "unknown"),
        ("dependency_error", "dependency_error"),
    ]
    scores = category_scores(pairs, ("syntax_error", "timeout", "dependency_error", "network_error"))

    assert scores["syntax_error"]["support"] == 2
    assert scores["syntax_error"]["precision"] == 1.0
    assert scores["syntax_error"]["recall"] == 0.5
    assert scores["syntax_error"]["f1"] == pytest.approx(0.6667, abs=0.001)
    # Present in the ground truth, never predicted: recall 0, still listed.
    assert scores["timeout"]["support"] == 1
    assert scores["timeout"]["recall"] == 0.0
    # Never in the ground truth at all: no support, excluded from macro F1.
    assert scores["network_error"]["support"] == 0


def test_macro_f1_ignores_categories_with_no_ground_truth_support():
    scores = category_scores([("timeout", "timeout")], ("timeout", "network_error"))
    assert scores["network_error"]["support"] == 0
    assert macro_f1(scores) == 1.0


def test_macro_f1_is_none_when_nothing_can_be_scored():
    assert macro_f1({}) is None


def test_evidence_line_scores_measure_overlap_with_the_annotated_lines():
    result = evidence_line_scores(predicted=[10, 11, 99], actual=[10, 11, 12])
    assert result["scorable"] is True
    assert result["matched_lines"] == 2
    assert result["precision"] == pytest.approx(0.6667, abs=0.001)
    assert result["recall"] == pytest.approx(0.6667, abs=0.001)
    assert result["jaccard"] == 0.5


def test_a_case_with_no_annotated_lines_is_unscorable_not_zero():
    """Missing annotation must never be reported as a model failure."""
    result = evidence_line_scores(predicted=[1, 2], actual=[])
    assert result["scorable"] is False
    assert result["f1"] is None
    assert aggregate_evidence_lines([result])["scorable_cases"] == 0


def test_aggregate_evidence_lines_averages_only_scorable_cases():
    cases = [
        evidence_line_scores([1], [1]),
        evidence_line_scores([9], [1]),
        evidence_line_scores([1], []),
    ]
    summary = aggregate_evidence_lines(cases)
    assert summary["scorable_cases"] == 2
    assert summary["mean_f1"] == 0.5
