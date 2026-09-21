#!/usr/bin/env python3
"""Render the canonical project architecture as a standalone PNG."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture.png"

COLORS = {
    "source": "#E8F1FB",
    "process": "#EAF6EF",
    "model": "#F3EBFA",
    "data": "#FFF3DD",
    "evaluation": "#FDEBEC",
    "border": "#344054",
    "text": "#172B4D",
    "muted": "#667085",
    "arrow": "#475467",
}


def node(ax, x, y, text, kind="process", width=1.65, height=0.62):
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.04,rounding_size=0.08",
        linewidth=1.1,
        edgecolor=COLORS["border"],
        facecolor=COLORS[kind],
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=8.6,
        color=COLORS["text"],
        fontweight="medium",
        zorder=4,
    )
    return {"x": x, "y": y, "w": width, "h": height}


def arrow(ax, start, end, label=None, dashed=False, bend=0.0):
    x1 = start["x"] + (start["w"] / 2 if end["x"] >= start["x"] else -start["w"] / 2)
    x2 = end["x"] - (end["w"] / 2 if end["x"] >= start["x"] else -end["w"] / 2)
    y1, y2 = start["y"], end["y"]
    connection = f"arc3,rad={bend}" if bend else "arc3"
    patch = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle="-|>",
        mutation_scale=11,
        linewidth=1.15,
        linestyle="--" if dashed else "-",
        color=COLORS["arrow"],
        connectionstyle=connection,
        zorder=2,
    )
    ax.add_patch(patch)
    if label:
        ax.text(
            (x1 + x2) / 2,
            (y1 + y2) / 2 + 0.18,
            label,
            ha="center",
            va="bottom",
            fontsize=7.2,
            color=COLORS["muted"],
        )


def vertical_arrow(ax, start, end, label=None, dashed=False):
    direction = 1 if end["y"] >= start["y"] else -1
    y1 = start["y"] + direction * start["h"] / 2
    y2 = end["y"] - direction * end["h"] / 2
    patch = FancyArrowPatch(
        (start["x"], y1),
        (end["x"], y2),
        arrowstyle="-|>",
        mutation_scale=11,
        linewidth=1.15,
        linestyle="--" if dashed else "-",
        color=COLORS["arrow"],
        connectionstyle="arc3",
        zorder=2,
    )
    ax.add_patch(patch)
    if label:
        ax.text(
            start["x"] + 0.16,
            (y1 + y2) / 2,
            label,
            ha="left",
            va="center",
            fontsize=7.2,
            color=COLORS["muted"],
        )


def section(ax, y, title, subtitle):
    ax.text(0.35, y, title, fontsize=15, fontweight="bold", color=COLORS["text"], va="top")
    ax.text(0.35, y - 0.36, subtitle, fontsize=8.8, color=COLORS["muted"], va="top")


def render():
    fig, ax = plt.subplots(figsize=(18, 11), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 11)
    ax.axis("off")

    ax.text(
        0.35,
        10.65,
        "CI/CD Failure Diagnosis — Architecture and Thesis Dataflow",
        fontsize=20,
        fontweight="bold",
        color=COLORS["text"],
        va="top",
    )
    ax.text(
        0.35,
        10.17,
        "The model is a replaceable component inside the evaluated diagnostic system.",
        fontsize=10,
        color=COLORS["muted"],
        va="top",
    )

    section(
        ax,
        9.65,
        "A. Current end-to-end system",
        "Dataset construction → controlled diagnosis → evidence grounding → research evaluation",
    )

    github = node(ax, 0.9, 8.55, "GitHub Actions\nAPI", "source", 1.35)
    collect = node(ax, 2.55, 8.55, "Collect failed\nworkflow logs")
    raw = node(ax, 4.25, 8.55, "Immutable raw\nlogs + metadata", "data")
    triage = node(ax, 5.95, 8.55, "Eligibility, noise\nfiltering, deduplication")
    cohort = node(ax, 7.75, 8.55, "Eligible study\ncohort", "data", 1.45)
    filtering = node(ax, 9.35, 8.55, "Deterministic\nLogFilter")
    prompt = node(ax, 11.05, 8.55, "Shared prompt +\nstrict JSON schema")
    proprietary = node(ax, 12.85, 9.0, "Proprietary\nmodel", "model", 1.35)
    open_weights = node(ax, 12.85, 8.08, "Open-weights\nmodel", "model", 1.35)
    grounded = node(ax, 14.65, 8.55, "Structured result +\nevidence grounding")
    predictions = node(ax, 16.45, 8.55, "Predictions +\nrun metadata", "data", 1.5)

    for start, end in [
        (github, collect),
        (collect, raw),
        (raw, triage),
        (triage, cohort),
        (cohort, filtering),
        (filtering, prompt),
    ]:
        arrow(ax, start, end)
    arrow(ax, prompt, proprietary, bend=-0.08)
    arrow(ax, prompt, open_weights, bend=0.08)
    arrow(ax, proprietary, grounded, bend=0.08)
    arrow(ax, open_weights, grounded, bend=-0.08)
    arrow(ax, grounded, predictions)

    excluded = node(ax, 5.95, 7.23, "Excluded cases +\nrecorded reasons", "data", 1.55)
    vertical_arrow(ax, triage, excluded)

    ground_truth = node(ax, 10.7, 7.02, "Blind human\nground truth", "source", 1.45)
    baselines = node(ax, 10.7, 6.25, "Rule-based\nbaselines", "source", 1.35)
    evaluation = node(ax, 13.45, 6.65, "Scoring +\nstatistical analysis", "evaluation", 1.65)
    findings = node(ax, 16.0, 6.65, "Overall, model and\ncategory findings", "evaluation", 2.15)
    arrow(ax, ground_truth, evaluation, bend=-0.08)
    arrow(ax, baselines, evaluation, bend=0.08)
    arrow(ax, predictions, evaluation, bend=0.18)
    arrow(ax, evaluation, findings)

    ax.plot([0.35, 17.65], [5.75, 5.75], color="#D0D5DD", linewidth=1)

    section(
        ax,
        5.45,
        "B. Controlled thesis execution",
        "The final cohort remains frozen while annotation, pilot and paired model runs are performed.",
    )

    protocol = node(ax, 0.95, 4.35, "Versioned study\nprotocol", "source", 1.55)
    preflight = node(ax, 2.85, 4.35, "Offline preflight +\none-log smoke test")
    fixed_collect = node(ax, 4.85, 4.35, "Fixed six-repository\ncollection", "process", 1.85)
    stored = node(ax, 7.0, 4.35, "Raw logs, manifest\nand SHA-256", "data", 1.75)
    controlled_triage = node(ax, 9.05, 4.35, "Deterministic\ntriage")
    frozen = node(ax, 10.9, 4.35, "Frozen eligible\ncohort", "data", 1.5)

    for start, end in [
        (protocol, preflight),
        (preflight, fixed_collect),
        (fixed_collect, stored),
        (stored, controlled_triage),
        (controlled_triage, frozen),
    ]:
        arrow(ax, start, end)

    audit = node(ax, 9.05, 3.18, "Exclusion audit\ntrail", "data", 1.45)
    vertical_arrow(ax, controlled_triage, audit)

    annotation = node(ax, 12.75, 4.35, "Blind ground-truth\nannotation", "source", 1.65)
    pilot = node(ax, 14.65, 4.35, "Five-log paired\npilot", "process", 1.45)
    final_run = node(ax, 16.45, 4.35, "Final paired\nexperiment", "model", 1.5)
    arrow(ax, frozen, annotation)
    arrow(ax, annotation, pilot)
    arrow(ax, pilot, final_run)

    paired = node(ax, 12.65, 2.35, "Paired conditions\nproprietary | open-weights", "model", 2.05)
    results = node(ax, 15.0, 2.35, "Append-only results\nwith full lineage", "data", 1.7)
    thesis = node(ax, 17.0, 2.35, "Thesis tables,\nfigures and findings", "evaluation", 1.55)
    arrow(ax, final_run, paired, bend=0.18)
    arrow(ax, paired, results)
    arrow(ax, results, thesis)

    ax.text(
        0.45,
        1.45,
        "Legend",
        fontsize=9,
        fontweight="bold",
        color=COLORS["text"],
    )
    legend_x = 2.05
    for label, kind in [
        ("Source / human input", "source"),
        ("Deterministic process", "process"),
        ("Model condition", "model"),
        ("Stored research data", "data"),
        ("Evaluation output", "evaluation"),
    ]:
        swatch = FancyBboxPatch(
            (legend_x, 1.28),
            0.28,
            0.22,
            boxstyle="round,pad=0.02,rounding_size=0.03",
            facecolor=COLORS[kind],
            edgecolor=COLORS["border"],
            linewidth=0.8,
        )
        ax.add_patch(swatch)
        ax.text(legend_x + 0.38, 1.39, label, fontsize=8, va="center", color=COLORS["muted"])
        legend_x += 2.9

    ax.text(
        0.45,
        0.7,
        "Scope boundary: RAG comparison, human-versus-LLM study, dashboards and additional model families remain future work.",
        fontsize=8.7,
        color=COLORS["muted"],
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, bbox_inches="tight", pad_inches=0.2, facecolor="white")
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    render()
