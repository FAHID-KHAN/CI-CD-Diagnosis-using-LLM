#!/usr/bin/env bash
# Single entry point for the controlled study: run a stage, or check where the
# study actually stands.
#
# Every stage is judged by the files it leaves on disk, not by whether a command
# appeared to succeed, so `./run_workflow.sh status` is the truthful answer to
# "what have I actually got?" at any point.
#
#   ./run_workflow.sh                       prepare the cohort (default)
#   ./run_workflow.sh status                what is done, what is blocking
#   ./run_workflow.sh --help                every command

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
STUDY_CONFIG="configs/thesis_fresh_2026.yaml"
SMOKE_ROOT="data/studies/system_smoke_001"
SKIP_INSTALL=false
SKIP_LIVE_PREFLIGHT=false
RESUME=false
OVERWRITE_TRIAGE=false
FROM_STEP=1
STUDY_DIR=""
ANNOTATOR=""
VERIFIER=""
COMMAND=""

usage() {
    cat <<'USAGE'
Usage: ./run_workflow.sh [command] [options]

Commands:
  status            Report every stage from the files on disk, and what to do next
  check             Offline verification: lint, type check and the full test suite
  cohort            Prepare the thesis cohort: setup, preflight, collect, triage (default)
  smoke             Create the reproducible five-case engineering cohort
  annotate          Blind annotation of the thesis cohort        (needs ANNOTATOR=)
  annotate-smoke    Blind annotation of the smoke cohort         (needs ANNOTATOR=)
  recheck           Revisit only the cases the audit flags       (needs ANNOTATOR=)
  verify            Independent second review of the thesis cohort (needs VERIFIER=)
  verify-smoke      Independent second review of the smoke cohort  (needs VERIFIER=)
  audit             Ground-truth audit against the evidence requirements
  pilot             Paired five-case engineering run on the smoke cohort
  compare           Terminal comparison plus the self-contained HTML page
  engineering       smoke -> pilot -> compare, stopping at any human step
  final             The held-out paired experiment (refuses unless every gate passes)

Options:
  --skip-install          Reuse the existing virtual environment
  --skip-live-preflight   Run offline checks only
  --resume                Resume an interrupted collection
  --overwrite-triage      Intentionally regenerate derived triage files
  --from STEP             cohort only: 1=setup, 2=collection, 3=triage
  --study-config PATH     Use another versioned study protocol
  --study-dir PATH        Inspect or operate on another study directory
  ANNOTATOR=id            Reviewer identifier for annotate commands
  VERIFIER=id             Second-reviewer identifier for verify commands

Examples:
  ./run_workflow.sh status
  ./run_workflow.sh status --study-dir data/studies/system_smoke_001
  ./run_workflow.sh cohort --skip-install
  ./run_workflow.sh verify-smoke VERIFIER=mahade
USAGE
}

# The first bare word is the command; everything else keeps the original flags,
# so existing invocations such as `./run_workflow.sh --skip-install` still work.
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-install) SKIP_INSTALL=true; shift ;;
        --skip-live-preflight) SKIP_LIVE_PREFLIGHT=true; shift ;;
        --resume) RESUME=true; shift ;;
        --overwrite-triage) OVERWRITE_TRIAGE=true; shift ;;
        --from) FROM_STEP="$2"; shift 2 ;;
        --study-config) STUDY_CONFIG="$2"; shift 2 ;;
        --study-dir) STUDY_DIR="$2"; shift 2 ;;
        ANNOTATOR=*) ANNOTATOR="${1#ANNOTATOR=}"; shift ;;
        VERIFIER=*) VERIFIER="${1#VERIFIER=}"; shift ;;
        --help|-h) usage; exit 0 ;;
        -*) echo "Unknown option: $1"; usage; exit 1 ;;
        *)
            if [[ -n "${COMMAND}" ]]; then echo "Unexpected argument: $1"; usage; exit 1; fi
            COMMAND="$1"; shift ;;
    esac
done

cd "${PROJECT_DIR}"
COMMAND="${COMMAND:-cohort}"

step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }
fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

ensure_python() {
    if [[ "${COMMAND}" == "cohort" && "${SKIP_INSTALL}" == false && ${FROM_STEP} -le 1 ]]; then
        if [[ ! -d "${VENV_DIR}" ]]; then
            command -v python3.12 >/dev/null || fail "Python 3.12 is required to create .venv"
            python3.12 -m venv "${VENV_DIR}"
        fi
        "${VENV_DIR}/bin/python" -m pip install -e ".[dev]"
    fi
    [[ -x "${VENV_DIR}/bin/python" ]] || fail "Virtual environment missing. Run 'cohort' without --skip-install first."
    PYTHON="${VENV_DIR}/bin/python"
}

require_id() {
    [[ -n "$2" ]] || fail "$1 is required, e.g. ./run_workflow.sh ${COMMAND} $1=your-stable-id"
}

# Built without mapfile so the script runs on the bash 3.2 that ships with macOS.
run_status() {
    local args=(--study-config "${STUDY_CONFIG}")
    [[ -n "${STUDY_DIR}" ]] && args+=(--study-dir "${STUDY_DIR}")
    "${PYTHON}" automated_scripts/study_status.py "${args[@]}" "$@"
}

cmd_check() {
    step "Lint"
    "${PYTHON}" -m flake8 src/ automated_scripts/ tests/
    step "Type check"
    "${PYTHON}" -m mypy src/ || true
    step "Offline test suite"
    MPLCONFIGDIR="${TMPDIR:-/tmp}/cicd-matplotlib" "${PYTHON}" -m pytest tests/ -q
    printf '\nOffline verification passed.\n'
}

