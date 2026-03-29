# TODO

## Goal

Bootstrap a dedicated GitHub coordination repository for OpenArchives direct upstream recovery while keeping live secrets and bulk PDF artifacts out of Git.

The GitHub repo should store:

- the full agent coordination setup
- prompts, schemas, manifests, and retry logic
- deterministic scraper code and tests
- compact lineage reports and snapshot manifests

The GitHub repo should not store:

- Codex auth
- AWS credentials
- Hugging Face tokens
- GitHub tokens
- SSH keys
- raw PDF snapshots
- bulky extracts or logs

AWS S3 should store the raw PDFs, extracted artifacts, and large run outputs.

## Ground Rules

- [ ] No live secrets in Git, ever.
- [ ] No raw PDFs in Git.
- [ ] No presigned S3 URLs in Git.
- [ ] Keep one lineage state bundle per collection.
- [ ] Require schema-valid stage reports before advancing a collection.
- [ ] Require explicit failure classification before retrying a collection.
- [ ] Optimize early waves for Greek fit, academic usefulness, and extraction ease.

## Already Prepared

- [x] Create the coordination-repo plan:
  - `analysis/openarchives_direct_repo_harness/GITHUB_COORDINATION_REPO_PLAN.md`
- [x] Prepare the all-collection harness manifests:
  - `analysis/openarchives_direct_repo_harness/config/all_strict_target_collections.json`
  - `analysis/openarchives_direct_repo_harness/config/all_known_host_collections.json`
  - `analysis/openarchives_direct_repo_harness/config/wave1_high_quality_easy.json`
- [x] Prepare the current staged launcher and schema:
  - `analysis/openarchives_direct_repo_harness/scripts/launch_codex_exec_harness.py`
  - `analysis/openarchives_direct_repo_harness/schemas/stage_report.schema.json`
- [x] Verify dry-run harness execution locally:
  - `analysis/openarchives_direct_repo_harness/runs/20260329T124653Z_discover/`
  - `analysis/openarchives_direct_repo_harness/runs/20260329T125340Z_discover/`

## Phase 0: Repo Bootstrap

- [x] Decide GitHub owner:
  - `fffoivos`
- [x] Decide GitHub repo name:
  - `automated-glossapi`
- [x] Decide visibility, default `private`:
  - current choice: `private`
- [x] Create the empty GitHub repo or provide authenticated GitHub CLI access:
  - repo: `https://github.com/fffoivos/automated-glossapi`
- [x] Scaffold the repo layout from `GITHUB_COORDINATION_REPO_PLAN.md`.
- [x] Add `.gitignore` covering secrets, local Codex state, bulky run artifacts, caches, and downloads.
- [ ] Add `.gitattributes` if needed for generated artifacts and line endings.
- [x] Add `docs/secret_policy.md`.
- [x] Add `.env.example` with placeholders only, no live values.
- [ ] Add a bootstrap script for syncing the harness into the repo layout.

## Phase 1: Secret Safety And Hygiene

- [ ] Add a pre-commit or CI secret scan before merge.
- [ ] Add a repo-level checklist for forbidden files:
  - `.env`
  - `.env.*` with real values
  - `auth.json`
  - `config.toml` if it contains auth or sensitive local paths
  - `*.pem`
  - `*.key`
  - `codex-home/`
  - `.codex/`
  - browser cookie exports
  - presigned URL captures
- [ ] Redact strongbox runtime docs before copying them into a sharable repo.
- [ ] Keep secret injection runtime-only on AWS via `CODEX_HOME`, IAM, or out-of-repo env files.
- [ ] Decide whether to use SSM Parameter Store / Secrets Manager for any non-IAM secrets.

## Phase 2: Migrate The Existing Harness

- [ ] Copy the current harness docs, config, schemas, and scripts into the new repo layout.
- [ ] Normalize paths so the launcher is repo-relative rather than workspace-relative.
- [ ] Keep the all-collection manifest, known-host subset, and wave manifests in the repo.
- [x] Move or mirror the prompt text into a dedicated `prompts/` directory.
  - stage prompts now live under `prompts/` with retry guidance under `prompts/repairs/`
- [x] Add a clear agentic source-acquisition workflow doc:
  - `docs/agentic_pipeline.md`
- [ ] Add an operator README for local versus strongbox execution.
- [ ] Add a sync script to push the coordination repo to the AWS strongbox.

## Phase 2.5: Runtime And GlossAPI Infrastructure

- [x] Add a dedicated runtime area for host bootstrap, runtime checks, and OCR tuning:
  - `runtime/`
- [x] Add an AWS bootstrap script that includes Rust and GlossAPI setup:
  - `runtime/aws/bootstrap_glossapi_aws.sh`
