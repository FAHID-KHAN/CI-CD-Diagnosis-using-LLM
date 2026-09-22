#!/usr/bin/env python3
"""Generate docs/architecture/architecture.svg from a single declarative layout.

The diagram was previously a committed PNG with no source, so it could not be
corrected or diffed. This script is the source: edit the PANELS structure below
and re-run it.

    python docs/architecture/make_architecture.py

Render the PNG for the README and slides with any headless browser, e.g.

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
      --headless --disable-gpu --window-size=2400,1560 --force-device-scale-factor=2 \\
      --screenshot=docs/architecture/architecture.png docs/architecture/architecture.svg

The split into panels is deliberate: panel A is the *artifact* being evaluated,
panels B and C are the *evaluation apparatus* that produces and checks the
evidence. Keeping that boundary visible is what lets the thesis argue the
evaluation is independent of the thing it evaluates.
"""

from __future__ import annotations

import html
from pathlib import Path

WIDTH = 2400
BOX_W = 268
BOX_H = 92
GAP_X = 44
GAP_Y = 54

# Fill, border and heading colour per role. Roles carry meaning, so the legend
# can be read without the boxes.
ROLES = {
    "source": ("#e4ecf9", "#5b7ba8", "Source or human input"),
    "process": ("#e2f0e8", "#5f9b7c", "Deterministic process"),
    "model": ("#ece3f6", "#8a6fb2", "Model condition"),
    "data": ("#fdf1d8", "#cfa44a", "Stored research data"),
    "output": ("#fae7e7", "#c07a7a", "Evaluation output"),
    "gate": ("#fbe2cd", "#c2702a", "Methodological gate"),
}

INK = "#16233d"
MUTED = "#5a6678"
ARROW = "#56627a"


def box(x, y, title, lines, role, w=BOX_W, h=BOX_H):
    fill, stroke, _ = ROLES[role]
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    ]
    total = 1 + len(lines)
    start = y + h / 2 - (total - 1) * 8.5 + 5
    parts.append(
        f'<text x="{x + w / 2}" y="{start}" text-anchor="middle" '
        f'font-size="15.5" font-weight="650" fill="{INK}">{html.escape(title)}</text>'
    )
    for index, line in enumerate(lines):
        parts.append(
            f'<text x="{x + w / 2}" y="{start + 19 + index * 16}" text-anchor="middle" '
            f'font-size="12.5" fill="{MUTED}">{html.escape(line)}</text>'
        )
    return "".join(parts)


def arrow(x1, y1, x2, y2, dashed=False):
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    return (
        f'<path d="M {x1} {y1} L {x2} {y2}" stroke="{ARROW}" stroke-width="2.2" '
        f'fill="none" marker-end="url(#tip)"{dash}/>'
    )


def elbow(x1, y1, x2, y2, dashed=False):
    """Right-angled connector: out horizontally, then vertically into the target."""
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    mid = (x1 + x2) / 2
    return (
        f'<path d="M {x1} {y1} H {mid} V {y2} H {x2}" stroke="{ARROW}" stroke-width="2.2" '
        f'fill="none" marker-end="url(#tip)"{dash}/>'
    )


def row(x0, y, items, gap=GAP_X):
    """Lay out boxes left to right, joining them with arrows."""
    parts = []
    positions = []
    x = x0
    for title, lines, role in items:
        positions.append(x)
        parts.append(box(x, y, title, lines, role))
        x += BOX_W + gap
    for index in range(len(items) - 1):
        left = positions[index] + BOX_W
        parts.append(arrow(left + 6, y + BOX_H / 2, left + gap - 8, y + BOX_H / 2))
    return "".join(parts), positions


def heading(x, y, letter, title, subtitle):
    return (
        f'<text x="{x}" y="{y}" font-size="23" font-weight="700" fill="{INK}">'
        f"{html.escape(letter)}  {html.escape(title)}</text>"
        f'<text x="{x}" y="{y + 26}" font-size="14.5" fill="{MUTED}">{html.escape(subtitle)}</text>'
    )


