"""The shared failure vocabulary every scoring and reporting module reads.

Kept in its own module so the metric, audit and reporting layers can agree on
the categories without importing each other.
"""

from __future__ import annotations

# Declared diagnosis vocabulary, in the order used by every matrix axis and
# category table so two models are always read against the same rows.
ERROR_TYPE_ORDER = (
    "dependency_error",
    "test_failure",
    "build_configuration",
    "timeout",
    "permission_denied",
    "syntax_error",
    "network_error",
    "unknown",
)

# Placeholder recorded for a log the model never diagnosed, so an inference
# failure counts as incorrect rather than silently dropping out of the pairing.
INFERENCE_ERROR = "__inference_error__"
