"""A deterministic keyword-and-pattern classifier: the floor for comparison.

Without a baseline, an accuracy figure has nothing to be measured against. This
condition answers the question the LLM results otherwise leave open: does an
LLM-based system do better than fixed rules over the same logs?

Three properties keep the comparison honest:

* **Same input.** It receives the filtered log the models receive, so neither
  side sees evidence the other did not.
* **Same output shape.** It returns a category from the same taxonomy and the
  line numbers that triggered the match, so it is scored by the same code.
* **Frozen and hashed.** The ruleset carries a checksum recorded in the freeze
  package. Rules may be developed on development cases and revised after the
  pilot, but a ruleset changed after held-out results were seen would no longer
  match its recorded hash.

The default ruleset below is a starting point to be tuned on the development
partition, not a finished artefact. Patterns are matched case-insensitively and
the first category with any match wins, so the order of ``DEFAULT_RULES``
encodes precedence and is part of what the checksum covers.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from src.api.models import ErrorType

# Ordered: earlier categories win when a log matches several. Specific failures
# are placed before general ones, so a dependency resolution error inside a
# build step is not simply reported as a build failure.
DEFAULT_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        ErrorType.DEPENDENCY.value,
        (
            "modulenotfounderror",
            "no module named",
            "could not resolve dependency",
            "could not find artifact",
            "unresolved dependency",
            "npm err! 404",
            "package not found",
            "importerror",
            "unable to resolve",
        ),
    ),
    (
        ErrorType.NETWORK.value,
        (
            "connection refused",
            "could not resolve host",
            "etimedout",
            "econnreset",
            "network is unreachable",
            "temporary failure in name resolution",
            "failed to connect",
            "ssl certificate problem",
        ),
    ),
    (
        ErrorType.PERMISSION.value,
        (
            "permission denied",
            "eacces",
            "forbidden",
            "403",
            "access denied",
            "not authorized",
            "insufficient permission",
        ),
    ),
    (
        ErrorType.TIMEOUT.value,
        (
            "timed out",
            "timeout exceeded",
            "exceeded the maximum execution time",
            "cancelled because it exceeded",
            "deadline exceeded",
        ),
    ),
    (
        ErrorType.SYNTAX.value,
        (
            "syntaxerror",
            "parseerror",
            "unexpected token",
            "invalid syntax",
            "expected double-quoted property name",
            "unterminated string",
        ),
    ),
    (
        ErrorType.TEST_FAILURE.value,
        (
            "assertionerror",
            "test failed",
            "tests failed",
            "failed:",
            "expected but was",
            "snapshot test failed",
            "assertion failed",
            " failed -",
            "tests: 1 failed",
        ),
    ),
    (
        ErrorType.BUILD_CONFIG.value,
        (
            "execution failed for task",
            "build failed",
            "compilation error",
            "cannot find symbol",
            "configuration error",
            "gradle build failed",
            "could not compile",
            "task failed",
        ),
    ),
)

LINE_MARKER = re.compile(r"\[Line (\d+)\]\s?(.*)")


def ruleset_sha256(rules: Sequence[Tuple[str, Sequence[str]]]) -> str:
    """Checksum of the rules, including their order, for the freeze record."""
    payload = [[category, list(patterns)] for category, patterns in rules]
    return hashlib.sha256(json.dumps(payload, sort_keys=False).encode()).hexdigest()


def load_rules(path: str | Path) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """Load a frozen ruleset from JSON, preserving its order."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = data["rules"] if isinstance(data, dict) else data
    return tuple((entry["category"], tuple(entry["patterns"])) for entry in rules)


class BaselineClassifier:
    """Classify a filtered log by fixed patterns, with no model involved."""

    def __init__(self, rules: Optional[Sequence[Tuple[str, Sequence[str]]]] = None):
        self.rules = tuple((category, tuple(patterns)) for category, patterns in (rules or DEFAULT_RULES))
        self.ruleset_sha256 = ruleset_sha256(self.rules)

    def _numbered_lines(self, filtered_log: str) -> List[Tuple[int, str]]:
        """Recover (original line number, content) from the filtered extract."""
        lines = []
        for raw in (filtered_log or "").split("\n"):
            match = LINE_MARKER.match(raw)
            if match:
                lines.append((int(match.group(1)), match.group(2)))
        if not lines:
            # An unfiltered log carries no markers; fall back to 1-based position.
            lines = list(enumerate((filtered_log or "").split("\n"), 1))
        return lines

    def classify(self, filtered_log: str) -> Dict[str, object]:
        """Return a category, the lines that matched, and which patterns fired.

        Reports ``unknown`` when nothing matches rather than guessing, so the
        baseline's failures are visible instead of being spread across
        categories by a fallback.
        """
        numbered = self._numbered_lines(filtered_log)
        lowered = [(number, content.lower()) for number, content in numbered]

        for category, patterns in self.rules:
            matched_lines: List[int] = []
            matched_patterns: List[str] = []
            for pattern in patterns:
                for number, content in lowered:
                    if pattern in content:
                        if number not in matched_lines:
                            matched_lines.append(number)
                        if pattern not in matched_patterns:
                            matched_patterns.append(pattern)
            if matched_lines:
                return {
                    "error_type": category,
                    "failure_lines": sorted(matched_lines),
                    "matched_patterns": matched_patterns,
                    "ruleset_sha256": self.ruleset_sha256,
                }

        return {
            "error_type": ErrorType.UNKNOWN.value,
            "failure_lines": [],
            "matched_patterns": [],
            "ruleset_sha256": self.ruleset_sha256,
        }