def build() -> str:
    parts = []
    left = 60

    parts.append(
        f'<text x="{left}" y="66" font-size="38" font-weight="750" fill="{INK}">'
        "CI/CD Failure Diagnosis — Artifact and Evaluation Apparatus</text>"
        f'<text x="{left}" y="98" font-size="16" fill="{MUTED}">'
        "The model is one replaceable component inside a fixed apparatus. "
        "Only the model varies between the two conditions.</text>"
    )

    # ── A. the artifact ────────────────────────────────────────────────
    y = 150
    parts.append(heading(left, y, "A.", "The diagnostic artifact", "This is what the thesis evaluates."))
    y += 54
    artifact = [
        ("Raw failure log", ["one failed workflow run"], "source"),
        ("LogFilter", ["error keywords, ±20 lines", "[Line N] numbers preserved"], "process"),
        ("Shared prompt", ["strict JSON schema,", "8 fixed categories"], "process"),
    ]
    parts_row, positions = row(left, y, artifact)
    parts.append(parts_row)

    # The two conditions branch from the shared prompt and rejoin unchanged.
    branch_x = positions[-1] + BOX_W + GAP_X
    model_h = 72
    spread = 62
    centre = y + BOX_H / 2
    top_y = centre - spread - model_h / 2
    bottom_y = centre + spread - model_h / 2
    parts.append(box(branch_x, top_y, "Proprietary", ["openai/gpt-5.6-terra"], "model", h=model_h))
    parts.append(box(branch_x, bottom_y, "Open-weights", ["local/thesis-qwen3.5:9b-24k"], "model", h=model_h))
    fork = positions[-1] + BOX_W
    parts.append(elbow(fork + 6, y + BOX_H / 2, branch_x - 8, top_y + model_h / 2))
    parts.append(elbow(fork + 6, y + BOX_H / 2, branch_x - 8, bottom_y + model_h / 2))

    after_x = branch_x + BOX_W + GAP_X
    rest = [
        ("Structured diagnosis", ["category, failure lines,", "root cause, fix, evidence"], "data"),
        ("Grounding check", ["do the cited lines", "exist in the extract?"], "process"),
        ("Result + run metadata", ["tokens, cost, latency,", "raw response"], "data"),
    ]
    parts_row, rest_positions = row(after_x, y, rest)
    parts.append(parts_row)
    parts.append(elbow(branch_x + BOX_W + 6, top_y + model_h / 2, after_x - 8, y + BOX_H / 2))
    parts.append(elbow(branch_x + BOX_W + 6, bottom_y + model_h / 2, after_x - 8, y + BOX_H / 2))

    note_y = bottom_y + model_h + 34
    parts.append(
        f'<text x="{left}" y="{note_y}" font-size="13.5" fill="{MUTED}">'
        "Identical filtered text, prompt, response schema and reasoning effort for both conditions — "
        "so any measured difference is attributable to the model.</text>"
    )

    # ── B. evidence construction ───────────────────────────────────────
    y = note_y + 56
    parts.append(
        heading(
            left,
            y,
            "B.",
            "Evaluation apparatus — constructing the evidence",
            "Never sees model output, so the labels cannot be influenced by the predictions.",
        )
    )
    y += 54
    collection = [
        ("GitHub Actions API", ["failed runs only"], "source"),
        ("Collect", ["fixed repository list,", "no auto-discovery"], "process"),
        ("Immutable raw logs", ["+ SHA-256 per log"], "data"),
        ("Triage", ["cancelled · auth · too short", "· duplicate signature"], "process"),
        ("Eligible cohort", ["the frozen study set"], "data"),
    ]
    parts_row, collect_positions = row(left, y, collection)
    parts.append(parts_row)

    drop_x = collect_positions[3] + BOX_W / 2
    drop_y = y + BOX_H
    parts.append(f'<path d="M {drop_x} {drop_y + 6} V {drop_y + GAP_Y - 8}" stroke="{ARROW}" '
                 f'stroke-width="2.2" fill="none" marker-end="url(#tip)"/>')
    parts.append(box(drop_x - BOX_W / 2, drop_y + GAP_Y, "Excluded cases", ["with a recorded reason"], "data", h=72))

    y2 = drop_y + GAP_Y + 72 + GAP_Y
    ground_truth = [
        ("Blind annotation", ["category · root cause · lines", "· linked evidence"], "source"),
        ("Independent review", ["a different reviewer,", "blind to the first"], "source"),
        ("Adjudicated ground truth", ["written decision on", "every disagreement"], "data"),
        ("Audit gate", ["evidence, independence,", "usable root cause"], "gate"),
    ]
    parts_row, gt_positions = row(left + BOX_W + GAP_X, y2, ground_truth)
    parts.append(parts_row)
    cohort_x = collect_positions[-1] + BOX_W / 2
    parts.append(
        f'<path d="M {cohort_x} {y + BOX_H + 6} V {y2 - 34} H {left + BOX_W + GAP_X + BOX_W / 2} '
        f'V {y2 - 8}" stroke="{ARROW}" stroke-width="2.2" fill="none" marker-end="url(#tip)"/>'
    )

    # ── C. measurement ─────────────────────────────────────────────────
    y3 = y2 + BOX_H + 80
    parts.append(
        heading(
            left,
            y3,
            "C.",
            "Evaluation apparatus — measurement",
            "Both conditions are scored on exactly the same cases against the same ground truth.",
        )
    )
    y3 += 54
    measurement = [
        ("Partition guard", ["refuses a held-out run over", "any exploratory case"], "gate"),
        ("Scoring", ["exact category match;", "per-category P/R/F1; lines"], "process"),
        ("Paired statistics", ["McNemar · permutation", "· bootstrap CI"], "process"),
        ("Comparison report", ["terminal table +", "self-contained HTML page"], "output"),
    ]
    parts_row, _ = row(left, y3, measurement)
    parts.append(parts_row)

    # ── legend ─────────────────────────────────────────────────────────
    legend_y = y3 + BOX_H + 62
    parts.append(
        f'<text x="{left}" y="{legend_y}" font-size="14" font-weight="650" fill="{INK}">Legend</text>'
    )
    lx = left + 90
    for role, (fill, stroke, label) in ROLES.items():
        parts.append(
            f'<rect x="{lx}" y="{legend_y - 13}" width="17" height="17" rx="4" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{lx + 26}" y="{legend_y}" font-size="13.5" fill="{MUTED}">{html.escape(label)}</text>'
        )
        lx += 42 + len(label) * 7.6

    parts.append(
        f'<text x="{left}" y="{legend_y + 38}" font-size="13.5" fill="{MUTED}">'
        "Out of scope in the current system: rule-based or heuristic baselines, RAG comparison, "
        "human-versus-LLM study, and root-cause rubric scoring.</text>"
    )

    height = int(legend_y + 76)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" font-family="Helvetica Neue, Helvetica, Arial, sans-serif">'
        '<defs><marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{ARROW}"/></marker></defs>'
        f'<rect width="{WIDTH}" height="{height}" fill="#ffffff"/>'
        f"{''.join(parts)}</svg>"
    )


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "architecture.svg"
    target.write_text(build(), encoding="utf-8")
    print(f"Wrote {target}")
