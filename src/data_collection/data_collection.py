"""GitHub Actions log collection used by the controlled thesis study."""

from __future__ import annotations

import hashlib
import io
import logging
import time
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _request_with_retry(
    method: str,
    url: str,
    max_retries: int = 3,
    backoff: float = 2.0,
    **kwargs,
) -> requests.Response:
    """Retry transient GitHub failures with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code not in {429, 502, 503}:
                return response
            wait = backoff**attempt
            logger.warning("GitHub returned HTTP %d; retrying in %.1fs", response.status_code, wait)
        except requests.RequestException as exc:
            last_error = exc
            wait = backoff**attempt
            logger.warning("GitHub request failed (%s); retrying in %.1fs", exc, wait)
        time.sleep(wait)
    if last_error:
        raise last_error
    raise RuntimeError("GitHub request retries exhausted")


class GitHubActionsCollector:
    """Download failed GitHub Actions workflow logs with provenance metadata."""

    def __init__(self, github_token: str):
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def collect_logs_from_repo(
        self,
        owner: str,
        repo: str,
        num_logs: int,
        exclude_run_ids: Optional[set[int]] = None,
    ) -> List[Dict]:
        excluded = exclude_run_ids or set()
        # Inspect up to one API page so unavailable or preflight-excluded runs
        # do not prevent the collector from reaching the requested count.
        runs = self.get_workflow_runs(owner, repo, max(100, num_logs + len(excluded)))
        collected: List[Dict] = []

        for run in runs:
            if len(collected) >= num_logs:
                break
            if run["id"] in excluded:
                continue
            content = self.download_log(owner, repo, run["id"])
            if content is None:
                continue
            collected.append(
                {
                    "log_id": f"gh_{owner}_{repo}_{run['id']}",
                    "source": "github_actions",
                    "repository": f"{owner}/{repo}",
                    "workflow_name": run.get("name", ""),
                    "run_id": run["id"],
                    "run_attempt": run.get("run_attempt"),
                    "event": run.get("event", ""),
                    "status": run.get("status", ""),
                    "conclusion": run.get("conclusion", ""),
                    "commit_sha": run.get("head_sha", ""),
                    "log_content": content,
                    "log_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": run.get("created_at", ""),
                    "run_started_at": run.get("run_started_at", ""),
                    "updated_at": run.get("updated_at", ""),
                    "url": run.get("html_url", ""),
                }
            )
            time.sleep(1)
        return collected

    def get_workflow_runs(self, owner: str, repo: str, max_runs: int) -> List[Dict]:
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs"
        response = _request_with_retry(
            "GET",
            url,
            headers=self.headers,
            params={"status": "failure", "per_page": min(100, max(1, max_runs))},
            timeout=20,
        )
        if response.status_code != 200:
            message = response.text[:300].replace("\n", " ")
            raise RuntimeError(
                f"GitHub workflow-runs API returned HTTP {response.status_code} " f"for {owner}/{repo}: {message}"
            )
        payload = response.json()
        runs = payload.get("workflow_runs", [])
        if not isinstance(runs, list):
            raise RuntimeError(f"GitHub returned an invalid workflow-runs payload for {owner}/{repo}")
        return runs[:max_runs]

    def download_log(self, owner: str, repo: str, run_id: int) -> Optional[str]:
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
        response = _request_with_retry("GET", url, headers=self.headers, timeout=45)
        if response.status_code != 200:
            logger.warning(
                "Skipping unavailable log %s/%s run %d (HTTP %d)",
                owner,
                repo,
                run_id,
                response.status_code,
            )
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                parts = []
                for name in sorted(archive.namelist()):
                    if name.endswith("/"):
                        continue
                    with archive.open(name) as handle:
                        content = handle.read().decode("utf-8", errors="ignore")
                    parts.append(f"=== {name} ===\n{content}")
                return "\n".join(parts) if parts else None
        except zipfile.BadZipFile:
            logger.warning("GitHub returned a non-ZIP response for %s/%s run %d", owner, repo, run_id)
            return None
