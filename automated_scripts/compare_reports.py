#!/usr/bin/env python3
"""Compare the reports an experiment run produced, in the terminal and visually.

A benchmark run leaves one ``results_<model>.json`` per condition next to its
run-level summaries. This script aligns any number of those directories on log
id and ground truth, prints a comparison table, and writes one self-contained
HTML page that can be opened directly or archived with the run.

Examples::

    python automated_scripts/compare_reports.py --list
    python automated_scripts/compare_reports.py            # every experiment found
    python automated_scripts/compare_reports.py \\
        --experiment data/studies/system_smoke_001/experiments/pilot_002 --open
"""

import argparse
import os
import sys
import webbrowser
from datetime import datetime

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from src.evaluation.comparison_view import fmt_ms, fmt_usd, pct, render_html, type_label
from src.evaluation.report_comparison import (
    build_comparison,
    discover_experiments,
    load_experiment,
    pairwise_agreements,
)

DEFAULT_STUDIES_ROOT = "data/studies"


def parse_args():
    parser = argparse.ArgumentParser(description="Compare generated diagnosis reports")
    parser.add_argument(
        "--experiment",
        action="append",
        default=[],
        metavar="DIR",
        help="Experiment directory to include; repeat for a cross-run comparison",
    )
    parser.add_argument(
        "--studies-root",
        default=DEFAULT_STUDIES_ROOT,
        help=f"Where to look for experiments when none are named (default: {DEFAULT_STUDIES_ROOT})",
    )
    parser.add_argument("--ground-truth", help="Override the ground-truth file used for every experiment")
    parser.add_argument("--output", help="HTML output path")
    parser.add_argument("--json", dest="json_output", help="Also write the aligned comparison data as JSON")
    parser.add_argument("--list", action="store_true", help="List the experiments that were found and exit")
    parser.add_argument("--no-html", action="store_true", help="Print the terminal comparison only")
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Report ground-truth quality against the kickoff evidence requirements, then exit",
    )
    parser.add_argument("--open", action="store_true", help="Open the rendered page in the default browser")
    return parser.parse_args()


def resolve_experiments(args):
    """Use the named directories, or every experiment under the studies root."""
    if args.experiment:
        missing = [path for path in args.experiment if not os.path.isdir(path)]
        if missing:
            print(f"ERROR: Experiment directory does not exist: {', '.join(missing)}")
            sys.exit(1)
        return args.experiment
    found = discover_experiments(args.studies_root)
    if not found:
        print(f"ERROR: No experiments with results files were found under {args.studies_root}/")
        print("       Run 'make pilot' first, or pass --experiment DIR.")
        sys.exit(1)
    return found


def default_output(reports):
    if len(reports) == 1:
        return os.path.join(reports[0].path, "comparison_view.html")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(DEFAULT_STUDIES_ROOT, f"comparison_view_{stamp}.html")


def print_ground_truth_audit(report):
    """Terminal view of whether this ground truth can carry an accuracy claim."""
    audit = report.ground_truth_audit
    print()
    print("=" * 96)
    print(f"  GROUND TRUTH — {report.label}")
    print("=" * 96)
    if audit is None:
        print("  Not audited.")
        return
    print(f"  File: {audit.path or 'none found'}")
    verdict = "defensible" if audit.is_defensible else "NOT defensible for accuracy claims"
    print(f"  Verdict: {verdict}")
    print(f"  Cases                    : {audit.case_count}")
    print(f"  Usable root causes       : {audit.usable_root_causes}/{audit.case_count}")
    print(f"  With supporting lines    : {audit.cases_with_lines}/{audit.case_count}")
    print(f"  Independently verified   : {audit.verified_cases}/{audit.case_count}")
    print(f"  Reviewers                : {', '.join(audit.annotators) or 'none recorded'}")
    methods = ", ".join(f"{name} ({count})" for name, count in audit.evidence_methods.items())
    print(f"  Evidence methods         : {methods or 'none recorded'}")
    lines = audit.summary_lines()
    if lines:
        print()
        for line in lines:
            print(f"    {line}")
    print()


