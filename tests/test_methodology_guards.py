"""Offline tests for the kickoff-decision guards: partitions, evidence, metrics."""

import json
import os
from datetime import date
from unittest import mock

import pytest

from src.evaluation.case_partitions import describe_overlap, find_overlap, load_exclusions
from src.evaluation.category_metrics import (
    aggregate_evidence_lines,
    category_scores,
    evidence_line_scores,
    macro_f1,
)
from src.evaluation.ground_truth_audit import audit_annotations, audit_ground_truth_file, root_cause_problem
from src.evaluation.job_scope import is_bot_run, is_excluded, is_in_scope, is_umbrella_job
from src.data_collection.data_collection import GitHubActionsCollector, created_window
from automated_scripts.triage import compute_error_signature
from src.api.filtering import LogFilter, _count_tokens

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


def _log(log_id, repo="org/one", job="test", step="Run pytest", content=None, job_count=3):
    return {
        "log_id": log_id,
        "repository": repo,
        "failing_job": job,
        "failing_step": step,
        "job_count": job_count,
        "log_content": content or (f"error: {log_id} broke\n" * 30),
    }


def test_triage_excludes_out_of_scope_jobs_with_the_reason_recorded():
    """Lint and docs failures are outside what the taxonomy claims to diagnose."""
    from automated_scripts.triage import triage_logs

    logs = [
        _log("a", job="test", step="Run pytest"),
        _log("b", job="lint", step="Run flake8"),
        _log("c", job="Docs", step="Build documentation"),
    ]
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=5)

    assert [case["log_id"] for case in eligible] == ["a"]
    reasons = {case["log_id"]: case["reason"] for case in excluded}
    assert reasons == {"b": "out_of_scope_job", "c": "out_of_scope_job"}
    assert next(case for case in excluded if case["log_id"] == "b")["job_scope"] == "lint_format"


def test_triage_excludes_bot_generated_runs():
    """Dependency bots are automation, not CI faults.

    Thirty-five bot runs reached an eligible cohort because the rule lived in
    the scouting tool, where collection and triage could not see it.
    """
    from automated_scripts.triage import triage_logs

    logs = [
        _log("real", job="test", step="Run pytest"),
        {**_log("submission"), "workflow_name": "Automatic Dependency Submission (Gradle)"},
        {**_log("maven"), "workflow_name": "maven in /.teamcity - Update #1620039762"},
        {**_log("dependabot"), "failing_job": "Dependabot", "failing_step": "Run Dependabot"},
    ]
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=5)

    assert [case["log_id"] for case in eligible] == ["real"]
    assert {case["reason"] for case in excluded} == {"bot_generated_run"}


def test_the_bot_rule_reads_the_workflow_the_job_and_the_actor():
    from src.evaluation.job_scope import is_bot_run

    assert is_bot_run({"workflow_name": "Automatic Dependency Submission (Gradle)"})
    assert is_bot_run({"name": "maven in /. - Update #123"})
    assert is_bot_run({"failing_job": "Dependabot"})
    assert is_bot_run({"triggering_actor": {"login": "dependabot[bot]"}})
    assert not is_bot_run({"workflow_name": "Contributor CI Build", "failing_job": "Compile All"})


def test_triage_drops_runs_where_no_job_executed():
    from automated_scripts.triage import triage_logs

    logs = [_log("a"), _log("b", job="", step="", job_count=0)]
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=5)
    assert [case["log_id"] for case in eligible] == ["a"]
    assert excluded[0]["reason"] == "no_job_executed"


def test_triage_keeps_one_case_per_causal_family():
    """Two runs of the same fault contribute one case, not two."""
    from automated_scripts.triage import triage_logs

    shared = "error: ModuleNotFoundError no module named foo\n" * 30
    logs = [
        _log("a", content=shared),
        _log("b", content=shared),
        _log("c", job="build", step="Run ./gradlew compileAll"),
    ]
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=5)

    assert len(eligible) == 2
    assert {case["log_id"] for case in eligible} == {"a", "c"}
    assert [case["reason"] for case in excluded] == ["duplicate_failure_family"]
    # Every surviving case carries the family it represents.
    assert all(case.get("family_id") for case in eligible)


def test_triage_never_lets_an_excluded_case_represent_a_family():
    """Scope is applied before grouping, so a lint run cannot stand in for a test run."""
    from automated_scripts.triage import triage_logs

    shared = "error: same underlying fault\n" * 30
    logs = [
        _log("lint-first", job="lint", step="Run eslint", content=shared),
        _log("real-test", job="test", step="Run pytest", content=shared),
    ]
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=5)

    assert [case["log_id"] for case in eligible] == ["real-test"]
    assert [case["reason"] for case in excluded] == ["out_of_scope_job"]


def test_triage_excludes_a_case_an_exploratory_cohort_already_used():
    """The cohort is kept clean by construction, with the reason recorded."""
    from automated_scripts.triage import triage_logs
    from src.evaluation.case_partitions import ExcludedCase

    logs = [
        {"log_id": "a", "repository": "org/one", "log_content": "error: boom\n" * 30},
        {"log_id": "b", "repository": "org/one", "log_content": "failure: other\n" * 30},
    ]
    exploratory = {
        "b": ExcludedCase("b", "smoke_001", "smoke_manifest.json", "engineering_smoke_test"),
    }
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=2, exploratory=exploratory)

    assert [case["log_id"] for case in eligible] == ["a"]
    assert len(excluded) == 1
    assert excluded[0]["reason"] == "used_in_exploratory_cohort"
    assert excluded[0]["exploratory_cohort"] == "smoke_001"


def test_triage_without_exploratory_cohorts_keeps_everything_eligible():
    from automated_scripts.triage import triage_logs

    logs = [{"log_id": "a", "repository": "org/one", "log_content": "error: boom\n" * 30}]
    eligible, excluded = triage_logs(logs, min_lines=5, max_duplicates=2)
    assert len(eligible) == 1 and excluded == []


# ── Failure families: when are two failures the same problem? ─────────────


def _case(log_id, repo="org/one", signature=None, fix=None, template=None):
    case = {"log_id": log_id, "repository": repo}
    if signature:
        case["error_signature"] = signature
    if fix:
        case["fixing_revision"] = fix
    if template:
        case["controlled_defect_template"] = template
    return case


def test_shared_error_signature_groups_cases_under_the_signature_rule():
    from src.evaluation.failure_families import assign_families

    cases = [_case("a", signature="deadbeef"), _case("b", signature="deadbeef"), _case("c", signature="other")]
    families = assign_families(cases, "signature")
    assert families["a"] == families["b"]
    assert families["c"] != families["a"]


def test_the_same_signature_in_two_repositories_is_not_one_family():
    """Identical error text in unrelated projects is not evidence of one fault."""
    from src.evaluation.failure_families import assign_families

    cases = [_case("a", repo="org/one", signature="same"), _case("b", repo="org/two", signature="same")]
    assert assign_families(cases, "signature")["a"] != assign_families(cases, "signature")["b"]


def test_the_fix_rule_groups_only_cases_with_a_recorded_repair():
    from src.evaluation.failure_families import assign_families

    cases = [_case("a", fix="sha1"), _case("b", fix="sha1"), _case("c", signature="x")]
    families = assign_families(cases, "fix")
    assert families["a"] == families["b"]
    # No repair recorded, so the case is its own family rather than dropped.
    assert families["c"] not in (families["a"], families["b"])


def test_the_both_rule_is_transitive_across_the_two_relations():
    """A shares a repair with B; B shares a signature with C; all three are one."""
    from src.evaluation.failure_families import assign_families

    cases = [
        _case("a", fix="sha1"),
        {"log_id": "b", "repository": "org/one", "fixing_revision": "sha1", "error_signature": "sig"},
        _case("c", signature="sig"),
    ]
    families = assign_families(cases, "combined")
    assert families["a"] == families["b"] == families["c"]
    # Under either rule alone the chain does not close.
    assert assign_families(cases, "fix")["a"] != assign_families(cases, "fix")["c"]


def test_an_umbrella_job_does_not_merge_unrelated_faults():
    """Chosen rule: job, step AND error signature must all match.

    Inspecting gradle/gradle showed one "Sanity Check on Linux" job running
    binary-compatibility checks, checkstyle, detekt and architecture tests.
    Grouping on the job name alone merged four distinct faults into one case,
    so the signature is required as well.
    """
    from src.evaluation.failure_families import assign_families

    job, step = "Sanity Check on Linux", "Run ./gradlew sanityCheck"

    def case(log_id, signature):
        return {
            "log_id": log_id,
            "repository": "org/one",
            "failing_job": job,
            "failing_step": step,
            "error_signature": signature,
        }

    cases = [
        case("binary-compat", "sig-binary-compat"),
        case("checkstyle", "sig-checkstyle"),
        case("nullability-1", "sig-nullability"),
        case("nullability-2", "sig-nullability"),
    ]
    families = assign_families(cases, "job_step")

    # The genuine repeat groups; the unrelated faults stay apart.
    assert families["nullability-1"] == families["nullability-2"]
    assert len({families[c] for c in ("binary-compat", "checkstyle", "nullability-1")}) == 3


def test_job_step_needs_a_signature_before_it_groups_anything():
    """Without an error signature, the job name alone must not group cases."""
    from src.evaluation.failure_families import assign_families

    cases = [
        {"log_id": "a", "repository": "org/one", "failing_job": "test", "failing_step": "Run tests"},
        {"log_id": "b", "repository": "org/one", "failing_job": "test", "failing_step": "Run tests"},
    ]
    assert assign_families(cases, "job_step")["a"] != assign_families(cases, "job_step")["b"]