- [x] Add a structured GlossAPI runtime readiness checker:
  - `runtime/aws/check_glossapi_runtime.py`
- [x] Add an OCR worker-planning utility that turns VRAM/CPU/utilization measurements into an initial workers-per-GPU guess:
  - `runtime/ocr/worker_planning.py`
- [x] Add a Codex runtime failure investigation harness:
  - `runtime/investigation.py`
- [x] Add an operator doc for AWS/remote GlossAPI hosts:
  - `docs/aws_runtime.md`
- [x] Add stored host profiles and runtime knowledge bundles:
  - `runtime/host_profiles/`
  - `runtime/knowledge/`
- [x] Add runtime task examples and prompt templates:
  - `runtime/examples/`
  - `runtime/prompts/`
- [x] Add a runtime task renderer that turns a task spec into a resolved Codex bundle:
  - `runtime/render_runtime_task.py`
- [x] Add a schema for runtime task specs:
  - `schemas/runtime_task.schema.json`
- [x] Add a runtime execution spec so task bundles have an explicit remote execution contract:
  - `docs/runtime_execution_spec.md`
- [x] Add a runtime executor that can run a resolved task against an existing remote host:
  - `runtime/aws/execute_runtime_task.py`
- [x] Add a controller-managed runtime launcher so runtime work is first-class in the repo run structure:
  - `controller/launch_runtime_task.py`
- [x] Split bootstrap behavior between fresh provisioning and repairing an existing host:
  - `BOOTSTRAP_MODE=provision|repair`
  - repair mode now avoids updating a dirty repo by default
- [x] Add a runtime OCR smoke test that verifies `Corpus.ocr()` plus Rust cleaner refresh:
  - `runtime/aws/smoke_test_glossapi_runtime.py`
- [x] Make the readiness checker requirement-aware and validate Cargo against the actual repo crates:
  - `runtime/aws/check_glossapi_runtime.py`
- [x] Add a dedicated OCR worker-sizing note covering VRAM, CPU, utilization, GPU count, and the limited role of FLOPS:
  - `docs/ocr_worker_sizing.md`
- [x] Add a runtime stack-fit review for GPU hosts so OCR planning checks hardware, driver, Torch, CUDA, arch support, attention backend, and OCR mode before benchmarking:
  - `runtime/ocr/deepseek_runtime_fit.py`
  - `docs/runtime_stack_fit.md`
- [ ] Add machine manifests for concrete host profiles:
  - `g7e.48xlarge`
  - `r7i.16xlarge`
  - persistent Hetzner builder
- [x] Wire the runtime lane into a first-class non-collection controller flow.
- [ ] Add true provision-mode host creation and selection for tasks that do not yet have a public IP.
- [ ] Capture benchmark baselines and recommended OCR configs per machine profile.
- [x] Replace OCR-vs-reference similarity scoring with a review-bundle workflow for Codex/manual inspection:
  - `runtime/ocr/build_ocr_review_bundle.py`
  - `runtime/ocr/evaluate_ocr_quality.py` now delegates to the review-bundle builder for backward compatibility
- [ ] Capture the current `g7e.48xlarge` DeepSeek blocker explicitly in runtime knowledge and prompts:
  - the current DeepSeek path still rejects `sdpa` and falls back to `eager`
  - guarded `plain_ocr` on the 43 selected OA pages reduced repeat flags to `13/43` but slowed to `15.8 s/page`
  - attention/runtime fit is still the main bottleneck before any further worker-per-GPU tuning
- [ ] Feed runtime findings back upstream into GlossAPI defaults and preflight checks.
- [ ] Add automated artifact syncing from runtime executions into tracked run directories or S3.

## Phase 3: Controller Hardening

- [ ] Extend `stage_report.schema.json` with richer state:
  - `failed_checklist_ids`
  - `tried_hypotheses`
  - `alternative_hypotheses`
  - `best_next_hypothesis`
  - `stuck_reason`
  - `blocked_on`
  - `exhausted_paths`
  - `confidence`
  - `needs_human_input`
- [x] Implement `controller/validate_stage_report.py`.
- [x] Implement `controller/route_next_action.py`.
- [x] Implement a persistent lineage state bundle per collection.
- [x] Add stage-specific evidence checks, not only JSON schema checks.
- [x] Require explicit count evidence in stage reports:
  - repository-claimed totals
  - per-collection claimed counts when available
  - API-reported counts
  - scraper-observed counts
  - discrepancy notes and request-capacity observations
- [x] Require throughput evidence in stage reports:
  - metadata/API benchmark rate
  - file-download benchmark rate
  - ETA estimate
  - threshold-breach recommendation for slow runs
- [x] Add repair prompts for:
  - invalid JSON
  - missing evidence
  - blocked stage retries
  - partial stage completion
