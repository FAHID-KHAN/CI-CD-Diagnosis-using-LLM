#!/usr/bin/env python3
"""Score model root causes against the verified record, blind to the model.

The evaluation plan scores root-cause identification separately from the
category label, using a 0/1/2 rubric. Two properties protect the scoring:

* **Blind.** The scorer never sees which model produced a response, nor its
  confidence, latency or cost. Knowing the condition would let an expectation
  about hosted-versus-local performance leak into the score.
* **Randomly ordered.** Responses from both conditions are interleaved with a
  recorded seed, so a scorer cannot infer the condition from position, and
  cannot drift systematically through one model's answers in sequence.

Scores are written to their own file and never merged into ground truth, so the
record of what was true stays separate from the record of how a model did.

    python automated_scripts/score_root_cause.py --experiment <dir> --scorer <id>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json
from src.evaluation.report_comparison import load_experiment

SCORES = {
    "2": (
        "Correct",
        "Identifies the causal mechanism and affected component, agrees with the "
        "verified record, is supported by relevant evidence and contains no material "
        "contradiction",
    ),
    "1": (
        "Partial",
        "Identifies a relevant mechanism or component but is incomplete, too general, "
        "imprecise, partly symptom-focused or insufficiently supported",
    ),
    "0": (
        "Incorrect",
        "Gives the wrong cause, repeats only a symptom, makes a materially "
        "unsupported claim or abstains when the cause is known",
    ),
}

# The plan also asks whether cited lines genuinely support the diagnosis, which
# overlap metrics cannot answer.
EVIDENCE_SUPPORT = {
    "y": "supports",
    "n": "does not support",
    "p": "partly supports",
    "x": "no lines cited",
}

SCORES_FILE = "root_cause_scores.json"


def build_queue(report, seed: int) -> List[dict]:
    """Interleave every condition's responses into one de-identified queue."""
    items = []
    for model in report.model_labels:
        for log_id in report.log_order:
            outcome = report.outcome(model, log_id)
            truth = report.ground_truth.get(log_id)
            if outcome is None or truth is None or outcome.status != "success":
                continue
            items.append(
                {
                    "response_id": f"{log_id}::{model}",
                    "log_id": log_id,
                    "model": model,
                    "repository": report.log_info.get(log_id, {}).get("repository", ""),
                    "verified_category": truth.get("actual_error_type"),
                    "verified_cause": truth.get("actual_root_cause", ""),
                    "verified_lines": truth.get("failure_lines", []),
                    "response_cause": outcome.root_cause,
                    "response_fix": outcome.suggested_fix,
                    "response_lines": outcome.failure_lines,
                }
            )
    random.Random(seed).shuffle(items)
    return items


def prompt_choice(label: str, options: Dict[str, tuple]) -> str:
    while True:
        value = input(f"{label}: ").strip().lower()
        if value == "q":
            raise KeyboardInterrupt
        if value in options:
            return value
        print(f"  Enter one of: {', '.join(options)} (or q to save and quit)")


def present(item: dict, index: int, total: int) -> None:
    print("\n" + "=" * 74)
    print(f"Response {index}/{total}   ({item['repository']})")
    print("=" * 74)
    print(f"\n  VERIFIED CATEGORY : {item['verified_category']}")
    print(f"  VERIFIED CAUSE    : {item['verified_cause']}")
    print(f"  VERIFIED LINES    : {', '.join(str(n) for n in item['verified_lines'][:20]) or 'none'}")
    print("\n  ---- response under review ----")
    print(f"  CAUSE : {item['response_cause']}")
    print(f"  FIX   : {item['response_fix']}")
    print(f"  LINES : {', '.join(str(n) for n in item['response_lines'][:20]) or 'none'}")
    print("\n  Rubric:")
    for key, (label, rule) in SCORES.items():
        print(f"    {key} = {label:<10}{rule[:88]}")


def parse_args():
    parser = argparse.ArgumentParser(description="Blind 0/1/2 scoring of model root causes")
    parser.add_argument("--experiment", required=True, help="Experiment directory holding results_<model>.json")
    parser.add_argument("--scorer", required=True, help="Stable scorer identifier")
    parser.add_argument("--seed", type=int, default=20261010, help="Recorded shuffle seed")
    parser.add_argument("--ground-truth", help="Override the ground-truth file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_experiment(args.experiment, args.ground_truth)
    if not report.model_labels:
        print(f"ERROR: No readable results in {args.experiment}")
        return 1

    output_path = Path(args.experiment) / SCORES_FILE
    if output_path.exists():
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if payload.get("scorer") != args.scorer:
            print("ERROR: Existing scores belong to a different scorer. Use a separate file per scorer.")
            return 1
        if payload.get("seed") != args.seed:
            print(f"ERROR: Existing scores used seed {payload.get('seed')}; the order would change.")
            return 1
    else:
        payload = {
            "schema_version": 1,
            "experiment": str(Path(args.experiment).resolve()),
            "scorer": args.scorer,
            "seed": args.seed,
            "rubric": {key: {"label": label, "rule": rule} for key, (label, rule) in SCORES.items()},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scores": [],
        }

    done = {entry["response_id"] for entry in payload["scores"]}
    queue = build_queue(report, args.seed)
    pending = [item for item in queue if item["response_id"] not in done]

    if not pending:
        print(f"All {len(queue)} responses already scored by {args.scorer}.")
        return 0
    print(f"{len(pending)} of {len(queue)} responses still to score.")
    print("The model behind each response is hidden and the order is shuffled.")

    for offset, item in enumerate(pending, 1):
        present(item, len(done) + offset, len(queue))
        try:
            score = prompt_choice("Root-cause score [2/1/0]", SCORES)
            support = prompt_choice("Do the cited lines support the diagnosis? [y/n/p/x]", EVIDENCE_SUPPORT)
            note = input("Note (optional): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaving progress.")
            atomic_write_json(output_path, payload)
            return 0

        payload["scores"].append(
            {
                "response_id": item["response_id"],
                "log_id": item["log_id"],
                # Recorded for analysis, never shown during scoring.
                "model": item["model"],
                "root_cause_score": int(score),
                "evidence_support": EVIDENCE_SUPPORT[support],
                "note": note,
                "scored_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(output_path, payload)
        done.add(item["response_id"])
        print(f"Saved {len(done)}/{len(queue)}.")

    print(f"\nScoring complete: {len(done)} responses in {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
