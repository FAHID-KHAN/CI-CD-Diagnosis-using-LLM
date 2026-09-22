# Action Items

What to do, in order. Based on the kickoff meeting (21 September 2026) and the
email sent before it.

**Where things stand:** the tool is finished and tested. The dataset is empty.
Nothing can be run for real results until the supervisors approve the method.

**Next deadline:** the review meeting, about two weeks after 21 September.
**Then:** thesis seminar, 9 November 2026.

---

## Part 1 — Do these before the review meeting

### 1. Book the meeting
**Do:** Email Jussi and Mahade with two or three time options.
**Why:** Everything else waits for this meeting. No date means no progress.
**Done when:** The date is in your calendar.
**From the meeting:** D8

### 2. Ask Mahade about the second reviewer
**Do:** Ask if he will review your cases, or if you should find someone else.
**Why:** The supervisors said your own judgement cannot be the only basis for
your results. You need a second person to check your labels. Finding that person
takes time, so ask now.
**Done when:** You know who the second reviewer is.
**From the meeting:** D3, A9

### 3. Check if repository history shows the fixes
**Do:** Take failed runs from your chosen repositories. For each one, look for
the commit or pull request that fixed it.
**Why:** If the fix is documented, you do not have to rely on your own opinion
about what broke. That is the strongest kind of ground truth, and it is what the
supervisors asked for.
**Done when:** You can say "X out of Y failures have a documented fix."
**From the meeting:** A4

### 4. Read the related papers
**Do:** Read papers on CI/CD log diagnosis, bug diagnosis, defect seeding, and
how such tools are evaluated. Read them yourself. Do not rely on an LLM summary.
Keep a table: paper, dataset, categories used, ground truth method, metrics,
how they split their data.
**Why:** The supervisors want your categories and metrics justified by prior
work, not chosen by you alone.
**Done when:** The table has entries and you have read the key papers directly.
**From the meeting:** A1, D6

### 5. Finish the evaluation plan
**Do:** Open `docs/thesis/EVALUATION_PLAN_DRAFT.md`. Answer the nine decisions in
Section 10. Rewrite anything that does not sound like you.
**Why:** This is the actual thing the supervisors asked you to bring.
**Done when:** No `[DECISION]` marker is left unanswered.
**From the meeting:** A2

---

## Part 2 — Nine decisions you must make

These are in Section 10 of the plan. Make a choice for each one. If you are
unsure, write down your preference and your reason, then let the supervisors
correct you. A plan that decides nothing pushes the work back to them.

| # | Decision |
| --- | --- |
| 1 | Should cases be chosen by pipeline stage (build/test jobs only) and by whether a fix exists? |
| 2 | Which two repositories? |
| 3 | Which ground-truth method, and who is the second reviewer? |
| 4 | Keep 8 failure categories and widen the data, or cut the categories down to what the data actually contains? |
| 5 | Is a rule-based baseline in scope? You promised one in your email. It does not exist. |
| 6 | How many cases in total? |
| 7 | How do you score whether the model found the right log lines? Exact match, or something looser? |
| 8 | Do you score the root cause with a rubric, or narrow your main question to categories only? |
| 9 | Do you score the suggested fix, describe it, or drop it? You promised it in your email. |

Decisions 4 and 8 must be settled **before** you start annotating. Both change
what you have to write down for each case, and redoing annotation is expensive.

---

## Part 3 — After the supervisors approve

Do not start these early. If the method changes, the work is wasted.

### 6. Build only what the approved method needs
Possible items: a two-repository config, a split file that keeps development and
final cases apart, a check that refuses to run from uncommitted code, a rubric
for scoring root causes, and a rule-based baseline if decision 5 says yes.

### 7. Build the cases and get them checked
Annotate. Then the second reviewer labels the same cases without seeing your
answers. Write down a decision wherever you disagree.
Check with: `./run_workflow.sh audit`

### 8. Freeze the system
Tag the code version. Record the model versions, prompt, and checksums.
Nothing changes after this point.

### 9. Run the experiment once
Both models, same cases, one time. Do not change anything afterwards because you
did not like a result.

### 10. Analyse and prepare the seminar
Which failure types did the models handle well and badly? Separate what you
observed from what you think explains it. Cover the problem, the gap, the
method, the tool, the evaluation, and early results.
**Deadline:** 9 November 2026

---

## Part 4 — Two promises from your email that are not built

You told the supervisors you would do these. Neither exists in the code. Decide
whether to build them or tell the supervisors you are dropping them. Do not let
them sit unmentioned.

| Promise | Status |
| --- | --- |
| "run the same logs through the **baseline methods**" | No baseline exists. Nothing compares the LLM to a simple keyword or regex approach. |
| "**root-cause and suggested-fix quality**" | The model writes both. Nothing scores either. Only the failure category is checked against your ground truth. |

The second one matters more than it looks. Your main research question asks how
well the system identifies failure **causes**. Right now the system only measures
whether it picked the right **category**. Those are not the same claim.

---

## What changed after the meeting

Your email planned to freeze the data, make the ground truth, and run the
experiments. The meeting changed three things:

1. **You cannot be the only person deciding what the right answer is.** Use
   documented fixes, or a second reviewer, or both.
2. **One dataset is not enough.** You need separate sets: one to improve the
   tool, one to test the pipeline, and one kept untouched for the real result.
3. **Two repositories to start, not six.**

Your research questions did not change. The supervisors said they were heading
in the right direction.

---

## Things that are already done

- The full tool: collect, filter, run both models, score, compare.
- Two-pass annotation with a second reviewer and disagreement handling.
- A check that tells you if your ground truth is good enough to use.
- A guard that stops practice cases leaking into the final test.
- Per-category results, confusion matrices, and paired statistical tests.
- A comparison page you can open in a browser.
- 70 automated tests.

Check the state at any time with:

```bash
./run_workflow.sh status
```
