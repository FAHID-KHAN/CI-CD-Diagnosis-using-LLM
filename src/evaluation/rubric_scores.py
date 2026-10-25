"""Rubric scores for root causes and suggested fixes, and what they say.

Category accuracy and evidence-line F1 are computed mechanically. Whether a
model's *explanation* is right cannot be, so a human scores every root cause and
every suggested fix on a 0/1/2 rubric, blind to the model, with
``automated_scripts/score_root_cause.py``. This module holds the rubric and
turns the stored scores into results. It is read-only over
``root_cause_scores.json`` and never writes to ground truth.

The root-cause wording is the supervisors' (``SUPERVISOR_CONDITIONS.md`` §3),
verbatim. The longer guidance under each score is the scorer's aid for applying
it consistently and does not change what a score means.

These are secondary metrics. Category and evidence-line accuracy remain the
primary measurement because they need no judgement at scoring time.
"""

from __future__ import annotations

import os
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats

from src.evaluation.study_io import read_json

SCORES_FILE = "root_cause_scores.json"
SCHEMA_VERSION = 2
SCALE = (0, 1, 2)

# Supervisor wording, adopted 6 October 2026. Do not paraphrase.
ROOT_CAUSE_RUBRIC = {
    "0": ("Incorrect", "The predicted root cause is incorrect."),
    "1": (
        "Partial",
        "The prediction is partially correct but incomplete, too general, or insufficiently supported.",
    ),
    "2": (
        "Correct",
        "The root cause is correct and supported by relevant evidence from the logs or other available artefacts.",
    ),
}

ROOT_CAUSE_GUIDANCE = {
    "0": "Wrong cause, only a restated symptom, a materially unsupported claim, or no cause given.",
    "1": "Relevant mechanism or component, but imprecise, partly symptom-focused or thinly supported.",
    "2": "Names the causal mechanism and affected component and agrees with the verified record.",
}

# The fix is judged against the verified cause and, where the case has one, the
# documented repair. A fix can be right without matching the repair line for
# line; it has to address the same cause.
FIX_RUBRIC = {
    "0": (
        "Incorrect",
        "The suggested fix would not resolve the verified root cause, or is irrelevant to it.",
    ),
    "1": (
        "Partial",
        "The suggested fix points in the right direction but is generic, incomplete, or treats a symptom.",
    ),
    "2": (
        "Correct",
        "The suggested fix would resolve the verified root cause and is consistent with the documented "
        "repair where one exists.",
    ),
}

FIX_GUIDANCE = {
    "0": "Addresses a different problem, or offers nothing actionable.",
    "1": "E.g. 're-run the job', 'check the failing test', or one of several needed changes.",
    "2": "A developer following it would make the change that fixed, or would fix, this failure.",
}

# Asked alongside the scores because overlap metrics cannot say whether the cited
# lines genuinely support the diagnosis (supervisor requirement R8).
EVIDENCE_SUPPORT = {
    "y": "supports",
    "n": "does not support",
    "p": "partly supports",
    "x": "no lines cited",
}
NOT_ASSESSED = "not assessed"

# A response that states no cause and no fix is scored 0 without being shown.
# Putting it in the blind queue would reveal its condition -- only the baseline
# answers that way -- and there is nothing to judge.
AUTO_REASON_EMPTY = "no root cause or fix offered"

# Ground truth whose label rests on an artefact the project produced, rather
# than on the annotator's reading alone.
REPAIR_ANCHORED = frozenset({"historical_fix", "seeded_defect"})

SCORE_FIELDS = ("root_cause_score", "fix_score")


def is_empty_response(root_cause: Optional[str], suggested_fix: Optional[str]) -> bool:
    return not (root_cause or "").strip() and not (suggested_fix or "").strip()


def auto_score_entry(response_id: str, log_id: str, model: str, scored_at: str) -> dict:
    return {
        "response_id": response_id,
        "log_id": log_id,
        "model": model,
        "root_cause_score": 0,
        "fix_score": 0,
        "evidence_support": NOT_ASSESSED,
        "note": "",
        "auto": True,
        "auto_reason": AUTO_REASON_EMPTY,
        "scored_at": scored_at,
    }


