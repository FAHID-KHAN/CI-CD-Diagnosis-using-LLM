"""GitHub Actions log collection used by the controlled thesis study."""

from __future__ import annotations

import hashlib
import io
import logging
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
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


def created_window(minimum_age_days: int, maximum_age_days: int, today: Optional[date] = None) -> str:
    """Build GitHub's ``created`` range for runs between two ages, in days.

    Sampling the newest failed runs is the worst choice for ground truth. A
    repair is found by looking for a later passing run, so a failure needs time
    to have been fixed before the repair exists to be read. Measured on
    18 October 2026: in a 0-7 day window 5 of 20 vite runs had a findable
    repair, against 10 of 20 in a 14-45 day window; scrapy went from 11 of 20 to
    17 of 20. Beyond about 45 days the rate falls again, because GitHub expires
    logs at around 90 days and branches are deleted.

    The caller must record the resolved dates, not the ages. "14 to 45 days ago"
    denotes a different interval every day it is run, so only the absolute range
    makes a cohort's sampling frame reproducible.
    """
    if minimum_age_days < 0 or maximum_age_days <= minimum_age_days:
        raise ValueError(f"invalid sampling window: {minimum_age_days}..{maximum_age_days} days")
    reference = today or datetime.now(timezone.utc).date()
    newest = reference - timedelta(days=minimum_age_days)
    oldest = reference - timedelta(days=maximum_age_days)
    return f"{oldest.isoformat()}..{newest.isoformat()}"


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
        created: Optional[str] = None,
    ) -> List[Dict]:
        excluded = exclude_run_ids or set()
        # Inspect up to one API page so unavailable or preflight-excluded runs
        # do not prevent the collector from reaching the requested count.
        runs = self.get_workflow_runs(owner, repo, max(100, num_logs + len(excluded)), created=created)
        collected: List[Dict] = []

        for run in runs:
            if len(collected) >= num_logs:
                break
            if run["id"] in excluded:
                continue
            content = self.download_log(owner, repo, run["id"])
            if content is None:
                continue
            job_details = self.get_failing_job(owner, repo, run["id"])
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
                    **job_details,
                }
            )
            time.sleep(1)
        return collected

    def get_failing_job(self, owner: str, repo: str, run_id: int) -> Dict:
        """Return the failing job and step for a run, recorded at collection time.

        Triage decides whether a failure is in scope from the failing job, but
        triage runs offline on stored cases. Capturing this during collection
        keeps triage deterministic and re-runnable without further API calls,
        and preserves the information after GitHub expires the run.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        try:
            response = _request_with_retry("GET", url, headers=self.headers, params={"per_page": 50}, timeout=30)
        except requests.RequestException as exc:
            logger.warning("Could not read jobs for %s/%s run %d: %s", owner, repo, run_id, exc)
            return {"failing_job": "", "failing_step": "", "job_count": None}
        if response.status_code != 200:
            return {"failing_job": "", "failing_step": "", "job_count": None}

        jobs = response.json().get("jobs", []) or []
        for job in jobs:
            if job.get("conclusion") != "failure":
                continue
            for step in job.get("steps", []) or []:
                if step.get("conclusion") == "failure":
                    return {
                        "failing_job": job.get("name", ""),
                        "failing_step": step.get("name", ""),
                        "job_count": len(jobs),
                    }
            return {"failing_job": job.get("name", ""), "failing_step": "", "job_count": len(jobs)}
        # A run can fail with no job at all -- a workflow-level or startup
        # failure, which produces no log and nothing to diagnose.
        return {"failing_job": "", "failing_step": "", "job_count": len(jobs)}

    def get_workflow_runs(
        self,
        owner: str,
        repo: str,
        max_runs: int,
        created: Optional[str] = None,
    ) -> List[Dict]:
        """List failed runs, optionally restricted to a ``created`` date range.

        Without *created* GitHub returns the newest failed runs, which is the
        window with the least repair traceability -- see ``created_window``.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs"
        params: Dict[str, object] = {"status": "failure", "per_page": min(100, max(1, max_runs))}
        if created:
            params["created"] = created
        response = _request_with_retry(
            "GET",
            url,
            headers=self.headers,
            params=params,
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
