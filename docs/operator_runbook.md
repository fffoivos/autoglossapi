# Operator Runbook

## Local dry run

```bash
python3 controller/launch_codex_exec_harness.py \
  --stage discover \
  --collections-file config/collections/wave1_high_quality_easy.json
```

## Local targeted live run

```bash
python3 controller/launch_codex_exec_harness.py \
  --stage discover \
  --apply \
  --collection-slugs pyxida \
  --collections-file config/collections/wave1_high_quality_easy.json
```

## Strongbox assumptions

- `codex` is already installed
- `CODEX_HOME` is already seeded
- GitHub and AWS credentials remain outside the repo
- bulk outputs should go to S3 or other external storage, not Git

## Safety

- Start with one or two collections before scaling out
- Validate stage reports before promoting to the next stage
- Treat repeated `blocked` results as a routing problem, not a cue for blind retries
