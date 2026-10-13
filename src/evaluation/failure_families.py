"""Group failures that are really the same problem.

The evaluation plan uses one relation in three places, so it is defined once
here and read everywhere:

* eligibility excludes duplicate instances of the same causal failure family;
* a family must never be split across the development, pilot and held-out
  partitions, or the held-out set is contaminated by something the system was
  tuned on;
* repository assessment reports how many distinct families a history can supply,
  which is a better measure of what a repository contributes than a raw count of
  failed runs.

Three grouping rules are provided rather than one. Which relation counts as
"the same problem" is a methodological choice with consequences for how many
cases survive triage, so the rule is a parameter and the choice is recorded in
the manifest rather than hidden in the code.
"""

from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

# Available grouping rules.
#
#   fix        two failures repaired by the same revision are the same problem.
#              Strongest evidence, but only available where history records a
#              repair, so unrepaired failures all fall back to singletons.
#   signature  two failures whose normalised error lines hash alike are the same
#              problem. Always available, but strict: anything varying between
#              runs that normalisation misses -- paths, shard numbers, durations
#              -- separates two instances of one fault.
#   job_step   the same job failing at the same step in the same repository,
#              AND with a matching error signature. The conjunction is
#              deliberate: inspecting gradle/gradle showed that one "Sanity
#              Check on Linux" job runs binary-compatibility checks, checkstyle,
#              detekt and architecture tests, so the job name alone merged four
#              distinct faults. Requiring the signature too keeps a genuine
#              repeat together without collapsing an umbrella job.
#   combined   any of the above relations groups them, applied transitively.
RULES = ("fix", "signature", "job_step", "combined")

# Cases carrying one of these keys are grouped by it before anything else: a
# controlled defect's identity is its template, not whatever its log happens to
# look like.
TEMPLATE_KEYS = ("controlled_defect_template", "seed_reference")


@dataclass
class Family:
    family_id: str
    case_ids: List[str] = field(default_factory=list)
    basis: str = ""

    @property
    def size(self) -> int:
        return len(self.case_ids)

    def to_dict(self) -> dict:
        return {"family_id": self.family_id, "basis": self.basis, "size": self.size, "case_ids": self.case_ids}


def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _template_key(case: dict) -> Optional[str]:
    for key in TEMPLATE_KEYS:
        value = case.get(key)
        if value:
            return f"template:{value}"
    return None


def _fix_key(case: dict) -> Optional[str]:
    """A repair identifies a family only when the repository records one."""
    for key in ("fixing_revision", "fixing_reference", "repair_reference"):
        value = case.get(key)
        if value:
            return f"fix:{case.get('repository', '')}:{value}"
    return None


def _job_step_key(case: dict) -> Optional[str]:
    """A recurring failure of one job, at one step, with the same error.

    All three must match. An umbrella job such as gradle's "Sanity Check on
    Linux" runs many unrelated checks, so the job and step alone would merge
    faults that have nothing to do with each other.
    """
    job = (case.get("failing_job") or "").strip()
    step = (case.get("failing_step") or "").strip()
    signature = (case.get("error_signature") or "").strip()
    if not signature or not (job or step):
        return None
    return f"jobstep:{case.get('repository', '')}:{job}:{step}:{signature}"


def _signature_key(case: dict) -> Optional[str]:
    value = case.get("error_signature")
    if not value:
        return None
    # Scoped by repository: the same normalised error text in two projects is
    # not evidence of one shared fault.
    return f"sig:{case.get('repository', '')}:{value}"


def _keys_for(case: dict, rule: str) -> List[str]:
    template = _template_key(case)
    if template:
        return [template]
    if rule == "fix":
        key = _fix_key(case)
    elif rule == "signature":
        key = _signature_key(case)
    elif rule == "job_step":
        key = _job_step_key(case)
    elif rule == "combined":
        return [key for key in (_fix_key(case), _signature_key(case), _job_step_key(case)) if key]
    else:
        raise ValueError(f"Unknown grouping rule: {rule!r}. Use one of {', '.join(RULES)}.")
    return [key] if key else []


