# automated-glossapi

Coordination repository for automated source acquisition and runtime operations for GlossAPI.

## What This Pipeline Does

This repository is the control plane for source discovery, crawl validation, scraper handoff, runtime provisioning, and lineage review around GlossAPI.

The intended workflow is:

1. agent teams discover and de-risk an upstream repository
2. agent teams prove crawl feasibility and validate sample quality
3. agent teams write the adapter spec and implement the repository-specific scraper
4. the downloader emitted by the agent teams performs the real bulk acquisition
5. runtime tasks provision or repair the remote infrastructure needed for OCR and extraction
6. downloaded source data is handed off to downstream GlossAPI extraction, OCR, dedup, and publishing

The agents are therefore the scouting, validation, specification, review, and implementation teams. They are expected to emit the repository-specific downloader, then test, repair, and supervise it. They are not meant to perform the full corpus download manually in-chat. See [docs/agentic_pipeline.md](docs/agentic_pipeline.md) for the workflow view.

This repository stores:

- agent prompts and stage definitions
- collection manifests
- stage schemas
- controller, validator, retry routing, progress scoring, and review-loop logic
- deterministic scraper handoff artifacts
- compact lineage reports and snapshot manifests

This repository does not store:

- Codex auth
- GitHub auth
- AWS credentials
- raw PDF corpora
- bulky extracts
- large logs

Raw PDFs, extracted outputs, and large run artifacts belong in AWS S3.

## Scope Today

The repository started as an OpenArchives-adjacent academic-repository harness, but it now has three active lanes:

1. source-acquisition lineages for upstream repositories
2. runtime infrastructure work for GlossAPI hosts, OCR, and remote execution
3. controller and review-loop tooling for retries, progress scoring, and human decisions

The current source-acquisition wave still targets university repositories that feed `openarchives.gr`, with priority on:

1. Greek-language fit
2. high-quality academic text
3. easy deterministic traversal
4. low stub / notice pollution
5. pushing as close to complete coverage as practical
6. download plans that can plausibly finish inside roughly two days

That first execution wave is defined in [wave1_high_quality_easy.json](config/collections/wave1_high_quality_easy.json).

## Navigation

Start with [docs/repo_map.md](docs/repo_map.md) for the shortest repo tour.

- [config/collections](config/collections): collection manifests for direct-recovery work
- [controller](controller): staged Codex harness, review loop, human-decision handling, and routing logic
- [docs](docs): operator docs, architecture notes, runtime specs, and navigation help
- [lineages](lineages): persistent lineage state and human-decision bundles across multiple stage attempts
- [prompts](prompts): stage prompts plus repair prompts for retries
- [runtime](runtime): GlossAPI host bootstrap, readiness checks, OCR tuning helpers, and runtime investigation hooks
- [schemas](schemas): JSON schemas for stage reports and routing decisions
- [scrapers](scrapers): deterministic downloader code and shared scraper utilities
- [scripts](scripts): deterministic helpers such as manifest generation and recovery indexing
- [tracking](tracking): generated source backlogs plus manual enrichment overlays
- [tests](tests): unit and harness dry-run tests

The most useful folder-level navigation docs are:

- [controller/README.md](controller/README.md)
- [prompts/README.md](prompts/README.md)
- [lineages/README.md](lineages/README.md)

## Quick start

Dry-run the first discover wave without spending tokens:

```bash
python3 controller/launch_codex_exec_harness.py \
  --stage discover \
  --collections-file config/collections/wave1_high_quality_easy.json
```

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Run a persistent lineage loop for one collection:

```bash
python3 controller/run_lineage_loop.py \
  --collection-slug pyxida \
  --collections-file config/collections/wave1_high_quality_easy.json \
  --through-stage feasibility
```

## Key docs

- [docs/repo_map.md](docs/repo_map.md)
- [docs/architecture_plan.md](docs/architecture_plan.md)
- [docs/agentic_pipeline.md](docs/agentic_pipeline.md)
- [docs/aws_runtime.md](docs/aws_runtime.md)
- [docs/ocr_worker_sizing.md](docs/ocr_worker_sizing.md)
- [docs/runtime_stack_fit.md](docs/runtime_stack_fit.md)
- [docs/runtime_execution_spec.md](docs/runtime_execution_spec.md)
- [docs/download_telemetry.md](docs/download_telemetry.md)
- [docs/secret_policy.md](docs/secret_policy.md)
- [docs/operator_runbook.md](docs/operator_runbook.md)
- [TODO.md](TODO.md)

## Runtime task bundles

The runtime lane is task-driven. Stored host profiles, prompts, and benchmark knowledge can be resolved into a concrete Codex bundle with:

```bash
python3 runtime/render_runtime_task.py \
  --task-file runtime/examples/provision_g7e_deepseek.json \
  --output-dir runs/runtime_tasks/provision_g7e
```

That produces a resolved task JSON plus a prompt text file, so requests like “provision a GlossAPI OCR box” and “repair the existing OCR box and find the right DeepSeek settings” can be executed against stored workflows rather than chat memory.

For a first-class controller-managed runtime run:

```bash
python3 controller/launch_runtime_task.py \
  --task-file runtime/examples/repair_existing_ocr_host.json \
  --output-root runs/runtime_tasks
```

To execute a resolved runtime task directly against a host:

```bash
python3 runtime/aws/execute_runtime_task.py \
  --resolved-task runs/runtime_tasks/repair_existing_ocr_host/resolved_task.json \
  --ssh-key-path /path/to/key.pem \
  --artifacts-dir runs/runtime_exec/repair_existing_ocr_host
```

## Mental Model

If you only need the shortest orientation:

- collection candidates live in [config/collections](config/collections)
- staged source work starts in [controller/launch_codex_exec_harness.py](controller/launch_codex_exec_harness.py)
- persistent lineage loops run through [controller/run_lineage_loop.py](controller/run_lineage_loop.py)
- runtime and remote-host work starts in [controller/launch_runtime_task.py](controller/launch_runtime_task.py)
- current run artifacts live in [runs](runs)
- longer-lived lineage state lives in [lineages](lineages)
