# filtering.py - Log filtering strategies

from typing import List


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
    def apply_smart_filtering(log_content: str, max_lines: int = 500, window_size: int = 20) -> str:
        """Intelligently reduce log size while preserving error context.

        Returns a string where each kept line is prefixed with its original
        line number: ``[Line N] content``.
        """
        lines = log_content.split('\n')

        error_indices = LogFilter.filter_by_keywords(lines)

        if not error_indices:
            return '\n'.join(lines[-max_lines:])

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
        return '\n'.join(result)
