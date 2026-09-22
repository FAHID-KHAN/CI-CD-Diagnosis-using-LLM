Subject: Revised Research Questions — Thesis on LLM-Based CI/CD Failure Diagnosis

Dear Jussi and Mahade,

Thank you both for taking the time to meet today. Your feedback was really helpful, especially the point about making sure research questions lead to actual experiments with measurable outcomes rather than staying too abstract.

I spent some time after the meeting rethinking my research questions. Formulating good ones is harder than it looks — they need to be focused enough to answer properly, broad enough to be worth investigating, and most importantly, they need to lead to concrete experiments that produce real numbers [1]. I have tried to keep that in mind with the revised versions below.

I would really appreciate your thoughts on whether these are on the right track.


PRIMARY RESEARCH QUESTION

    How effectively can an LLM-based diagnostic system identify
    failure causes in CI/CD pipeline logs?

The idea here is to evaluate the diagnostic tool I have built as a whole. The system takes a raw CI/CD log, filters and preprocesses it, sends it to an LLM, and gets back a structured diagnosis: what type of error it is, what caused it, how to fix it, and which log lines support that conclusion.

To answer this question, I plan to measure several things: how often the system correctly classifies the error type, how good the root cause explanations are, how often the model cites evidence that actually exists in the log (as opposed to hallucinating), and how long each diagnosis takes. All of this would be measured against human-annotated ground truth and compared to simpler baselines like regex pattern matching and keyword heuristics.

I deliberately kept this narrower than something like "Can LLMs help developers with CI/CD?" because that would be hard to measure objectively. This version ties directly to the artifact and the metrics the tool already produces.


SUB-RESEARCH QUESTION 1

    How does a proprietary LLM (GPT-4o-mini) compare to a locally
    hosted open-source LLM (Llama 3) for CI/CD failure diagnosis?

This comes directly from Mahade's feedback that relying on a single commercial model does not offer enough novelty. I agree — the interesting question is not just "does it work?" but "does a free, locally hosted model work just as well as a paid cloud API?"

The experiment is straightforward: I run both models on the exact same set of 50+ annotated logs and compare them on accuracy, root cause quality, grounding (did the model cite real log lines?), speed, and cost. GPT-4o-mini runs through the OpenAI API with per-token pricing. Llama 3 runs locally on my machine through Ollama with zero API cost but requiring local compute.

What makes this interesting beyond just reporting two sets of numbers is the trade-off analysis. If the local model is 10% less accurate but completely free and keeps data on-premises, that is a meaningful finding for teams that cannot send CI/CD logs to external APIs for confidentiality reasons. On the other hand, if the gap is large, that tells us something about where open-source models still fall short for this kind of structured reasoning task.

I chose two models rather than three or four to keep the scope realistic for a master's thesis while still having a clean proprietary-versus-open-source comparison.


SUB-RESEARCH QUESTION 2

    Which categories of CI/CD failures are LLMs most and least
    effective at diagnosing?

The motivation here is that not all CI/CD failures look the same in logs. A dependency error usually includes an explicit message like "ModuleNotFoundError" or "version conflict," which is relatively easy for a model to pick up. A timeout or a configuration issue might only show up as a vague exit code or a missing environment variable buried in hundreds of lines of output. I want to understand which types of failures the system handles well and where it struggles.

The tool classifies failures into eight categories: dependency errors, test failures, build configuration issues, timeouts, permission errors, syntax errors, network errors, and unknown. For the experiment, I would compute precision, recall, and F1 for each category separately, build a confusion matrix to see which types get confused with each other, and rank the categories from easiest to hardest for the model.

This is useful for two reasons. For the thesis, it gives the results chapter much more depth than a single overall accuracy number. For practitioners, it tells them exactly what they can and cannot rely on the system for — for example, "use it confidently for dependency errors, but double-check its output on timeout issues."


HOW THESE QUESTIONS FIT TOGETHER

I tried to structure these so they build on each other naturally:

  - The primary question asks: does the system work?
  - RQ1 asks: does the choice of model matter?
  - RQ2 asks: where exactly does it work and where does it break down?

Together, they cover the artifact evaluation from three angles — overall effectiveness, a key design decision (model selection), and the boundaries of the approach. This fits the Design Science Research framework we are using: the artifact is the diagnostic system, and the research questions evaluate it.

One thing I considered but decided against including as a separate RQ is the impact of log preprocessing (filtering, truncation). The tool does include a preprocessing pipeline, but since it is already baked into the artifact design, I think it is better described in the methodology chapter rather than turned into its own research question. I will still report token usage statistics and explain the preprocessing choices, just not as a standalone experiment.


WHAT THE RESULTS CHAPTER WOULD LOOK LIKE

Each question maps to specific outputs:

  PRQ  → Overall accuracy table comparing the system against regex and
         heuristic baselines, plus hallucination rate and latency summary
  RQ1  → Side-by-side comparison of GPT-4o-mini vs Llama 3 with a
         cost-accuracy trade-off chart and statistical significance tests
  RQ2  → Per-error-type breakdown with a confusion matrix heatmap and
         a ranked list of failure categories from easiest to hardest


I would really value your feedback on these — whether the scope feels right, whether you think anything important is missing, or whether you would frame things differently. I am happy to adjust before I start running the full experiments.

I have also attached a progress report on the tool's current state for your reference, since the OneDrive sharing issue is still being sorted out with IT.

Best regards,
Fahid Khan
Master's Student — Tampere University

[1] Monash University Library, "Developing Research Questions,"
    https://www.monash.edu/library/help/assignments-research/developing-research-questions
