# Next Steps — Post-Meeting 11 March 2026

**Meeting participants:** Fahid Khan, Jussi Rasku (supervisor), Mahade Hasan (advisor)

---

## Key Decision: Evaluation Strategy

Jussi outlined two evaluation paths and recommended starting with **Path A**:

| | Path A: Demonstration | Path B: Robust Evaluation |
|---|---|---|
| **What** | Manual expert evaluation on a small subset of real failures | Formal dataset with controlled experiments and statistical metrics |
| **Evidence strength** | Qualitative — sufficient for master's thesis | Quantitative — stronger, but more work |
| **Effort** | Low — can be done now with existing diagnosed logs | High — requires annotated ground truth, baselines, ablations |
| **Jussi's view** | "Start from this" | "Later in the spring, if you still have time" |

**Decision:** Do Path A first. Extend to Path B only if time allows after the demonstration is complete.

---

## Immediate: Manual Evaluation (Path A)

### What to do

1. Select **10–15 diagnosed logs** from the 52 available — pick a diverse mix across repositories and error types
2. For each log, **manually read the raw failure log** and independently determine the root cause
3. Compare your expert judgment against the LLM's diagnosis on three dimensions:
   - **Correctness** — Did the LLM identify the right error type and root cause?
   - **Usefulness** — Would this diagnosis actually help a developer fix the problem faster?
   - **Misleadingness** — Did the LLM hallucinate or suggest something that would waste the developer's time?
4. Write up the results as a **DSR demonstration** — this is the core evaluation artifact for the thesis

### Output format (suggested per log)

| Field | Content |
|---|---|
| Repository | e.g., `pytorch/pytorch` |
| Workflow | e.g., `Upload test stats` |
| LLM error type | e.g., `test_failure` |
| LLM root cause (summary) | 1–2 sentences |
| Expert assessment | Correct / Partially correct / Incorrect |
| Usefulness rating | High / Medium / Low |
| Notes | Any hallucinations, missing context, or surprising accuracy |

---

## Near-Term: Use Real Work Failures

Jussi specifically suggested using CI/CD failures **from your own work experience** — cases where you already know the root cause from having debugged them yourself. This is stronger evidence than evaluating against open-source logs you've never seen before.

**Action:** If possible, collect 3–5 failure logs from your own workplace CI/CD pipelines and run them through the system. Compare the LLM diagnosis against your firsthand knowledge of what went wrong.

---

## Scope Boundaries (Do NOT Pursue Now)

Jussi flagged these as interesting but out of scope unless research questions demand them:

1. **LLM-based run classification** — Having the AI decide "good run vs bad run" instead of regex triage. Interesting extension, but would require its own evaluation framework. Current rule-based triage works and is fast.

2. **Multi-log context** — Giving the LLM access to multiple logs, project structure, or historical runs instead of a single log. Jussi acknowledged this is a limitation ("very narrow view to the entire project") but warned against scope creep.

3. **Robust quantitative evaluation** — Full dataset annotation, statistical significance, ablation studies. Defer to later in spring *only if* the demonstration is done and time remains.

---

## Meeting Format Change

Jussi proposed shifting to **more frequent, shorter meetings** instead of fewer long ones. Agree on a cadence (e.g., biweekly 20-minute check-ins) at the next meeting.

---

## Task Checklist

- [ ] Select 10–15 diverse logs from the 52 diagnosed
- [ ] Manually evaluate each (correctness, usefulness, misleadingness)
- [ ] Write demonstration evaluation report
- [ ] (Optional) Collect 3–5 failure logs from own work, run through system
- [ ] Begin thesis Chapter 2 (Background & Related Work)
- [ ] Propose new meeting cadence to Jussi
- [ ] (Later) If time allows, annotate full 52-log set for Path B evaluation
