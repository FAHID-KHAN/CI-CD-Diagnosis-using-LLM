#!/usr/bin/env python3
"""Score model root causes and suggested fixes against the verified record, blind to the model.

The evaluation plan scores root-cause identification separately from the
category label, using the supervisors' 0/1/2 rubric, and scores the suggested
fix on a parallel 0/1/2 rubric. Both rubrics live in
``src/evaluation/rubric_scores.py``. Three properties protect the scoring:

* **Blind.** The scorer never sees which model produced a response, nor its
  confidence, latency or cost. Knowing the condition would let an expectation
  about hosted-versus-local performance leak into the score.
* **Randomly ordered.** Responses from every condition are interleaved with a
  recorded seed, so a scorer cannot infer the condition from position, and
  cannot drift systematically through one model's answers in sequence.
* **No giveaways.** A response with neither a cause nor a fix -- the baseline's,
  always -- is scored 0 automatically and never shown. In the queue it would
  identify its condition at a glance, and there is nothing in it to judge.

Scores are written to their own file and never merged into ground truth, so the
record of what was true stays separate from the record of how a model did.

``--rescore N`` re-presents a seeded sample of N already-scored responses, in a
fresh order and without their earlier scores, for the intra-rater
self-consistency check. Run it after a gap of one to two weeks.

    python automated_scripts/score_root_cause.py --experiment <dir> --scorer <id>
    python automated_scripts/score_root_cause.py --experiment <dir> --scorer <id> --rescore 20
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automated_scripts.study_utils import atomic_write_json
from src.evaluation.report_comparison import load_experiment
from src.evaluation.rubric_scores import (
    EVIDENCE_SUPPORT,
    FIX_GUIDANCE,
    FIX_RUBRIC,
    ROOT_CAUSE_GUIDANCE,
    ROOT_CAUSE_RUBRIC,
    SCHEMA_VERSION,
    SCORES_FILE,
    auto_score_entry,
    intra_rater_agreement,
    is_empty_response,
)

# Kept under the old name: the rubric the form presents for root causes.
SCORES = ROOT_CAUSE_RUBRIC

REFERENCE_FIELDS = ("fixing_reference", "seed_reference")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_responses(report, seed: int) -> Tuple[List[dict], List[dict]]:
    """Split every scorable response into the blind queue and the auto-scored set.

    The queue is interleaved across conditions and shuffled with ``seed``.
    """
    items = []
    automatic = []
    for model in report.model_labels:
        for log_id in report.log_order:
            outcome = report.outcome(model, log_id)
            truth = report.ground_truth.get(log_id)
            if outcome is None or truth is None or outcome.status != "success":
                continue
            response_id = f"{log_id}::{model}"
            if is_empty_response(outcome.root_cause, outcome.suggested_fix):
                automatic.append({"response_id": response_id, "log_id": log_id, "model": model})
                continue
            items.append(
                {
                    "response_id": response_id,
                    "log_id": log_id,
                    "model": model,
                    "repository": report.log_info.get(log_id, {}).get("repository", ""),
                    "verified_category": truth.get("actual_error_type"),
                    "verified_cause": truth.get("actual_root_cause", ""),
                    "verified_lines": truth.get("failure_lines", []),
                    "verified_repair": next((truth[f] for f in REFERENCE_FIELDS if truth.get(f)), ""),
                    "response_cause": outcome.root_cause,
                    "response_fix": outcome.suggested_fix,
                    "response_lines": outcome.failure_lines,
                }
            )
    random.Random(seed).shuffle(items)
    return items, automatic


def build_queue(report, seed: int) -> List[dict]:
    """Interleave every condition's responses into one de-identified queue."""
    return collect_responses(report, seed)[0]


def rescore_sample(queue: List[dict], scored_ids: set, already: set, size: int, seed: int) -> List[dict]:
    """A seeded sample of scored responses, in an order unrelated to the first pass."""
    eligible = [item for item in queue if item["response_id"] in scored_ids]
    # Offset the seed so the sample's order is not the first pass's order.
    rng = random.Random(seed + 1)
    sample = rng.sample(eligible, min(size, len(eligible)))
    return [item for item in sample if item["response_id"] not in already]


def prompt_choice(label: str, options: Dict[str, object]) -> str:
    while True:
        value = input(f"{label}: ").strip().lower()
        if value == "q":
            raise KeyboardInterrupt
        if value in options:
            return value
        print(f"  Enter one of: {', '.join(options)} (or q to save and quit)")


def _print_rubric(title: str, rubric: Dict[str, tuple], guidance: Dict[str, str]) -> None:
    print(f"\n  {title}:")
    for key in ("2", "1", "0"):
        label, rule = rubric[key]
        print(f"    {key} = {label:<10}{rule}")
        print(f"        {'':<10}{guidance[key]}")


def present(item: dict, index: int, total: int) -> None:
    print("\n" + "=" * 74)
    print(f"Response {index}/{total}   ({item['repository']})")
    print("=" * 74)
    print(f"\n  VERIFIED CATEGORY : {item['verified_category']}")
    print(f"  VERIFIED CAUSE    : {item['verified_cause']}")
    print(f"  VERIFIED LINES    : {', '.join(str(n) for n in item['verified_lines'][:20]) or 'none'}")
    print(f"  DOCUMENTED REPAIR : {item.get('verified_repair') or 'none recorded'}")
    print("\n  ---- response under review ----")
    print(f"  CAUSE : {item['response_cause'] or '(none given)'}")
    print(f"  FIX   : {item['response_fix'] or '(none given)'}")
    print(f"  LINES : {', '.join(str(n) for n in item['response_lines'][:20]) or 'none'}")
    _print_rubric("Root-cause rubric", ROOT_CAUSE_RUBRIC, ROOT_CAUSE_GUIDANCE)
    _print_rubric("Suggested-fix rubric", FIX_RUBRIC, FIX_GUIDANCE)


