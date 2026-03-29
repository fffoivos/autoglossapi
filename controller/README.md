# Controller

This folder contains the orchestration layer for both source-acquisition lineages and runtime tasks.

## Main Entry Points

- `launch_codex_exec_harness.py`
  - prepare or launch one stage for one or more source collections
- `run_lineage_loop.py`
  - run the persistent worker -> validate -> score -> review -> retry/advance loop
- `launch_runtime_task.py`
  - run runtime and host-operation tasks as first-class controller jobs

## Core Flow

For source-acquisition stages, the controller sequence is:

1. render the stage prompt
2. collect the worker output
3. validate it against schema and stage evidence
4. score progress and ETA health
5. run a review pass
6. decide whether to advance, retry, stop, or request a human decision

## Main Modules

- `stage_definitions.py`
  - stage order and required checklist items
- `validate_stage_report.py`
  - structural and evidence validation
- `progress_scoring.py`
  - deterministic progress and health scoring
- `review_stage_outcome.py`
  - improvement plan and reviewer decision generation
- `route_next_action.py`
  - next-step routing for simpler stage outcomes
- `advance_stage.py`
  - stage promotion helpers
- `human_decision.py`
  - render and validate explicit user-decision steps
- `reviewer_memory.py`
  - look up reusable recovery ideas from previous runs

## Related Folders

- [../prompts](../prompts): stage and repair prompts
- [../schemas](../schemas): JSON contracts
- [../lineages](../lineages): persistent lineage state
- [../runs](../runs): run-specific job artifacts
