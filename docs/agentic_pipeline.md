# Agentic Source-Acquisition Pipeline

## Core purpose

`automated-glossapi` is not just a research harness. It is the control plane for automated source-data acquisition for GlossAPI.

The end goal is:

1. identify upstream repositories worth crawling
2. prove that they can be crawled deterministically
3. implement repository-specific downloader code
4. run that code to download the source corpus
5. hand off downloaded source data to the downstream GlossAPI pipeline

The agents are not meant to perform the full corpus download by hand. The agents are the scouting, validation, specification, review, and implementation teams that make bulk downloading safe enough to hand over to deterministic code.

## Agentic teams workflow

```text
Source backlog / collection manifests
  -> portfolio routing team
  -> discovery team
  -> feasibility team
  -> sample-validation team
  -> adapter-spec team
  -> scraper-build team
  -> smoke-test team
  -> bulk-run operations team
  -> snapshot manifest / storage handoff
  -> downstream GlossAPI extraction, OCR, dedup, and publish
```

## Team roles

### 1. Portfolio routing team

- choose which repositories and collections are worth pursuing first
- optimize for Greek fit, academic usefulness, extraction ease, and throughput plausibility

### 2. Discovery team

- map repository structure
- identify APIs, feeds, and traversal routes
- capture initial count claims and safe request patterns

### 3. Feasibility team

- prove deterministic enumeration
- prove PDF presence detection
- benchmark throughput and ETA
- decide whether the repository is operationally viable

### 4. Sample-validation team

- download a small bounded sample
- confirm that the files are real academic content
- reject notices, stubs, duplicates, and low-value branches

### 5. Adapter-spec team

- turn research evidence into a downloader contract
- name crawl entrypoints, pagination rules, metadata mapping, PDF filtering, pacing, and failure modes

### 6. Scraper-build team

- implement repository-specific deterministic downloader code
- add bounded tests, fixtures, and telemetry integration

### 7. Smoke-test team

- run a small live validation of the implemented scraper
- confirm parsing, telemetry, and sample outputs before bulk work

### 8. Bulk-run operations team

- launch the deterministic downloader at corpus scale
- supervise throughput, checkpoints, rate limits, and failure summaries
- produce a download snapshot manifest

### 9. Snapshot / storage handoff

- record where the downloaded source data lives
- write counts, bytes, checksum references, and storage prefixes
- hand the acquired source corpus to the downstream GlossAPI pipeline

## Success and failure reporting

Success and failure are reported after every stage, not only at the end of the whole lineage.

The sequence is:

```text
worker stage run
  -> final.json
  -> validation.json
  -> progress_evaluation.json
  -> improvement_plan.json
  -> next stage advance / same-stage retry / user decision / stop
```

That means each team is judged stage by stage:

- the worker reports what happened
- the validator checks structural and stage evidence
- progress scoring measures completeness, ETA health, and quality fit
- the review pass decides whether to advance, retry, stop, or request a user decision

## Current implemented scope

The active coded lineage currently runs through:

1. `discover`
2. `feasibility`
3. `sample_validation`
4. `adapter_spec`
5. `build_scraper`
6. `smoke_test_scraper`
7. `bulk_run_scraper`

The bulk source-data acquisition mission is therefore now modeled explicitly in the stage chain, even though repository-specific downloader implementations and storage plumbing still need to be completed per source.