def ask_scores(item: dict) -> dict:
    """The three judgements for one response. A blank field scores 0 unasked."""
    if item["response_cause"].strip():
        cause = int(prompt_choice("Root-cause score [2/1/0]", ROOT_CAUSE_RUBRIC))
    else:
        print("Root-cause score: 0 (no cause given)")
        cause = 0
    if item["response_fix"].strip():
        fix = int(prompt_choice("Suggested-fix score [2/1/0]", FIX_RUBRIC))
    else:
        print("Suggested-fix score: 0 (no fix given)")
        fix = 0
    if item["response_lines"]:
        cited = {key: value for key, value in EVIDENCE_SUPPORT.items() if key != "x"}
        support = EVIDENCE_SUPPORT[prompt_choice("Do the cited lines support the diagnosis? [y/n/p]", cited)]
    else:
        support = EVIDENCE_SUPPORT["x"]
    note = input("Note (optional): ").strip()
    return {"root_cause_score": cause, "fix_score": fix, "evidence_support": support, "note": note}


def new_payload(experiment: str, scorer: str, seed: int) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": str(Path(experiment).resolve()),
        "scorer": scorer,
        "seed": seed,
        "rubric": {
            "root_cause": {key: {"label": label, "rule": rule} for key, (label, rule) in ROOT_CAUSE_RUBRIC.items()},
            "suggested_fix": {key: {"label": label, "rule": rule} for key, (label, rule) in FIX_RUBRIC.items()},
        },
        "created_at": _now(),
        "scores": [],
        "rescores": [],
    }


def check_existing(payload: dict, scorer: str, seed: int) -> str:
    """Why an existing scores file cannot be resumed, or an empty string."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        return (
            f"Existing scores use schema version {payload.get('schema_version')}, which recorded no fix score. "
            "Move the file aside and score again."
        )
    if payload.get("scorer") != scorer:
        return "Existing scores belong to a different scorer. Use a separate file per scorer."
    if payload.get("seed") != seed:
        return f"Existing scores used seed {payload.get('seed')}; the order would change."
    return ""


def add_automatic(payload: dict, automatic: List[dict]) -> int:
    done = {entry["response_id"] for entry in payload["scores"]}
    added = 0
    for item in automatic:
        if item["response_id"] not in done:
            payload["scores"].append(auto_score_entry(item["response_id"], item["log_id"], item["model"], _now()))
            added += 1
    return added


def run_session(payload: dict, pending: List[dict], output_path: Path, target: str, total: int) -> bool:
    """Score ``pending`` into ``payload[target]``, saving after each. False if the scorer quit."""
    done = len(payload[target])
    for offset, item in enumerate(pending, 1):
        present(item, done + offset, total)
        try:
            judged = ask_scores(item)
        except (KeyboardInterrupt, EOFError):
            print("\nSaving progress.")
            atomic_write_json(output_path, payload)
            return False
        payload[target].append(
            {
                "response_id": item["response_id"],
                "log_id": item["log_id"],
                # Recorded for analysis, never shown during scoring.
                "model": item["model"],
                **judged,
                "auto": False,
                "scored_at": _now(),
            }
        )
        payload["updated_at"] = _now()
        atomic_write_json(output_path, payload)
        print(f"Saved {done + offset}/{total}.")
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="Blind 0/1/2 scoring of model root causes and suggested fixes")
    parser.add_argument("--experiment", required=True, help="Experiment directory holding results_<model>.json")
    parser.add_argument("--scorer", required=True, help="Stable scorer identifier")
    parser.add_argument("--seed", type=int, default=20261010, help="Recorded shuffle seed")
    parser.add_argument("--ground-truth", help="Override the ground-truth file")
    parser.add_argument(
        "--rescore",
        type=int,
        metavar="N",
        help="Blindly re-score a seeded sample of N scored responses for the intra-rater check",
    )
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
        problem = check_existing(payload, args.scorer, args.seed)
        if problem:
            print(f"ERROR: {problem}")
            return 1
        payload.setdefault("rescores", [])
    else:
        payload = new_payload(args.experiment, args.scorer, args.seed)

    queue, automatic = collect_responses(report, args.seed)
    added = add_automatic(payload, automatic)
    if added:
        print(f"{added} responses offered no cause or fix and were scored 0 without being shown.")
        atomic_write_json(output_path, payload)

    if args.rescore:
        scored = {entry["response_id"] for entry in payload["scores"] if not entry.get("auto")}
        already = {entry["response_id"] for entry in payload["rescores"]}
        pending = rescore_sample(queue, scored, already, args.rescore, args.seed)
        total = len(already) + len(pending)
        if not pending:
            print(f"Re-scoring complete: {len(already)} responses.")
            print(json.dumps(intra_rater_agreement(payload), indent=2))
            return 0
        print(f"Re-scoring {len(pending)} responses. Earlier scores are not shown.")
        if run_session(payload, pending, output_path, "rescores", total):
            print(json.dumps(intra_rater_agreement(payload), indent=2))
        return 0

    done = {entry["response_id"] for entry in payload["scores"]}
    pending = [item for item in queue if item["response_id"] not in done]
    if not pending:
        print(f"All {len(queue)} shown responses already scored by {args.scorer}.")
        return 0
    print(f"{len(pending)} of {len(queue)} responses still to score.")
    print("The model behind each response is hidden and the order is shuffled.")
    if run_session(payload, pending, output_path, "scores", len(payload["scores"]) + len(pending)):
        print(f"\nScoring complete: {len(payload['scores'])} responses in {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
