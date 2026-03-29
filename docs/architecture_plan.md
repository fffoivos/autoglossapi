# GitHub Coordination Repo Plan

## Goal

Create a dedicated GitHub repository that stores the full OpenArchives direct-recovery coordination layer while keeping bulk binaries out of Git.

This coordination layer should be understood as an agentic source-acquisition pipeline for GlossAPI: agents discover, validate, specify, review, and implement repository-specific downloaders, and deterministic code performs the actual bulk corpus download.

This repository should contain:

- agent orchestration
- prompts and checklists
- stage schemas
- controller / verifier / retry logic
- deterministic scraper adapters and tests
- run manifests and compact reports
- snapshot manifests that point to S3

This repository should not contain:

- Codex auth
- AWS credentials
- Hugging Face tokens
- SSH keys
- large PDF snapshots
- presigned URLs
- bulky extracted corpora

## Storage split

### GitHub stores

- orchestration code
- manifests
- schemas
- prompt templates
- evaluation and verification code
- deterministic scraper code
- compact per-run summaries
- small fixture samples for tests only
- snapshot indexes and metadata

### S3 stores

- raw PDFs
- extracted text artifacts
- OCR outputs
- bulky logs
- large HTML captures if needed
- any replay bundles too large for Git

### GitHub references to S3

GitHub should track manifests, not binaries. Each dataset snapshot should have a manifest with:

- `snapshot_id`
- `collection_slug`
- `stage`
- `created_at`
- `scraper_version`
- `agent_run_id`
- `s3_pdf_prefix`
- `s3_extract_prefix`
- `document_count`
- `pdf_file_count`
- `total_bytes`
- `sha256_manifest_path`
- `notes`

## Secret policy

### Hard rule

No live secrets are ever committed to the coordination repo.

### Must never be committed

- `auth.json`
- `config.toml` if it contains auth or sensitive local paths
- `.env`
- `.env.*` with real values
- AWS access keys
- Hugging Face tokens
- GitHub tokens
- `CODEX_HOME`
- SSH private keys
- browser cookies
- presigned S3 URLs
- local machine usernames or home paths when avoidable

### Allowed in repo

- `.env.example`
- redacted config examples
- bucket names
- instance ids
- non-secret hostnames
- secret-loading instructions

### Secret injection model

Use runtime-only secrets on AWS:

- `CODEX_HOME` on the strongbox
- AWS IAM role for S3 access where possible
- environment files outside the repo
- optional SSM Parameter Store / Secrets Manager if needed

### Git hygiene requirements

The coordination repo should include a strict `.gitignore` covering:

- `.env`
- `.env.*`
- `*.pem`
- `*.key`
- `auth.json`
- `codex-home/`
- `.codex/`
- `runs/*/jobs/*/events.jsonl`
- `runs/*/jobs/*/downloads/`
- `runs/*/jobs/*/artifacts/large/`
- `snapshots/cache/`
- `tmp/`

It should also include a pre-commit or CI secret scan before merge.

## Repository scope

### Recommended repository name

Something close to:

- `openarchives-direct-recovery`
- `glossapi-openarchives-direct-recovery`

### Recommended visibility

- `private` at first

Move to `public` only when:

- secrets policy is enforced
- prompts are cleaned up
- AWS details are redacted where appropriate
- the controller and scraper code are presentable

## Proposed repository structure

```text
openarchives-direct-recovery/
  README.md
  LICENSE
  .gitignore
  .gitattributes
  docs/
    architecture.md
    aws_runtime.md
    secret_policy.md
    operator_runbook.md
  config/
    collections/
      all_strict_target_collections.json
      all_known_host_collections.json
      wave1_high_quality_easy.json
    waves/
    retry_policy.yaml
    storage_policy.yaml
  prompts/
    discover.md
    feasibility.md
    sample_validation.md
    adapter_spec.md
    build_scraper.md
    repair_stage_output.md
    blocked_stage_retry.md
  schemas/
    stage_report.schema.json
    scraper_spec.schema.json
    snapshot_manifest.schema.json
    retry_decision.schema.json
  controller/
    launch_codex_exec_harness.py
    validate_stage_report.py
    route_next_action.py
    summarize_lineage.py
    advance_stage.py
  runtime/
    README.md
    aws/
      bootstrap_glossapi_aws.sh
      check_glossapi_runtime.py
    ocr/
      worker_planning.py
    investigation.py
  lineages/
    README.md
  scrapers/
    common/
    adapters/
    tests/
  verification/
    pdf_sample_checks.py
    metadata_checks.py
    count_reconciliation.py
  snapshots/
    manifests/
    indexes/
  runs/
    manifests/
    summaries/
  scripts/
    bootstrap_repo.sh
    sync_to_strongbox.sh
    launch_wave.sh
  tests/
```