def test_job_step_grouping_is_scoped_to_one_repository():
    from src.evaluation.failure_families import assign_families

    cases = [
        {
            "log_id": "a",
            "repository": "org/one",
            "failing_job": "test",
            "failing_step": "Run tests",
            "error_signature": "same",
        },
        {
            "log_id": "b",
            "repository": "org/two",
            "failing_job": "test",
            "failing_step": "Run tests",
            "error_signature": "same",
        },
    ]
    assert assign_families(cases, "job_step")["a"] != assign_families(cases, "job_step")["b"]


def test_a_controlled_defect_is_identified_by_its_template_not_its_log():
    from src.evaluation.failure_families import assign_families

    cases = [
        _case("a", template="seed-timeout-1", signature="noise-one"),
        _case("b", template="seed-timeout-1", signature="noise-two"),
    ]
    assert assign_families(cases, "combined")["a"] == assign_families(cases, "combined")["b"]


def test_family_ids_are_stable_regardless_of_case_order():
    from src.evaluation.failure_families import assign_families

    cases = [_case("a", signature="s"), _case("b", signature="s"), _case("c", signature="t")]
    assert assign_families(cases, "combined") == assign_families(list(reversed(cases)), "combined")


def test_one_representative_is_kept_per_family():
    from src.evaluation.failure_families import select_representatives

    cases = [_case("a", signature="s"), _case("b", signature="s"), _case("c", signature="t")]
    result = select_representatives(cases, "signature")
    assert result["kept"] == ["a", "c"]
    assert result["dropped"] == ["b"]


def test_a_family_spanning_two_partitions_is_reported():
    """Development and held-out sharing one fault contaminates the final test."""
    from src.evaluation.failure_families import assign_families, check_no_family_spans_partitions

    cases = [_case("a", signature="s"), _case("b", signature="s"), _case("c", signature="t")]
    assignment = assign_families(cases, "signature")

    clean = {"development": ["a", "b"], "held_out": ["c"]}
    assert check_no_family_spans_partitions(clean, assignment) == []

    leaking = {"development": ["a"], "held_out": ["b", "c"]}
    breaches = check_no_family_spans_partitions(leaking, assignment)
    assert len(breaches) == 1
    assert set(breaches[0]["partitions"]) == {"development", "held_out"}


def test_comparing_rules_shows_the_effect_of_each_choice():
    from src.evaluation.failure_families import compare_rules

    cases = [_case("a", fix="sha1", signature="s"), _case("b", signature="s"), _case("c", fix="sha1")]
    summaries = {item["rule"]: item for item in compare_rules(cases)}
    assert summaries["combined"]["families"] == 1
    assert summaries["fix"]["families"] == 2
    assert summaries["signature"]["families"] == 2
    assert summaries["combined"]["duplicate_cases"] == 2


def test_an_unknown_rule_is_rejected_rather_than_guessed():
    import pytest as _pytest

    from src.evaluation.failure_families import assign_families

    with _pytest.raises(ValueError, match="Unknown grouping rule"):
        assign_families([_case("a")], "whatever")


# ── The freeze: what was fixed before the one-time held-out run ───────────


def _freeze_record(clean=True, commit="abc123", pilot=True, approver="supervisor", methodology=True, **dataset):
    base = {
        "cohort_sha256": "c1",
        "split_manifest_sha256": "s1",
        "ground_truth_sha256": "g1",
    }
    base.update(dataset)
    return {
        "source": {"git_commit": commit, "worktree_clean": clean, "git_describe": "v1"},
        "artifact": {"prompt_sha256": "p1", "preprocessing": {"max_tokens": 12000}},
        "baseline": {"ruleset_sha256": "b1"},
        "dataset": base,
        "pilot": {"complete": pilot, "latest": "pilot_20261021" if pilot else None},
        "approval": {
            "freeze_approved_by": approver,
            "methodology": (
                {"single_annotator_approved": True, "approved_by": "supervisors", "approved_on": "2026-10-21"}
                if methodology
                else None
            ),
        },
    }


def test_a_dirty_worktree_blocks_the_freeze():
    """A recorded commit does not describe code with uncommitted changes."""
    from automated_scripts.freeze_package import blocking_problems

    assert blocking_problems(_freeze_record()) == []
    assert any("dirty" in p for p in blocking_problems(_freeze_record(clean=False)))


def test_a_missing_split_or_ground_truth_blocks_the_freeze():
    from automated_scripts.freeze_package import blocking_problems

    assert any("split" in p for p in blocking_problems(_freeze_record(split_manifest_sha256=None)))
    assert any("ground-truth" in p for p in blocking_problems(_freeze_record(ground_truth_sha256=None)))


def test_verification_detects_a_changed_prompt():
    """The prompt is part of the artifact; changing it changes the experiment."""
    from automated_scripts.freeze_package import compare

    frozen = _freeze_record()
    current = _freeze_record()
    current["artifact"]["prompt_sha256"] = "p2"

    changes = compare(frozen, current)
    assert len(changes) == 1
    assert "artifact.prompt_sha256" in changes[0]


def test_verification_detects_changed_ground_truth_or_baseline_rules():
    from automated_scripts.freeze_package import compare

    frozen = _freeze_record()
    current = _freeze_record(ground_truth_sha256="g2")
    current["baseline"]["ruleset_sha256"] = "b2"

    changes = compare(frozen, current)
    assert any("dataset.ground_truth_sha256" in c for c in changes)
    assert any("baseline.ruleset_sha256" in c for c in changes)


def test_verification_reports_nothing_when_the_system_is_unchanged():
    from automated_scripts.freeze_package import compare

    assert compare(_freeze_record(), _freeze_record()) == []


def test_verification_looks_inside_nested_settings():
    from automated_scripts.freeze_package import compare

    current = _freeze_record()
    current["artifact"]["preprocessing"]["max_tokens"] = 8000
    changes = compare(_freeze_record(), current)
    assert any("preprocessing.max_tokens" in c for c in changes)


# ── The baseline: the floor the LLM results are measured against ──────────


def _log_lines(*pairs):
    return "\n".join(f"[Line {n}] {text}" for n, text in pairs)


def test_the_baseline_returns_a_category_and_the_lines_that_matched():
    from src.api.baseline import BaselineClassifier

    log = _log_lines((10, "Collecting packages"), (42, "ModuleNotFoundError: No module named 'foo'"))
    result = BaselineClassifier().classify(log)

    assert result["error_type"] == "dependency_error"
    assert result["failure_lines"] == [42], "original line numbers, not positions"
    assert result["matched_patterns"]


def test_the_baseline_says_unknown_rather_than_guessing():
    """A fallback category would spread its failures across the taxonomy."""
    from src.api.baseline import BaselineClassifier

    result = BaselineClassifier().classify(_log_lines((1, "everything went fine")))
    assert result["error_type"] == "unknown"
    assert result["failure_lines"] == []


def test_rule_order_decides_which_category_wins():
    """A dependency failure inside a build step is a dependency failure."""
    from src.api.baseline import BaselineClassifier

    log = _log_lines(
        (5, "Execution failed for task ':app:compile'"), (9, "Could not resolve dependency: com.example:thing")
    )
    assert BaselineClassifier().classify(log)["error_type"] == "dependency_error"

    # Reversing precedence reverses the outcome, which is why order is hashed.
    reversed_rules = (
        ("build_configuration", ("execution failed for task",)),
        ("dependency_error", ("could not resolve dependency",)),
    )
    assert BaselineClassifier(reversed_rules).classify(log)["error_type"] == "build_configuration"


def test_the_baseline_is_deterministic():
    from src.api.baseline import BaselineClassifier

    log = _log_lines((3, "AssertionError: expected 1 but was 2"))
    classifier = BaselineClassifier()
    assert classifier.classify(log) == classifier.classify(log)


def test_changing_a_rule_changes_the_ruleset_checksum():
    """A ruleset revised after held-out results would not match its freeze record."""
    from src.api.baseline import DEFAULT_RULES, ruleset_sha256

    assert ruleset_sha256(DEFAULT_RULES) == ruleset_sha256(DEFAULT_RULES)
    tampered = (("timeout", ("timed out", "and one more")),) + DEFAULT_RULES[1:]
    assert ruleset_sha256(tampered) != ruleset_sha256(DEFAULT_RULES)
    # Order is part of the identity, not just the contents.
    assert ruleset_sha256(tuple(reversed(DEFAULT_RULES))) != ruleset_sha256(DEFAULT_RULES)


def test_the_baseline_reads_the_same_filtered_log_the_models_receive():
    """Same evidence for every condition, or the comparison is not fair."""
    from src.api.baseline import BaselineClassifier
    from src.api.filtering import LogFilter

    raw = "\n".join(["setup step"] * 40 + ["ERROR: Connection refused by registry"] + ["cleanup"] * 10)
    filtered = LogFilter.apply_smart_filtering(raw, max_lines=500, window_size=5, max_tokens=12000)
    result = BaselineClassifier().classify(filtered)

    assert result["error_type"] == "network_error"
    # The reported line is its position in the original log, matching the models.
    assert result["failure_lines"] == [41]


# ── Controlled defects: known interventions, capped and documented ────────


def _defect(defect_id="seed-01", category="timeout", reproduced=True, **overrides):
    record = {
        "defect_id": defect_id,
        "category": category,
        "repository": "org/fork",
        "injection_procedure": "Set the job timeout to 1 second in ci.yml",
        "intended_cause": "The build exceeds an artificially short job timeout",
        "affected_component": "ci.yml build job",
        "expected_evidence": "The runner reports the job cancelled after exceeding the time limit",
        "repair": "Restore the original timeout value",
        "reproduced": reproduced,
    }
    record.update(overrides)
    return record


def test_a_defect_missing_any_required_field_is_unusable():
    """Without the procedure nobody can check the intervention did what it should."""
    from automated_scripts.controlled_defects import record_problems

    assert record_problems(_defect()) == []
    problems = record_problems(_defect(injection_procedure=""))
    assert len(problems) == 1 and "injection_procedure" in problems[0]


