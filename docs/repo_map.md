# Repo Map

## Fast Orientation

This repo has grown beyond a single OpenArchives discovery harness.

At a high level, there are three main lanes:

1. source-acquisition lineages for upstream repositories
2. runtime tooling for remote GlossAPI hosts and OCR infrastructure
3. controller and review-loop logic that turns stage runs into repeatable workflows

## Start Here

- [README.md](../README.md): top-level scope and entrypoints
- [TODO.md](../TODO.md): current project plan and status
- [docs/agentic_pipeline.md](agentic_pipeline.md): how stages fit together
- [docs/operator_runbook.md](operator_runbook.md): practical commands

## Top-Level Map

- [config/collections](../config/collections)
  - source manifests and the current acquisition wave definitions
- [controller](../controller)
  - orchestration and review loop
  - start here for stage execution, validation, retries, and human decisions
- [prompts](../prompts)
  - stage prompts and repair prompts used by the controller
- [runtime](../runtime)
  - remote-host provisioning, readiness checks, OCR planning, runtime task rendering, and execution
- [schemas](../schemas)
  - JSON contracts for stage reports, retry decisions, runtime tasks, human decisions, and snapshot manifests
- [scrapers](../scrapers)
  - deterministic downloader code
- [scripts](../scripts)
  - manifest generation and recovery helpers
- [tracking](../tracking)
  - generated backlog views plus manual enrichment overlays
- [runs](../runs)
  - per-run transient and stage-scoped artifacts
- [lineages](../lineages)
  - longer-lived lineage state bundles that survive across retries and user decisions
- [knowledge](../knowledge)
  - reviewer-oriented knowledge and recovery memory
- [tests](../tests)
  - unit tests and dry-run harness coverage

## If You Want To...

- launch a source stage:
  - [controller/launch_codex_exec_harness.py](../controller/launch_codex_exec_harness.py)
- run a persistent lineage loop:
  - [controller/run_lineage_loop.py](../controller/run_lineage_loop.py)
- inspect stage definitions:
  - [controller/stage_definitions.py](../controller/stage_definitions.py)
- inspect retry and review logic:
  - [controller/review_stage_outcome.py](../controller/review_stage_outcome.py)
  - [controller/route_next_action.py](../controller/route_next_action.py)
  - [controller/progress_scoring.py](../controller/progress_scoring.py)
- work on runtime provisioning or OCR hosts:
  - [runtime/README.md](../runtime/README.md)
  - [docs/aws_runtime.md](aws_runtime.md)
- understand where a collection stands:
  - [tracking/README.md](../tracking/README.md)
  - [runs](../runs)
  - [lineages/README.md](../lineages/README.md)

## Folder READMEs

The repo now has small navigation docs in the main folders that benefit from them:

- [controller/README.md](../controller/README.md)
- [prompts/README.md](../prompts/README.md)
- [runtime/README.md](../runtime/README.md)
- [tracking/README.md](../tracking/README.md)
- [lineages/README.md](../lineages/README.md)