- [x] Add deterministic progress scoring with exact completeness, ETA-health, and quality-fit percentages.
- [x] Add a second-pass review artifact that decides whether to retry, advance, or stop for user review.
- [x] Add a persistent lineage loop that chains worker -> validate -> score -> review -> retry/advance/stop.
- [x] Bound retries with explicit user-decision stops for ETA breaches, hard blockers, and exhausted attempt budgets.

## Phase 4: Scraper Build Stages

- [x] Add `build_scraper` as a first-class stage after `adapter_spec`.
- [x] Add `smoke_test_scraper`.
- [x] Keep `bulk_run_scraper` deterministic and code-driven, not LLM-driven.
  - the stage contract and prompt now make bulk acquisition an explicit downloader-run stage rather than a manual LLM crawl
- [x] Add a reusable rolling download telemetry helper with request logging, ETA snapshots, and a Codex investigation hook.
- [ ] Add a per-adapter contract for:
  - crawl entrypoints
  - listing traversal
  - pagination strategy
  - item-page parsing
  - PDF detection
  - restricted-entry detection
  - metadata mapping
- [ ] Add scraper tests using small HTML fixtures where practical.

## Phase 5: S3 Snapshot Plumbing

- [ ] Decide the S3 bucket and top-level prefix for direct-recovery artifacts.
- [x] Add `schemas/snapshot_manifest.schema.json`.
- [ ] Write manifests that point to S3 prefixes instead of embedding binaries in Git.
- [ ] Decide where large HTML captures and bulky logs should live in S3.
- [ ] Add checksum manifests for downloaded PDF batches.
- [ ] Add a compact Git-tracked snapshot index for each collection and snapshot.

## Phase 6: Pilot Execution

- [ ] Launch the first live `discover` wave on:
  - `uth_rep`
  - `psepheda`
  - `ntua`
  - `pyxida`
- [x] Run a first live single-collection `discover` test from the new repo:
  - `pyxida`
  - result so far: the launcher, schema, and router are now working against a real collection run; the `pyxida` agent successfully detected the DSpace 7 structure, top communities, and a direct sample PDF bitstream while the longer discover pass was still in progress
- [x] Verify stage outputs with the new validator.
- [ ] Advance only successful collections to `feasibility`.
- [ ] Run `sample_validation` only after pagination, PDF detection, and metadata checks are credible.
- [ ] Promote only collections with convincing academic sample PDFs.

## Phase 6.5: Source Tracking

- [x] Create a generated backlog of potential sources to check.
- [x] Create a generated active-source status backlog with run state, modality hints, and count fields.
- [x] Add manual enrichment overlays so the backlogs can be extended without clobbering generated data.
- [x] Refresh the local Projects MCP catalog so `automated-glossapi` is discoverable there.
- [x] Expose progress percentages, review decisions, and user-decision flags in the generated active-source backlog.

## Phase 6.8: OpenArchives OCR Remediation

- [ ] Provision the first dedicated OA OCR host on `p5en.48xlarge`.
- [ ] Patch GlossAPI DeepSeek fallback from `eager` to `sdpa`.
- [ ] Add OCR mode and inference-size controls to GlossAPI for throughput benchmarking.
- [ ] Download OA metadata and build the 50-PDF benchmark/quality sample.
- [ ] Run the workers-per-GPU sweep and quality review before the full OA OCR run.
- [ ] Follow [docs/oa_ocr_execution_plan_20260329.md](/home/foivos/Projects/automated-glossapi/docs/oa_ocr_execution_plan_20260329.md).

## Phase 7: Expansion

- [ ] Expand from `wave1_high_quality_easy` to the 10-collection pilot.
- [ ] Then expand to the rest of the known-host collections.
- [ ] Only after that, start the discovery-heavy no-host backlog.
- [ ] Track per-collection blockers so repeated failures do not silently loop.

## Inputs Still Needed

- [x] GitHub owner:
  - `fffoivos`
- [x] GitHub repo name:
  - `automated-glossapi`
- [x] GitHub visibility:
  - `private`
- [x] Either:
  - empty repo URL available: `https://github.com/fffoivos/automated-glossapi`
  - authenticated `gh` access now works in this environment
- [ ] Decision on whether to reuse the existing dedup S3 bucket or create a dedicated direct-recovery bucket/prefix

## First Recommended Follow-Up

- [ ] Bootstrap the GitHub repo and copy in the current harness plus the secret-policy docs.
- [ ] Add the validator/router layer before launching paid multi-agent runs.
- [ ] Drive one full lineage (`discover -> feasibility -> sample_validation`) with `controller/run_lineage_loop.py`.
- [ ] Only then launch the first live multi-collection wave on AWS.