def test_a_defect_that_did_not_reproduce_is_rejected():
    from automated_scripts.controlled_defects import record_problems

    assert any("did not reproduce" in p for p in record_problems(_defect(reproduced=False)))
    assert any("not recorded" in p for p in record_problems(_defect(reproduced=None)))


def test_a_category_outside_the_taxonomy_is_rejected():
    from automated_scripts.controlled_defects import record_problems

    assert any("not in the taxonomy" in p for p in record_problems(_defect(category="disk_full")))


def test_the_per_category_and_overall_caps_are_enforced():
    """Caps keep seeded cases a supplement, not a substitute for real failures."""
    from automated_scripts.controlled_defects import MAX_PER_CATEGORY, audit

    over = {"defects": [_defect(defect_id=f"s{i}", category="timeout") for i in range(MAX_PER_CATEGORY + 1)]}
    assert any("more than" in finding["problem"] for finding in audit(over)["findings"])


def test_the_audit_reports_which_categories_are_still_uncovered():
    from automated_scripts.controlled_defects import audit

    summary = audit({"defects": [_defect(category="timeout"), _defect(defect_id="s2", category="network_error")]})
    assert summary["categories_covered"] == ["network_error", "timeout"]
    assert "dependency_error" in summary["categories_missing"]
    assert summary["usable"] == 2


def test_the_defect_hash_covers_the_intervention_not_the_bookkeeping():
    """Editing the procedure must break the commitment; a note must not."""
    from automated_scripts.controlled_defects import defect_hash

    base = _defect()
    assert defect_hash(base) == defect_hash({**base, "notes": "added later"})
    assert defect_hash(base) != defect_hash({**base, "injection_procedure": "something else"})


# ── Blind root-cause scoring: the scorer must not know the model ──────────


class _FakeOutcome:
    def __init__(self, root_cause, status="success"):
        self.root_cause = root_cause
        self.suggested_fix = "do the thing"
        self.failure_lines = [1, 2]
        self.status = status


class _FakeReport:
    """Minimal stand-in for an ExperimentReport, enough to build a queue."""

    def __init__(self, models, log_ids):
        self.model_labels = models
        self.log_order = log_ids
        self.log_info = {log_id: {"repository": "org/one"} for log_id in log_ids}
        self.ground_truth = {
            log_id: {
                "actual_error_type": "test_failure",
                "actual_root_cause": "a real cause here",
                "failure_lines": [1],
            }
            for log_id in log_ids
        }

    def outcome(self, model, log_id):
        return _FakeOutcome(f"{model} says something about {log_id}")


def test_scoring_queue_interleaves_both_conditions():
    """A scorer must not be able to infer the model from position in the queue."""
    from automated_scripts.score_root_cause import build_queue

    report = _FakeReport(["openai/hosted", "local/open"], [f"log{i}" for i in range(10)])
    queue = build_queue(report, seed=1)

    assert len(queue) == 20
    models_in_order = [item["model"] for item in queue]
    # Not grouped: the first ten are not all one model.
    assert len(set(models_in_order[:10])) == 2


def test_the_scoring_order_is_reproducible_from_the_seed():
    from automated_scripts.score_root_cause import build_queue

    report = _FakeReport(["a/one", "b/two"], [f"log{i}" for i in range(8)])
    first = [item["response_id"] for item in build_queue(report, seed=7)]
    assert first == [item["response_id"] for item in build_queue(report, seed=7)]
    assert first != [item["response_id"] for item in build_queue(report, seed=8)]


def test_a_failed_inference_is_not_put_up_for_scoring():
    """There is no root cause to score when the model never produced one."""
    from automated_scripts.score_root_cause import build_queue

    report = _FakeReport(["a/one"], ["log0", "log1"])
    report.outcome = lambda model, log_id: _FakeOutcome("x", status="error" if log_id == "log1" else "success")
    assert [item["log_id"] for item in build_queue(report, seed=1)] == ["log0"]


def test_the_rubric_covers_exactly_the_three_defined_scores():
    from automated_scripts.score_root_cause import EVIDENCE_SUPPORT, SCORES

    assert sorted(SCORES) == ["0", "1", "2"]
    assert SCORES["2"][0] == "Correct" and SCORES["0"][0] == "Incorrect"
    # The plan also asks whether cited lines genuinely support the diagnosis.
    assert set(EVIDENCE_SUPPORT) == {"y", "n", "p", "x"}


def test_an_empty_response_is_auto_scored_and_never_shown():
    """Only the baseline answers with no cause and no fix; showing it would unmask it."""
    from automated_scripts.score_root_cause import collect_responses

    report = _FakeReport(["openai/hosted", "baseline/rules"], ["log0", "log1"])
    real = report.outcome

    def outcome(model, log_id):
        result = real(model, log_id)
        if model == "baseline/rules":
            result.root_cause, result.suggested_fix = "", "   "
        return result

    report.outcome = outcome
    queue, automatic = collect_responses(report, seed=1)
    assert {item["model"] for item in queue} == {"openai/hosted"}
    assert [item["response_id"] for item in automatic] == ["log0::baseline/rules", "log1::baseline/rules"]


def test_auto_scored_entries_are_zero_and_flagged():
    from automated_scripts.score_root_cause import add_automatic, new_payload

    payload = new_payload(".", "s1", 1)
    automatic = [{"response_id": "a::m", "log_id": "a", "model": "m"}]
    assert add_automatic(payload, automatic) == 1
    # Resuming must not add the same response twice.
    assert add_automatic(payload, automatic) == 0
    (entry,) = payload["scores"]
    assert entry["root_cause_score"] == 0 and entry["fix_score"] == 0 and entry["auto"] is True


def test_a_blank_fix_scores_zero_without_asking():
    from automated_scripts import score_root_cause

    item = {"response_cause": "a cause", "response_fix": "", "response_lines": []}
    answers = iter(["2", ""])
    with mock.patch("builtins.input", lambda prompt="": next(answers)):
        judged = score_root_cause.ask_scores(item)
    assert judged == {"root_cause_score": 2, "fix_score": 0, "evidence_support": "no lines cited", "note": ""}


def test_the_scorer_sees_the_documented_repair_but_not_the_model():
    from automated_scripts.score_root_cause import build_queue, present

    report = _FakeReport(["openai/hosted"], ["log0"])
    report.ground_truth["log0"]["fixing_reference"] = "https://github.com/org/one/pull/7"
    report.outcome = lambda model, log_id: _FakeOutcome("an import fails")
    (item,) = build_queue(report, seed=1)
    assert item["verified_repair"] == "https://github.com/org/one/pull/7"
    with mock.patch("builtins.print") as printed:
        present(item, 1, 1)
    shown = " ".join(str(call.args[0]) for call in printed.call_args_list if call.args)
    assert "pull/7" in shown
    assert "openai" not in shown and "hosted" not in shown


def test_the_root_cause_rubric_is_the_supervisors_wording_verbatim():
    """SUPERVISOR_CONDITIONS.md section 3 is the approved definition; the form must not drift from it."""
    from src.evaluation.rubric_scores import ROOT_CAUSE_RUBRIC

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "docs", "thesis", "SUPERVISOR_CONDITIONS.md"), encoding="utf-8") as handle:
        conditions = handle.read()
    for score, (_, rule) in ROOT_CAUSE_RUBRIC.items():
        assert f"| {score} | {rule} |" in conditions


def test_a_version_one_scores_file_is_not_resumed():
    """Version 1 recorded no fix score; resuming it would leave fixes silently unscored."""
    from automated_scripts.score_root_cause import check_existing, new_payload

    payload = new_payload(".", "s1", 5)
    assert check_existing(payload, "s1", 5) == ""
    assert "schema version 1" in check_existing({**payload, "schema_version": 1}, "s1", 5)
    assert "different scorer" in check_existing(payload, "s2", 5)
    assert "seed" in check_existing(payload, "s1", 6)


def test_the_rescore_sample_excludes_auto_scores_and_reorders():
    from automated_scripts.score_root_cause import build_queue, rescore_sample

    report = _FakeReport(["a/one", "b/two"], [f"log{i}" for i in range(10)])
    queue = build_queue(report, seed=3)
    scored = {item["response_id"] for item in queue}
    sample = rescore_sample(queue, scored, set(), 8, seed=3)
    assert len(sample) == 8
    assert [item["response_id"] for item in sample] != [item["response_id"] for item in queue[:8]]
    # Already re-scored responses are not offered again, and the sample is stable.
    again = rescore_sample(queue, scored, {sample[0]["response_id"]}, 8, seed=3)
    assert [item["response_id"] for item in again] == [item["response_id"] for item in sample[1:]]
    # Responses never scored by hand (auto-scored ones) are never in the sample.
    assert rescore_sample(queue, set(), set(), 8, seed=3) == []


# ── Rubric analysis: what the scores say ──────────────────────────────────


def test_weighted_kappa_matches_a_hand_computed_value():
    from src.evaluation.rubric_scores import weighted_kappa

    first, second = [0, 1, 2, 2], [0, 2, 2, 1]
    assert weighted_kappa(first, second) == pytest.approx(3 / 7)
    assert weighted_kappa(first, second, weights="none") == pytest.approx(0.2)
    assert weighted_kappa([0, 1, 2], [0, 1, 2]) == pytest.approx(1.0)
    # Perfect agreement on a constant leaves chance agreement perfect too.
    assert weighted_kappa([2, 2], [2, 2]) is None
    assert weighted_kappa([], []) is None