def assign_families(cases: Sequence[dict], rule: str = "combined") -> Dict[str, str]:
    """Map every case id to a family id under the chosen rule.

    ``combined`` is transitive: if case A shares a fixing revision with B and B
    shares an error signature with C, then A, B and C are one family. A case
    with no usable key becomes its own family rather than being dropped.
    """
    if rule not in RULES:
        raise ValueError(f"Unknown grouping rule: {rule!r}. Use one of {', '.join(RULES)}.")

    # Union-find over the keys each case carries.
    parent: Dict[str, str] = {}

    def find(item: str) -> str:
        while parent.setdefault(item, item) != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for case in cases:
        case_id = case.get("log_id")
        if not case_id:
            continue
        node = f"case:{case_id}"
        find(node)
        for key in _keys_for(case, rule):
            union(node, key)

    # Name each family after the lowest case id it contains, so the identifier
    # is stable across runs rather than depending on iteration order.
    members: Dict[str, List[str]] = collections.defaultdict(list)
    for case in cases:
        case_id = case.get("log_id")
        if case_id:
            members[find(f"case:{case_id}")].append(case_id)

    assignment: Dict[str, str] = {}
    for case_ids in members.values():
        family_id = f"fam_{_short(min(case_ids))}"
        for case_id in case_ids:
            assignment[case_id] = family_id
    return assignment


def build_families(cases: Sequence[dict], rule: str = "combined") -> List[Family]:
    assignment = assign_families(cases, rule)
    grouped: Dict[str, List[str]] = collections.defaultdict(list)
    for case_id, family_id in assignment.items():
        grouped[family_id].append(case_id)

    by_id = {case["log_id"]: case for case in cases if case.get("log_id")}
    families = []
    for family_id, case_ids in grouped.items():
        ordered = sorted(case_ids)
        sample = by_id.get(ordered[0], {})
        if _template_key(sample):
            basis = "controlled-defect template"
        elif _fix_key(sample) and rule == "combined":
            basis = "shared repair"
        elif _fix_key(sample) and rule == "fix":
            basis = "shared repair"
        elif _signature_key(sample) and rule in ("signature", "combined"):
            basis = "shared error signature"
        elif _job_step_key(sample) and rule in ("job_step", "combined"):
            basis = "recurring job and step"
        else:
            basis = "singleton"
        families.append(Family(family_id=family_id, case_ids=ordered, basis=basis))
    return sorted(families, key=lambda item: (-item.size, item.family_id))


def family_report(cases: Sequence[dict], rule: str = "combined") -> dict:
    """Summarise what a grouping rule does to a set of cases."""
    families = build_families(cases, rule)
    sizes = [family.size for family in families]
    duplicates = sum(size - 1 for size in sizes)
    return {
        "rule": rule,
        "cases": len(sizes) and sum(sizes) or 0,
        "families": len(families),
        "singletons": sum(1 for size in sizes if size == 1),
        "largest_family": max(sizes) if sizes else 0,
        "duplicate_cases": duplicates,
        "basis_counts": dict(collections.Counter(family.basis for family in families)),
        "families_detail": [family.to_dict() for family in families],
    }


def compare_rules(cases: Sequence[dict], rules: Iterable[str] = RULES) -> List[dict]:
    """Run every rule over the same cases so the choice can be made on evidence."""
    summaries = []
    for rule in rules:
        report = family_report(cases, rule)
        report.pop("families_detail", None)
        summaries.append(report)
    return summaries


def select_representatives(cases: Sequence[dict], rule: str = "combined") -> Dict[str, List[str]]:
    """Split case ids into the one kept per family and the duplicates dropped.

    The earliest case id in a family is kept, so the choice does not depend on
    collection order and the same cohort always yields the same survivors.
    """
    kept, dropped = [], []
    for family in build_families(cases, rule):
        kept.append(family.case_ids[0])
        dropped.extend(family.case_ids[1:])
    return {"kept": sorted(kept), "dropped": sorted(dropped)}


def check_no_family_spans_partitions(partitions: Dict[str, Sequence[str]], assignment: Dict[str, str]) -> List[dict]:
    """Return every family that appears in more than one partition.

    An empty list is the only acceptable result before a held-out run: a family
    straddling development and held-out means the system was tuned on the same
    underlying fault it is then tested against.
    """
    seen: Dict[str, Dict[str, List[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for partition, case_ids in partitions.items():
        for case_id in case_ids:
            family_id = assignment.get(case_id)
            if family_id:
                seen[family_id][partition].append(case_id)
    return [
        {"family_id": family_id, "partitions": {name: sorted(ids) for name, ids in spread.items()}}
        for family_id, spread in sorted(seen.items())
        if len(spread) > 1
    ]
