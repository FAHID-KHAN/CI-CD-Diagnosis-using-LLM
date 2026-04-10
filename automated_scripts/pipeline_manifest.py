"""
pipeline_manifest.py - Track every step of the CI/CD diagnosis pipeline.

Maintains ``data/pipeline_manifest.json`` with a timestamped record of
each pipeline step: what ran, when, what config was used, how many logs
were produced, and where the output files live.

Usage from any script:

    from automated_scripts.pipeline_manifest import record_step

    record_step(
        step="collect",
        config={"repos": 17, "per_repo": "variable"},
        inputs={"source": "GitHub Actions API"},
        outputs={"batch1.json": 109},
        notes="Collected from 17 target repos",
    )
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "pipeline_manifest.json",
)

# Canonical step names and their order
STEP_ORDER = [
    "collect",
    "triage",
    "diagnose",
    "annotate",
    "evaluate",
    "benchmark",
]


def _load() -> dict:
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {"runs": []}


def _save(manifest: dict) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def record_step(
    step: str,
    config: Optional[Dict[str, Any]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, Any]] = None,
    notes: str = "",
    duration_seconds: Optional[float] = None,
) -> None:
    """Append a completed step record to the manifest."""
    manifest = _load()

    entry = {
        "step": step,
        "timestamp": datetime.now().isoformat(),
        "config": config or {},
        "inputs": inputs or {},
        "outputs": outputs or {},
        "notes": notes,
    }
    if duration_seconds is not None:
        entry["duration_seconds"] = round(duration_seconds, 1)

    manifest["runs"].append(entry)
    _save(manifest)


def get_latest(step: str) -> Optional[dict]:
    """Return the most recent run record for a given step, or None."""
    manifest = _load()
    for entry in reversed(manifest["runs"]):
        if entry["step"] == step:
            return entry
    return None


def summary() -> str:
    """Return a human-readable summary of pipeline state."""
    manifest = _load()
    if not manifest["runs"]:
        return "  No pipeline runs recorded yet."

    lines = []
    for step_name in STEP_ORDER:
        latest = get_latest(step_name)
        if latest:
            ts = latest["timestamp"][:19].replace("T", " ")
            outputs = latest.get("outputs", {})
            counts = ", ".join(f"{k}: {v}" for k, v in outputs.items() if isinstance(v, int))
            lines.append(f"  {step_name:<12} {ts}  {counts}")
        else:
            lines.append(f"  {step_name:<12} (not run)")

    return "\n".join(lines)