def test_weighted_kappa_penalises_a_two_step_disagreement_more():
    from src.evaluation.rubric_scores import weighted_kappa

    near = weighted_kappa([0, 1, 2, 0, 1, 2], [0, 1, 2, 1, 1, 2])
    far = weighted_kappa([0, 1, 2, 0, 1, 2], [0, 1, 2, 2, 1, 2])
    assert near > far


def test_holm_adjustment():
    from src.evaluation.rubric_scores import holm_adjust

    assert holm_adjust([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert holm_adjust([0.04, 0.01]) == pytest.approx([0.04, 0.02])
    assert holm_adjust([0.6, 0.7]) == pytest.approx([1.0, 1.0])


def _score(log_id, model, cause, fix, auto=False):
    return {
        "response_id": f"{log_id}::{model}",
        "log_id": log_id,
        "model": model,
        "root_cause_score": cause,
        "fix_score": fix,
        "evidence_support": "not assessed" if auto else "supports",
        "auto": auto,
    }


def _scores_payload(entries, rescores=()):
    return {"schema_version": 2, "scorer": "s1", "seed": 1, "scores": list(entries), "rescores": list(rescores)}


def test_summary_compares_models_and_leaves_an_all_auto_condition_out():
    from src.evaluation.rubric_scores import summarize_scores

    entries = []
    for i in range(8):
        entries.append(_score(f"log{i}", "a/hosted", 2, 2 if i < 6 else 1))
        entries.append(_score(f"log{i}", "b/local", 0 if i < 7 else 2, 1))
        entries.append(_score(f"log{i}", "baseline/rules", 0, 0, auto=True))
    truth = {f"log{i}": {"evidence_method": "historical_fix" if i < 5 else "expert_review"} for i in range(8)}
    summary = summarize_scores(_scores_payload(entries), truth)

    hosted = summary["conditions"]["a/hosted"]
    assert hosted["root_cause_score"]["counts"] == {"0": 0, "1": 0, "2": 8}
    assert hosted["fix_score"]["share_correct"] == pytest.approx(0.75)
    assert hosted["by_ground_truth_anchor"]["repair_anchored"]["root_cause_score"]["n"] == 5
    assert hosted["by_ground_truth_anchor"]["judgement_only"]["root_cause_score"]["n"] == 3
    assert summary["conditions"]["baseline/rules"]["auto_scored"] == 8

    assert summary["not_compared"] == ["baseline/rules"]
    (comparison,) = summary["comparisons"]
    assert (comparison["model_a"], comparison["model_b"]) == ("a/hosted", "b/local")
    cause = comparison["root_cause_score"]
    assert (cause["a_better"], cause["b_better"], cause["ties"]) == (7, 0, 1)
    assert cause["p_value_holm"] >= cause["p_value"]
    assert cause["significant_at_005"] is True


def test_identical_scores_give_no_p_value():
    from src.evaluation.rubric_scores import paired_score_test

    result = paired_score_test({"a": 1, "b": 2}, {"a": 1, "b": 2})
    assert result["p_value"] is None and result["verdict"] == "Identical scores on every case"
    assert paired_score_test({"a": 1}, {"a": 2})["verdict"] == "Too few paired cases for a test"


def test_intra_rater_agreement_compares_rescores_with_first_scores():
    from src.evaluation.rubric_scores import intra_rater_agreement

    first = [_score("x", "m", 0, 0), _score("y", "m", 1, 2), _score("z", "m", 2, 2), _score("w", "m", 0, 0, auto=True)]
    again = [_score("x", "m", 0, 1), _score("y", "m", 1, 2), _score("z", "m", 2, 2), _score("w", "m", 2, 2)]
    result = intra_rater_agreement(_scores_payload(first, again))
    # The auto-scored response was never judged, so it cannot be re-judged.
    assert result["rescored"] == 3
    assert result["root_cause_score"]["raw_agreement"] == pytest.approx(1.0)
    assert result["fix_score"]["raw_agreement"] == pytest.approx(2 / 3)


def test_a_malformed_scores_file_is_rejected():
    from src.evaluation.rubric_scores import validate_payload

    assert validate_payload(_scores_payload([_score("x", "m", 2, 1)])) == []
    assert "schema_version" in validate_payload({"schema_version": 1, "scores": []})[0]
    assert "fix_score=3" in validate_payload(_scores_payload([_score("x", "m", 2, 3)]))[0]
    assert "twice" in validate_payload(_scores_payload([_score("x", "m", 2, 1), _score("x", "m", 1, 1)]))[0]


# ── Preprocessing recall: was the evidence even shown to the model? ───────


def _filtered(*line_numbers):
    return "\n".join(f"[Line {n}] some content for line {n}" for n in line_numbers)


def test_preprocessing_recall_counts_verified_lines_reaching_the_model():
    from src.evaluation.category_metrics import preprocessing_recall

    result = preprocessing_recall([10, 20, 30], _filtered(10, 20, 99))
    assert result["recall"] == pytest.approx(0.6667, abs=0.001)
    assert result["surviving_lines"] == 2
    assert result["lost_lines"] == [30]


def test_a_filter_that_drops_all_evidence_is_visible():
    """The model cannot select evidence it was never given."""
    from src.evaluation.category_metrics import preprocessing_recall

    result = preprocessing_recall([10, 20], _filtered(500, 600))
    assert result["recall"] == 0.0
    assert result["lost_lines"] == [10, 20]


def test_a_case_with_no_annotated_lines_is_unscorable_for_preprocessing():
    from src.evaluation.category_metrics import preprocessing_recall

    assert preprocessing_recall([], _filtered(1, 2))["scorable"] is False


def test_evidence_lines_are_scored_only_against_what_survived_filtering():
    """Otherwise a model is penalised for lines the filter discarded."""
    from src.evaluation.category_metrics import evidence_line_scores

    # Verified lines 10, 20, 30; the filter kept only 10 and 20; model cited both.
    without_filter = evidence_line_scores([10, 20], [10, 20, 30])
    with_filter = evidence_line_scores([10, 20], [10, 20, 30], filtered_log=_filtered(10, 20))

    assert without_filter["recall"] == pytest.approx(0.6667, abs=0.001)
    assert with_filter["recall"] == 1.0, "the model found everything it was shown"


def test_evidence_scoring_is_unscorable_when_the_filter_kept_no_evidence():
    from src.evaluation.category_metrics import evidence_line_scores

    result = evidence_line_scores([1, 2], [10, 20], filtered_log=_filtered(500))
    assert result["scorable"] is False


def test_aggregate_preprocessing_recall_flags_total_evidence_loss():
    from src.evaluation.category_metrics import aggregate_preprocessing_recall, preprocessing_recall

    cases = [
        preprocessing_recall([1, 2], _filtered(1, 2)),
        preprocessing_recall([3, 4], _filtered(3)),
        preprocessing_recall([5, 6], _filtered(99)),
        preprocessing_recall([], _filtered(1)),
    ]
    summary = aggregate_preprocessing_recall(cases)
    assert summary["scorable_cases"] == 3
    assert summary["cases_with_no_evidence_surviving"] == 1
    assert summary["cases_fully_preserved"] == 1
    assert summary["mean_recall"] == pytest.approx(0.5, abs=0.001)


# ── Completion budget: the open-weights condition needs room to answer ─────


def test_the_local_condition_gets_a_larger_completion_budget():
    """At 4,096 it exhausted the budget reasoning and returned nothing.

    Measured on development: finish_reason 'length', exactly 4,096 completion
    tokens and zero characters on 5 of 16 cases, so those inferences counted as
    failures and the condition was measured with a handicap.
    """
    from src.api.llm_service import HOSTED_MAX_TOKENS, LOCAL_MAX_TOKENS, LLMDiagnoser
    from src.api.models import LLMProvider

    local = LLMDiagnoser(provider=LLMProvider.LOCAL, model="thesis-qwen3.5:9b-24k")
    hosted = LLMDiagnoser(provider=LLMProvider.OPENAI, model="gpt-5.6-terra", api_key="x")

    assert local.max_tokens == LOCAL_MAX_TOKENS > HOSTED_MAX_TOKENS == hosted.max_tokens
    # The largest observed development prompt was 16,923 tokens against a fixed
    # 24,576-token context, so the budget must still fit.
    assert 16923 + LOCAL_MAX_TOKENS <= 24576


def test_an_explicit_completion_budget_still_wins():
    """So the budget can be varied deliberately and recorded."""
    from src.api.llm_service import LLMDiagnoser
    from src.api.models import LLMProvider

    assert LLMDiagnoser(provider=LLMProvider.LOCAL, model="thesis-qwen3.5:9b-24k", max_tokens=2048).max_tokens == 2048


# ── Provider errors: stop on permanent ones, retry transient ones ─────────


def test_an_exhausted_quota_is_not_treated_as_a_transient_rate_limit():
    """Retrying 'no credits' wastes time and fills a run with identical failures."""
    from src.api.llm_service import _is_permanent_quota_error

    assert _is_permanent_quota_error(Exception("Error code: 429 - credit_balance_exhausted"))
    assert _is_permanent_quota_error(Exception("insufficient_quota"))
    assert not _is_permanent_quota_error(Exception("Error code: 429 - rate_limit_exceeded, slow down"))


def test_provider_unavailable_is_its_own_error_type():
    """The benchmark distinguishes 'this run cannot proceed' from one bad case."""
    from src.api.llm_service import ProviderUnavailable

    assert issubclass(ProviderUnavailable, RuntimeError)


# ── Annotation order: finish development before touching held-out ─────────


def test_annotation_offers_development_then_pilot_then_held_out(tmp_path):
    """Refine the codebook on development cases before the held-out set is read."""
    import json as _json

    from automated_scripts.annotate_blind import order_by_partition

    (tmp_path / "split_manifest.json").write_text(
        _json.dumps({"partitions": {"development": ["d1", "d2"], "pilot": ["p1"], "held_out": ["h1", "h2"]}})
    )
    logs = [{"log_id": i} for i in ("h1", "p1", "d1", "h2", "d2")]

    ordered = [log["log_id"] for log in order_by_partition(logs, tmp_path)]
    assert ordered == ["d1", "d2", "p1", "h1", "h2"]


def test_a_cohort_with_no_split_keeps_its_original_order(tmp_path):
    """The smoke cohort and any un-split study must behave as before."""
    from automated_scripts.annotate_blind import order_by_partition

    logs = [{"log_id": i} for i in ("c", "a", "b")]
    assert [log["log_id"] for log in order_by_partition(logs, tmp_path)] == ["c", "a", "b"]


def test_cases_outside_every_partition_are_offered_last(tmp_path):
    import json as _json

    from automated_scripts.annotate_blind import order_by_partition

    (tmp_path / "split_manifest.json").write_text(_json.dumps({"partitions": {"development": ["d1"]}}))
    logs = [{"log_id": i} for i in ("stray", "d1")]
    assert [log["log_id"] for log in order_by_partition(logs, tmp_path)] == ["d1", "stray"]


# ── The split: families move together, repositories stay represented ──────


def _split_case(log_id, repo, signature):
    return {"log_id": log_id, "repository": repo, "error_signature": signature}


def test_a_family_is_never_split_across_partitions():
    """The guarantee the held-out set depends on."""
    from automated_scripts.make_split import allocate
    from src.evaluation.failure_families import assign_families, check_no_family_spans_partitions

    # Ten families of two cases each, so every family must move as a pair.
    cases = [_split_case(f"c{i}", "org/one", f"sig{i // 2}") for i in range(20)]
    allocation = allocate(cases, {"development": 4, "pilot": 4, "held_out": 12}, "signature", seed=1)

    assert check_no_family_spans_partitions(allocation, assign_families(cases, "signature")) == []
    assert sum(len(ids) for ids in allocation.values()) == 20


def test_every_repository_appears_in_every_partition():
    """RQ2 compares across repositories, so one must not land in a single partition."""
    from automated_scripts.make_split import allocate

    cases = [_split_case(f"a{i}", "org/one", f"a{i}") for i in range(30)]
    cases += [_split_case(f"b{i}", "org/two", f"b{i}") for i in range(30)]
    allocation = allocate(cases, {"development": 15, "pilot": 15, "held_out": 30}, "signature", seed=7)

    by_case = {case["log_id"]: case for case in cases}
    from automated_scripts.make_split import PARTITIONS

    # The reserve is surplus and carries no representativeness requirement.
    for partition in PARTITIONS:
        repositories = {by_case[case_id]["repository"] for case_id in allocation[partition]}
        assert repositories == {"org/one", "org/two"}, f"{partition} lost a repository"


def test_the_same_seed_gives_the_same_split():
    from automated_scripts.make_split import allocate

    cases = [_split_case(f"c{i}", "org/one", f"sig{i}") for i in range(30)]
    targets = {"development": 5, "pilot": 5, "held_out": 20}
    assert allocate(cases, targets, "signature", seed=42) == allocate(cases, targets, "signature", seed=42)
    assert allocate(cases, targets, "signature", seed=42) != allocate(cases, targets, "signature", seed=43)


def test_every_case_is_allocated_exactly_once():
    from automated_scripts.make_split import allocate

    cases = [_split_case(f"c{i}", "org/one" if i % 3 else "org/two", f"sig{i // 2}") for i in range(25)]
    allocation = allocate(cases, {"development": 5, "pilot": 5, "held_out": 15}, "signature", seed=3)

    allocated = [case_id for ids in allocation.values() for case_id in ids]
    assert sorted(allocated) == sorted(case["log_id"] for case in cases)
    assert len(allocated) == len(set(allocated)), "a case was allocated twice"


def test_a_short_cohort_starves_held_out_not_the_working_sets():
    """Development and pilot are needed now; held-out can grow with a later pass."""
    from automated_scripts.make_split import allocate, summarise

    # 40 cases against targets totalling 80, so half the cohort is missing.
    cases = [_split_case(f"c{i}", "org/one", f"sig{i}") for i in range(40)]
    targets = {"development": 15, "pilot": 15, "held_out": 50}
    rows = {row["partition"]: row for row in summarise(allocate(cases, targets, "signature", seed=5), cases, targets)}

    assert rows["development"]["shortfall"] == 0
    assert rows["pilot"]["shortfall"] == 0
    assert rows["held_out"]["shortfall"] > 0, "the shortfall must land on held-out"


def test_a_shortfall_is_reported_rather_than_hidden():
    """Too few cases must surface, not be papered over by under-filling quietly."""
    from automated_scripts.make_split import allocate, summarise

    cases = [_split_case(f"c{i}", "org/one", f"sig{i}") for i in range(10)]
    targets = {"development": 15, "pilot": 15, "held_out": 50}
    rows = summarise(allocate(cases, targets, "signature", seed=1), cases, targets)

    assert sum(row["shortfall"] for row in rows) == 70
    assert sum(row["allocated"] for row in rows) == 10


# ── Repository gate: which repositories may enter the study at all ────────


def test_gate_classifies_build_and_test_jobs_as_in_scope():
    from src.evaluation.job_scope import IN_SCOPE, classify_job as classify

    assert classify("test (3.12)", "Run pytest") == IN_SCOPE
    assert classify("build", "Build with Gradle") == IN_SCOPE
    assert classify("ci", "npm ci") == IN_SCOPE
    assert classify("integration", "Run integration suite") == IN_SCOPE


def test_gate_excludes_lint_docs_spell_and_admin_jobs():
    from src.evaluation.job_scope import classify_job as classify

    assert classify("lint", "Run flake8") == "lint_format"
    assert classify("Docs", "Build documentation") == "docs"
    assert classify("Spell Check", "codespell") == "spell"
    assert classify("Check commit prefix", "Verify commit message") == "admin_other"


def test_gate_prefers_the_excluded_bucket_when_a_name_matches_both():
    """'Build docs' is a documentation job, not a build job."""
    from src.evaluation.job_scope import classify_job as classify

    assert classify("Build docs", "Build sphinx documentation") == "docs"
    assert classify("build", "Run prettier --check") == "lint_format"


def test_gate_reports_an_unrecognised_job_rather_than_guessing():
    from src.evaluation.job_scope import UNKNOWN, classify_job as classify

    assert classify("", "") == UNKNOWN
    assert classify("mystery-job", "do the thing") == UNKNOWN


def test_gate_reports_each_reference_threshold_without_deciding():
    """The plan asks for a reasoned selection, so the gate reports rather than rules."""
    from src.evaluation.job_scope import IN_SCOPE
    from tools.check_repository_gate import evaluate

    def case(classification=IN_SCOPE, log=True, linked=True, workflow="CI", log_id="x"):
        return {
            "log_id": log_id,
            "repository": "org/one",
            "classification": classification,
            "log_available": log,
            "repair_linked": linked,
            "workflow": workflow,
            "error_signature": log_id,
        }

    good = [case(workflow="CI" if i % 2 else "Build", log_id=f"g{i}") for i in range(30)]
    result = evaluate({"cases": good}, min_logs=30, min_repairs=15)
    assert "passed" not in result, "the gate must not emit a verdict"
    assert result["references_met"] == 4

    # Mostly lint failures: the scope reference is not met, and it is flagged.
    # Workflows still alternate, so only the scope reference is unmet.
    linty = [
        case(
            classification="lint_format" if i > 9 else IN_SCOPE,
            workflow="CI" if i % 2 else "Build",
            log_id=f"l{i}",
        )
        for i in range(30)
    ]
    result = evaluate({"cases": linty}, min_logs=30, min_repairs=15)
    assert result["references_met"] == 3
    assert result["criteria"][1]["reference"] is False


def test_gate_reports_family_counts_under_every_rule():
    """Distinct problems a history supplies, not just how many runs failed."""
    from src.evaluation.job_scope import IN_SCOPE
    from tools.check_repository_gate import evaluate

    cases = [
        {
            "log_id": "a",
            "repository": "org/one",
            "error_signature": "same",
            "classification": IN_SCOPE,
            "log_available": True,
            "repair_linked": True,
            "workflow": "CI",
        },
        {
            "log_id": "b",
            "repository": "org/one",
            "error_signature": "same",
            "classification": IN_SCOPE,
            "log_available": True,
            "repair_linked": True,
            "workflow": "CI",
        },
        {
            "log_id": "c",
            "repository": "org/one",
            "error_signature": "other",
            "classification": IN_SCOPE,
            "log_available": True,
            "repair_linked": True,
            "workflow": "Build",
        },
    ]
    result = evaluate({"cases": cases}, min_logs=30, min_repairs=15)
    by_rule = {item["rule"]: item for item in result["family_rules"]}
    # Three failed runs, but only two distinct problems.
    assert by_rule["signature"]["families"] == 2
    assert by_rule["signature"]["duplicate_cases"] == 1
    assert result["families"]["families"] == 2


def test_adjudication_preserves_both_independent_labels():
    """Cohen's kappa needs both original labels, so consensus must not overwrite one.

    Mirrors what run_verify records: the first reviewer's labels are snapshotted
    before an adjudicated value replaces the stored consensus.
    """
    record = {
        "log_id": "a",
        "actual_error_type": "syntax_error",
        "actual_root_cause": "A trailing comma broke the generated JSON map.",
        "failure_lines": [12],
    }
    verifier_label = "build_configuration"

    record.setdefault("annotator_error_type", record.get("actual_error_type"))
    record.setdefault("annotator_root_cause", record.get("actual_root_cause"))
    record.setdefault("annotator_failure_lines", list(record.get("failure_lines", [])))
    record["actual_error_type"] = "dependency_error"  # the adjudicated consensus
    record["verifier_error_type"] = verifier_label

    assert record["annotator_error_type"] == "syntax_error"
    assert record["verifier_error_type"] == "build_configuration"
    assert record["actual_error_type"] == "dependency_error"
    # All three are distinguishable, so agreement can still be computed.
    assert len({record["annotator_error_type"], record["verifier_error_type"]}) == 2


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


def test_a_root_cause_that_only_repeats_its_category_is_rejected():
    """Padding to clear the length floor must not pass as an explanation."""
    from src.evaluation.ground_truth_audit import restates_category

    assert restates_category("build configuration issue", "build_configuration")
    assert restates_category("syntax error from the log", "syntax_error")
    # A typo in the restatement is still a restatement.
    assert restates_category("build configuratio problem", "build_configuration")
    # Real explanations survive, including under the catch-all category.
    assert not restates_category("5 snapshots failed in the Jest suite for fabric", "test_failure")
    assert not restates_category("drop hyphen in alphanumeric characters", "unknown")

    audit = audit_annotations(
        [_annotation(actual_root_cause="build configuration issue", actual_error_type="build_configuration")]
    )
    assert not audit.is_defensible
    assert any(finding.code == "root_cause_restates_category" for finding in audit.findings)


def test_recorded_uncertainty_warns_without_blocking():
    """Honest uncertainty is worth keeping, but it cannot score a model."""
    audit = audit_annotations([_annotation(actual_root_cause="no idea where the error happened here")])
    codes = {finding.code for finding in audit.findings}
    assert "unresolved_root_cause" in codes
    # A warning does not block, and the case still counts as annotated.
    assert audit.is_defensible
    assert audit.usable_root_causes == 1


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


# ── Scope: an umbrella job has no single root cause to diagnose ────────────


def test_an_umbrella_job_listing_many_modules_is_out_of_scope():
    """A run where sixteen unrelated module suites executed has no one root cause.

    Admitting it would mean annotating ambiguous ground truth, and scoring a
    model against a question that is not well posed.
    """
    job = (
        "antlr, build-cache-local, build-profile, concurrent, declarative-dsl-core, "
        "file-collections, ide-model-impls, internal-testing (Unit Test)"
    )
    assert is_umbrella_job(job) is True


def test_an_inspected_aggregate_wrapper_is_out_of_scope():
    """gradle's sanityCheck fans out internally, which its job name does not reveal."""
    assert is_umbrella_job("Sanity Check on Linux") is True
    assert is_in_scope("Sanity Check on Linux", "Run ./gradlew sanityCheck") is True, (
        "the scope buckets read this as a legitimate check job, which is why the "
        "umbrella rule has to be applied separately in triage"
    )


def test_a_single_purpose_job_stays_in_scope():
    for job in ("Compile All", "Run tests", "antlr:test", "build, test"):
        assert is_umbrella_job(job) is False, job


def test_a_missing_job_name_is_not_treated_as_umbrella():
    """An unrecorded job name is a reason to inspect, not to discard."""
    assert is_umbrella_job("") is False
    assert is_umbrella_job(None) is False


def test_maintenance_automation_is_recognised_as_a_bot_run():
    """Five such runs reached an eligible gradle cohort before these markers existed."""
    for workflow in (
        "Submit Dependency Graph",
        "Running Copilot Code Review",
        "Auto update test buckets",
        "Auto update performance test buckets",
        "Upgrade to latest wrapper",
    ):
        assert is_bot_run({"workflow_name": workflow}) is True, workflow


def test_a_human_build_failure_is_not_a_bot_run():
    assert is_bot_run({"workflow_name": "Contributor CI Build", "failing_job": "Compile All"}) is False


# ── Sampling frame: ground truth needs repairs to exist before it is annotated ──


def test_the_sampling_window_resolves_to_absolute_dates():
    """A cohort's frame must be a fixed interval, not an age relative to today."""
    assert created_window(14, 45, today=date(2026, 10, 18)) == "2026-09-03..2026-10-04"


def test_the_window_is_ordered_oldest_to_newest():
    older, newer = created_window(7, 30, today=date(2026, 10, 18)).split("..")
    assert older < newer


def test_an_inverted_or_negative_window_is_refused():
    """Failing loudly here beats silently collecting from the wrong population."""
    for bad in ((45, 14), (10, 10), (-1, 30)):
        with pytest.raises(ValueError):
            created_window(*bad, today=date(2026, 10, 18))


def test_the_collector_requests_the_window_it_is_given():
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"workflow_runs": []}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs.get("params") or {})
        return FakeResponse()

    collector = GitHubActionsCollector("token")
    with mock.patch("src.data_collection.data_collection._request_with_retry", fake_request):
        collector.get_workflow_runs("owner", "repo", 100, created="2026-09-03..2026-10-04")
    assert captured["created"] == "2026-09-03..2026-10-04"
    assert captured["status"] == "failure"


