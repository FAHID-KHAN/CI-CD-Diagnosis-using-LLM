# filtering.py - Log filtering strategies

import logging
import re
from typing import Any, List, Optional

from src.api.log_sections import scope_to_failing_job

logger = logging.getLogger(__name__)

_encoder: Any = None
try:
    import tiktoken

    # Both thesis models use an o200k-derived tokenizer family. Pinning the
    # encoding avoids token-count drift when a moving model alias changes.
    _encoder = tiktoken.get_encoding("o200k_base")
except Exception:
    pass


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken if available, else estimate ~4 chars/token."""
    if _encoder is not None:
        return len(_encoder.encode(text))
    return len(text) // 4


class LogFilter:
    """Strategies for reducing log size before sending to LLM."""

    ERROR_KEYWORDS = [
        "error",
        "failed",
        "failure",
        "exception",
        "fatal",
        "critical",
        "panic",
        "traceback",
        "stack trace",
        "npm err!",
        "gradle failed",
        "maven error",
        "pytest failed",
    ]

    @staticmethod
    def filter_by_keywords(log_lines: List[str], keywords: List[str] | None = None) -> List[int]:
        """Return indices of lines containing any of the given keywords."""
        if keywords is None:
            keywords = LogFilter.ERROR_KEYWORDS
        error_indices = []
        for i, line in enumerate(log_lines):
            lower = line.lower()
            if any(kw in lower for kw in keywords):
                error_indices.append(i)
        return error_indices

    @staticmethod
    def get_context_window(
        log_lines: List[str],
        error_indices: List[int],
        window_size: int = 10,
    ) -> List[tuple]:
        """Return (start, end, lines) tuples around each error index."""
        contexts = []
        for idx in error_indices:
            start = max(0, idx - window_size)
            end = min(len(log_lines), idx + window_size + 1)
            contexts.append((start, end, log_lines[start:end]))
        return contexts

    @staticmethod
    def trace_filtering(
        log_content: str,
        evidence_lines,
        max_lines: int = 500,
        window_size: int = 20,
        max_tokens: int = 12000,
        failing_job: Optional[str] = None,
    ) -> dict:
        """Report how many verified evidence lines survive each filtering stage.

        Filtering is three stages and any of them can discard the evidence a
        diagnosis depends on. Knowing the total loss is not enough to fix it;
        this attributes the loss to the stage that caused it.

        Stages: keyword matching with its context window, the line cap, then
        truncation to the token budget. Line numbers are 1-based throughout, to
        match the ``[Line N]`` markers and the annotated evidence.
        """
        wanted = {int(n) for n in (evidence_lines or [])}
        offset = 0
        if failing_job:
            log_content, offset, _ = scope_to_failing_job(log_content, failing_job)
        lines = log_content.split("\n")
        total = len(lines)

        error_indices = LogFilter.filter_by_keywords(lines)
        if error_indices:
            covered: set[int] = set()
            for start, end, _ in LogFilter.get_context_window(lines, error_indices, window_size=window_size):
                covered.update(range(start, end))
            after_window = {offset + index + 1 for index in covered}
        else:
            # No keyword matched, so the tail is kept instead.
            tail_start = max(0, total - max_lines)
            after_window = {offset + index + 1 for index in range(tail_start, total)}

        ordered = sorted(after_window)
        after_cap = set(ordered[-max_lines:])

        rendered = "\n".join(f"[Line {n}] {lines[n - offset - 1]}" for n in sorted(after_cap))
        after_tokens = {
            int(match.group(1))
            for match in re.finditer(r"\[Line (\d+)\]", LogFilter._truncate_to_tokens(rendered, max_tokens))
        }

        def share(kept: set) -> float:
            return round(len(wanted & kept) / len(wanted), 4) if wanted else 0.0

        return {
            "raw_lines": total,
            "evidence_lines": len(wanted),
            "keyword_matches": len(error_indices),
            "after_keyword_window": {
                "lines": len(after_window),
                "evidence_kept": len(wanted & after_window),
                "recall": share(after_window),
            },
            "after_line_cap": {
                "lines": len(after_cap),
                "evidence_kept": len(wanted & after_cap),
                "recall": share(after_cap),
            },
            "after_token_truncation": {
                "lines": len(after_tokens),
                "evidence_kept": len(wanted & after_tokens),
                "recall": share(after_tokens),
            },
            "lost_at": (
                "keyword_window"
                if wanted and not (wanted & after_window)
                else (
                    "line_cap"
                    if wanted and not (wanted & after_cap)
                    else "token_truncation" if wanted and not (wanted & after_tokens) else None
                )
            ),
        }

    @staticmethod
    def apply_smart_filtering(
        log_content: str,
        max_lines: int = 500,
        window_size: int = 20,
        max_tokens: int = 12000,
        failing_job: Optional[str] = None,
    ) -> str:
        """Intelligently reduce log size while preserving error context.

        Returns a string where each kept line is prefixed with its original
        line number: ``[Line N] content``.

        After line-based filtering, the result is further truncated to
        *max_tokens* so that the LLM prompt stays within context limits.

        When *failing_job* is given, the log is first narrowed to that job's own
        section. A stored run log concatenates every job in the run and ends
        with the runner's system files, so without narrowing the line cap keeps
        the tail of unrelated jobs: on the first eleven annotated development
        cases that discarded every verified evidence line in ten of them. Line
        numbers remain those of the full stored log, because the annotated
        evidence is recorded in that frame and the two are compared directly.
        """
        offset = 0
        if failing_job:
            log_content, offset, _ = scope_to_failing_job(log_content, failing_job)
        lines = log_content.split("\n")

        error_indices = LogFilter.filter_by_keywords(lines)

        if not error_indices:
            tail = lines[-max_lines:]
            start_idx = len(lines) - len(tail)
            result = [f"[Line {offset + start_idx + i + 1}] {line}" for i, line in enumerate(tail)]
            return LogFilter._truncate_to_tokens("\n".join(result), max_tokens)

        contexts = LogFilter.get_context_window(lines, error_indices, window_size=window_size)

        # Merge overlapping ranges
        covered: set[int] = set()
        filtered_lines: list[tuple[int, str]] = []

        for start, end, _ in contexts:
            for i in range(start, end):
                if i not in covered:
                    covered.add(i)
                    filtered_lines.append((i, lines[i]))

        filtered_lines.sort(key=lambda x: x[0])

        # Keep the LAST max_lines, not the first. A CI log is chronological and
        # a failure is reported where it happens, which is near the end: the
        # failure summary, the stack trace, the "BUILD FAILED" block. Keeping
        # the head discarded every verified evidence line in 7 of 16 development
        # cases, because setup noise at the top filled the budget before the
        # failure was reached.
        result = [f"[Line {offset + number + 1}] {content}" for number, content in filtered_lines[-max_lines:]]
        return LogFilter._truncate_to_tokens("\n".join(result), max_tokens)

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """Trim text from the middle if it exceeds *max_tokens*.

        Keeps the first and last portions so the LLM sees both the
        beginning of the log context and the final error lines.
        """
        token_count = _count_tokens(text)
        if token_count <= max_tokens:
            return text

        lines = text.split("\n")
        half = len(lines) // 2
        head = lines[:half]
        tail = lines[half:]

        # Trim from the middle: shorten head, then tail, until under budget
        while _count_tokens("\n".join(head + ["... [truncated] ..."] + tail)) > max_tokens:
            if len(head) > len(tail) and len(head) > 5:
                head.pop()
            elif len(tail) > 5:
                tail.pop(0)
            else:
                break

        truncated = head + ["... [truncated] ..."] + tail
        logger.info(
            "Truncated log from %d to %d tokens (%d lines)",
            token_count,
            _count_tokens("\n".join(truncated)),
            len(truncated),
        )
        return "\n".join(truncated)
