"""Keep exploratory cases out of the held-out evaluation.

The kickoff meeting requires development and pilot cases to be separated from
the final test set (decision D4). The smoke cohort already records that
requirement in its manifest -- ``usable_as_final_thesis_evidence: false`` and
``exclude_from_future_held_out_evaluation: true`` -- but nothing enforced it,
so a final run over the source cohort would silently re-score cases the
researcher has already read.

This module finds every cohort that declares itself exploratory and reports the
overlap with a run's input, so the benchmark can refuse instead of producing
contaminated evidence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Manifests that can mark a set of cases as unusable for final claims. Each is
# read defensively: an unreadable manifest is reported, never silently skipped.
MANIFEST_NAMES = ("smoke_manifest.json", "partition_manifest.json")

EXCLUSION_FLAGS = ("exclude_from_future_held_out_evaluation",)


@dataclass
class ExcludedCase:
    """One case a cohort has declared off-limits for final evaluation."""

    case_id: str
    cohort_id: str
    manifest_path: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "cohort_id": self.cohort_id,
            "manifest_path": self.manifest_path,
            "reason": self.reason,
        }


def _same_file(first: Optional[str], second: Optional[str]) -> bool:
    if not first or not second:
        return False
    return os.path.realpath(first) == os.path.realpath(second)


def load_exclusions(
    studies_root: str = "data/studies",
    current_input: Optional[str] = None,
) -> Tuple[Dict[str, ExcludedCase], List[str]]:
    """Collect every case id declared exploratory, plus any manifest problems.

    A manifest describing the run's own input is skipped: running the smoke
    cohort against its own cases is the point of that cohort, and only a
    *different* run inheriting them is contamination.
    """
    excluded: Dict[str, ExcludedCase] = {}
    problems: List[str] = []
    if not os.path.isdir(studies_root):
        return excluded, problems

    for study in sorted(os.listdir(studies_root)):
        for manifest_name in MANIFEST_NAMES:
            manifest_path = os.path.join(studies_root, study, manifest_name)
            if not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path) as handle:
                    manifest = json.load(handle)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                problems.append(
                    f"{manifest_path} could not be read ({exc.__class__.__name__}); exclusions may be incomplete."
                )
                continue
            if not isinstance(manifest, dict):
                problems.append(f"{manifest_path} is not a JSON object; exclusions may be incomplete.")
                continue
            if not any(manifest.get(flag) for flag in EXCLUSION_FLAGS):
                continue

            output = manifest.get("output")
            output_file = output.get("file") if isinstance(output, dict) else None
            if _same_file(output_file, current_input):
                continue

            cohort_id = manifest.get("cohort_id", study)
            reason = manifest.get("purpose", "declared exploratory")
            for case in manifest.get("selected_cases", []):
                case_id = case.get("log_id") if isinstance(case, dict) else None
                if case_id:
                    excluded[case_id] = ExcludedCase(
                        case_id=case_id,
                        cohort_id=cohort_id,
                        manifest_path=manifest_path,
                        reason=reason,
                    )
    return excluded, problems


def find_overlap(logs: List[dict], excluded: Dict[str, ExcludedCase]) -> List[ExcludedCase]:
    """Return the excluded cases that appear in this run's input, in input order."""
    hits = []
    for log in logs:
        case_id = log.get("log_id")
        if case_id and case_id in excluded:
            hits.append(excluded[case_id])
    return hits


def describe_overlap(hits: List[ExcludedCase]) -> str:
    """Human-readable refusal text naming every contaminating case."""
    lines = [
        f"{len(hits)} case(s) in this input were already used by an exploratory cohort",
        "and are excluded from held-out evaluation:",
    ]
    for hit in hits:
        lines.append(f"  - {hit.case_id}  (from {hit.cohort_id}: {hit.reason})")
    lines.append("")
    lines.append("Build a final cohort that excludes these cases, or pass")
    lines.append("--allow-excluded-cases with a written justification if this run is not")
    lines.append("thesis evidence.")
    return "\n".join(lines)
