# grounding.py - Verify that LLM-cited evidence exists in the log

import logging
import re
from difflib import SequenceMatcher
from typing import List

from src.api.models import LogLine

logger = logging.getLogger(__name__)

# Minimum similarity ratio to consider a cited line as verified
_FUZZY_THRESHOLD = 0.75


class GroundingVerifier:
    """Check cited log lines against the actual (filtered) log content."""

    @staticmethod
    def verify_evidence(
        log_content: str,
        evidence: List[LogLine],
        threshold: float = 0.8,
    ) -> tuple[bool, float]:
        """Return (hallucination_detected, grounding_score).

        The filtered log has lines formatted as ``[Line N] content``.
        We build a mapping from the original line number N to its content
        so we can look up each piece of evidence by the line number the
        LLM cited.
        """
        if not evidence:
            return False, 0.0

        # Build {original_line_number: content} from the filtered log
        line_map: dict[int, str] = {}
        raw_lines = log_content.split('\n')
        for raw in raw_lines:
            m = re.match(r'\[Line (\d+)\]\s?(.*)', raw)
            if m:
                line_map[int(m.group(1))] = m.group(2)

        # If the log was NOT filtered (no [Line N] markers), fall back to
        # a simple list where index == line number.
        if not line_map:
            line_map = {i: line for i, line in enumerate(raw_lines)}

        verified = 0
        for ev in evidence:
            actual = line_map.get(ev.line_number, "")
            cited = ev.content.strip()
            if not cited:
                continue
            # Exact substring match (fast path)
            if cited in actual:
                verified += 1
            else:
                # Fuzzy match: handles minor LLM paraphrasing / truncation
                ratio = SequenceMatcher(None, cited, actual.strip()).ratio()
                if ratio >= _FUZZY_THRESHOLD:
                    verified += 1
                else:
                    logger.debug(
                        "Evidence mismatch: line %d cited '%s' but actual is '%s' (ratio=%.2f)",
                        ev.line_number,
                        cited[:60],
                        actual[:60],
                        ratio,
                    )

        score = verified / len(evidence)
        hallucination_detected = score < threshold
        return hallucination_detected, score
