#!/usr/bin/env bash
# ==========================================================================
#  CI/CD Diagnosis LLM - Full Workflow Runner
# ==========================================================================
#
#  Runs the complete 6-step pipeline:
#    1. Install dependencies
#    2. Collect CI/CD logs from GitHub Actions
#    3. Triage collected logs (filter noise)
#    4. Start diagnostic API server
#    5. Diagnose logs via the API
#    6. Annotate diagnosed logs (interactive ground truth)
#    7. Run demonstration evaluation (report + charts)
#
#  Usage:
#    ./run_workflow.sh                 # Run full pipeline
#    ./run_workflow.sh --skip-install  # Skip pip install step
#    ./run_workflow.sh --skip-collect  # Skip collection (use existing logs)
#    ./run_workflow.sh --skip-annotate # Skip interactive annotation
#    ./run_workflow.sh --from 4        # Resume from step 4 (start API + diagnose + ...)
#    ./run_workflow.sh --only 7        # Run only step 7 (evaluate)
#    ./run_workflow.sh --help          # Show this help
#
# ==========================================================================

set -euo pipefail

# ── Colours & helpers ─────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_PORT=8000
API_URL="http://localhost:${API_PORT}"
API_PID=""
VENV_DIR="${PROJECT_DIR}/.venv"

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
banner()  {
    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  Step $1: $2${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ── Cleanup on exit ───────────────────────────────────────────────────────
cleanup() {
    if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
        info "Shutting down API server (PID ${API_PID})..."
        kill "${API_PID}" 2>/dev/null || true
        wait "${API_PID}" 2>/dev/null || true
        success "API server stopped."
    fi
}
trap cleanup EXIT INT TERM

# ── Parse arguments ───────────────────────────────────────────────────────
SKIP_INSTALL=false
SKIP_COLLECT=false
SKIP_ANNOTATE=false
FROM_STEP=1
ONLY_STEP=0
MODEL="gpt-4o-mini"
PROVIDER="openai"
LIMIT=""

usage() {
    head -25 "$0" | tail -18 | sed 's/^#//;s/^ //'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-install)  SKIP_INSTALL=true; shift ;;
        --skip-collect)  SKIP_COLLECT=true; shift ;;
        --skip-annotate) SKIP_ANNOTATE=true; shift ;;
        --from)          FROM_STEP="$2"; shift 2 ;;
        --only)          ONLY_STEP="$2"; shift 2 ;;
        --model)         MODEL="$2"; shift 2 ;;
        --provider)      PROVIDER="$2"; shift 2 ;;
        --limit)         LIMIT="$2"; shift 2 ;;
        --port)          API_PORT="$2"; API_URL="http://localhost:${API_PORT}"; shift 2 ;;
        --help|-h)       usage ;;
        *) warn "Unknown option: $1"; shift ;;
    esac
done

should_run() {
    local step=$1
    if [[ ${ONLY_STEP} -ne 0 ]]; then
        [[ ${step} -eq ${ONLY_STEP} ]]
    else
        [[ ${step} -ge ${FROM_STEP} ]]
    fi
}

cd "${PROJECT_DIR}"

echo -e "${BOLD}"
echo "  _____ ___  ___ ___    ___  _                            _"
echo " / ____|_ _|/ __| _ \\  |   \\(_)__ _ __ _ _ _  ___ ___ __(_)___"
echo "| |     | || (__|  _/  | |) | / _\` / _\` | ' \\/ _ (_-</ _| (_-<"
echo "|_|     |_| \\___|_|    |___/|_\\__,_\\__, |_||_\\___/__/\\__|_/__/"
echo "                                   |___/"
echo -e "${NC}"
echo -e "  Model: ${PROVIDER}/${MODEL}   Port: ${API_PORT}"
echo ""

# ══════════════════════════════════════════════════════════════════════════
# Step 1: Install dependencies
# ══════════════════════════════════════════════════════════════════════════
if should_run 1; then
    banner 1 "Install Dependencies"

    if [[ "${SKIP_INSTALL}" == true ]]; then
        warn "Skipping install (--skip-install)."
    else
        # Create venv if it doesn't exist
        if [[ ! -d "${VENV_DIR}" ]]; then
            info "Creating virtual environment at ${VENV_DIR}..."
            python3 -m venv "${VENV_DIR}"
        fi

        # Activate venv
        # shellcheck disable=SC1091
        source "${VENV_DIR}/bin/activate"

        info "Installing project in editable mode..."
        pip install -e . --quiet 2>&1 | tail -3
        success "Dependencies installed."
    fi
