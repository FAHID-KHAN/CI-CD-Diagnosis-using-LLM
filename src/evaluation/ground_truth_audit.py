"""Audit ground truth against the evidence requirements agreed at the kickoff.

Decision D3 rules out the researcher's unaided judgement as the sole basis for
accuracy claims: a case needs evidence -- a documented historical fix, a
recorded seeded defect, or an independent expert -- and an independent verifier.
Decision D5 needs usable per-category labels, and the roadmap's metric list
needs supporting line numbers and a real root-cause statement.

The annotation tool records some of that and leaves the rest empty, so this
module states, per record and per file, exactly which requirements are met. It
reports; it never rewrites an annotation.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.evaluation.study_io import load_ground_truth
from src.evaluation.taxonomy import ERROR_TYPE_ORDER

# Evidence methods from the roadmap's ground-truth hierarchy, strongest first.
EVIDENCE_METHODS = ("historical_fix", "seeded_defect", "expert_review", "combined_adjudicated")

# A root cause has to be a statement. Anything shorter is a placeholder, and a
# bare number is the category-menu digit typed one prompt too late.
MIN_ROOT_CAUSE_CHARS = 25

# Words that carry no diagnostic content when deciding whether a root cause says
# anything beyond the category name it was filed under.
STOPWORDS = frozenset(
    "the a an of on in for from to is was were and or at by with this that it its "
    "as be been has have had not no when while during".split()
)

# A root cause that reduces to fewer than this many content words, once the
# category's own words are removed, is a restatement rather than an explanation.
MIN_CONTENT_WORDS = 3

# Phrases that record unresolved uncertainty. Honest, but a case labelled this
# way cannot score a model, so it belongs in notes or out of the cohort.
UNCERTAINTY_PHRASES = (
    "no idea",
    "not sure",
    "unsure",
    "unclear",
    "dont know",
    "don't know",
    "cannot tell",
    "can't tell",
    "could not determine",
)

SEVERITY_ORDER = {"blocking": 0, "warning": 1}


@dataclass
class Finding:
    """One unmet requirement, on one record or on the file as a whole."""

    code: str
    severity: str
    message: str
    case_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "case_id": self.case_id,
        }


@dataclass
class GroundTruthAudit:
    """Everything the audit can say about one ground-truth file."""

    path: str
    exists: bool
    case_count: int = 0
    annotators: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    evidence_methods: Dict[str, int] = field(default_factory=dict)
    verified_cases: int = 0
    usable_root_causes: int = 0
    cases_with_lines: int = 0

    @property
    def blocking(self) -> List[Finding]:
        return [finding for finding in self.findings if finding.severity == "blocking"]

    @property
    def is_defensible(self) -> bool:
        """True when nothing blocks using this file for accuracy claims."""
        return self.exists and self.case_count > 0 and not self.blocking

    def summary_lines(self) -> List[str]:
        """One line per distinct finding code, worst first, with case counts."""
        grouped: Dict[str, List[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.code, []).append(finding)
        lines = []
        for code, findings in sorted(
            grouped.items(), key=lambda item: (SEVERITY_ORDER.get(item[1][0].severity, 9), item[0])
        ):
            head = findings[0]
            cases = [finding.case_id for finding in findings if finding.case_id]
            scope = f" ({len(cases)} case(s))" if cases else ""
            lines.append(f"[{head.severity}] {code}: {head.message}{scope}")
        return lines

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "exists": self.exists,
            "case_count": self.case_count,
            "annotators": self.annotators,
            "evidence_methods": self.evidence_methods,
            "verified_cases": self.verified_cases,
            "usable_root_causes": self.usable_root_causes,
            "cases_with_lines": self.cases_with_lines,
            "is_defensible": self.is_defensible,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def restates_category(text: str, category: object) -> bool:
    """True when a root cause is essentially the category name written again.

    ``"build configuration issue"`` filed under ``build_configuration`` adds
    nothing a second reviewer could adjudicate against, but it clears a length
    floor, so length alone cannot catch it.
    """
    if not isinstance(category, str):
        return False
    category_words = set(re.findall(r"[a-z]+", category.lower()))
    words = [word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2]
    content = [word for word in words if word not in category_words and word not in STOPWORDS]
    return len(content) < MIN_CONTENT_WORDS


def records_uncertainty(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in UNCERTAINTY_PHRASES)


def root_cause_problem(value: object) -> Optional[str]:
    """Explain why a root-cause field is unusable, or return None if it is fine."""
    if not isinstance(value, str) or not value.strip():
        return "is empty"
    text = value.strip()
    if re.fullmatch(r"\d+", text):
        return f"is the bare number {text!r}, which is the error-type menu index rather " "than a root-cause statement"
    if text in ERROR_TYPE_ORDER:
        return f"repeats the category name {text!r} instead of explaining the cause"
    if len(text) < MIN_ROOT_CAUSE_CHARS:
        return f"is only {len(text)} characters, too short to state a cause"
    return None


def audit_annotations(annotations: List[dict], path: str = "", exists: bool = True) -> GroundTruthAudit:
    """Check a list of annotation records against the agreed requirements."""
    audit = GroundTruthAudit(path=path, exists=exists, case_count=len(annotations))
    if not annotations:
        if exists:
            audit.findings.append(
                Finding("empty_ground_truth", "blocking", "The ground-truth file contains no annotations.")
            )
        return audit

    annotators = []
    for record in annotations:
        case_id = record.get("log_id")

        root_cause = record.get("actual_root_cause")
        problem = root_cause_problem(root_cause)
        if problem:
            audit.findings.append(
                Finding(
                    "unusable_root_cause",
                    "blocking",
                    f"The recorded root cause {problem}.",
                    case_id,
                )
            )
        elif restates_category(str(root_cause), record.get("actual_error_type")):
            audit.findings.append(
                Finding(
                    "root_cause_restates_category",
                    "blocking",
                    f"The root cause {str(root_cause)!r} only repeats its category in other words, "
                    "so it states nothing a second reviewer could adjudicate against.",
                    case_id,
                )
            )
        elif records_uncertainty(str(root_cause)):
            audit.usable_root_causes += 1
            audit.findings.append(
                Finding(
                    "unresolved_root_cause",
                    "warning",
                    f"The root cause {str(root_cause)!r} records unresolved uncertainty. Honest, but a "
                    "model cannot be scored against it — flag it in notes, or exclude the case.",
                    case_id,
                )
            )
        else:
            audit.usable_root_causes += 1

        error_type = record.get("actual_error_type")
        if error_type not in ERROR_TYPE_ORDER:
            audit.findings.append(
                Finding("unknown_category", "blocking", f"Category {error_type!r} is not in the taxonomy.", case_id)
            )

        lines = record.get("failure_lines") or []
        if lines:
            audit.cases_with_lines += 1
        else:
            audit.findings.append(
                Finding(
                    "no_supporting_lines",
                    "warning",
                    "No supporting log lines were recorded, so evidence-line metrics cannot score this case.",
                    case_id,
                )
            )

        method = record.get("evidence_method")
        if method in EVIDENCE_METHODS:
            audit.evidence_methods[method] = audit.evidence_methods.get(method, 0) + 1
            if method == "historical_fix" and not record.get("fixing_reference"):
                audit.findings.append(
                    Finding(
                        "missing_fix_reference",
                        "blocking",
                        "Evidence method is historical_fix but no fixing commit, pull request or issue is recorded.",
                        case_id,
                    )
                )
            if method == "seeded_defect" and not record.get("seed_reference"):
                audit.findings.append(
                    Finding(
                        "missing_seed_reference",
                        "blocking",
                        "Evidence method is seeded_defect but no defect-seed identifier is recorded.",
                        case_id,
                    )
                )
        else:
            audit.findings.append(
                Finding(
                    "no_evidence_method",
                    "blocking",
                    "The case records a human judgement with no linked evidence "
                    f"(expected one of: {', '.join(EVIDENCE_METHODS)}).",
                    case_id,
                )
            )

        verifier = record.get("verifier")
        annotator = record.get("annotator")
        if verifier and verifier != annotator:
            audit.verified_cases += 1
        else:
            audit.findings.append(
                Finding(
                    "no_independent_verification",
                    "blocking",
                    "No second reviewer distinct from the annotator has verified this case.",
                    case_id,
                )
            )
        if annotator and annotator not in annotators:
            annotators.append(annotator)

    audit.annotators = annotators
    # One annotator is only a problem where a second reviewer has not signed off:
    # independent verification of every case is exactly the mitigation D3 asks for.
    if len(annotators) == 1 and audit.verified_cases < audit.case_count:
        audit.findings.append(
            Finding(
                "single_annotator",
                "blocking",
                f"{audit.case_count - audit.verified_cases} case(s) rest on one annotator "
                f"({annotators[0]}) with no independent sign-off, so accuracy claims would rest "
                "on the researcher's own judgement.",
            )
        )
    return audit


def audit_ground_truth_file(path: str) -> GroundTruthAudit:
    """Load and audit one ground-truth file, tolerating a missing or bad file."""
    if not path or not os.path.exists(path):
        audit = GroundTruthAudit(path=path or "", exists=False)
        audit.findings.append(
            Finding("missing_ground_truth", "blocking", "No ground-truth file was found for this experiment.")
        )
        return audit
    annotations, status = load_ground_truth(path)
    if status != "ok":
        audit = GroundTruthAudit(path=path, exists=True)
        audit.findings.append(Finding("unreadable_ground_truth", "blocking", f"The ground-truth file is {status}."))
        return audit
    return audit_annotations(annotations, path=path)