def test_no_window_means_no_created_parameter():
    """Absent a declared frame the collector must not invent one."""
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"workflow_runs": []}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs.get("params") or {})
        return FakeResponse()

    collector = GitHubActionsCollector("token")
    with mock.patch("src.data_collection.data_collection._request_with_retry", fake_request):
        collector.get_workflow_runs("owner", "repo", 100)
    assert "created" not in captured


def test_static_analysis_jobs_are_out_of_scope():
    """scrapy names these "checks (3.10, mypy)", and "check" is an in-scope word.

    Without an explicit pattern they classify as build_test, which is how
    django's "Run Quality Checks on a PR" reached an eligible cohort.
    """
    for job in ("checks (3.10, mypy)", "checks (3.11, mypy)", "typecheck", "pyright"):
        assert is_excluded(job, "Run check") is True, job


def test_pre_commit_is_out_of_scope():
    """It runs whatever hooks a repository configures, mostly lint, many at once."""
    assert is_excluded("pre-commit", "Run pre-commit/action@2c") is True


def test_genuine_test_jobs_are_still_in_scope():
    for job, step in (
        ("tests (ubuntu, 3.12, py)", "Run tests"),
        ("Build&Test: node-24, windows-latest", "Test serve"),
        ("Compile All", ""),
    ):
        assert is_excluded(job, step) is False, job
        assert is_in_scope(job, step) is True, job


