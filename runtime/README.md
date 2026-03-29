# Runtime Tooling

This directory contains reusable infrastructure helpers for running GlossAPI on AWS or other remote boxes as part of the automated corpus pipeline.

Current scope:

- `aws/`
  - bootstrap, execution, smoke tests, and readiness checks for GlossAPI runtime hosts
- `ocr/`
  - worker-planning utilities for DeepSeek OCR and similar GPU-bound phases
- `host_profiles/`
  - stored machine profiles and default expectations
- `knowledge/`
  - compact benchmark summaries and runtime conclusions
- `prompts/`
  - task-specific Codex prompt templates for provisioning, repair, and OCR benchmarking
- `examples/`
  - example runtime task specs
- `investigation.py`
  - structured Codex investigation launcher for runtime failures and performance bottlenecks
- `render_runtime_task.py`
  - turns a runtime task spec into a resolved task bundle plus a Codex prompt
- `aws/execute_runtime_task.py`
  - executes a resolved runtime task against a remote host and collects machine-readable artifacts

Design goals:

- keep environment setup explicit and repeatable
- make missing prerequisites fail early with structured evidence
- turn runtime/performance failures into machine-readable incidents
- capture tuning logic in code instead of scattering it across chat transcripts
- make runtime work triggerable from a stored task spec instead of relying on remembered chat context
- make the task bundle executable, not just descriptive

The AWS operator doc is in [docs/aws_runtime.md](/home/foivos/Projects/automated-glossapi/docs/aws_runtime.md).