else
    info "Skipping step 1 (install)."
fi

# Ensure venv is active for all subsequent steps
if [[ -d "${VENV_DIR}" ]]; then
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
fi

# ══════════════════════════════════════════════════════════════════════════
# Step 2: Collect CI/CD logs
# ══════════════════════════════════════════════════════════════════════════
if should_run 2; then
    banner 2 "Collect CI/CD Logs from GitHub Actions"

    if [[ "${SKIP_COLLECT}" == true ]]; then
        warn "Skipping collection (--skip-collect)."
    else
        # Check for GitHub token
        if [[ -z "${GITHUB_TOKEN:-}" ]]; then
            if [[ -f "${PROJECT_DIR}/.env" ]] && grep -q "GITHUB_TOKEN" "${PROJECT_DIR}/.env"; then
                info "Loading GITHUB_TOKEN from .env file..."
                # shellcheck disable=SC1091
                set -a; source "${PROJECT_DIR}/.env"; set +a
            else
                fail "GITHUB_TOKEN not set. Export it or add to .env file."
            fi
        fi

        RAW_LOG_FILE="${PROJECT_DIR}/data/raw_logs/github_actions/batch1.json"
        if [[ -f "${RAW_LOG_FILE}" ]]; then
            EXISTING_COUNT=$(python3 -c "import json; print(len(json.load(open('${RAW_LOG_FILE}'))))" 2>/dev/null || echo 0)
            info "Found existing batch1.json with ${EXISTING_COUNT} logs."
            echo -n "  Re-collect? (y/N): "
            read -r ans
            if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
                success "Keeping existing logs."
            else
                info "Running data collection..."
                python automated_scripts/data_collection.py
                success "Data collection complete."
            fi
        else
            info "Running data collection..."
            python automated_scripts/data_collection.py
            success "Data collection complete."
        fi
    fi
else
    info "Skipping step 2 (collect)."
fi

# ══════════════════════════════════════════════════════════════════════════
# Step 3: Triage collected logs
# ══════════════════════════════════════════════════════════════════════════
if should_run 3; then
    banner 3 "Triage Collected Logs"

    RAW_LOG_FILE="${PROJECT_DIR}/data/raw_logs/github_actions/batch1.json"
    TRIAGED_FILE="${PROJECT_DIR}/data/raw_logs/github_actions/batch1_triaged.json"

    if [[ ! -f "${RAW_LOG_FILE}" ]]; then
        fail "No raw logs found at ${RAW_LOG_FILE}. Run step 2 first."
    fi

    info "Running triage on collected logs..."
    python automated_scripts/triage.py --input "${RAW_LOG_FILE}"

    if [[ -f "${TRIAGED_FILE}" ]]; then
        TRIAGED_COUNT=$(python3 -c "import json; print(len(json.load(open('${TRIAGED_FILE}'))))")
        success "Triage complete: ${TRIAGED_COUNT} logs passed filters."
    else
        fail "Triage did not produce output file."
    fi
else
    info "Skipping step 3 (triage)."
fi

# ══════════════════════════════════════════════════════════════════════════
# Step 4: Start API server
# ══════════════════════════════════════════════════════════════════════════
start_api() {
    # Kill any existing process on the port
    if lsof -ti:"${API_PORT}" &>/dev/null; then
        warn "Port ${API_PORT} in use. Killing existing process..."
        lsof -ti:"${API_PORT}" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    # Check for OpenAI key
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        if [[ -f "${PROJECT_DIR}/.env" ]] && grep -q "OPENAI_API_KEY" "${PROJECT_DIR}/.env"; then
            set -a; source "${PROJECT_DIR}/.env"; set +a
        else
            fail "OPENAI_API_KEY not set. Export it or add to .env file."
        fi
    fi

    info "Starting API server on port ${API_PORT}..."
    uvicorn src.api.main:app --host 0.0.0.0 --port "${API_PORT}" \
        --log-level warning &>/dev/null &
    API_PID=$!

    # Wait for server to be ready
    local retries=0
    local max_retries=30
    while ! curl -s "${API_URL}/health" &>/dev/null; do
        retries=$((retries + 1))
        if [[ ${retries} -ge ${max_retries} ]]; then
            fail "API server failed to start after ${max_retries} seconds."
        fi
        if ! kill -0 "${API_PID}" 2>/dev/null; then
            fail "API server process died. Check logs or run manually: uvicorn src.api.main:app --port ${API_PORT}"
        fi
        sleep 1
    done

    success "API server running (PID ${API_PID}, port ${API_PORT})."
}

if should_run 4; then
    banner 4 "Start Diagnostic API Server"
    start_api
