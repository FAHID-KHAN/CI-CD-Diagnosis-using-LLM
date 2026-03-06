# data_collection.py - Tools for collecting and annotating CI/CD logs

import io
import json
import logging
import re
import sqlite3
import time
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _request_with_retry(method: str, url: str, max_retries: int = 3, backoff: float = 2.0, **kwargs) -> requests.Response:
    """HTTP request with exponential backoff on transient failures."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = requests.request(method, url, **kwargs)
            if resp.status_code in (429, 502, 503):
                wait = backoff ** attempt
                logger.warning("HTTP %d from %s, retrying in %.1fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            wait = backoff ** attempt
            logger.warning("Request error (%s), retrying in %.1fs", exc, wait)
            time.sleep(wait)
    raise last_exc or RuntimeError("request_with_retry exhausted")

@dataclass
class LogAnnotation:
    """Structure for annotated logs"""
    log_id: str
    source: str  # 'github_actions' or 'bugswarm'
    repository: str
    workflow_name: str
    failure_type: str
    failure_lines: List[int]
    root_cause: str
    fix_description: str
    log_content: str
    annotator: str
    annotation_date: str
    confidence: float

class GitHubActionsCollector:
    """Collect failed workflow logs from GitHub Actions"""
    
    def __init__(self, github_token: str):
        self.token = github_token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def search_failed_workflows(self, query: str = "language:python", 
                                max_results: int = 100) -> List[Dict]:
        """Search for repositories with failed workflows"""
        repos = []
        url = f"{self.base_url}/search/repositories"
        params = {
            "q": f"{query} stars:>100",
            "sort": "stars",
            "per_page": min(max_results, 100)
        }
        try:
            response = _request_with_retry("GET", url, headers=self.headers, params=params, timeout=15)
            if response.status_code == 200:
                repos = response.json()['items']
        except Exception as e:
            logger.error("Error searching repositories: %s", e)
        return repos
    
    def collect_logs_from_repo(self, owner: str, repo: str, num_logs: int = 50) -> List[Dict]:
        """Collect failed logs from a specific GitHub repository"""
        collected_logs = []
        runs = self.get_workflow_runs(owner, repo, max_runs=num_logs)
        for run in runs:
            if len(collected_logs) >= num_logs:
                break
            log_content = self.download_log(owner, repo, run['id'])
            if log_content:
                collected_logs.append({
                    'log_id': f"gh_{owner}_{repo}_{run['id']}",
                    'source': 'github_actions',
                    'repository': f"{owner}/{repo}",
                    'workflow_name': run.get('name', ''),
                    'run_id': run['id'],
                    'log_content': log_content,
                    'created_at': run.get('created_at', ''),
                    'url': run.get('html_url', '')
                })
                logger.info("Collected log %d/%d", len(collected_logs), num_logs)
            time.sleep(1)
        return collected_logs
    def get_workflow_runs(self, owner: str, repo: str, 
                         status: str = "failure", max_runs: int = 100) -> List[Dict]:
        """Get workflow runs for a repository (with pagination)"""
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs"
        params = {
            "status": status,
            "per_page": 100
        }
        runs = []
        page = 1
        while len(runs) < max_runs:
            params['page'] = page
            try:
                response = _request_with_retry("GET", url, headers=self.headers, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()['workflow_runs']
                    if not data:
                        break
                    runs.extend(data)
                    if len(data) < 100:
                        break
                    page += 1
                else:
                    break
            except Exception as e:
                logger.error("Error fetching workflow runs: %s", e)
                break
        return runs[:max_runs]
    
    def download_log(self, owner: str, repo: str, run_id: int) -> Optional[str]:
        """Download workflow log (reads ALL files from the ZIP archive)"""
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
        try:
            response = _request_with_retry("GET", url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                try:
                    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                        parts = []
                        for name in sorted(z.namelist()):
                            if name.endswith('/'):
                                continue
                            with z.open(name) as f:
                                content = f.read().decode('utf-8', errors='ignore')
                                parts.append(f"=== {name} ===\n{content}")
                        return "\n".join(parts) if parts else None
                except Exception:
                    return response.text
        except Exception as e:
            logger.error("Error downloading log for %s/%s run %d: %s", owner, repo, run_id, e)
        return None
    
    def collect_logs(self, num_logs: int = 500) -> List[Dict]:
        """Collect failed logs from GitHub Actions"""
        collected_logs = []
        repos = self.search_failed_workflows(max_results=50)
        for repo in repos:
            if len(collected_logs) >= num_logs:
                break
            owner = repo['owner']['login']
            repo_name = repo['name']
            runs = self.get_workflow_runs(owner, repo_name, max_runs=50)
            for run in runs:
                if len(collected_logs) >= num_logs:
                    break
                log_content = self.download_log(owner, repo_name, run['id'])
                if log_content:
                    collected_logs.append({
                        'log_id': f"gh_{owner}_{repo_name}_{run['id']}",
                        'source': 'github_actions',
                        'repository': f"{owner}/{repo_name}",
                        'workflow_name': run.get('name', ''),
                        'run_id': run['id'],
                        'log_content': log_content,
                        'created_at': run.get('created_at', ''),
                        'url': run.get('html_url', '')
                    })
                    logger.info("Collected log %d/%d", len(collected_logs), num_logs)
                time.sleep(1)
        return collected_logs

class BugSwarmCollector:
    """Collect logs from BugSwarm dataset"""
    
    def __init__(self, bugswarm_path: str):
        self.bugswarm_path = Path(bugswarm_path)
    
    def load_bugswarm_artifacts(self) -> List[Dict]:
        """Load BugSwarm artifacts"""
        artifacts = []
        metadata_file = self.bugswarm_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                for artifact in data:
                    if artifact.get('failed_build'):
                        artifacts.append({
                            'log_id': f"bs_{artifact['repo']}_{artifact['failed_build_id']}",
                            'source': 'bugswarm',
                            'repository': artifact['repo'],
                            'build_id': artifact['failed_build_id'],
                            'log_path': artifact.get('failed_log_path'),
                            'fix_commit': artifact.get('fix_commit'),
                            'workflow_name': ''  # For consistency with GitHub logs
                        })
        return artifacts
    
    def load_log_file(self, log_path: str) -> Optional[str]:
        """Load log content from file"""
        full_path = self.bugswarm_path / log_path
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        return None
    
    def collect_logs(self, num_logs: int = 300) -> List[Dict]:
        """Collect logs from BugSwarm"""
        artifacts = self.load_bugswarm_artifacts()
        collected_logs = []
        for artifact in artifacts[:num_logs]:
            if artifact['log_path']:
                log_content = self.load_log_file(artifact['log_path'])
                if log_content:
                    collected_logs.append({
                        'log_id': artifact['log_id'],
                        'source': artifact['source'],
                        'repository': artifact['repository'],
                        'workflow_name': artifact.get('workflow_name', ''),
                        'build_id': artifact['build_id'],
                        'log_content': log_content,
                        'fix_commit': artifact.get('fix_commit')
                    })
        return collected_logs

class LogAnnotationTool:
    """Tool for manual annotation of logs"""
    
    def __init__(self, db_path: str = "annotations.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for annotations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS annotations (
                log_id TEXT PRIMARY KEY,
                source TEXT,
                repository TEXT,
                workflow_name TEXT,
                failure_type TEXT,
                failure_lines TEXT,
                root_cause TEXT,
                fix_description TEXT,
                log_content TEXT,
                annotator TEXT,
                annotation_date TEXT,
                confidence REAL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_annotation(self, annotation: LogAnnotation):
        """Save annotation to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO annotations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            annotation.log_id,
            annotation.source,
            annotation.repository,
            annotation.workflow_name,
            annotation.failure_type,
            json.dumps(annotation.failure_lines),
            annotation.root_cause,
            annotation.fix_description,
            annotation.log_content,
            annotation.annotator,
            annotation.annotation_date,
            annotation.confidence
        ))
        
        conn.commit()
        conn.close()
    
    def get_annotation(self, log_id: str) -> Optional[LogAnnotation]:
        """Retrieve annotation from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM annotations WHERE log_id = ?", (log_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return LogAnnotation(
                log_id=row[0],
                source=row[1],
                repository=row[2],
                workflow_name=row[3],
                failure_type=row[4],
                failure_lines=json.loads(row[5]),
                root_cause=row[6],
                fix_description=row[7],
                log_content=row[8],
                annotator=row[9],
                annotation_date=row[10],
                confidence=row[11]
            )
        return None
    
    def export_annotations(self, output_path: str):
        """Export all annotations to JSON"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM annotations")
        rows = cursor.fetchall()
        conn.close()
        
        annotations = []
        for row in rows:
            annotations.append({
                'log_id': row[0],
                'source': row[1],
                'repository': row[2],
                'workflow_name': row[3],
                'failure_type': row[4],
                'failure_lines': json.loads(row[5]),
                'root_cause': row[6],
                'fix_description': row[7],
                'annotator': row[9],
                'annotation_date': row[10],
                'confidence': row[11]
            })
        
        with open(output_path, 'w') as f:
            json.dump(annotations, f, indent=2)
        
        logger.info("Exported %d annotations to %s", len(annotations), output_path)
    
    def get_statistics(self) -> Dict:
        """Get annotation statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM annotations")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT failure_type, COUNT(*) FROM annotations GROUP BY failure_type")
        by_type = dict(cursor.fetchall())
        
        cursor.execute("SELECT AVG(confidence) FROM annotations")
        avg_confidence = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_annotations': total,
            'by_failure_type': by_type,
            'average_confidence': avg_confidence
        }

class ErrorLineDetector:
    """Automated error line detection helper"""
    
    ERROR_PATTERNS = [
        r'(?i)error:?\s',
        r'(?i)exception:?\s',
        r'(?i)failed:?\s',
        r'(?i)failure:?\s',
        r'(?i)fatal:?\s',
        r'(?i)traceback',
        r'npm ERR!',
        r'FAILED',
        r'BUILD FAILED',
        r'Test.*failed'
    ]
    
    @staticmethod
    def detect_error_lines(log_content: str) -> List[int]:
        """Automatically detect potential error lines"""
        lines = log_content.split('\n')
        error_lines = []
        
        for i, line in enumerate(lines):
            for pattern in ErrorLineDetector.ERROR_PATTERNS:
                if re.search(pattern, line):
                    error_lines.append(i + 1)  # 1-indexed
                    break
        
        return error_lines
    
    @staticmethod
    def classify_error_type(log_content: str) -> str:
        """Automatically classify error type"""
        content_lower = log_content.lower()
        
        if any(word in content_lower for word in ['dependency', 'package', 'module not found', 'import error']):
            return 'dependency_error'
        elif any(word in content_lower for word in ['test failed', 'assertion', 'expected']):
            return 'test_failure'
        elif any(word in content_lower for word in ['timeout', 'timed out']):
            return 'timeout'
        elif any(word in content_lower for word in ['permission denied', 'access denied']):
            return 'permission_denied'
        elif any(word in content_lower for word in ['syntax error', 'parse error']):
            return 'syntax_error'
        elif any(word in content_lower for word in ['connection', 'network', 'dns']):
            return 'network_error'
        elif any(word in content_lower for word in ['build.gradle', 'pom.xml', 'package.json']):
            return 'build_configuration'
        else:
            return 'unknown'

# Example usage
if __name__ == "__main__":
    # Collect logs from GitHub Actions
    # collector = GitHubActionsCollector(github_token="your_token_here")
    # logs = collector.collect_logs(num_logs=100)
    
    # Initialize annotation tool
    annotation_tool = LogAnnotationTool()
    
    # Example annotation
    example_annotation = LogAnnotation(
        log_id="test_001",
        source="github_actions",
        repository="user/repo",
        workflow_name="CI",
        failure_type="dependency_error",
        failure_lines=[45, 46],
        root_cause="Missing dependency: requests",
        fix_description="Add 'requests' to requirements.txt",
        log_content="...",
        annotator="researcher_1",
        annotation_date=datetime.now().isoformat(),
        confidence=0.95
    )
    
    annotation_tool.save_annotation(example_annotation)
    stats = annotation_tool.get_statistics()
    logger.info("Annotation statistics: %s", stats)