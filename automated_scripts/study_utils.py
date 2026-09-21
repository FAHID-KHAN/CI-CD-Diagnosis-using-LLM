"""Shared helpers for immutable, study-specific dataset runs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    """Write JSON through a sibling temporary file to avoid partial records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def load_study_config(path: str | Path) -> tuple[dict, Path]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Study config must contain a YAML mapping")

    required = {"study_id", "repositories", "eligibility"}
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Study config missing required fields: {', '.join(missing)}")
    if not config["repositories"]:
        raise ValueError("Study config must contain at least one repository")

    seen = set()
    for item in config["repositories"]:
        name = item.get("name", "")
        if name.count("/") != 1:
            raise ValueError(f"Invalid repository name: {name!r}")
        if name in seen:
            raise ValueError(f"Duplicate repository in study config: {name}")
        if not isinstance(item.get("max_logs"), int) or item["max_logs"] < 1:
            raise ValueError(f"Invalid max_logs for repository {name}")
        seen.add(name)
    return config, config_path


def study_directory(config: dict, override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "data" / "studies" / config["study_id"]


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None

