# Prompts

This folder stores the stage prompts used by the source-acquisition controller.

## Stage Prompts

- `discover.md`
- `feasibility.md`
- `sample_validation.md`
- `adapter_spec.md`
- `build_scraper.md`
- `smoke_test_scraper.md`
- `bulk_run_scraper.md`

These correspond to the stage chain defined in [../controller/stage_definitions.py](../controller/stage_definitions.py).

## Repair Prompts

The `repairs/` subfolder holds retry-mode prompts used when the controller decides a stage should be rerun with a more specific repair objective:

- `schema_repair.md`
- `missing_evidence.md`
- `runtime_repair.md`
- `alternative_hypotheses.md`
- `unresolved_checklist.md`

## How They Fit

The prompts are not standalone workflow docs.

They are selected and parameterized by the controller, usually through:

- [../controller/launch_codex_exec_harness.py](../controller/launch_codex_exec_harness.py)
- [../controller/run_lineage_loop.py](../controller/run_lineage_loop.py)

For the broader workflow description, see [../docs/agentic_pipeline.md](../docs/agentic_pipeline.md).