else
    info "Skipping step 4 (API server)."
    # If we're running step 5+, make sure API is reachable
    if should_run 5 || should_run 6; then
        if ! curl -s "${API_URL}/health" &>/dev/null; then
            warn "API not reachable at ${API_URL}. Starting it now..."
            start_api
        else
            success "API already running at ${API_URL}."
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# Step 5: Diagnose logs
# ══════════════════════════════════════════════════════════════════════════
if should_run 5; then
    banner 5 "Diagnose Logs via API"

    DIAGNOSE_ARGS=(
        --model "${MODEL}"
        --provider "${PROVIDER}"
        --api-url "${API_URL}"
        --yes
    )
    if [[ -n "${LIMIT}" ]]; then
        DIAGNOSE_ARGS+=(--limit "${LIMIT}")
    fi

    info "Sending logs to diagnostic API..."
    python automated_scripts/diagnose_logs.py "${DIAGNOSE_ARGS[@]}"

    DIAGNOSED_FILE="${PROJECT_DIR}/data/annotated_logs/diagnosed_batch1.json"
    if [[ -f "${DIAGNOSED_FILE}" ]]; then
        DIAGNOSED_COUNT=$(python3 -c "import json; print(len(json.load(open('${DIAGNOSED_FILE}'))))")
        success "Diagnosis complete: ${DIAGNOSED_COUNT} logs diagnosed."
    else
        fail "Diagnosis did not produce output file."
    fi
else
    info "Skipping step 5 (diagnose)."
fi

# ══════════════════════════════════════════════════════════════════════════
# Step 6: Annotate (interactive ground truth)
# ══════════════════════════════════════════════════════════════════════════
if should_run 6; then
    banner 6 "Annotate Diagnosed Logs (Ground Truth)"

    if [[ "${SKIP_ANNOTATE}" == true ]]; then
        warn "Skipping annotation (--skip-annotate)."
        GT_FILE="${PROJECT_DIR}/data/evaluation/ground_truth.json"
        if [[ -f "${GT_FILE}" ]]; then
            info "Using existing ground truth at ${GT_FILE}."
        else
            warn "No ground truth found. Evaluation (step 7) will fail without it."
        fi
    else
        info "Starting interactive annotation..."
        info "(You will rate each diagnosis for accuracy, root cause, and fix quality.)"
        echo ""
        python automated_scripts/annotate.py
        success "Annotation complete."
    fi
else
    info "Skipping step 6 (annotate)."
fi

# ══════════════════════════════════════════════════════════════════════════
# Step 7: Run evaluation
# ══════════════════════════════════════════════════════════════════════════
if should_run 7; then
    banner 7 "Run Demonstration Evaluation"

    GT_FILE="${PROJECT_DIR}/data/evaluation/ground_truth.json"
    if [[ ! -f "${GT_FILE}" ]]; then
        fail "No ground truth found at ${GT_FILE}. Run step 6 (annotate) first."
    fi

    info "Generating evaluation report and charts..."
    python automated_scripts/evaluate_demo.py

    REPORT="${PROJECT_DIR}/results/evaluation/demonstration/evaluation_report.json"
    if [[ -f "${REPORT}" ]]; then
        success "Evaluation report saved to results/evaluation/demonstration/"
        echo ""
        info "Generated artifacts:"
        ls -1 "${PROJECT_DIR}/results/evaluation/demonstration/" 2>/dev/null | sed 's/^/    /'
    else
        fail "Evaluation did not produce report."
    fi
else
    info "Skipping step 7 (evaluate)."
fi

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Workflow Complete!${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Print a quick summary of what exists
for label_path in \
    "Raw logs:data/raw_logs/github_actions/batch1.json" \
    "Triaged logs:data/raw_logs/github_actions/batch1_triaged.json" \
    "Diagnosed logs:data/annotated_logs/diagnosed_batch1.json" \
    "Ground truth:data/evaluation/ground_truth.json" \
    "Eval report:results/evaluation/demonstration/evaluation_report.json"; do

    label="${label_path%%:*}"
    path="${label_path##*:}"

    if [[ -f "${PROJECT_DIR}/${path}" ]]; then
        count=$(python3 -c "import json; print(len(json.load(open('${PROJECT_DIR}/${path}'))))" 2>/dev/null || echo "?")
        echo -e "  ${GREEN}[exists]${NC} ${label} (${count} entries) - ${path}"
    else
        echo -e "  ${RED}[missing]${NC} ${label} - ${path}"
    fi
done

echo ""
info "API server will be stopped on script exit."
echo ""