def test_surplus_becomes_reserve_rather_than_inflating_held_out():
    """held_out must stay the size it was declared, or it is not a defined set.

    Scoring needs ground truth, so surplus parked in held_out would leave the
    confirmatory set to be chosen case by case during annotation.
    """
    from automated_scripts.make_split import RESERVE, allocate

    cases = [_split_case(f"c{i}", "org/one", f"sig{i}") for i in range(99)]
    targets = {"development": 10, "pilot": 10, "held_out": 30}
    allocation = allocate(cases, targets, "signature", seed=11)

    assert len(allocation["held_out"]) <= 30
    assert len(allocation[RESERVE]) == 99 - sum(len(allocation[n]) for n in ("development", "pilot", "held_out"))
    assert sum(len(ids) for ids in allocation.values()) == 99


def test_no_family_straddles_the_reserve_and_a_partition():
    """A reserved case sharing a fault with a held-out case would leak it back in."""
    from automated_scripts.make_split import allocate
    from src.evaluation.failure_families import assign_families, check_no_family_spans_partitions

    cases = [_split_case(f"c{i}", "org/one", f"sig{i // 3}") for i in range(60)]
    allocation = allocate(cases, {"development": 5, "pilot": 5, "held_out": 10}, "signature", seed=13)
    assert check_no_family_spans_partitions(allocation, assign_families(cases, "signature")) == []


# ── Signatures: one fault must not enter the cohort many times ────────────


def _vcs_build_failure(sha: str, c_files: list, seconds: str) -> str:
    """Two runs of the same dependency-build fault, differing only in noise."""
    lines = [
        f"2026-09-30T04:06:29.8050126Z error: Failed to build `aiohttp @ git+https://host/aiohttp@{sha}`",
        "2026-09-30T04:06:29.8050127Z   cause: The build backend returned an error",
        "2026-09-30T04:06:29.8050128Z   cause: Call to `setuptools.build_meta.build_wheel` failed (exit status: 1)",
        f"2026-09-30T04:06:29.8050129Z evaluation failed :( ({seconds} seconds)",
    ]
    lines += [f"2026-09-30T04:06:29.8050130Z cc1: fatal error: {name}: No such file or directory" for name in c_files]
    return "\n".join(lines)


def test_one_fault_gets_one_signature_despite_revision_order_and_timing():
    """This fault reached a cohort 19 times, across development, pilot and held-out."""
    first = _vcs_build_failure(
        "3489636c044df3176665a2173d91ddef6d8161ec",
        ["aiohttp/_websocket/mask.c", "aiohttp/_http_writer.c", "aiohttp/_find_header.c"],
        "177.25",
    )
    # Same fault: different commit, diagnostics raced out in another order, different elapsed time.
    second = _vcs_build_failure(
        "31b6ebee2249d1cdf19da0f3af0c14ee2bf5d6b1",
        ["aiohttp/_http_writer.c", "aiohttp/_find_header.c", "aiohttp/_websocket/mask.c"],
        "203.90",
    )
    assert compute_error_signature(first) == compute_error_signature(second)


def test_different_faults_keep_different_signatures():
    """Normalisation must not merge unrelated failures."""
    build = _vcs_build_failure("abc1234def5678", ["aiohttp/mask.c"], "10.0")
    test = "\n".join(
        [
            "2026-09-30T04:06:29Z FAILED tests/test_exporters.py::TestCsvItemExporter::test_dropped_fields",
            "2026-09-30T04:06:29Z E       AssertionError: assert 3 == 1",
        ]
    )
    assert compute_error_signature(build) != compute_error_signature(test)


