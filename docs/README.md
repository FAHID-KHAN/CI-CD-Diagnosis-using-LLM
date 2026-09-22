# Documentation

Three folders. Only the first two describe the current system.

## `architecture/` — how the system works and how to run it

| File | What it is |
| --- | --- |
| [architecture.png](architecture/architecture.png) | The system in one picture: the artifact, and the evaluation apparatus around it |
| [make_architecture.py](architecture/make_architecture.py) | Source for that picture. Edit it and run `make architecture` |
| [CONTROLLED_STUDY_RUNBOOK.md](architecture/CONTROLLED_STUDY_RUNBOOK.md) | The exact operating procedure, phase by phase, with every gate |
| [RUNNING.md](architecture/RUNNING.md) | Short entry point if you just want to run something |

## `thesis/` — the research work

| File | What it is |
| --- | --- |
| [ACTION_ITEMS.md](thesis/ACTION_ITEMS.md) | **Start here.** What to do, in order |
| [EVALUATION_PLAN_DRAFT.md](thesis/EVALUATION_PLAN_DRAFT.md) | The plan for the supervision review. Has open decisions to answer |
| [THESIS_EXECUTION_ROADMAP_2026-09-21.md](thesis/THESIS_EXECUTION_ROADMAP_2026-09-21.md) | Phase-by-phase roadmap from the kickoff meeting |
| [KICKOFF_ACTION_ITEM_VERIFICATION.md](thesis/KICKOFF_ACTION_ITEM_VERIFICATION.md) | Each meeting decision checked against the actual code |

## `archive/` — superseded, kept only as history

Written between December 2025 and March 2026. They describe a different system:
RAG retrieval, ChromaDB, a Flask API, a human study, GPT-4o-mini, Llama 3 and
Mistral, and 17 repositories. None of that exists any more.

Keep them for the supervision record. Do not use them as a description of the
system or as operating instructions.

Two are actively misleading if read as current:

- `project_overview.md` — 3,014 lines titled "Complete Architecture &
  Implementation Documentation", with 116 references to removed components.
- `proof_of_work.md` — an evaluation of a demonstration path that was deleted.
