# Lineages

This folder stores longer-lived lineage state that persists across multiple stage attempts.

Use this folder to answer:

- what is the current state of one collection lineage?
- which user decisions were made for that lineage?
- what loop is still active or was last active?

## Difference From `runs/`

- `runs/`
  - stage-run and job artifacts
  - often transient, attempt-oriented, and grouped by timestamped run
- `lineages/`
  - collection-oriented state bundles
  - survives across retries, reviews, and user decisions

## Current Contents

A lineage bundle typically contains:

- `loop_manifest.json`
  - top-level state for the lineage loop
- `human_decisions/`
  - explicit user-decision artifacts and review plans

As the controller grows, this folder is the right place for durable lineage-level state rather than per-run scratch artifacts.
