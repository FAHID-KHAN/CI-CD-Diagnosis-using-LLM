#!/usr/bin/env bash
# Remove generated files. Nothing here is source, and nothing here is study data
# unless you ask for it explicitly.
#
#   ./clean.sh              caches and build artefacts
#   ./clean.sh --studies    also delete collected data (asks first)
#   ./clean.sh --dry-run    show what would go, delete nothing

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${PROJECT_DIR}"

DRY_RUN=false
WITH_STUDIES=false

usage() {
    cat <<'USAGE'
Usage: ./clean.sh [options]

Always removed:
  __pycache__ directories and .pyc files
  .pytest_cache, .mypy_cache, .ruff_cache
  *.egg-info, build/, dist/
  htmlcov/, .coverage
  .DS_Store

Only with --studies:
  data/studies/*        collected logs, ground truth and experiment results

Options:
  --studies    also delete study data, after confirming
  --dry-run    list what would be removed and exit
  --help       this message

Never touched: source code, configs, docs, .env, .venv, git history.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --studies) WITH_STUDIES=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# Collect first, report, then delete: the caller sees the size before it goes.
TARGETS=()
while IFS= read -r path; do
    [[ -n "${path}" ]] && TARGETS+=("${path}")
done < <(
    find . -path ./.venv -prune -o -path ./.git -prune -o \
        \( -name "__pycache__" -o -name "*.pyc" -o -name ".pytest_cache" \
           -o -name ".mypy_cache" -o -name ".ruff_cache" -o -name "*.egg-info" \
           -o -name ".DS_Store" -o -name "htmlcov" -o -name ".coverage" \
           -o -name "build" -o -name "dist" \) -print 2>/dev/null
)

if [[ ${#TARGETS[@]} -eq 0 ]]; then
    echo "No cache or build artefacts to remove."
else
    echo "Cache and build artefacts (${#TARGETS[@]} paths):"
    du -ch "${TARGETS[@]}" 2>/dev/null | tail -1 | sed 's/^/  total  /'
    for path in "${TARGETS[@]}"; do
        echo "  ${path}"
    done | head -12
    [[ ${#TARGETS[@]} -gt 12 ]] && echo "  ... and $(( ${#TARGETS[@]} - 12 )) more"
fi

STUDY_DIRS=()
if [[ "${WITH_STUDIES}" == true ]]; then
    while IFS= read -r path; do
        [[ -n "${path}" ]] && STUDY_DIRS+=("${path}")
    done < <(find data/studies -mindepth 1 -maxdepth 1 2>/dev/null)
    if [[ ${#STUDY_DIRS[@]} -gt 0 ]]; then
        echo
        echo "Study data (${#STUDY_DIRS[@]} directories):"
        du -sh "${STUDY_DIRS[@]}" 2>/dev/null | sed 's/^/  /'
        echo
        echo "  This includes collected logs, ground truth and experiment results."
        echo "  It is not in git. Deleting it cannot be undone."
    fi
fi

if [[ "${DRY_RUN}" == true ]]; then
    echo
    echo "Dry run; nothing was removed."
    exit 0
fi

# Study data is irreplaceable and ungitted, so it needs a typed confirmation
# rather than a flag alone.
if [[ ${#STUDY_DIRS[@]} -gt 0 ]]; then
    echo
    read -r -p "Type 'delete' to remove the study data: " reply
    if [[ "${reply}" != "delete" ]]; then
        echo "Study data kept."
        STUDY_DIRS=()
    fi
fi

[[ ${#TARGETS[@]} -gt 0 ]] && rm -rf "${TARGETS[@]}"
[[ ${#STUDY_DIRS[@]} -gt 0 ]] && rm -rf "${STUDY_DIRS[@]}"

echo
echo "Clean. Repository is now $(du -sh . 2>/dev/null | cut -f1)."
