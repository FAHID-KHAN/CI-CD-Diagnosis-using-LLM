"""Tolerant readers for the JSON a study run leaves on disk.

A benchmark run can be interrupted mid-write, which leaves a truncated file
behind. Reporting has to survive that, so every reader here degrades to a
status string instead of raising.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple


def read_json(path: str) -> Tuple[Optional[object], str]:
    """Return ``(data, status)`` with status ``ok``, ``missing`` or ``unreadable``."""
    if not os.path.exists(path):
        return None, "missing"
    try:
        with open(path) as handle:
            return json.load(handle), "ok"
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, "unreadable"


def load_ground_truth(path: str) -> Tuple[List[dict], str]:
    """Load blind annotations from either the wrapped or bare list format."""
    data, status = read_json(path)
    if status != "ok":
        return [], status
    if isinstance(data, dict):
        annotations = data.get("annotations", [])
    elif isinstance(data, list):
        annotations = data
    else:
        annotations = []
    return [item for item in annotations if isinstance(item, dict)], "ok"
