# Runtime Execution Spec

This document defines what a runtime task bundle must do when it is actually executed against a host.

## Objective

Runtime tasks should be executable from stored repo state, not reconstructed from chat memory. A resolved runtime task is complete only when it includes:

- the host assumptions
- the exact readiness requirements
- the repair or provision mode
- the verification steps
- the artifact paths that prove the host is actually usable

## Execution phases

Every runtime execution should follow this order:

1. Copy the runtime tooling to the target host.
2. Run a pre-repair readiness check when repairing an existing host.
3. Run the bootstrap or repair flow.
4. Run a strict readiness check after the repair.
5. Run a bounded OCR smoke test when the task needs DeepSeek OCR.
6. Save machine-readable artifacts for every step.

## Provision vs repair

`provision_glossapi_host`

- may clone or update the GlossAPI checkout
- should fail if bootstrap cannot bring the host to a fully ready state
- should run the OCR smoke test when OCR is part of the task

`repair_glossapi_host`

- must inspect the host before changing anything
- must not update a dirty GlossAPI checkout by default
- should apply the smallest repair set needed to satisfy readiness
- should keep pre-repair and post-repair readiness reports

## Truth conditions

A host should not be treated as ready unless all of the relevant checks pass:

- the expected GlossAPI checkout exists
- the selected runtime interpreter is the real runtime, not a resolved system-Python fallback
- required commands exist for the requested workflow
- required Python modules import in the selected runtime
- Cargo is compatible with the repo's Rust crates when cleaner support is required
- GPUs are visible when GPU work is required
- the OCR smoke test passes when DeepSeek OCR is required

## Required artifacts

At minimum, a runtime execution should produce:

- `execution_summary.json`
- `readiness_before.json` for repair tasks
- `bootstrap.log`
- `readiness_after.json`
- `smoke_test_report.json` for OCR tasks

## Current implementation

The execution contract is implemented by:

- [controller/launch_runtime_task.py](/home/foivos/Projects/automated-glossapi/controller/launch_runtime_task.py)
- [runtime/aws/task_execution.py](/home/foivos/Projects/automated-glossapi/runtime/aws/task_execution.py)
- [runtime/aws/execute_runtime_task.py](/home/foivos/Projects/automated-glossapi/runtime/aws/execute_runtime_task.py)
- [runtime/aws/bootstrap_glossapi_aws.sh](/home/foivos/Projects/automated-glossapi/runtime/aws/bootstrap_glossapi_aws.sh)
- [runtime/aws/check_glossapi_runtime.py](/home/foivos/Projects/automated-glossapi/runtime/aws/check_glossapi_runtime.py)
- [runtime/aws/smoke_test_glossapi_runtime.py](/home/foivos/Projects/automated-glossapi/runtime/aws/smoke_test_glossapi_runtime.py)