cmd_cohort() {
    if (( FROM_STEP <= 2 )); then
        step "Preflight"
        local preflight=(--study-config "${STUDY_CONFIG}")
        local collect=(--study-config "${STUDY_CONFIG}")
        if [[ "${RESUME}" == true ]]; then
            preflight+=(--allow-existing-output)
            collect+=(--resume)
        elif [[ "${SKIP_LIVE_PREFLIGHT}" == false ]]; then
            preflight+=(--live)
        fi
        "${PYTHON}" automated_scripts/preflight_study.py "${preflight[@]}"
        step "Collection"
        "${PYTHON}" automated_scripts/data_collection.py "${collect[@]}"
    fi
    if (( FROM_STEP <= 3 )); then
        step "Triage"
        local triage=(--study-config "${STUDY_CONFIG}")
        [[ "${OVERWRITE_TRIAGE}" == true ]] && triage+=(--overwrite)
        "${PYTHON}" automated_scripts/triage.py "${triage[@]}"
    fi
    run_status || true
}

cmd_annotate() {
    require_id ANNOTATOR "${ANNOTATOR}"
    local args=(--study-config "${STUDY_CONFIG}" --mode annotate --annotator "${ANNOTATOR}")
    [[ -n "$1" ]] && args+=(--study-dir "$1")
    "${PYTHON}" automated_scripts/annotate_blind.py "${args[@]}"
}

cmd_recheck() {
    require_id ANNOTATOR "${ANNOTATOR}"
    local args=(--study-config "${STUDY_CONFIG}" --mode recheck --annotator "${ANNOTATOR}")
    [[ -n "${STUDY_DIR}" ]] && args+=(--study-dir "${STUDY_DIR}")
    "${PYTHON}" automated_scripts/annotate_blind.py "${args[@]}"
}

cmd_verify() {
    require_id VERIFIER "${VERIFIER}"
    local args=(--study-config "${STUDY_CONFIG}" --mode verify --annotator "${VERIFIER}")
    [[ -n "$1" ]] && args+=(--study-dir "$1")
    "${PYTHON}" automated_scripts/annotate_blind.py "${args[@]}"
}

cmd_pilot() {
    step "Paired pilot on the smoke cohort"
    "${PYTHON}" automated_scripts/benchmark_models.py \
        --input "${SMOKE_ROOT}/triaged/eligible_logs.json" \
        --ground-truth "${SMOKE_ROOT}/ground_truth/ground_truth.json" \
        --pilot \
        --output-dir "${SMOKE_ROOT}/experiments/pilot_002"
}

cmd_final() {
    step "Held-out gate"
    # Every gate is checked before the first model call, because a refusal after
    # the run has started has already spent the money and read the cases.
    "${PYTHON}" automated_scripts/study_status.py \
        --study-config "${STUDY_CONFIG}" \
        --require "Ground truth" --require "Held-out separation" \
        || fail "The held-out experiment is blocked. Fix the stages marked above first."

    local study_root
    study_root="$("${PYTHON}" -c "
import sys; sys.path.insert(0, '.')
from automated_scripts.study_utils import load_study_config, study_directory
config, _ = load_study_config('${STUDY_CONFIG}')
print(study_directory(config))")"

    step "Final paired experiment"
    "${PYTHON}" automated_scripts/benchmark_models.py \
        --input "${study_root}/triaged/eligible_logs.json" \
        --ground-truth "${study_root}/ground_truth/ground_truth.json" \
        --output-dir "${study_root}/experiments/final_001"
}

cmd_engineering() {
    if [[ ! -f "${SMOKE_ROOT}/triaged/eligible_logs.json" ]]; then
        step "Smoke cohort"
        "${PYTHON}" automated_scripts/create_smoke_cohort.py
    else
        printf '\nSmoke cohort already exists; keeping it.\n'
    fi
    if [[ ! -f "${SMOKE_ROOT}/ground_truth/ground_truth.json" ]]; then
        printf '\nSTOP: the smoke cohort has no ground truth yet.\n'
        printf 'Annotation is a human step. Run:\n'
        printf '  ./run_workflow.sh annotate-smoke ANNOTATOR=your-stable-id\n\n'
        exit 2
    fi
    cmd_pilot
    step "Comparison"
    "${PYTHON}" automated_scripts/compare_reports.py --experiment "${SMOKE_ROOT}/experiments/pilot_002"
    STUDY_DIR="${SMOKE_ROOT}"
    run_status || true
}

ensure_python

case "${COMMAND}" in
    status)         run_status ;;
    check)          cmd_check ;;
    cohort)         cmd_cohort ;;
    smoke)          "${PYTHON}" automated_scripts/create_smoke_cohort.py ;;
    annotate)       cmd_annotate "" ;;
    annotate-smoke) cmd_annotate "${SMOKE_ROOT}" ;;
    recheck)        cmd_recheck ;;
    verify)         cmd_verify "" ;;
    verify-smoke)   cmd_verify "${SMOKE_ROOT}" ;;
    audit)          "${PYTHON}" automated_scripts/compare_reports.py --audit-only ;;
    pilot)          cmd_pilot ;;
    compare)        "${PYTHON}" automated_scripts/compare_reports.py ;;
    engineering)    cmd_engineering ;;
    final)          cmd_final ;;
    *)              echo "Unknown command: ${COMMAND}"; usage; exit 1 ;;
esac
