"""Render an aligned experiment comparison as one self-contained HTML page.

The page has no external assets, no JavaScript and no build step: it is written
next to the experiment it describes and opened directly in a browser, so a
comparison can be archived alongside the run it came from.

Charts follow the project's two-condition palette (blue = first condition,
orange = second). Correctness is never carried by colour alone -- every outcome
cell pairs its tint with a glyph and the predicted type in text.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Dict, List, Optional

from src.evaluation.report_comparison import (
    INFERENCE_ERROR,
    ExperimentReport,
    active_error_types,
    confusion_rows,
    cross_experiment_deltas,
    pairwise_agreements,
)

# Categorical slots in fixed order; a condition keeps its colour everywhere on
# the page, so a filter or a missing run never repaints the survivors.
SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")

# Steps in the single-hue sequential ramp the confusion matrices use. The step
# colours themselves live in CSS (classes ``.s0``-``.s4``) so the dark ramp is
# selected by the media query instead of being baked into an inline style.
RAMP_STEPS = 5


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def pct(value: Optional[float], digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def fmt_ms(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if value >= 60_000:
        return f"{value / 60_000:.1f} min"
    if value >= 1_000:
        return f"{value / 1_000:.1f} s"
    return f"{value:.0f} ms"


def fmt_usd(value: Optional[float]) -> str:
    # Per-diagnosis costs sit in the cents range, so anything under a dollar
    # keeps four decimals; two would round the study's cost metric away.
    if value is None:
        return "n/a"
    if value == 0:
        return "$0.00"
    if abs(value) < 1:
        return f"${value:.4f}"
    return f"${value:.2f}"


def fmt_metric(value: Optional[float], unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "ratio":
        return pct(value)
    if unit == "ms":
        return fmt_ms(value)
    if unit == "usd":
        return fmt_usd(value)
    return f"{value:g}"


def type_label(name: Optional[str]) -> str:
    if name is None:
        return "not annotated"
    if name == INFERENCE_ERROR:
        return "no diagnosis"
    return name.replace("_", " ")


CSS = """
:root {
  color-scheme: light;
  --surface-0: #f5f5f3;
  --surface-1: #fcfcfb;
  --surface-2: #eeeeeb;
  --border: #dcdcd6;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #77766f;
  --good: #0ca30c;
  --warning: #fab219;
  --critical: #d03b3b;
  --good-tint: #e6f5e6;
  --critical-tint: #fae9e9;
  --warning-tint: #fdf3dd;
  --grid: #e6e6e1;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --surface-0: #121211;
    --surface-1: #1a1a19;
    --surface-2: #232321;
    --border: #3a3a36;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #96958c;
    --good-tint: #16301a;
    --critical-tint: #3a1f1f;
    --warning-tint: #3a2f14;
    --grid: #2e2e2b;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0 16px 64px;
  background: var(--surface-0);
  color: var(--text-primary);
  font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1100px; margin: 0 auto; }