def test_generic_runner_noise_does_not_swamp_the_informative_lines():
    """Sorting the whole list before selecting merged six unrelated pypy failures.

    "##[error]Process completed with exit code 1." sorts ahead of real content,
    so selection has to happen in document order and only the window is sorted.
    """
    noise = "\n".join(f"2026-09-30T04:06:2{i}Z ##[error]Process completed with exit code 1." for i in range(9))
    one = f"2026-09-30T04:06:29Z FAILED tests/test_a.py::test_one - AssertionError\n{noise}"
    two = f"2026-09-30T04:06:29Z FAILED tests/test_b.py::test_two - TypeError\n{noise}"
    assert compute_error_signature(one) != compute_error_signature(two)


def test_the_failing_jobs_section_is_located_in_the_archive():
    """Line numbers must be read in the frame the scoring uses, not GitHub's."""
    from automated_scripts.annotate_blind import failing_job_section

    content = "\n".join(
        ["=== 0_tests (ubuntu, 3.15, default-reactor).txt ==="]
        + ["noise"] * 400
        + ["=== 18_tests (ubuntu, 3.14, no-reactor-extra-deps).txt ==="]
        + ["the real failure"] * 50
    )
    log = {"log_content": content, "failing_job": "tests (ubuntu, 3.14, no-reactor-extra-deps)"}
    start, end, name = failing_job_section(log)
    assert start == 402 and end == 452
    assert name.startswith("18_")


def test_a_single_job_archive_reports_no_offset():
    from automated_scripts.annotate_blind import failing_job_section

    log = {"log_content": "=== 0_tests.txt ===\nboom", "failing_job": "tests"}
    assert failing_job_section(log)[0] == 1


def test_an_unlocatable_failing_job_is_reported_as_unknown():
    """Better to say nothing than to print an offset for the wrong section."""
    from automated_scripts.annotate_blind import failing_job_section

    assert failing_job_section({"log_content": "=== 0_other.txt ===\nx", "failing_job": "tests"}) == (None, None, None)
    assert failing_job_section({"log_content": "x", "failing_job": ""}) == (None, None, None)


def test_the_section_matcher_survives_githubs_filename_sanitising():
    """A colon in the job name is dropped from the stored section filename.

    Comparing literally found no section for any vite case, so the offset banner
    stayed silent and six annotations were recorded against the wrong matrix
    entry of the same run.
    """
    from automated_scripts.annotate_blind import failing_job_section

    content = "\n".join(
        ["=== 0_Build & Test Failed.txt ==="]
        + ["summary"] * 34
        + ["=== 2_Build&Test node-24, windows-latest.txt ==="]
        + ["other matrix entry"] * 100
        + ["=== 4_Build&Test node-24, ubuntu-latest.txt ==="]
        + ["the failing entry"] * 50
    )
    log = {"log_content": content, "failing_job": "Build&Test: node-24, ubuntu-latest"}
    start, end, name = failing_job_section(log)
    assert name.startswith("4_"), name
    assert start == 137 and end == 187


def test_a_matrix_entry_is_not_confused_with_a_similarly_named_one():
    """node-24 must not match the node-24-with-a-different-os section."""
    from automated_scripts.annotate_blind import failing_job_section

    content = "\n".join(
        ["=== 2_Build&Test node-24, macos-latest.txt ==="]
        + ["wrong os"] * 20
        + ["=== 3_Build&Test node-24, ubuntu-latest.txt ==="]
        + ["right one"] * 10
    )
    log = {"log_content": content, "failing_job": "Build&Test: node-24, ubuntu-latest"}
    assert failing_job_section(log)[0] == 22


# ── Filtering: the model must be shown the job that failed ────────────────


def _run_archive() -> str:
    """A stored run log: several job sections, runner system files at the end."""
    return "\n".join(
        ["=== 0_tests (ubuntu, 3.15, py).txt ==="]
        + ["an unrelated job failed here: error in something else"] * 300
        + ["=== 18_tests (ubuntu, 3.14, extra-deps).txt ==="]
        + ["setup"] * 10
        + ["FAILED tests/test_target.py::test_it - AssertionError: the real failure"]
        + ["teardown"] * 10
        + ["=== tests (ubuntu, 3.14, extra-deps)/system.txt ==="]
        + ["runner noise: error reading something irrelevant"] * 400
    )


def test_scoping_keeps_the_failing_jobs_evidence():
    """Unscoped, the line cap keeps the trailing system logs and loses the failure."""
    archive = _run_archive()
    # Locate it rather than hardcoding, so the fixture can be edited safely.
    failed_line = next(i for i, line in enumerate(archive.split("\n"), 1) if line.startswith("FAILED"))
    evidence = [failed_line]

    unscoped = LogFilter.trace_filtering(archive, evidence, max_lines=50)
    scoped = LogFilter.trace_filtering(
        archive, evidence, max_lines=50, failing_job="tests (ubuntu, 3.14, extra-deps)"
    )
    assert unscoped["after_line_cap"]["recall"] == 0.0
    assert scoped["after_line_cap"]["recall"] == 1.0


def test_scoped_line_numbers_stay_in_the_stored_logs_frame():
    """The model's [Line N] and the annotated evidence must be the same frame."""
    archive = _run_archive()
    filtered = LogFilter.apply_smart_filtering(
        archive, max_lines=50, window_size=2, failing_job="tests (ubuntu, 3.14, extra-deps)"
    )
    failed_line = next(i for i, line in enumerate(archive.split("\n"), 1) if line.startswith("FAILED"))
    assert failed_line > 300, "the failure must sit well past the first section"
    assert f"[Line {failed_line}]" in filtered, "the failing line must keep its archive-wide number"
    assert "[Line 1]" not in filtered


def test_an_unlocatable_job_falls_back_to_the_whole_log():
    """Scoping to the wrong section would hide the failure entirely."""
    archive = _run_archive()
    whole = LogFilter.apply_smart_filtering(archive, max_lines=50, window_size=2)
    missing = LogFilter.apply_smart_filtering(
        archive, max_lines=50, window_size=2, failing_job="a job that is not in this run"
    )
    assert missing == whole


def test_escape_codes_are_stripped_without_moving_line_numbers():
    """Colour codes cost budget and tell the model nothing, but the frame must hold."""
    raw = "\n".join(
        ["plain setup"] * 5
        + ["\x1b[41m\x1b[1m FAIL \x1b[22m\x1b[49m playground/a.spec.ts > it works"]
        + ["more setup"] * 5
    )
    filtered = LogFilter.apply_smart_filtering(raw, max_lines=50, window_size=2)
    assert "\x1b[" not in filtered
    assert "FAIL" in filtered
    assert "[Line 6]" in filtered, "the failing line must keep its original number"


def test_the_token_budget_is_enforced_even_for_enormous_lines():
    """Middle-trimming stops at five head and five tail lines.

    One vite case returned 24,246 tokens against a 12,000 budget because ten of
    its lines alone exceeded it, which would have overflowed the local model's
    context mid-run.
    """
    huge = " ".join(f"error token{i}" for i in range(4000))
    raw = "\n".join([huge] * 12)
    filtered = LogFilter.apply_smart_filtering(raw, max_lines=500, window_size=20, max_tokens=2000)
    assert _count_tokens(filtered) <= 2000


def test_a_log_inside_the_budget_is_left_alone():
    raw = "\n".join(["setup", "ERROR something failed", "teardown"])
    filtered = LogFilter.apply_smart_filtering(raw, max_lines=50, window_size=1, max_tokens=12000)
    assert "... [truncated] ..." not in filtered
    assert "ERROR something failed" in filtered


# ── SRQ1 must be testable on a cohort that carries one category ───────────


def _prediction(log_id: str, predicted_lines: list, actual_lines: list):
    from src.evaluation.evaluation import PredictionResult

    return PredictionResult(
        log_id=log_id,
        predicted_error_type="test_failure",
        actual_error_type="test_failure",
        predicted_lines=predicted_lines,
        actual_lines=actual_lines,
        confidence=0.9,
        hallucination_detected=False,
        execution_time_ms=1000.0,
    )


def test_a_one_category_cohort_still_yields_a_testable_difference():
    """McNemar is forced to "identical" when every label is the same.

    On the first development run both models scored 11/11 on category and
    McNemar returned p = 1.0, while the hosted model was ahead on evidence lines
    in all eleven cases. The category test was answering a question the data
    could not distinguish.
    """
    from src.evaluation.evaluation import StatisticalTests

    truth = [[10, 11, 12, 13] for _ in range(8)]
    # The tested statistic is precision, so the two conditions have to differ in
    # what they cite, not only in how much: the weaker one mixes in lines that
    # are not evidence.
    better = [_prediction(f"c{i}", [10, 11, 12], truth[i]) for i in range(8)]
    worse = [_prediction(f"c{i}", [10, 97, 98], truth[i]) for i in range(8)]

    mcnemar = StatisticalTests.mcnemar_test(better, worse)
    assert mcnemar["n01"] == 0 and mcnemar["n10"] == 0, "category accuracy cannot discriminate here"

    evidence = StatisticalTests.paired_evidence_line_test(better, worse)
    assert evidence["primary_metric"] == "f1"
    assert evidence["a_better"] == 8 and evidence["b_better"] == 0
    assert evidence["significant_at_005"] is True
    assert evidence["mean_f1_difference"] > 0


def test_cases_without_annotated_lines_are_excluded_not_scored_zero():
    """Missing annotation must never be counted as a model failure."""
    from src.evaluation.evaluation import StatisticalTests

    a = [_prediction("c1", [1, 2], [1, 2]), _prediction("c2", [5], [])]
    b = [_prediction("c1", [1], [1, 2]), _prediction("c2", [9], [])]
    assert StatisticalTests.paired_evidence_line_test(a, b)["scorable_pairs"] == 1


