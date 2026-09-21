#!/usr/bin/env bash
# Prepare the controlled thesis cohort: preflight, collect, then triage.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
STUDY_CONFIG="configs/thesis_fresh_2026.yaml"
SKIP_INSTALL=false
SKIP_LIVE_PREFLIGHT=false
RESUME=false
OVERWRITE_TRIAGE=false
FROM_STEP=1

usage() {
    echo "Usage: ./run_workflow.sh [options]"
    echo "  --skip-install          Reuse the existing virtual environment"
    echo "  --skip-live-preflight   Run offline checks only"
    echo "  --resume                Resume an interrupted collection"
    echo "  --overwrite-triage      Intentionally regenerate derived triage files"
    echo "  --from STEP             Start from 1=setup, 2=collection, or 3=triage"
    echo "  --study-config PATH     Use another versioned study protocol"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-install) SKIP_INSTALL=true; shift ;;
        --skip-live-preflight) SKIP_LIVE_PREFLIGHT=true; shift ;;
        --resume) RESUME=true; shift ;;
        --overwrite-triage) OVERWRITE_TRIAGE=true; shift ;;
        --from) FROM_STEP="$2"; shift 2 ;;
        --study-config) STUDY_CONFIG="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

cd "${PROJECT_DIR}"

if (( FROM_STEP <= 1 )); then
    if [[ "${SKIP_INSTALL}" == false ]]; then
        if [[ ! -d "${VENV_DIR}" ]]; then
            command -v python3.12 >/dev/null || {
                echo "Python 3.12 is required to create .venv"; exit 1;
            }
            python3.12 -m venv "${VENV_DIR}"
        fi
        "${VENV_DIR}/bin/python" -m pip install -e ".[dev]"
    fi
fi

[[ -x "${VENV_DIR}/bin/python" ]] || {
    echo "Virtual environment missing. Run without --skip-install first."; exit 1;
}
PYTHON="${VENV_DIR}/bin/python"

if (( FROM_STEP <= 2 )); then
    PREFLIGHT_ARGS=(--study-config "${STUDY_CONFIG}")
    COLLECT_ARGS=(--study-config "${STUDY_CONFIG}")
    if [[ "${RESUME}" == true ]]; then
        PREFLIGHT_ARGS+=(--allow-existing-output)
        COLLECT_ARGS+=(--resume)
    elif [[ "${SKIP_LIVE_PREFLIGHT}" == false ]]; then
        PREFLIGHT_ARGS+=(--live)
    fi
    "${PYTHON}" automated_scripts/preflight_study.py "${PREFLIGHT_ARGS[@]}"
    "${PYTHON}" automated_scripts/data_collection.py "${COLLECT_ARGS[@]}"
fi

if (( FROM_STEP <= 3 )); then
    TRIAGE_ARGS=(--study-config "${STUDY_CONFIG}")
    if [[ "${OVERWRITE_TRIAGE}" == true ]]; then
        TRIAGE_ARGS+=(--overwrite)
    fi
    "${PYTHON}" automated_scripts/triage.py "${TRIAGE_ARGS[@]}"
fi

echo "Controlled cohort preparation complete."
echo "Next: make annotate ANNOTATOR=<stable-id>"
