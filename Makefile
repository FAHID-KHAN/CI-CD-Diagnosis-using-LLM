.PHONY: help install test local-model preflight collect triage smoke-cohort annotate annotate-smoke pilot final compare compare-pilot verify verify-smoke audit-ground-truth architecture status

STUDY_CONFIG := configs/thesis_fresh_2026.yaml
STUDY_ROOT := data/studies/thesis_fresh_2026
SMOKE_ROOT := data/studies/system_smoke_001

help:
	@echo "Controlled thesis commands:"
	@echo "  ./run_workflow.sh status  Where the study stands, and what to do next"
	@echo "  ./run_workflow.sh --help  Every stage from one entry point"
	@echo ""
	@echo "  make install             Install the lean project environment"
	@echo "  make test                Run offline tests"
	@echo "  make local-model         Create the fixed Qwen 3.5 thesis model"
	@echo "  make preflight           Validate study configuration"
	@echo "  make collect             Collect the fixed fresh dataset"
	@echo "  make triage              Apply fixed eligibility rules"
	@echo "  make smoke-cohort        Create the five-case engineering cohort"
	@echo "  make annotate ANNOTATOR=id  Blindly annotate eligible logs"
	@echo "  make annotate-smoke ANNOTATOR=id  Annotate the smoke cohort"
	@echo "  make verify VERIFIER=id   Independent second review and adjudication"
	@echo "  make verify-smoke VERIFIER=id  Second review of the smoke cohort"
	@echo "  make audit-ground-truth   Check ground truth against the evidence rules"
	@echo "  make pilot               Run the paired engineering smoke test"
	@echo "  make final               Run the complete paired experiment"
	@echo "  make compare             Compare every experiment found, visually"
	@echo "  make compare-pilot       Compare the pilot run only"
	@echo "  make architecture        Regenerate the architecture diagram"

install:
	python -m pip install -e ".[dev]"

test:
	MPLCONFIGDIR=/tmp/cicd-matplotlib pytest tests/ -v

local-model:
	ollama pull qwen3.5:9b
	ollama create thesis-qwen3.5:9b-24k -f configs/Modelfile.qwen3.5-thesis

preflight:
	python automated_scripts/preflight_study.py --study-config $(STUDY_CONFIG)

collect:
	python automated_scripts/data_collection.py --study-config $(STUDY_CONFIG)

triage:
	python automated_scripts/triage.py --study-config $(STUDY_CONFIG)

smoke-cohort:
	python automated_scripts/create_smoke_cohort.py

annotate:
	@test -n "$(ANNOTATOR)" || (echo "Usage: make annotate ANNOTATOR=your-id"; exit 1)
	python automated_scripts/annotate_blind.py --study-config $(STUDY_CONFIG) --annotator "$(ANNOTATOR)"

annotate-smoke:
	@test -n "$(ANNOTATOR)" || (echo "Usage: make annotate-smoke ANNOTATOR=your-id"; exit 1)
	python automated_scripts/annotate_blind.py \
		--study-config $(STUDY_CONFIG) \
		--study-dir $(SMOKE_ROOT) \
		--annotator "$(ANNOTATOR)"

# Decision D3: a second reviewer, who must not be the annotator, labels each
# case independently and adjudicates every disagreement in writing.
verify:
	@test -n "$(VERIFIER)" || (echo "Usage: make verify VERIFIER=second-reviewer-id"; exit 1)
	python automated_scripts/annotate_blind.py \
		--study-config $(STUDY_CONFIG) \
		--mode verify \
		--annotator "$(VERIFIER)"

verify-smoke:
	@test -n "$(VERIFIER)" || (echo "Usage: make verify-smoke VERIFIER=second-reviewer-id"; exit 1)
	python automated_scripts/annotate_blind.py \
		--study-config $(STUDY_CONFIG) \
		--study-dir $(SMOKE_ROOT) \
		--mode verify \
		--annotator "$(VERIFIER)"

audit-ground-truth:
	python automated_scripts/compare_reports.py --audit-only

pilot:
	python automated_scripts/benchmark_models.py \
		--input $(SMOKE_ROOT)/triaged/eligible_logs.json \
		--ground-truth $(SMOKE_ROOT)/ground_truth/ground_truth.json \
		--pilot \
		--output-dir $(SMOKE_ROOT)/experiments/pilot_002

final:
	python automated_scripts/benchmark_models.py \
		--input $(STUDY_ROOT)/triaged/eligible_logs.json \
		--ground-truth $(STUDY_ROOT)/ground_truth/ground_truth.json \
		--output-dir $(STUDY_ROOT)/experiments/final_001

# Compare generated reports: a terminal table plus one self-contained HTML page.
compare:
	python automated_scripts/compare_reports.py

compare-pilot:
	python automated_scripts/compare_reports.py \
		--experiment $(SMOKE_ROOT)/experiments/pilot_002 \
		--json $(SMOKE_ROOT)/experiments/pilot_002/comparison_data.json

# The diagram is generated from docs/make_architecture.py, so it can be
# corrected and diffed rather than being an opaque committed image.
CHROME ?= /Applications/Google Chrome.app/Contents/MacOS/Google Chrome

architecture:
	python docs/make_architecture.py
	@height=$$(python -c "import re;print(re.search(r'<svg[^>]*height=\"(\\d+)\"', open('docs/architecture.svg').read()).group(1))"); \
	"$(CHROME)" --headless --disable-gpu --hide-scrollbars \
		--force-device-scale-factor=2 --window-size=2400,$$height \
		--screenshot=docs/architecture.png docs/architecture.svg 2>/dev/null; \
	echo "Wrote docs/architecture.png"

# Same inspector run_workflow.sh uses; judged from the files on disk. A blocking
# stage is shown with [!] rather than failing the target, because this one is for
# reading; './run_workflow.sh final' is where the non-zero exit gates the run.
status:
	@python automated_scripts/study_status.py --study-config $(STUDY_CONFIG) || true