def test_identical_evidence_lines_are_reported_as_such():
    from src.evaluation.evaluation import StatisticalTests

    a = [_prediction(f"c{i}", [1, 2], [1, 2]) for i in range(5)]
    b = [_prediction(f"c{i}", [1, 2], [1, 2]) for i in range(5)]
    result = StatisticalTests.paired_evidence_line_test(a, b)
    assert result["ties"] == 5
    assert "Identical" in result["verdict"]


def test_freezing_before_the_pilot_is_blocked():
    """The held-out run happens once; it must not be the first full exercise."""
    from automated_scripts.freeze_package import blocking_problems

    problems = blocking_problems(_freeze_record(pilot=False))
    assert any("pilot" in p for p in problems), problems


def test_a_freeze_needs_a_recorded_approver():
    from automated_scripts.freeze_package import blocking_problems

    assert any("approver" in p for p in blocking_problems(_freeze_record(approver="")))


def test_single_annotator_ground_truth_needs_a_recorded_approval():
    """Permitted where supervisors accepted it, and the acceptance must be on file."""
    from automated_scripts.freeze_package import blocking_problems

    problems = blocking_problems(_freeze_record(methodology=False))
    assert any("methodology_approval" in p for p in problems), problems


def test_allow_dirty_forgives_only_the_worktree():
    """It used to forgive every gate, which would pass a freeze with no pilot."""
    from automated_scripts.freeze_package import blocking_problems

    problems = blocking_problems(_freeze_record(clean=False, pilot=False))
    survivors = [p for p in problems if "worktree is dirty" not in p]
    assert any("pilot" in p for p in survivors), survivors


# ── Workflow routing: which cases each command actually runs ──────────────


def _workflow_source() -> str:
    import pathlib

    return pathlib.Path("run_workflow.sh").read_text(encoding="utf-8")


def test_the_final_run_is_scoped_to_the_held_out_partition():
    """Without --partition it covered all 81 cases, development included.

    The confirmatory run would then have been scored partly on the cases the
    system was tuned on. This is asserted on the script because the defect was
    in the routing, not in the Python it calls.
    """
    source = _workflow_source()
    final = source[source.index("cmd_final()") : source.index("cmd_engineering()")]
    assert "--partition held_out" in final, "the held-out run must be scoped to its partition"


def test_pilot_runs_the_partition_and_pilot_smoke_runs_the_smoke_cohort():
    """"pilot" ran the five-case smoke cohort, leaving the partition unreachable."""
    source = _workflow_source()
    assert "    pilot)          cmd_pilot_partition ;;" in source
    assert "    pilot-smoke)    cmd_pilot_smoke ;;" in source
    assert "cmd_pilot_partition() { cmd_partition_run pilot; }" in source


def test_the_engineering_workflow_still_uses_the_smoke_pilot():
    """engineering is the smoke rehearsal and must not touch the study cohort."""
    source = _workflow_source()
    start = source.index("cmd_engineering()")
    # Bound at the function's closing brace; slicing to end-of-file would also
    # pick up the dispatch table, which legitimately names both pilot commands.
    engineering = source[start : source.index("\n}", start)]
    assert "cmd_pilot_smoke" in engineering
    assert "cmd_pilot_partition" not in engineering


def test_the_default_study_config_is_the_active_one():
    """A stale default silently collects into the wrong study, and study dirs are immutable."""
    source = _workflow_source()
    assert 'STUDY_CONFIG="configs/thesis_scrapy_vite_2026.yaml"' in source


def test_every_dispatched_command_has_a_function():
    """A command listed in the dispatch table but never defined fails only at runtime."""
    import re

    source = _workflow_source()
    dispatched = set(re.findall(r"^\s+[a-z-]+\)\s+(cmd_[a-z_]+)", source, re.MULTILINE))
    defined = set(re.findall(r"^(cmd_[a-z_]+)\(\)", source, re.MULTILINE))
    assert dispatched <= defined, f"dispatched but undefined: {sorted(dispatched - defined)}"


def test_an_inapplicable_grounding_score_is_not_averaged_as_zero():
    """The baseline cites lines straight from the filtered log, so grounding
    says nothing about it and its records store None. Counting that as zero
    understates the condition; counting it as one flatters it."""
    from src.evaluation.report_comparison import compute_model_metrics

    baseline_rows = [
        {"status": "success", "log_id": f"c{i}", "error_type": "test_failure", "confidence_score": 0.0,
         "execution_time_ms": 1.0, "grounding_score": None, "failure_lines": [1]}
        for i in range(3)
    ]
    assert compute_model_metrics(baseline_rows)["mean_grounding_score"] is None

    model_rows = [
        {"status": "success", "log_id": f"c{i}", "error_type": "test_failure", "confidence_score": 0.9,
         "execution_time_ms": 1.0, "grounding_score": score, "failure_lines": [1]}
        for i, score in enumerate((1.0, 0.5))
    ]
    assert compute_model_metrics(model_rows)["mean_grounding_score"] == 0.75


def test_a_mixed_run_averages_only_the_applicable_scores():
    from src.evaluation.report_comparison import compute_model_metrics

    rows = [
        {"status": "success", "log_id": "a", "error_type": "test_failure", "confidence_score": 0.9,
         "execution_time_ms": 1.0, "grounding_score": 1.0, "failure_lines": [1]},
        {"status": "success", "log_id": "b", "error_type": "test_failure", "confidence_score": 0.9,
         "execution_time_ms": 1.0, "grounding_score": None, "failure_lines": [1]},
    ]
    assert compute_model_metrics(rows)["mean_grounding_score"] == 1.0


# ── The permutation test must agree with the data it is given ─────────────


def _correct_wrong(log_id: str, correct: bool):
    from src.evaluation.evaluation import PredictionResult

    return PredictionResult(
        log_id=log_id,
        predicted_error_type="test_failure" if correct else "timeout",
        actual_error_type="test_failure",
        predicted_lines=[1],
        actual_lines=[1],
        confidence=0.9,
        hallucination_detected=False,
        execution_time_ms=1.0,
    )


def test_the_permutation_test_matches_mcnemar_on_the_same_data():
    """The pilot reported p = 0.0 against McNemar's 0.248 on identical data.

    Taking the observed statistic as a.mean() - b.mean() put it one ULP above
    the identical quantity computed from the difference array, so no permutation
    ever counted as extreme. Three discordant pairs all favouring one model
    gives p = 0.25, not zero.
    """
    from src.evaluation.evaluation import StatisticalTests

    # 11 cases: 3 where a is right and b wrong, 6 both right, 2 both wrong.
    a = [_correct_wrong(f"c{i}", True) for i in range(9)] + [_correct_wrong(f"c{i}", False) for i in range(9, 11)]
    b = [_correct_wrong(f"c{i}", True) for i in range(6)] + [_correct_wrong(f"c{i}", False) for i in range(6, 11)]

    result = StatisticalTests.paired_permutation_test(a, b, n_permutations=2000)
    assert result["p_value"] > 0.1, result
    assert result["p_value"] < 0.5, result


def test_a_permutation_p_value_is_never_exactly_zero():
    """Resampling cannot demonstrate p = 0; the floor is set by the draw count."""
    from src.evaluation.evaluation import StatisticalTests

    a = [_correct_wrong(f"c{i}", True) for i in range(12)]
    b = [_correct_wrong(f"c{i}", False) for i in range(12)]
    result = StatisticalTests.paired_permutation_test(a, b, n_permutations=500)
    assert result["p_value"] > 0.0
    assert result["p_value"] <= 1.0 / 501 + 1e-9, result


def test_identical_predictions_give_a_p_value_of_one():
    from src.evaluation.evaluation import StatisticalTests

    a = [_correct_wrong(f"c{i}", True) for i in range(8)]
    b = [_correct_wrong(f"c{i}", True) for i in range(8)]
    assert StatisticalTests.paired_permutation_test(a, b, n_permutations=200)["p_value"] == 1.0


def test_precision_is_blind_to_a_model_that_cites_a_correct_subset():
    """Why precision is reported descriptively and F1 carries the test.

    A model citing one correct line scores the same precision as one citing
    three, so precision alone would call them equal. The citation count is
    reported beside it for the same reason.
    """
    from src.evaluation.evaluation import StatisticalTests

    truth = [[10, 11, 12, 13] for _ in range(6)]
    thorough = [_prediction(f"c{i}", [10, 11, 12], truth[i]) for i in range(6)]
    minimal = [_prediction(f"c{i}", [10], truth[i]) for i in range(6)]

    result = StatisticalTests.paired_evidence_line_test(thorough, minimal)
    assert result["mean_precision_a"] == result["mean_precision_b"], "precision cannot separate them"
    assert result["mean_f1_a"] > result["mean_f1_b"], "the tested metric can"
    assert result["mean_lines_cited_a"] > result["mean_lines_cited_b"]
    assert result["significant_at_005"] is True


def test_only_one_p_value_is_reported():
    """Two tests over the same pairs would be multiple testing without a correction.

    Precision is reported as a descriptive capability figure and deliberately
    carries no p-value; the absolute claim it supports is not a claim about a
    difference between conditions.
    """
    from src.evaluation.evaluation import StatisticalTests

    truth = [[10, 11, 12, 13] for _ in range(8)]
    thorough = [_prediction(f"c{i}", [10, 11, 12], truth[i]) for i in range(8)]
    minimal = [_prediction(f"c{i}", [10, 97], truth[i]) for i in range(8)]

    result = StatisticalTests.paired_evidence_line_test(thorough, minimal)
    assert result["primary_metric"] == "f1"
    p_keys = [k for k in result if "p_value" in k]
    assert p_keys == ["p_value"], f"exactly one p-value expected, found {p_keys}"
    assert "mean_precision_a" in result, "precision is still reported"
