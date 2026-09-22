"""Offline tests for the stage inspector that drives run_workflow.sh."""

import json
import os
from pathlib import Path

import pytest

from automated_scripts.study_status import (
    BLOCKED,
    DONE,
    PARTIAL,
    TODO,
    collect_stages,
    next_action,
    stage_collection,
    stage_ground_truth,
    stage_partitions,
    stage_triage,
)

CONFIG = {
    "study_id": "unit_study",
    "repositories": [{"name": "org/one", "max_logs": 5}, {"name": "org/two", "max_logs": 5}],
    "eligibility": {},
}


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def study(tmp_path):
    root = tmp_path / "studies" / "unit_study"
    root.mkdir(parents=True)
    return root


def _annotation(log_id, verified=True, root_cause=None):
    return {
        "log_id": log_id,
        "actual_error_type": "syntax_error",
        "actual_root_cause": root_cause or "A trailing comma in the generated map broke JSON parsing.",
        "failure_lines": [4],
        "evidence_method": "historical_fix",
        "fixing_reference": "https://example.invalid/pull/1",
        "annotator": "reviewer-one",
        **({"verifier": "reviewer-two"} if verified else {}),
    }


# ── stages are judged by artefacts, not by whether a command was run ──────


def test_collection_without_a_manifest_is_partial_not_done(study):
    write(study / "raw" / "logs.json", [{"log_id": "a"}, {"log_id": "b"}])
    stage = stage_collection(study)
    assert stage.state == PARTIAL
    assert "no manifest" in stage.detail


def test_an_incomplete_collection_manifest_is_partial(study):
    write(study / "raw" / "logs.json", [{"log_id": "a"}])
    write(study / "collection_manifest.json", {"status": "in_progress", "repositories": [{}]})
    assert stage_collection(study).state == PARTIAL


def test_collection_errors_surface_as_a_note(study):
    write(study / "raw" / "logs.json", [{"log_id": "a"}])
    write(
        study / "collection_manifest.json",
        {"status": "complete", "repositories": [{}], "collection_errors": [{"repo": "org/one"}]},
    )
    stage = stage_collection(study)
    assert stage.state == DONE
    assert "1 collection error(s) recorded" in stage.notes


def test_triage_below_the_configured_minimum_is_flagged(study):
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}])
    write(study / "excluded" / "excluded_logs.json", [])
    write(study / "triage_manifest.json", {"eligible_target": {"minimum": 50}})
    stage = stage_triage(study)
    assert stage.state == DONE
    assert any("below the configured minimum" in note for note in stage.notes)


def test_ground_truth_is_partial_until_every_case_is_annotated(study):
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}, {"log_id": "b"}])
    write(study / "ground_truth" / "ground_truth.json", {"annotations": [_annotation("a")]})
    stage = stage_ground_truth(study)
    assert stage.state == PARTIAL
    assert "1 of 2 annotated" in stage.detail


def test_ground_truth_is_done_only_when_complete_and_defensible(study):
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}, {"log_id": "b"}])
    write(
        study / "ground_truth" / "ground_truth.json",
        {"annotations": [_annotation("a"), _annotation("b")]},
    )
    stage = stage_ground_truth(study)
    assert stage.state == DONE
    assert "2 independently verified" in stage.detail


def test_unverified_ground_truth_blocks_even_when_complete(study):
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}])
    write(study / "ground_truth" / "ground_truth.json", {"annotations": [_annotation("a", verified=False)]})
    assert stage_ground_truth(study).state == BLOCKED


# ── the held-out separation gate ──────────────────────────────────────────


def test_a_cohort_sharing_cases_with_an_exploratory_set_is_blocked(study):
    cohort = study / "triaged" / "eligible_logs.json"
    write(cohort, [{"log_id": "a"}, {"log_id": "b"}, {"log_id": "c"}])

    smoke = study.parent / "smoke_001"
    smoke_cohort = smoke / "triaged" / "eligible_logs.json"
    write(smoke_cohort, [{"log_id": "b"}])
    write(
        smoke / "smoke_manifest.json",
        {
            "cohort_id": "smoke_001",
            "purpose": "engineering_smoke_test",
            "exclude_from_future_held_out_evaluation": True,
            "output": {"file": str(smoke_cohort)},
            "selected_cases": [{"log_id": "b"}],
        },
    )
    stage = stage_partitions(study, study.parent)
    assert stage.state == BLOCKED
    assert "smoke_001" in stage.detail


def test_a_clean_cohort_passes_the_separation_gate(study):
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}])
    assert stage_partitions(study, study.parent).state == DONE


# ── the derived-cohort view and the suggested next command ────────────────


def test_a_derived_cohort_is_not_judged_by_collection_stages(study):
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}])
    write(
        study / "smoke_manifest.json",
        {
            "cohort_id": "smoke_001",
            "usable_as_final_thesis_evidence": False,
            "exclude_from_future_held_out_evaluation": True,
            "source": {"file": "/somewhere/eligible_logs.json"},
            "selection": {"method": "seeded_repository_round_robin", "seed": 1},
        },
    )
    stages = collect_stages(CONFIG, study, study.parent)
    names = [stage.name for stage in stages]
    assert "Derived cohort" in names
    assert "Collection" not in names and "Triage" not in names
    derived = stages[0]
    assert any("excluded from the held-out evaluation" in note for note in derived.notes)


def test_next_action_points_at_annotation_before_anything_else(study):
    write(study / "study_protocol.yaml", {})
    write(study / "raw" / "logs.json", [{"log_id": "a"}])
    write(study / "collection_manifest.json", {"status": "complete", "repositories": [{}]})
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}])
    write(study / "excluded" / "excluded_logs.json", [])
    write(study / "triage_manifest.json", {})
    assert "annotate" in next_action(collect_stages(CONFIG, study, study.parent))


def test_next_action_asks_for_a_second_reviewer_once_annotation_is_done(study):
    write(study / "study_protocol.yaml", {})
    write(study / "raw" / "logs.json", [{"log_id": "a"}])
    write(study / "collection_manifest.json", {"status": "complete", "repositories": [{}]})
    write(study / "triaged" / "eligible_logs.json", [{"log_id": "a"}])
    write(study / "excluded" / "excluded_logs.json", [])
    write(study / "triage_manifest.json", {})
    write(study / "ground_truth" / "ground_truth.json", {"annotations": [_annotation("a", verified=False)]})
    assert "verify" in next_action(collect_stages(CONFIG, study, study.parent))


def test_an_empty_study_reports_every_stage_as_not_started(study):
    stages = collect_stages(CONFIG, study, study.parent)
    states = {stage.name: stage.state for stage in stages}
    assert states["Collection"] == TODO
    assert states["Triage"] == TODO
    assert states["Ground truth"] == TODO
    assert os.path.isdir(study)