## Controller architecture

The repo should implement a manager / worker / verifier pattern.

### Worker responsibilities

- run one collection lineage at a time
- work within the active stage
- emit schema-valid JSON
- record failed checklist items
- record tried hypotheses
- propose alternative hypotheses
- recommend the next action

### Verifier responsibilities

- validate JSON schema
- validate required evidence for the stage
- check artifact existence
- classify result:
  - `success`
  - `partial`
  - `blocked`
  - `exhausted`
  - `schema_failed`
  - `runtime_failed`

### Controller responsibilities

- choose the next stage or retry
- pass forward the lineage context
- stop infinite loops
- escalate when reasonable paths are exhausted

## Stage model

### Research stages

1. `discover`
2. `feasibility`
3. `sample_validation`
4. `adapter_spec`

### Build stages

5. `build_scraper`
6. `smoke_test_scraper`
7. `bulk_run_scraper`

### Post-download stages

8. `extract`
9. `quality_score`
10. `ocr_targeting`
11. `snapshot_publish`

## Retry policy

Retries should not be generic. They should be classified.

### Failure classes

- `runtime_failed`
- `schema_failed`
- `evidence_failed`
- `partial`
- `blocked`
- `exhausted`

### Retry behavior

- `runtime_failed`: rerun with command/output repair context
- `schema_failed`: rerun with strict JSON repair prompt
- `evidence_failed`: rerun same stage with missing checklist items only
- `partial`: rerun same stage with unresolved items only
- `blocked`: force agent to test alternative hypotheses
- `exhausted`: stop and escalate

### Required state fields per lineage

- `collection_slug`
- `current_stage`
- `attempt_number`
- `failed_checklist_ids`
- `tried_hypotheses`
- `alternative_hypotheses`
- `best_next_hypothesis`
- `blocked_on`
- `exhausted_paths`
- `recommended_next_step`
- `confidence`

## Quality priorities

The repository workflow should optimize for:

1. Greek-language fit
2. academic usefulness
3. high extraction quality
4. deterministic website traversal
5. low notice / stub pollution

This means the first live wave should prefer repositories that are:

- mostly Greek or unspecified in language
- dominated by theses, articles, books, papers, and other text-rich academic material
- easy to traverse with DSpace-like structure
- already showing real direct PDF access

## Initial rollout plan

### Phase 0: repo bootstrap

- create GitHub repo
- add `.gitignore`, docs, base layout
- copy the current harness
- add a no-secrets policy doc

### Phase 1: controller hardening

- add stage-report validator
- add next-action router
- add retry prompts
- add lineage state bundle format

### Phase 2: pilot live wave

- run `discover` on:
  - `uth_rep`
  - `psepheda`
  - `ntua`
  - `pyxida`
- verify stage outputs
- advance successful collections to `feasibility`

### Phase 3: scraper build

- generate adapter specs
- implement deterministic scrapers for the first successful repositories
- smoke test against small samples

### Phase 4: S3 snapshot path

- finalize S3 prefix layout
- write snapshot manifest schema
- upload sample PDF batches and manifests

### Phase 5: broaden scope

- expand to the 10-collection pilot
- then to the rest of known-host collections
- then to discovery-heavy collections with no current host hints

## S3 layout recommendation

```text
s3://<bucket>/openarchives-direct-recovery/
  raw-pdfs/
    <collection_slug>/
      <snapshot_id>/
  extracted/
    <collection_slug>/
      <snapshot_id>/
  manifests/
    <collection_slug>/
      <snapshot_id>.json
  logs/
    <run_id>/
  samples/
    <collection_slug>/
      <run_id>/
```

## GitHub setup still needed

To finish setup, I still need:

- GitHub owner
- repository name
- visibility: `private` or `public`

Because this environment does not currently have authenticated GitHub CLI access for repo creation, the cleanest path is:

1. you create the empty repo and send me the URL, or
2. you provide GitHub CLI/auth in this environment

## Acceptance criteria

The coordination repo is ready when:

- the repo contains the full orchestration layer
- no live secrets are in Git
- the first wave can be launched on AWS from repo code alone
- each collection lineage has persistent state
- stage outputs are schema-validated
- retries are routed automatically
- snapshot manifests point to S3 rather than embedding binaries in Git
