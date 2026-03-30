# filtering.py - Log filtering strategies

import logging
from typing import List

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _encoder = tiktoken.encoding_for_model("gpt-4o-mini")
except Exception:
    _encoder = None


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken if available, else estimate ~4 chars/token."""
    if _encoder is not None:
        return len(_encoder.encode(text))
    return len(text) // 4


class LogFilter:
    """Strategies for reducing log size before sending to LLM."""

    ERROR_KEYWORDS = [
        'error', 'failed', 'failure', 'exception', 'fatal',
        'critical', 'panic', 'traceback', 'stack trace',
        'npm err!', 'gradle failed', 'maven error', 'pytest failed',
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
    def apply_smart_filtering(
        log_content: str,
        max_lines: int = 500,
        window_size: int = 20,
        max_tokens: int = 12000,
    ) -> str:
        """Intelligently reduce log size while preserving error context.

        Returns a string where each kept line is prefixed with its original
        line number: ``[Line N] content``.

        After line-based filtering, the result is further truncated to
        *max_tokens* so that the LLM prompt stays within context limits.
        """
        lines = log_content.split('\n')

        error_indices = LogFilter.filter_by_keywords(lines)

        if not error_indices:
            tail = lines[-max_lines:]
            start_idx = len(lines) - len(tail)
            result = [f"[Line {start_idx + i}] {l}" for i, l in enumerate(tail)]
            return LogFilter._truncate_to_tokens('\n'.join(result), max_tokens)

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

        result = [f"[Line {num}] {content}" for num, content in filtered_lines[:max_lines]]
        return LogFilter._truncate_to_tokens('\n'.join(result), max_tokens)

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """Trim text from the middle if it exceeds *max_tokens*.

        Keeps the first and last portions so the LLM sees both the
        beginning of the log context and the final error lines.
        """
        token_count = _count_tokens(text)
        if token_count <= max_tokens:
            return text

        lines = text.split('\n')
        half = len(lines) // 2
        head = lines[:half]
        tail = lines[half:]

        # Trim from the middle: shorten head, then tail, until under budget
        while _count_tokens('\n'.join(head + ['... [truncated] ...'] + tail)) > max_tokens:
            if len(head) > len(tail) and len(head) > 5:
                head.pop()
            elif len(tail) > 5:
                tail.pop(0)
            else:
                break

        truncated = head + ['... [truncated] ...'] + tail
        logger.info("Truncated log from %d to %d tokens (%d lines)",
                    token_count, _count_tokens('\n'.join(truncated)), len(truncated))
        return '\n'.join(truncated)
