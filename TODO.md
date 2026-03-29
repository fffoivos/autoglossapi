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
- [ ] Move or mirror the prompt text into a dedicated `prompts/` directory.
- [ ] Add an operator README for local versus strongbox execution.
- [ ] Add a sync script to push the coordination repo to the AWS strongbox.

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
- [ ] Add repair prompts for:
  - invalid JSON
  - missing evidence
  - blocked stage retries
  - partial stage completion
- [ ] Bound retries and define explicit exhaustion rules.

## Phase 4: Scraper Build Stages

- [ ] Add `build_scraper` as a first-class stage after `adapter_spec`.
- [ ] Add `smoke_test_scraper`.
- [ ] Keep `bulk_run_scraper` deterministic and code-driven, not LLM-driven.
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
- [ ] Add `schemas/snapshot_manifest.schema.json`.
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
- [ ] Only then launch the first live `discover` wave on AWS.