def print_report(report):
    """Terminal view of one experiment: metrics, then the per-log pairing."""
    print()
    print("=" * 96)
    print(f"  {report.label}")
    print("=" * 96)
    context = report.run_context
    print(
        f"  logs {len(report.log_order)}  ·  mode {'pilot' if context.get('pilot') else 'full run'}"
        f"  ·  reasoning effort {context.get('reasoning_effort')}  ·  started {context.get('run_started_at_utc')}"
    )
    print()

    header = (
        f"  {'Model':<32} {'OK/All':>8} {'Accuracy':>9} {'Grounding':>10} "
        f"{'Halluc.':>8} {'Avg time':>11} {'Cost/diag':>10}"
    )
    print(header)
    print("  " + "-" * 92)
    for label in report.model_labels:
        metrics = report.metrics.get(label, {})
        completion = f"{metrics.get('successful_logs', 0)}/{metrics.get('total_logs', 0)}"
        print(
            f"  {label:<32} {completion:>8} {pct(metrics.get('error_type_accuracy'), 0):>9} "
            f"{pct(metrics.get('mean_grounding_score'), 0):>10} {pct(metrics.get('hallucination_rate'), 0):>8} "
            f"{fmt_ms(metrics.get('avg_execution_time_ms')):>11} {fmt_usd(metrics.get('cost_per_diagnosis_usd')):>10}"
        )

    if report.log_order and report.model_labels:
        print()
        print("  Per-log outcomes (✓ matches ground truth, ✗ does not)")
        print("  " + "-" * 92)
        width = 26
        columns = "".join(f"{label[:width]:<{width + 2}}" for label in report.model_labels)
        print(f"  {'Log':<30}{'Ground truth':<22}{columns}")
        for log_id in report.log_order:
            info = report.log_info.get(log_id, {})
            truth = report.ground_truth.get(log_id, {})
            cells = ""
            for label in report.model_labels:
                outcome = report.outcome(label, log_id)
                if outcome is None:
                    cells += f"{'— not run':<{width + 2}}"
                    continue
                mark = "·" if outcome.correct is None else ("✓" if outcome.correct else "✗")
                cells += f"{(mark + ' ' + type_label(outcome.predicted_error_type))[:width]:<{width + 2}}"
            name = (info.get("repository") or log_id)[:28]
            print(f"  {name:<30}{type_label(truth.get('actual_error_type'))[:20]:<22}{cells}")

    for pair in pairwise_agreements(report):
        print()
        print(f"  {pair.model_a}  vs  {pair.model_b}")
        print(
            f"    both correct {pair.both_correct}  ·  only {pair.model_a} {pair.only_a_correct}"
            f"  ·  only {pair.model_b} {pair.only_b_correct}  ·  both wrong {pair.both_wrong}"
        )
        agreement = pair.same_prediction / pair.n_common if pair.n_common else None
        print(
            f"    same predicted type on {pair.same_prediction}/{pair.n_common} shared logs " f"({pct(agreement, 0)})"
        )

    stats = report.statistical_tests
    if stats:
        mcnemar = stats.get("mcnemar", {})
        print()
        print(f"  McNemar: chi2 = {mcnemar.get('chi2')}, p = {mcnemar.get('p_value')} — {mcnemar.get('verdict')}")

    if report.issues:
        print()
        print("  DATA NOTES")
        for issue in report.issues:
            print(f"    ! {issue}")
    print()


def main():
    args = parse_args()
    paths = resolve_experiments(args)

    if args.list:
        print(f"\n  Experiments found under {args.studies_root}/:\n")
        for path in paths:
            report = load_experiment(path, args.ground_truth)
            models = ", ".join(report.model_labels) or "no readable results"
            print(f"    {path}\n      {len(report.log_order)} logs · {models}")
        print()
        return

    reports = [load_experiment(path, args.ground_truth) for path in paths]

    if args.audit_only:
        for report in reports:
            print_ground_truth_audit(report)
        return

    for report in reports:
        print_ground_truth_audit(report)
        print_report(report)

    if args.json_output:
        import json

        os.makedirs(os.path.dirname(os.path.abspath(args.json_output)), exist_ok=True)
        with open(args.json_output, "w") as handle:
            json.dump(build_comparison(reports), handle, indent=2)
        print(f"  Comparison data: {args.json_output}")

    if args.no_html:
        return

    output = args.output or default_output(reports)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w") as handle:
        handle.write(render_html(reports))
    print(f"  Visual comparison: {output}")
    print()

    if args.open:
        webbrowser.open(f"file://{os.path.abspath(output)}")


if __name__ == "__main__":
    main()
