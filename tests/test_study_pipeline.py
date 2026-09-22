import json
import pytest
import yaml

from automated_scripts.study_utils import atomic_write_json, load_study_config, sha256_text
from automated_scripts.annotate_blind import parse_line_numbers
from automated_scripts.benchmark_models import validate_inputs
from automated_scripts.create_smoke_cohort import select_smoke_cases
from automated_scripts.triage import triage_logs
from src.api.filtering import LogFilter
from src.api.grounding import GroundingVerifier
from src.data_collection.data_collection import GitHubActionsCollector


def test_study_config_is_balanced_and_declared_target_matches():
    config, _ = load_study_config("configs/thesis_fresh_2026.yaml")
    assert len(config["repositories"]) == 6
    assert sum(item["max_logs"] for item in config["repositories"]) == config["target_raw_logs"]
    assert {item["ecosystem"] for item in config["repositories"]} == {"python", "javascript_typescript", "jvm"}


def test_study_config_rejects_duplicate_repositories(tmp_path):
    config = {
        "study_id": "duplicate-test",
        "repositories": [
            {"name": "owner/repo", "max_logs": 1},
            {"name": "owner/repo", "max_logs": 1},
        ],
        "eligibility": {},
    }
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="Duplicate repository"):
        load_study_config(path)


def test_atomic_json_and_sha(tmp_path):
    path = tmp_path / "result.json"
    atomic_write_json(path, {"value": "stable"})
    assert json.loads(path.read_text()) == {"value": "stable"}
    assert sha256_text("stable") == "f379ccb92b9116442dc65bdc35648a85d3786b34779db7f704a901fa07b00cb6"


def test_triage_keeps_auditable_exclusion_metadata():
    logs = [
        {
            "log_id": "gh_owner_repo_1",
            "repository": "owner/repo",
            "workflow_name": "CI",
            "run_id": 1,
            "url": "https://example.test/run/1",
            "log_sha256": "abc",
            "log_content": "Bad credentials\n" * 25,
        }
    ]
    kept, removed = triage_logs(logs)
    assert kept == []
    assert removed == [
        {
            "log_id": "gh_owner_repo_1",
            "reason": "token_error",
            "repository": "owner/repo",
            "workflow_name": "CI",
            "run_id": 1,
            "url": "https://example.test/run/1",
            "log_sha256": "abc",
        }
    ]


def test_collector_adds_reproducibility_metadata(monkeypatch):
    collector = GitHubActionsCollector("test-token")
    monkeypatch.setattr(
        collector,
        "get_workflow_runs",
        lambda *args, **kwargs: [
            {
                "id": 42,
                "name": "CI",
                "run_attempt": 2,
                "event": "push",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": "deadbeef",
                "created_at": "2026-01-01T00:00:00Z",
                "run_started_at": "2026-01-01T00:00:01Z",
                "updated_at": "2026-01-01T00:01:00Z",
                "html_url": "https://example.test/run/42",
            }
        ],
    )
    monkeypatch.setattr(collector, "download_log", lambda *args, **kwargs: "line one\nERROR: failed")
    monkeypatch.setattr("src.data_collection.data_collection.time.sleep", lambda *_: None)

    result = collector.collect_logs_from_repo("owner", "repo", num_logs=1)[0]

    assert result["repository"] == "owner/repo"
    assert result["run_attempt"] == 2
    assert result["commit_sha"] == "deadbeef"
    assert result["conclusion"] == "failure"
    assert len(result["log_sha256"]) == 64
    assert result["collected_at"].endswith("+00:00")


def test_blind_annotation_line_parser():
    assert parse_line_numbers("4, 8-10, 8") == [4, 8, 9, 10]
    with pytest.raises(ValueError):
        parse_line_numbers("10-8")


def test_benchmark_rejects_stale_ground_truth():
    logs = [{"log_id": "case-1", "log_sha256": "new-hash"}]
    annotations = [{"log_id": "case-1", "log_sha256": "old-hash"}]
    assert "different log content" in validate_inputs(logs, annotations)


def test_benchmark_accepts_matching_ground_truth():
    logs = [{"log_id": "case-1", "log_sha256": "same-hash"}]
    annotations = [{"log_id": "case-1", "log_sha256": "same-hash"}]
    assert validate_inputs(logs, annotations) is None


def test_filtered_logs_keep_human_facing_one_based_line_numbers():
    filtered = LogFilter.apply_smart_filtering("setup\nERROR failed\ncleanup", window_size=0)
    assert filtered == "[Line 2] ERROR failed"


def test_missing_evidence_is_ungrounded():
    assert GroundingVerifier.verify_evidence("[Line 1] ERROR", []) == (True, 0.0)


def test_smoke_selection_is_deterministic_and_repository_diverse():
    cases = [
        {
            "log_id": f"{repository}-{index}",
            "repository": repository,
            "log_sha256": f"hash-{repository}-{index}",
        }
        for repository in ("a/one", "b/two", "c/three")
        for index in range(3)
    ]
    original = json.loads(json.dumps(cases))
    first = select_smoke_cases(cases, size=3, seed=42)
    second = select_smoke_cases(cases, size=3, seed=42)

    assert [item["log_id"] for item in first] == [item["log_id"] for item in second]
    assert len({item["repository"] for item in first}) == 3
    assert cases == original


def test_smoke_selection_rejects_duplicate_ids():
    cases = [
        {"log_id": "duplicate", "repository": "a/one", "log_sha256": "one"},
        {"log_id": "duplicate", "repository": "b/two", "log_sha256": "two"},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        select_smoke_cases(cases, size=1, seed=42)
