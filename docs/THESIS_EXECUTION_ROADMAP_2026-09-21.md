# Thesis Evaluation Roadmap

## Purpose and current conclusion

This roadmap translates the decisions from the thesis kickoff meeting on 21
September 2026 into concrete work for the CI/CD diagnosis tool. The prototype
is ready to support evaluation design, but the main experiment must not run
yet. Independent ground truth and a genuinely held-out final test set are the
two release-blocking methodological requirements.

The next supervision review should approve the evaluation protocol before
fresh final-study data is collected or either model is run on final cases.

## Tool readiness assessment

| Meeting requirement | Current tool position | Status | Required response |
|---|---|---:|---|
| Reproducible CI/CD log collection | Fixed GitHub repository configuration, immutable raw output, checksums and collection manifests exist | Ready | Retain this implementation |
| Start with two contrasting repositories | The current protocol contains six repositories across three ecosystems | Not aligned | Create a new two-repository protocol after the pair is justified |
| Known and defensible ground truth | The blind annotator records a human judgment, but it does not link a case to a historical fix, seeded defect or independent expert decision | Blocked | Define and implement the ground-truth evidence model first |
| Independent validation | An annotator identifier is recorded, but the workflow permits the researcher to be the sole annotator and has no adjudication step | Blocked | Use independent expert review or two-stage review with documented adjudication |
| Separate development and held-out final cases | The current five-log pilot selects the first five cases from the same eligible cohort later used by the full final command | Blocked | Split cases before any tuning; exclude development and pilot cases from final evaluation |
| Freeze the system before final evaluation | Git commit, prompt hash, model metadata and configuration checksums are recorded | Partial | Add an explicit freeze manifest and refuse final execution from a dirty or mismatched version |
| Proprietary versus open-weights comparison | Fixed paired conditions use `openai/gpt-5.6-terra` and `local/gpt-oss:20b` with shared schema and reasoning effort | Ready in code | Confirm the exact model conditions in the approved methodology |
| Rule-based or heuristic baseline | No baseline remains in the streamlined workflow | Missing decision | Confirm with supervisors whether a simple deterministic baseline is required, then add only that baseline |
| Failure taxonomy | Eight categories exist in the response schema, but they have not been justified from literature or mapped to inclusion criteria | Partial | Finalize the taxonomy from prior work and a small development sample |
| Category-level effectiveness | Overall exact-match category accuracy and paired tests exist | Partial | Add per-category support, precision, recall, F1 and a confusion matrix |
| Evidence and diagnosis quality | Grounding and hallucination indicators exist, but supporting-line accuracy, root-cause correctness and fix usefulness are not scored against a rubric | Partial | Define expert-scored rubrics and inter-rater procedure |
| Cost and runtime reporting | Token use, estimated API cost and runtime are recorded | Ready | Report as secondary operational outcomes |
| Literature-grounded methodology | No structured literature evidence matrix is part of the current study package | Missing | Complete and verify the focused literature review before locking the protocol |

## Methodological design to approve

### Repository pair

Begin with two repositories, not six. Select repositories that contrast on
language or build ecosystem, workflow structure, log style, project size and
failure distribution while still providing enough verifiable historical
cases. A defensible initial candidate pair is one Python repository and one
JavaScript or JVM repository, but the final choice must follow a short
feasibility study of historical failure-to-fix evidence.

For each candidate repository, inspect at least ten failed workflow runs and
record whether a later commit, pull request, issue or rerun identifies the
cause and repair. Choose the pair with adequate evidence and meaningful
contrast. Do not use model performance to select repositories.

### Ground-truth hierarchy

Use the following evidence hierarchy:

1. Historical failing revision linked to a documented fixing revision, pull
   request, issue or maintainer explanation.
2. Controlled defect seeding with a recorded injected change, expected failure
   category, causal lines and restoring fix.
3. Independent DevOps expert annotation supported by repository evidence.
4. A documented combination of the above with adjudication rules.

LLM-as-judge is not part of the primary plan. If it becomes unavoidable, it
must be separated from the main accuracy claims and reported as a validity
limitation.

Each ground-truth record should contain at least:

- case identifier and repository;
- evidence method: `historical_fix`, `seeded_defect` or `expert_review`;
- failing revision and workflow-run URL;
- fixing revision, pull request or defect-seed identifier;
- failure category and root-cause statement;
- supporting log-line numbers;
- expected repair or repair summary;
- annotator or verifier identifier;
- second-review status and adjudication notes;
- checksums of the exact log and evidence record.

### Development and held-out allocation

Create three non-overlapping partitions before prompt or category refinement:

| Partition | Purpose | May influence the tool | Included in final claims |
|---|---|---:|---:|
| Development | Refine filtering, prompt, taxonomy and rubric | Yes | No |
| Frozen pipeline pilot | Verify both conditions, storage and scoring end to end | No tuning unless the system is re-frozen and a new pilot is selected | No |
| Final held-out test | One-time evaluation of the frozen diagnostic system | No | Yes |

Partition by underlying failure or fix, not only by workflow-run ID, so reruns
or duplicate manifestations cannot leak across sets. Store the allocation in a
versioned split manifest with a fixed random seed and case hashes. The final
runner must reject development and pilot case identifiers.

### Metrics

Primary outcomes should be defined before the final run:

- failure-category macro F1;
- per-category precision, recall and F1;
- exact category accuracy;
- root-cause correctness using a fixed expert rubric;
- evidence-line precision and recall, or an explicitly defined overlap score;
- diagnostic completion rate, with inference failures counted as incorrect.