def validate_payload(payload: object) -> List[str]:
    """Problems that would make a scores file unsafe to analyse."""
    if not isinstance(payload, dict):
        return ["scores file is not a JSON object"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        return [
            f"scores file has schema_version {payload.get('schema_version')!r}; expected {SCHEMA_VERSION} "
            "(version 1 recorded no fix score)"
        ]
    problems = []
    seen = set()
    for index, entry in enumerate(payload.get("scores", [])):
        rid = entry.get("response_id")
        if rid in seen:
            problems.append(f"response {rid} is scored twice")
        seen.add(rid)
        for name in SCORE_FIELDS:
            if entry.get(name) not in SCALE:
                problems.append(f"entry {index} ({rid}) has {name}={entry.get(name)!r}, not one of {SCALE}")
    return problems


def load_scores(experiment_path: str) -> Tuple[Optional[dict], str]:
    """Read an experiment's scores file. Status is ok, missing, unreadable or invalid."""
    payload, status = read_json(os.path.join(experiment_path, SCORES_FILE))
    if status != "ok":
        return None, status
    if not isinstance(payload, dict) or validate_payload(payload):
        return None, "invalid"
    return payload, "ok"


# ── Agreement ─────────────────────────────────────────────────────────────


def weighted_kappa(
    first: Sequence[int],
    second: Sequence[int],
    categories: Sequence[int] = SCALE,
    weights: str = "linear",
) -> Optional[float]:
    """Cohen's weighted kappa for two ratings of the same items.

    Linear weights by default: on an ordinal 0/1/2 scale a 0-versus-2
    disagreement is twice as serious as a 0-versus-1. ``weights="none"`` gives
    unweighted Cohen's kappa, which is what a nominal label such as the failure
    category needs. Returns None when kappa is undefined: no items, or both
    ratings constant on the same value, where agreement is perfect but chance
    agreement is too.
    """
    if len(first) != len(second):
        raise ValueError("Both rating lists must have the same length")
    if not first:
        return None
    index = {value: position for position, value in enumerate(categories)}
    k = len(categories)
    observed = np.zeros((k, k))
    for a, b in zip(first, second):
        observed[index[a], index[b]] += 1
    observed /= observed.sum()
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0))

    grid = np.abs(np.subtract.outer(np.arange(k), np.arange(k))).astype(float)
    if weights == "linear":
        disagreement = grid / (k - 1)
    elif weights == "quadratic":
        disagreement = (grid / (k - 1)) ** 2
    elif weights == "none":
        disagreement = (grid > 0).astype(float)
    else:
        raise ValueError(f"Unknown weighting: {weights}")

    chance = float((disagreement * expected).sum())
    if chance == 0.0:
        return None
    return 1.0 - float((disagreement * observed).sum()) / chance


def intra_rater_agreement(payload: dict) -> dict:
    """Agreement between each response's first score and its blind re-score.

    Reported as the scorer's self-consistency, never as inter-rater agreement:
    the same person scored both times.
    """
    first = {entry["response_id"]: entry for entry in payload.get("scores", []) if not entry.get("auto")}
    pairs = [(first[r["response_id"]], r) for r in payload.get("rescores", []) if r["response_id"] in first]
    result: Dict[str, object] = {"rescored": len(pairs)}
    for name in SCORE_FIELDS:
        a = [original[name] for original, _ in pairs]
        b = [again[name] for _, again in pairs]
        result[name] = {
            "raw_agreement": (sum(1 for x, y in zip(a, b) if x == y) / len(pairs)) if pairs else None,
            "weighted_kappa_linear": weighted_kappa(a, b),
        }
    return result


# ── Results ───────────────────────────────────────────────────────────────


def _bootstrap_mean(values: Sequence[float], n_bootstrap: int = 2000, seed: int = 42) -> Optional[List[float]]:
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    data = np.asarray(values, dtype=float)
    means = rng.choice(data, size=(n_bootstrap, len(data)), replace=True).mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def describe(values: Sequence[int]) -> dict:
    """Distribution, mean and shares for one condition's scores on one field."""
    n = len(values)
    counts = {str(score): sum(1 for v in values if v == score) for score in SCALE}
    correct = [1.0 if v == 2 else 0.0 for v in values]
    at_least_partial = [1.0 if v >= 1 else 0.0 for v in values]
    return {
        "n": n,
        "counts": counts,
        "mean": (sum(values) / n) if n else None,
        "mean_ci95": _bootstrap_mean(list(values)),
        "share_correct": (sum(correct) / n) if n else None,
        "share_correct_ci95": _bootstrap_mean(correct),
        "share_at_least_partial": (sum(at_least_partial) / n) if n else None,
    }


def _anchor_of(truth: Optional[dict]) -> str:
    method = (truth or {}).get("evidence_method")
    return "repair_anchored" if method in REPAIR_ANCHORED else "judgement_only"


