.PHONY: help install test preflight collect triage annotate pilot final

STUDY_CONFIG := configs/thesis_fresh_2026.yaml
STUDY_ROOT := data/studies/thesis_fresh_2026

help:
	@echo "Controlled thesis commands:"
	@echo "  make install             Install the lean project environment"
	@echo "  make test                Run offline tests"
	@echo "  make preflight           Validate study configuration"
	@echo "  make collect             Collect the fixed fresh dataset"
	@echo "  make triage              Apply fixed eligibility rules"
	@echo "  make annotate ANNOTATOR=id  Blindly annotate eligible logs"
	@echo "  make pilot               Run the five-log paired pilot"
	@echo "  make final               Run the complete paired experiment"

install:
	python -m pip install -e ".[dev]"

test:
	MPLCONFIGDIR=/tmp/cicd-matplotlib pytest tests/ -v

preflight:
	python automated_scripts/preflight_study.py --study-config $(STUDY_CONFIG)

collect:
	python automated_scripts/data_collection.py --study-config $(STUDY_CONFIG)

triage:
	python automated_scripts/triage.py --study-config $(STUDY_CONFIG)

annotate:
	@test -n "$(ANNOTATOR)" || (echo "Usage: make annotate ANNOTATOR=your-id"; exit 1)
	python automated_scripts/annotate_blind.py --study-config $(STUDY_CONFIG) --annotator "$(ANNOTATOR)"

pilot:
	python automated_scripts/benchmark_models.py \
		--input $(STUDY_ROOT)/triaged/eligible_logs.json \
		--ground-truth $(STUDY_ROOT)/ground_truth/ground_truth.json \
		--pilot \
		--output-dir $(STUDY_ROOT)/experiments/pilot_001

final:
	python automated_scripts/benchmark_models.py \
		--input $(STUDY_ROOT)/triaged/eligible_logs.json \
		--ground-truth $(STUDY_ROOT)/ground_truth/ground_truth.json \
		--output-dir $(STUDY_ROOT)/experiments/final_001
