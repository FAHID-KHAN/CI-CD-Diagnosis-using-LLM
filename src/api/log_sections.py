"""Locate one job's output inside a stored GitHub Actions run log.

A run's log is downloaded as a ZIP of one file per job and stored here as those
files concatenated under ``=== name ===`` headers. A scrapy run produces around
eighty such sections and closes with the runner's own ``*/system.txt`` files, so
the failing job's output sits somewhere in the middle of tens of thousands of
lines.

That shape defeated the filter. Keeping the last 500 keyword-matching lines of
the archive lands in system logs, and on the first eleven annotated development
cases it discarded every verified evidence line in ten of them -- including vite
logs under 5,000 lines, so the cause was the evidence's *position*, not the log's
size. Scoping to the failing job's section first takes mean recall on the
verified scrapy cases from 8% to 80%.

One definition lives here because three callers need to agree on it: the filter,
which decides what the model sees; the trace used to measure preprocessing
recall; and blind annotation, which tells the reviewer where to read. A private
copy in any one of them would let the model's view and the annotated line
numbers drift apart, and evidence-line precision and recall are computed by
comparing exactly those two.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

SECTION_HEADER = re.compile(r"^=== (.+) ===$")


def _comparable(text: str) -> str:
    """Strip everything but letters and digits for name comparison.

    GitHub sanitises the section filename, so it is not the job name verbatim:
    the job ``Build&Test: node-24, ubuntu-latest`` is stored as
    ``4_Build&Test node-24, ubuntu-latest.txt`` with the colon dropped. Matching
    literally found no section for any vite case.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def find_sections(lines: List[str]) -> List[Tuple[int, str]]:
    """Return ``(1-based start line, section name)`` for every section header."""
    return [(index, match.group(1)) for index, line in enumerate(lines, 1) if (match := SECTION_HEADER.match(line))]


def failing_job_section(log_content: str, failing_job: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Return ``(start, end, name)`` for the failing job's section, 1-based inclusive.

    Returns ``(None, None, None)`` when the job is not named or cannot be found.
    Callers must treat that as "scope unknown" and fall back to the whole log
    rather than guessing a section, because scoping to the wrong job would hide
    the failure completely.
    """
    job = (failing_job or "").strip()
    if not job:
        return (None, None, None)
    lines = log_content.split("\n")
    marks = find_sections(lines)
    wanted = _comparable(job)
    if not wanted:
        return (None, None, None)
    for position, (start, name) in enumerate(marks):
        stem = name[:-4] if name.endswith(".txt") else name
        if _comparable(stem).endswith(wanted):
            end = marks[position + 1][0] - 1 if position + 1 < len(marks) else len(lines)
            return (start, end, name)
    return (None, None, None)


def scope_to_failing_job(log_content: str, failing_job: str) -> Tuple[str, int, Optional[str]]:
    """Narrow a run archive to the failing job's own output.

    Returns ``(content, line_offset, section_name)``, where *line_offset* is the
    number to add to a 1-based line number in *content* to recover its line
    number in the full stored log. Line numbers must stay in the stored log's
    frame: the model is shown ``[Line N]`` markers and the annotated evidence
    lines are recorded against the same frame, so the two are only comparable
    while both count from the start of the archive.

    When the section cannot be located the whole log is returned with a zero
    offset and ``None`` as the name. The caller is expected to record that, so a
    run where scoping silently did nothing is visible rather than mistaken for a
    scoped one.
    """
    start, end, name = failing_job_section(log_content, failing_job)
    if start is None or end is None:
        return (log_content, 0, None)
    lines = log_content.split("\n")
    return ("\n".join(lines[start - 1 : end]), start - 1, name)