header.page { padding: 40px 0 8px; }
h1 { font-size: 27px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
h3 {
  font-size: 14px; margin: 0 0 12px; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-secondary);
}
p.sub { margin: 0; color: var(--text-secondary); }
.card {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  margin: 16px 0;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; }
.chip {
  display: inline-flex; gap: 6px; align-items: baseline;
  background: var(--surface-2); border-radius: 999px;
  padding: 4px 11px; font-size: 12.5px; color: var(--text-secondary);
}
.chip b { color: var(--text-primary); font-weight: 600; }
.notes { border-left: 3px solid var(--warning); background: var(--warning-tint); }
.notes ul { margin: 8px 0 0; padding-left: 20px; }
.notes li { margin: 4px 0; color: var(--text-primary); }
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 0 0 18px; font-size: 13px; color: var(--text-secondary); }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.swatch { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
.scoreboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.score {
  border: 1px solid var(--border); border-radius: 9px;
  padding: 16px; background: var(--surface-1); border-top: 3px solid var(--border);
}
.score .name { font-size: 13px; font-weight: 600; color: var(--text-secondary); word-break: break-word; }
.score .hero {
  font-size: 36px; font-weight: 650; letter-spacing: -0.02em;
  margin: 6px 0 0; font-variant-numeric: tabular-nums;
}
.score .hero-label { font-size: 12.5px; color: var(--text-muted); margin-bottom: 12px; }
.score dl { display: grid; grid-template-columns: 1fr auto; gap: 5px 12px; margin: 0; font-size: 13px; }
.score dt { color: var(--text-secondary); }
.score dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.metric-row { margin: 0 0 16px; }
.metric-row .title { font-size: 13.5px; font-weight: 600; margin-bottom: 7px; }
.bar-line { display: grid; grid-template-columns: 170px 1fr 78px; align-items: center; gap: 10px; margin-bottom: 2px; }
.bar-name {
  font-size: 12.5px; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.bar-track { background: var(--surface-2); border-radius: 4px; height: 15px; position: relative; }
.bar-fill { height: 100%; border-radius: 2px 4px 4px 2px; }
.bar-value { font-size: 12.5px; text-align: right; font-variant-numeric: tabular-nums; color: var(--text-primary); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th {
  font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-secondary); font-weight: 600;
}
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; }
.outcome {
  display: inline-flex; align-items: center; gap: 7px; border-radius: 6px;
  padding: 4px 9px; font-size: 12.5px; white-space: nowrap;
}
.outcome.hit { background: var(--good-tint); }
.outcome.miss { background: var(--critical-tint); }
.outcome.none { background: var(--surface-2); color: var(--text-secondary); }
.outcome .mark { font-weight: 700; }
.outcome.hit .mark { color: var(--good); }
.outcome.miss .mark { color: var(--critical); }
.meta { color: var(--text-muted); font-size: 12px; }
.card > div > h3 { margin-top: 20px; }
dl.gt { display: grid; grid-template-columns: auto 1fr; gap: 4px 16px; margin: 14px 0; font-size: 13px; }
dl.gt dt { color: var(--text-secondary); }
dl.gt dd { margin: 0; }
.matrix td.cell {
  text-align: center; font-variant-numeric: tabular-nums;
  border: 2px solid var(--surface-1); padding: 7px 6px;
}
.matrix th.side {
  font-size: 11.5px; text-transform: none; letter-spacing: 0; padding: 7px 8px;
  color: var(--text-secondary); font-weight: 500; white-space: nowrap;
}
.matrix th.num { padding: 7px 6px; font-size: 10.5px; letter-spacing: 0.02em; }
.matrix .s-none { background: var(--surface-2); color: var(--text-muted); }
.matrix .s0 { background: #cde2fb; color: #0b0b0b; }
.matrix .s1 { background: #9ec5f4; color: #0b0b0b; }
.matrix .s2 { background: #6da7ec; color: #0b0b0b; }
.matrix .s3 { background: #3987e5; color: #ffffff; }
.matrix .s4 { background: #256abf; color: #ffffff; }
@media (prefers-color-scheme: dark) {
  .matrix .s0 { background: #184f95; color: #ffffff; }
  .matrix .s1 { background: #1c5cab; color: #ffffff; }
  .matrix .s2 { background: #256abf; color: #ffffff; }
  .matrix .s3 { background: #2a78d6; color: #ffffff; }
  .matrix .s4 { background: #3987e5; color: #ffffff; }
}
.split { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 20px; }
details { border-top: 1px solid var(--grid); padding: 10px 0; }
details summary { cursor: pointer; font-size: 13.5px; font-weight: 600; }
details .body { padding: 12px 0 4px; }
.diag { border-left: 3px solid var(--border); padding: 2px 0 2px 12px; margin: 0 0 14px; }
.diag h4 { margin: 0 0 4px; font-size: 13px; }
.diag p { margin: 0 0 6px; font-size: 13px; color: var(--text-secondary); }
.delta-up { color: var(--good); font-weight: 600; }
.delta-down { color: var(--critical); font-weight: 600; }
.delta-flat { color: var(--text-muted); }
footer { margin-top: 32px; font-size: 12.5px; color: var(--text-muted); }
@media (max-width: 640px) {
  .bar-line { grid-template-columns: 1fr; gap: 3px; }
  .bar-name, .bar-value { text-align: left; }
}
"""


def _series_css(labels: List[str]) -> str:
    """One CSS variable per condition, in both modes, assigned in fixed order."""
    light = "\n".join(f"  --series-{i}: {SERIES_LIGHT[i % len(SERIES_LIGHT)]};" for i in range(len(labels)))
    dark = "\n".join(f"    --series-{i}: {SERIES_DARK[i % len(SERIES_DARK)]};" for i in range(len(labels)))
    return f":root {{\n{light}\n}}\n@media (prefers-color-scheme: dark) {{\n  :root {{\n{dark}\n  }}\n}}\n"


def _bar(name: str, value: Optional[float], maximum: float, display: str, color: str, tooltip: str) -> str:
    width = 0.0 if not value or maximum <= 0 else max(min(value / maximum, 1.0), 0.0) * 100
    # A value that rounds to nothing still gets a visible stub, but a true zero
    # draws no mark at all rather than a sliver that reads as a small quantity.
    if 0 < width < 0.6:
        width = 0.6
    return (
        f'<div class="bar-line" title="{esc(tooltip)}">'
        f'<div class="bar-name">{esc(name)}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%;background:{color}"></div></div>'
        f'<div class="bar-value">{esc(display)}</div>'
        "</div>"
    )


def _metric_block(
    title: str,
    labels: List[str],
    values: List[Optional[float]],
    displays: List[str],
    maximum: float,
    slots: Dict[str, int],
) -> str:
    bars = "".join(
        _bar(label, value, maximum, display, f"var(--series-{slots[label]})", f"{label} — {title}: {display}")
        for label, value, display in zip(labels, values, displays)
    )
    return f'<div class="metric-row"><div class="title">{esc(title)}</div>{bars}</div>'


def _legend(labels: List[str], slots: Dict[str, int]) -> str:
    items = "".join(
        f'<span><i class="swatch" style="background:var(--series-{slots[label]})"></i>{esc(label)}</span>'
        for label in labels
    )
    return f'<div class="legend">{items}</div>'


def _context_chips(report: ExperimentReport) -> str:
    context = report.run_context
    entries = [
        ("study", report.study_id),
        ("experiment", report.experiment_id),
        ("logs", len(report.log_order)),
        ("mode", "pilot" if context.get("pilot") else "full run"),
        ("reasoning effort", context.get("reasoning_effort")),
        ("run started", context.get("run_started_at_utc")),
        ("commit", str(context.get("git_commit") or "")[:10] or None),
    ]
    chips = "".join(
        f'<span class="chip">{esc(key)} <b>{esc(value)}</b></span>' for key, value in entries if value not in (None, "")
    )
    return f'<div class="chips">{chips}</div>'


def _scoreboard(report: ExperimentReport, slots: Dict[str, int]) -> str:
    cards = []
    for label in report.model_labels:
        metrics = report.metrics.get(label, {})
        accuracy = metrics.get("error_type_accuracy")
        cards.append(
            f'<div class="score" style="border-top-color:var(--series-{slots[label]})">'
            f'<div class="name">{esc(label)}</div>'
            f'<div class="hero">{esc(pct(accuracy, 0))}</div>'
            f'<div class="hero-label">error-type accuracy vs blind ground truth</div>'
            "<dl>"
            f"<dt>Diagnosed</dt><dd>{metrics.get('successful_logs', 0)}/{metrics.get('total_logs', 0)}</dd>"
            f"<dt>Mean grounding</dt><dd>{esc(pct(metrics.get('mean_grounding_score')))}</dd>"
            f"<dt>Hallucination rate</dt><dd>{esc(pct(metrics.get('hallucination_rate')))}</dd>"
            f"<dt>Avg confidence</dt><dd>{esc(pct(metrics.get('avg_confidence')))}</dd>"
            f"<dt>Avg latency</dt><dd>{esc(fmt_ms(metrics.get('avg_execution_time_ms')))}</dd>"
            f"<dt>Cost / diagnosis</dt><dd>{esc(fmt_usd(metrics.get('cost_per_diagnosis_usd')))}</dd>"
            f"<dt>Total tokens</dt><dd>{metrics.get('total_tokens', 0):,}</dd>"
            "</dl></div>"
        )
    return f'<div class="scoreboard">{"".join(cards)}</div>'


RATIO_METRICS = (
    ("error_type_accuracy", "Error-type accuracy — higher is better"),
    ("mean_grounding_score", "Mean grounding score — higher is better"),
    ("avg_confidence", "Average self-reported confidence"),
    ("hallucination_rate", "Hallucination rate — lower is better"),
)


def _metric_charts(report: ExperimentReport, slots: Dict[str, int]) -> str:
    labels = report.model_labels
    blocks = []
    for key, title in RATIO_METRICS:
        values = [report.metrics.get(label, {}).get(key) for label in labels]
        if all(value is None for value in values):
            continue
        blocks.append(_metric_block(title, labels, values, [pct(value) for value in values], 1.0, slots))

    # Latency and cost live on their own scales; they are never plotted on a
    # shared axis with the ratio metrics or with each other.
    latencies = [report.metrics.get(label, {}).get("avg_execution_time_ms") or 0.0 for label in labels]
    if any(latencies):
        blocks.append(
            _metric_block(
                "Average latency per diagnosis — lower is better",
                labels,
                latencies,
                [fmt_ms(value) for value in latencies],
                max(latencies),
                slots,
            )
        )
    costs = [report.metrics.get(label, {}).get("cost_per_diagnosis_usd") or 0.0 for label in labels]
    if any(costs):
        blocks.append(
            _metric_block(
                "API cost per diagnosis — lower is better",
                labels,
                costs,
                [fmt_usd(value) for value in costs],
                max(costs),
                slots,
            )
        )
    return "".join(blocks)


def _outcome_cell(outcome) -> str:
    if outcome is None:
        return '<td><span class="outcome none">— not run</span></td>'
    if outcome.correct is None:
        state, mark = "none", "·"
    elif outcome.correct:
        state, mark = "hit", "✓"
    else:
        state, mark = "miss", "✗"
    detail = (
        f"confidence {pct(outcome.confidence, 0)} · grounding {pct(outcome.grounding_score, 0)} · "
        f"{fmt_ms(outcome.execution_time_ms)} · {fmt_usd(outcome.cost_usd)}"
    )
    flag = (
        ' <span class="meta" title="Evidence lines not found in the filtered log">hallucination</span>'
        if outcome.hallucination_detected
        else ""
    )
    return (
        f'<td><span class="outcome {state}" title="{esc(detail)}">'
        f'<span class="mark">{mark}</span>{esc(type_label(outcome.predicted_error_type))}</span>{flag}'
        f'<div class="meta">{esc(detail)}</div></td>'
    )


def _outcome_matrix(report: ExperimentReport, slots: Dict[str, int]) -> str:
    headers = "".join(
        f'<th><span class="swatch" style="background:var(--series-{slots[label]})"></span> {esc(label)}</th>'
        for label in report.model_labels
    )
    rows = []
    for log_id in report.log_order:
        info = report.log_info.get(log_id, {})
        truth = report.ground_truth.get(log_id, {})
        cells = "".join(_outcome_cell(report.outcome(label, log_id)) for label in report.model_labels)
        rows.append(
            "<tr>"
            f"<td><b>{esc(info.get('repository') or log_id)}</b>"
            f"<div class=\"meta\">{esc(info.get('workflow'))}</div></td>"
            f"<td>{esc(type_label(truth.get('actual_error_type')))}</td>"
            f"{cells}</tr>"
        )
    return (
        '<div class="scroll"><table>'
        f"<thead><tr><th>Log</th><th>Ground truth</th>{headers}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _agreement(report: ExperimentReport) -> str:
    pairs = pairwise_agreements(report)
    if not pairs:
        return ""
    blocks = []
    for pair in pairs:
        cells = [
            ("Both correct", pair.both_correct, "hit"),
            (f"Only {pair.model_a}", pair.only_a_correct, "none"),
            (f"Only {pair.model_b}", pair.only_b_correct, "none"),
            ("Both wrong", pair.both_wrong, "miss"),
        ]
        rows = "".join(
            f'<tr><td><span class="outcome {state}">{esc(name)}</span></td>'
            f'<td class="num">{count}</td>'
            f'<td class="num">{pct(count / pair.scored, 0) if pair.scored else "n/a"}</td></tr>'
            for name, count, state in cells
        )
        agreement = pair.same_prediction / pair.n_common if pair.n_common else None
        blocks.append(
            "<div>"
            f"<h3>{esc(pair.model_a)} vs {esc(pair.model_b)}</h3>"
            '<table><thead><tr><th>Outcome</th><th class="num">Logs</th><th class="num">Share</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
            f'<p class="meta">The two conditions predicted the same error type on '
            f"{pair.same_prediction} of {pair.n_common} shared logs ({esc(pct(agreement, 0))}).</p>"
            "</div>"
        )
    return f'<div class="split">{"".join(blocks)}</div>'


def _confusion(report: ExperimentReport, types: List[str]) -> str:
    if not types or not report.ground_truth:
        return ""
    blocks = []
    for label in report.model_labels:
        rows_data = confusion_rows(report, label)
        if not rows_data:
            continue
        counts: Dict[tuple, int] = {(row["actual"], row["predicted"]): row["count"] for row in rows_data}
        actual_types = [name for name in types if any(key[0] == name for key in counts)]
        predicted_types = [name for name in types if any(key[1] == name for key in counts)]
        if INFERENCE_ERROR in {key[1] for key in counts}:
            predicted_types.append(INFERENCE_ERROR)
        maximum = max(counts.values())
        head = "".join(f'<th class="num">{esc(type_label(name))}</th>' for name in predicted_types)
        body = []
        for actual in actual_types:
            cells = []
            for predicted in predicted_types:
                count = counts.get((actual, predicted), 0)
                tip = f"actual {type_label(actual)} → predicted {type_label(predicted)}: {count}"
                if count == 0:
                    step_class = "s-none"
                else:
                    step = min(int(count / maximum * RAMP_STEPS), RAMP_STEPS - 1)
                    step_class = f"s{step}"
                cells.append(f'<td class="cell {step_class}" title="{esc(tip)}">{count}</td>')
            body.append(f'<tr><th class="side">{esc(type_label(actual))}</th>{"".join(cells)}</tr>')
        blocks.append(
            "<div>"
            f"<h3>{esc(label)}</h3>"
            '<div class="scroll"><table class="matrix">'
            f'<thead><tr><th class="side">actual ↓ / predicted →</th>{head}</tr></thead>'
            f"<tbody>{''.join(body)}</tbody></table></div></div>"
        )
    return f'<div class="split">{"".join(blocks)}</div>' if blocks else ""


def _category_table(report: ExperimentReport, slots: Dict[str, int]) -> str:
    """Per-category precision, recall, F1 and support for every condition."""
    reports = {label: report.category_report(label) for label in report.model_labels}
    if not any(entry["scored_cases"] for entry in reports.values()):
        return '<p class="meta">No ground-truth categories to score.</p>'

    categories = [
        name
        for name in active_error_types([report])
        if any(entry["categories"].get(name, {}).get("support", 0) for entry in reports.values())
    ]
    head = "".join(
        f'<th class="num" colspan="3"><span class="swatch" style="background:var(--series-{slots[label]})">'
        f"</span> {esc(label)}</th>"
        for label in report.model_labels
    )
    subhead = "".join(
        '<th class="num">P</th><th class="num">R</th><th class="num">F1</th>' for _ in report.model_labels
    )
    rows = []
    for name in categories:
        cells = []
        support = 0
        for label in report.model_labels:
            entry = reports[label]["categories"].get(name, {})
            support = max(support, entry.get("support", 0))
            cells.append(
                f'<td class="num">{esc(pct(entry.get("precision"), 0))}</td>'
                f'<td class="num">{esc(pct(entry.get("recall"), 0))}</td>'
                f'<td class="num">{esc(pct(entry.get("f1"), 0))}</td>'
            )
        rows.append(f'<tr><td>{esc(type_label(name))}</td><td class="num">{support}</td>{"".join(cells)}</tr>')
    macro = "".join(
        f'<td class="num" colspan="3"><b>{esc(pct(reports[label]["macro_f1"], 0))}</b></td>'
        for label in report.model_labels
    )
    return (
        '<div class="scroll"><table>'
        f'<thead><tr><th rowspan="2">Category</th><th class="num" rowspan="2">Support</th>{head}</tr>'
        f"<tr>{subhead}</tr></thead>"
        f'<tbody>{"".join(rows)}'
        f'<tr><td><b>Macro F1</b></td><td class="num">—</td>{macro}</tr>'
        "</tbody></table></div>"
        '<p class="meta">Macro F1 averages the per-category F1 over categories the ground truth '
        "actually contains, so a single large category cannot carry the score. Support counts "
        "ground-truth cases; read any row with support below about five as indicative only.</p>"
    )


def _evidence_table(report: ExperimentReport, slots: Dict[str, int]) -> str:
    """How well each condition located the annotated failure lines."""
    reports = {label: report.evidence_report(label) for label in report.model_labels}
    if not any(entry["scorable_cases"] for entry in reports.values()):
        return (
            '<p class="meta">No case records ground-truth supporting lines, so evidence-line '
            "accuracy cannot be scored.</p>"
        )
    rows = []
    for label in report.model_labels:
        entry = reports[label]
        rows.append(
            f'<tr><td><span class="swatch" style="background:var(--series-{slots[label]})"></span> '
            f"{esc(label)}</td>"
            f'<td class="num">{entry["scorable_cases"]}</td>'
            f'<td class="num">{esc(pct(entry["mean_precision"], 0))}</td>'
            f'<td class="num">{esc(pct(entry["mean_recall"], 0))}</td>'
            f'<td class="num">{esc(pct(entry["mean_f1"], 0))}</td>'
            f'<td class="num">{esc(pct(entry["mean_jaccard"], 0))}</td></tr>'
        )
    return (
        '<div class="scroll"><table><thead><tr><th>Condition</th><th class="num">Scored cases</th>'
        '<th class="num">Precision</th><th class="num">Recall</th><th class="num">F1</th>'
        '<th class="num">Jaccard</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '<p class="meta">Measured against the annotated failure lines. This is different from the '
        "grounding score, which only checks that a cited line existed in the log the model was "
        "given — it says nothing about whether the line was the right one.</p>"
    )


def _ground_truth_panel(report: ExperimentReport) -> str:
    """State plainly whether this ground truth can carry an accuracy claim."""
    audit = report.ground_truth_audit
    if audit is None:
        return '<p class="meta">Ground truth was not audited for this experiment.</p>'
    verdict = (
        '<span class="outcome hit"><span class="mark">✓</span>evidence-backed and verified</span>'
        if audit.is_defensible
        else '<span class="outcome miss"><span class="mark">✗</span>not yet defensible for accuracy claims</span>'
    )
    stats = (
        f'<dl class="gt">'
        f"<dt>Cases</dt><dd>{audit.case_count}</dd>"
        f"<dt>Usable root causes</dt><dd>{audit.usable_root_causes}/{audit.case_count}</dd>"
        f"<dt>With supporting lines</dt><dd>{audit.cases_with_lines}/{audit.case_count}</dd>"
        f"<dt>Independently verified</dt><dd>{audit.verified_cases}/{audit.case_count}</dd>"
        f"<dt>Reviewers</dt><dd>{esc(', '.join(audit.annotators) or 'none recorded')}</dd>"
        f"<dt>Evidence methods</dt><dd>"
        f"{esc(', '.join(f'{k} ({v})' for k, v in audit.evidence_methods.items()) or 'none recorded')}</dd>"
        "</dl>"
    )
    findings = "".join(f"<li>{esc(line)}</li>" for line in audit.summary_lines())
    body = f"<ul>{findings}</ul>" if findings else '<p class="meta">Every requirement is met.</p>'
    return f"<p>{verdict}</p>{stats}{body}"


def _statistics(report: ExperimentReport) -> str:
    stats = report.statistical_tests
    if not stats:
        return (
            '<p class="meta">No usable <code>statistical_tests.json</code> for this run — '
            "see the data notes above.</p>"
        )
    mcnemar = stats.get("mcnemar", {})
    permutation = stats.get("permutation_test", {})
    bootstrap = stats.get("bootstrap_ci", {})
    rows = [
        ("Paired logs", stats.get("n_common_logs"), ""),
        ("McNemar χ²", mcnemar.get("chi2"), f"p = {mcnemar.get('p_value')}"),
        (
            "McNemar discordant pairs",
            f"n01 = {mcnemar.get('n01')}, n10 = {mcnemar.get('n10')}",
            mcnemar.get("verdict", ""),
        ),
        (
            "Permutation accuracy difference",
            (
                pct(permutation.get("observed_accuracy_diff"))
                if permutation.get("observed_accuracy_diff") is not None
                else None
            ),
            f"p = {permutation.get('p_value')}" if permutation.get("p_value") is not None else "",
        ),
    ]
    for label, interval in bootstrap.items():
        rows.append(
            (
                f"Bootstrap 95% CI — {label}",
                pct(interval.get("observed")),
                f"[{pct(interval.get('ci_lower'))}, {pct(interval.get('ci_upper'))}]",
            )
        )
    body = "".join(
        f'<tr><td>{esc(name)}</td><td class="num">{esc(value)}</td><td>{esc(note)}</td></tr>'
        for name, value, note in rows
        if value is not None
    )
    return f"<table><tbody>{body}</tbody></table>"


def _details(report: ExperimentReport, slots: Dict[str, int]) -> str:
    blocks = []
    for log_id in report.log_order:
        info = report.log_info.get(log_id, {})
        truth = report.ground_truth.get(log_id, {})
        diagnoses = []
        for label in report.model_labels:
            outcome = report.outcome(label, log_id)
            if outcome is None:
                continue
            if outcome.status != "success":
                body = f"<p><b>No diagnosis.</b> {esc(outcome.error)}</p>"
            else:
                lines_shown = ", ".join(str(line) for line in outcome.failure_lines[:20]) or "none"
                body = (
                    f"<p><b>{esc(type_label(outcome.predicted_error_type))}</b> · "
                    f"confidence {esc(pct(outcome.confidence, 0))} · "
                    f"grounding {esc(pct(outcome.grounding_score, 0))}</p>"
                    f"<p>{esc(outcome.root_cause)}</p>"
                    f"<p><b>Suggested fix:</b> {esc(outcome.suggested_fix)}</p>"
                    f'<p class="meta">Failure lines: {esc(lines_shown)}</p>'
                )
            diagnoses.append(
                f'<div class="diag" style="border-left-color:var(--series-{slots[label]})">'
                f"<h4>{esc(label)}</h4>{body}</div>"
            )
        blocks.append(
            "<details><summary>"
            f"{esc(info.get('repository') or log_id)} — {esc(info.get('workflow'))}"
            '</summary><div class="body">'
            f'<p class="meta">Ground truth: {esc(type_label(truth.get("actual_error_type")))} · '
            f'annotated lines {esc(", ".join(str(line) for line in truth.get("failure_lines", [])[:20]) or "none")}</p>'
            f'{"".join(diagnoses)}</div></details>'
        )
    return "".join(blocks)


def _cross_experiment(reports: List[ExperimentReport]) -> str:
    rows = cross_experiment_deltas(reports)
    if not rows:
        return ""
    by_model: Dict[str, List[dict]] = {}
    for row in rows:
        by_model.setdefault(row["model"], []).append(row)
    blocks = []
    for model, model_rows in by_model.items():
        experiments = [point["experiment"] for point in model_rows[0]["points"]]
        head = "".join(f'<th class="num">{esc(name)}</th>' for name in experiments)
        body = []
        for row in model_rows:
            cells = []
            for point in row["points"]:
                display = fmt_metric(point["value"], row["unit"])
                if point["is_baseline"] or point["delta"] is None:
                    note = '<span class="delta-flat">baseline</span>' if point["is_baseline"] else ""
                else:
                    delta = point["delta"]
                    improved = delta > 0 if row["higher_is_better"] else delta < 0
                    css = "delta-flat" if delta == 0 else ("delta-up" if improved else "delta-down")
                    sign = "+" if delta > 0 else ("−" if delta < 0 else "")
                    shown = (
                        f"{sign}{abs(delta) * 100:.1f} pp"
                        if row["unit"] == "ratio"
                        else f"{sign}{fmt_metric(abs(delta), row['unit'])}"
                    )
                    note = f'<span class="{css}">{esc(shown)}</span>'
                cells.append(f'<td class="num">{esc(display)}<div class="meta">{note}</div></td>')
            body.append(f"<tr><td>{esc(row['title'])}</td>{''.join(cells)}</tr>")
        blocks.append(
            "<div>"
            f"<h3>{esc(model)}</h3>"
            f'<div class="scroll"><table><thead><tr><th>Metric</th>{head}</tr></thead>'
            f"<tbody>{''.join(body)}</tbody></table></div></div>"
        )
    return (
        '<section class="card"><h2>Across runs</h2>'
        '<p class="sub">Each model measured against its earliest run in this comparison. '
        "Runs use different cohorts unless their input checksums match, so read these as engineering "
        "deltas, not as thesis evidence.</p>"
        f'{"".join(blocks)}</section>'
    )


def render_html(reports: List[ExperimentReport], title: str = "CI/CD diagnosis — model comparison") -> str:
    """Render one or more aligned experiments as a standalone HTML page."""
    if not reports:
        raise ValueError("At least one experiment report is required")

    all_labels: List[str] = []
    for report in reports:
        for label in report.model_labels:
            if label not in all_labels:
                all_labels.append(label)
    # Every experiment paints a condition with the same slot, so a model keeps
    # its colour across sections and across runs.
    slot_of = {label: index for index, label in enumerate(all_labels)}
    types = active_error_types(reports)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    sections = []
    for report in reports:
        ordered = report.model_labels
        issues = ""
        if report.issues:
            items = "".join(f"<li>{esc(issue)}</li>" for issue in report.issues)
            issues = f'<div class="card notes"><b>Data notes</b><ul>{items}</ul></div>'

        sections.append(
            f'<section id="{esc(report.experiment_id)}">'
            f'<div class="card"><h2>{esc(report.label)}</h2>'
            f'<p class="sub">{esc(report.run_context.get("input_file") or "")}</p>'
            f"{_context_chips(report)}</div>"
            f"{issues}"
            f'<div class="card"><h3>Scoreboard</h3>{_scoreboard(report, slot_of)}</div>'
            f'<div class="card"><h3>Metrics side by side</h3>'
            f"{_legend(ordered, slot_of)}{_metric_charts(report, slot_of)}</div>"
            f'<div class="card"><h3>Per-log outcomes</h3>{_outcome_matrix(report, slot_of)}</div>'
            f'<div class="card"><h3>Where the conditions disagree</h3>{_agreement(report)}</div>'
            f'<div class="card"><h3>Ground-truth quality</h3>{_ground_truth_panel(report)}</div>'
            f'<div class="card"><h3>Per-category effectiveness</h3>'
            f"{_category_table(report, slot_of)}</div>"
            f'<div class="card"><h3>Evidence-line accuracy</h3>{_evidence_table(report, slot_of)}</div>'
            f'<div class="card"><h3>Confusion matrices</h3>{_confusion(report, types)}</div>'
            f'<div class="card"><h3>Statistical tests</h3>{_statistics(report)}</div>'
            f'<div class="card"><h3>Diagnosis detail</h3>{_details(report, slot_of)}</div>'
            "</section>"
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title>"
        f"<style>{CSS}\n{_series_css(all_labels)}</style>"
        '</head><body><div class="wrap">'
        f'<header class="page"><h1>{esc(title)}</h1>'
        f'<p class="sub">{len(reports)} experiment(s) · {len(all_labels)} model condition(s) · '
        f"generated {esc(generated)}</p></header>"
        f"{_cross_experiment(reports)}"
        f"{''.join(sections)}"
        "<footer>Every metric on this page is recomputed from the per-log "
        "<code>results_&lt;model&gt;.json</code> files, so an interrupted run still reports correctly. "
        "Accuracy is measured against the blind ground truth, and an inference failure counts as incorrect."
        "</footer></div></body></html>"
    )