def holm_adjust(p_values: Sequence[float]) -> List[float]:
    """Holm-Bonferroni step-down adjustment, returned in the input order."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def paired_score_test(scores_a: Dict[str, int], scores_b: Dict[str, int]) -> dict:
    """Wilcoxon signed-rank over cases both conditions were scored on.

    Ties carry no information and are dropped by the test, as they are for the
    evidence-line test. Fewer than two shared cases, or no case where the
    conditions differ, yields no p-value rather than a misleading one.
    """
    shared = sorted(set(scores_a) & set(scores_b))
    a = [scores_a[log_id] for log_id in shared]
    b = [scores_b[log_id] for log_id in shared]
    a_better = sum(1 for x, y in zip(a, b) if x > y)
    b_better = sum(1 for x, y in zip(a, b) if y > x)
    result: Dict[str, object] = {
        "paired_cases": len(shared),
        "a_better": a_better,
        "b_better": b_better,
        "ties": len(shared) - a_better - b_better,
        "mean_a": (sum(a) / len(a)) if a else None,
        "mean_b": (sum(b) / len(b)) if b else None,
        "p_value": None,
    }
    if len(shared) < 2:
        result["verdict"] = "Too few paired cases for a test"
    elif a_better + b_better == 0:
        result["verdict"] = "Identical scores on every case"
    else:
        test = stats.wilcoxon(a, b)
        result["statistic"] = float(test.statistic)
        result["p_value"] = float(test.pvalue)
    return result


def _per_model(entries: Iterable[dict], name: str) -> Dict[str, Dict[str, int]]:
    by_model: Dict[str, Dict[str, int]] = {}
    for entry in entries:
        by_model.setdefault(entry["model"], {})[entry["log_id"]] = entry[name]
    return by_model


def summarize_scores(
    payload: dict,
    ground_truth: Optional[Dict[str, dict]] = None,
    order: Sequence[str] = (),
) -> dict:
    """Everything the thesis reports from one scores file.

    A condition whose every response was auto-scored offered no explanation at
    all, so it is described but left out of the paired tests: comparing a model
    against a column of structural zeros says nothing about the model.
    """
    ground_truth = ground_truth or {}
    entries = payload.get("scores", [])
    present = {entry["model"] for entry in entries}
    # The report's condition order first, so tables line up with the rest of it.
    models = [model for model in order if model in present] + sorted(present - set(order))

    conditions: Dict[str, dict] = {}
    for model in models:
        own = [entry for entry in entries if entry["model"] == model]
        support: Dict[str, int] = {}
        for entry in own:
            support[entry["evidence_support"]] = support.get(entry["evidence_support"], 0) + 1
        strata: Dict[str, dict] = {}
        for anchor in ("repair_anchored", "judgement_only"):
            subset = [entry for entry in own if _anchor_of(ground_truth.get(entry["log_id"])) == anchor]
            strata[anchor] = {name: describe([entry[name] for entry in subset]) for name in SCORE_FIELDS}
        conditions[model] = {
            "scored": len(own),
            "auto_scored": sum(1 for entry in own if entry.get("auto")),
            **{name: describe([entry[name] for entry in own]) for name in SCORE_FIELDS},
            "evidence_support": support,
            "by_ground_truth_anchor": strata,
        }

    explained = [model for model in models if conditions[model]["auto_scored"] < conditions[model]["scored"]]
    comparisons = []
    for model_a, model_b in combinations(explained, 2):
        tests = {}
        for name in SCORE_FIELDS:
            per_model = _per_model(entries, name)
            tests[name] = paired_score_test(per_model.get(model_a, {}), per_model.get(model_b, {}))
        # Two tests over the same cases: correct for it rather than report two
        # unadjusted p-values.
        tested = [name for name in SCORE_FIELDS if tests[name]["p_value"] is not None]
        for name, adjusted in zip(tested, holm_adjust([tests[name]["p_value"] for name in tested])):
            tests[name]["p_value_holm"] = adjusted
            tests[name]["significant_at_005"] = adjusted < 0.05
        comparisons.append({"model_a": model_a, "model_b": model_b, **tests})

    return {
        "scorer": payload.get("scorer"),
        "seed": payload.get("seed"),
        "conditions": conditions,
        "comparisons": comparisons,
        "not_compared": [model for model in models if model not in explained],
        "intra_rater": intra_rater_agreement(payload),
    }
