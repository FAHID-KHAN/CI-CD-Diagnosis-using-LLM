import json
import pytest
import yaml

from automated_scripts.study_utils import atomic_write_json, load_study_config, sha256_text
from automated_scripts.triage import triage_logs
from src.data_collection.data_collection import GitHubActionsCollector


def test_study_config_is_balanced_and_declared_target_matches():
    config, _ = load_study_config("configs/thesis_fresh_2026.yaml")
    assert len(config["repositories"]) == 6
    assert sum(item["max_logs"] for item in config["repositories"]) == config["target_raw_logs"]
    assert {item["ecosystem"] for item in config["repositories"]} == {
        "python", "javascript_typescript", "jvm"
    }


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
    logs = [{
        "log_id": "gh_owner_repo_1",
        "repository": "owner/repo",
        "workflow_name": "CI",
        "run_id": 1,
        "url": "https://example.test/run/1",
        "log_sha256": "abc",
        "log_content": "Bad credentials\n" * 25,
    }]
    kept, removed = triage_logs(logs)
    assert kept == []
    assert removed == [{
        "log_id": "gh_owner_repo_1",
        "reason": "token_error",
        "repository": "owner/repo",
        "workflow_name": "CI",
        "run_id": 1,
        "url": "https://example.test/run/1",
        "log_sha256": "abc",
    }]


def test_collector_adds_reproducibility_metadata(monkeypatch):
    collector = GitHubActionsCollector("test-token")
    monkeypatch.setattr(collector, "get_workflow_runs", lambda *args, **kwargs: [{
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
    }])
    monkeypatch.setattr(collector, "download_log", lambda *args, **kwargs: "line one\nERROR: failed")
    monkeypatch.setattr("src.data_collection.data_collection.time.sleep", lambda *_: None)

    result = collector.collect_logs_from_repo("owner", "repo", num_logs=1)[0]

    assert result["repository"] == "owner/repo"
    assert result["run_attempt"] == 2
    assert result["commit_sha"] == "deadbeef"
    assert result["conclusion"] == "failure"
    assert len(result["log_sha256"]) == 64
    assert result["collected_at"].endswith("+00:00")