Secondary outcomes can include grounding score, hallucination rate, fix
usefulness, latency, token use and estimated API cost. Use paired confidence
intervals and paired significance tests because both systems diagnose the same
held-out cases. Report category support counts so weak results from very small
groups are not overinterpreted.

## Execution roadmap

### Phase 1 Literature and feasibility review

**Target: 21 to 27 September 2026**

- Review directly verified work on CI/CD log diagnosis, automated bug
  diagnosis, defect seeding, ground-truth construction and tool evaluation.
- Maintain an evidence matrix containing citation, dataset, unit of analysis,
  taxonomy, ground truth, metrics, split method and threats to validity.
- Inspect historical failure-to-fix traceability in candidate repositories.
- Produce a shortlist of two repository pairs with a written comparison.

**Exit gate:** key papers have been read directly and at least one plausible
repository pair has sufficient verifiable cases.

### Phase 2 Evaluation protocol proposal

**Target: 28 September to 4 October 2026**

- Select and justify two contrasting repositories.
- Choose the ground-truth strategy and independent verification procedure.
- Freeze the failure taxonomy and definitions.
- Specify development, pilot and final partition sizes and leakage controls.
- Pre-register primary and secondary metrics.
- Decide whether the heuristic baseline is in scope.
- Document sample-size limitations and planned statistical analysis.

**Deliverable for supervision:** a concise evaluation plan covering ground
truth, repository selection, categories, metrics, held-out procedure and
freeze criteria.

**Exit gate:** supervisors approve the methodology or return a bounded list of
changes. Do not collect the final dataset before this gate.

### Phase 3 Minimal tool changes

**Target: 5 to 11 October 2026, after methodology approval**

- Add a versioned two-repository study configuration with a new study ID.
- Extend case metadata for historical or seeded ground-truth evidence.
- Add deterministic development, pilot and final split manifests.
- Make the final runner reject overlap and mismatched evidence hashes.
- Add the freeze manifest and final-run version checks.
- Add per-category metrics, confusion matrix and rubric result storage.
- Add one simple baseline only if the approved protocol requires it.
- Add offline tests for leakage, provenance, scoring and freeze enforcement.

**Exit gate:** all offline checks pass and every approved protocol requirement
maps to a stored field, validation rule or analysis output.

### Phase 4 Case construction and independent validation

**Target: 12 to 20 October 2026**

- Build the development cases first and refine the tool only on those cases.
- Construct the separate pilot and final cases using the approved evidence
  hierarchy.
- Have the independent reviewer validate labels, causes, evidence lines and
  fixes without seeing either model's output.
- Resolve disagreements using the written adjudication rule.
- Freeze raw logs, evidence records, split manifest and checksums.

**Exit gate:** every pilot and final case has complete evidence and independent
verification; no underlying defect appears in more than one partition.

### Phase 5 System freeze and pipeline pilot

**Target: 21 to 24 October 2026**

- Commit and tag the approved system version.
- Record code commit, clean-worktree status, prompt and schema hashes,
  dependency versions, model identifiers, Ollama version, model digest,
  quantization, reasoning effort and run date.
- Run the paired pilot only on the reserved pilot partition.
- Check schema compliance, output completeness, failure handling, metadata,
  cost calculation and scoring.

If the pilot reveals a defect that requires a tool change, fix it, create a new
freeze version and use a different reserved pilot set. Never move a viewed
pilot case into the final test set.

**Exit gate:** the frozen version completes the pilot without methodological or
storage defects.

### Phase 6 One-time held-out evaluation

**Target: 25 to 29 October 2026**

- Back up the frozen final dataset before execution.
- Run both model conditions on the exact same final cases.
- Do not change prompts, filtering, taxonomy or scoring after inspecting final
  outputs.
- Preserve successes, inference failures, raw responses, metadata and costs.
- Generate the pre-specified aggregate and per-category results.

**Exit gate:** the result package is complete, checksummed and reproducible
from the frozen inputs and system version.

### Phase 7 Analysis and seminar preparation

**Target: 30 October to 8 November 2026**

- Interpret which failure categories the diagnostic systems handle most and
  least effectively.
- Separate observed results from explanations and validity limitations.
- Document ground-truth limitations, repository scope, sample size, possible
  model contamination, evaluator effects and local-model hardware conditions.
- Prepare seminar material covering the problem, gap, methodology, artifact,
  evaluation design and preliminary findings.
- Confirm the seminar start time and participation requirements.

### Parallel supervision and administration

- Use the provisional working title **Leveraging Large Language Models for
  Automated Diagnosis of CI/CD Pipeline Failures** unless the supervisors
  approve another revision.
- Share promising papers and methodological questions with Mahade during the
  literature and protocol phases instead of waiting for the next review.
- Confirm the next review date and attendees.
- Follow up with Jussi on the examiner paperwork.
- Confirm whether the 9 November seminar begins at 10:00 or 10:15.

## Immediate next actions

1. Do not run the current `make pilot` or `make final` commands for thesis
   evidence.
2. Complete the literature evidence matrix and repository-history feasibility
   check.
3. Bring the two-repository choice, ground-truth plan, taxonomy, metrics,
   partitions and freeze criteria to the next supervision review.
4. After approval, implement only the Phase 3 changes needed by that protocol.

## Definition of ready for the main experiment

The project is ready only when all of the following are true:

- two repositories are selected and justified;
- every final case has evidence-backed, independently verified ground truth;
- development, pilot and final cases are disjoint by underlying defect;
- taxonomy and metrics are justified from verified literature;
- the system is frozen and its exact version is recorded;
- the pilot uses no final case and passes all integrity checks;
- the final runner refuses overlap, version drift and evidence mismatch;
- the complete result package can be reproduced from preserved inputs.
