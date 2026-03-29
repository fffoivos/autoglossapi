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

## Persistent lineage loop

```bash
python3 controller/run_lineage_loop.py \
  --collection-slug pyxida \
  --collections-file config/collections/wave1_high_quality_easy.json \
  --through-stage feasibility
```

What this does:

- runs one stage attempt
- validates the worker output
- scores exact progress percentages
- runs a second Codex review to decide whether to retry, advance, or stop for user review
- carries the review plan into the next attempt or stage

Hard-stop behavior:

- if recent ETA suggests the corpus cannot finish inside roughly 48 hours, the loop should stop with `decision_pending_user`
- if the worker explicitly requests human input, the loop should stop with `decision_pending_user`
- if the attempt budget is exhausted before the success threshold is reached, the loop should stop with `decision_pending_user`

## Strongbox assumptions

- `codex` is already installed
- `CODEX_HOME` is already seeded
- GitHub and AWS credentials remain outside the repo
- bulk outputs should go to S3 or other external storage, not Git

## Runtime setup on AWS or another remote host

Bootstrap a GlossAPI host with the runtime lane:

```bash
bash runtime/aws/bootstrap_glossapi_aws.sh
```

Run a readiness check against an existing GlossAPI checkout:

```bash
python3 runtime/aws/check_glossapi_runtime.py \
  --repo /path/to/glossAPI \
  --python /path/to/runtime/python \
  --expect-gpu \
  --strict
```

Estimate a starting `workers_per_gpu` value for OCR:

```bash
python3 runtime/ocr/worker_planning.py \
  --gpu-memory-gib 97.9 \
  --peak-worker-memory-gib 16.1 \
  --single-worker-utilization 0.187 \
  --cpu-cores-per-gpu 24 \
  --cpu-cores-per-worker 6
```

See [docs/ocr_worker_sizing.md](/home/foivos/Projects/automated-glossapi/docs/ocr_worker_sizing.md) for the sizing formulas and the role of VRAM, CPU, utilization, GPU count, and FLOPS.

Render a full task bundle for Codex to execute:

```bash
python3 runtime/render_runtime_task.py \
  --task-file runtime/examples/provision_g7e_deepseek.json \
  --output-dir runs/runtime_tasks/provision_g7e
```

Or repair an existing host from explicit flags:

```bash
python3 runtime/render_runtime_task.py \
  --task-type repair_glossapi_host \
  --target-name repair-box \
  --instance-profile aws_g7e_48xlarge \
  --expect-gpu \
  --needs-rust \
  --needs-cleaner \
  --needs-deepseek-ocr \
  --benchmark-ocr \
  --auto-worker-tuning \
  --public-ip 54.224.252.101 \
  --repo-path /opt/dlami/nvme/glossapi/glossAPI \
  --runtime-python /opt/dlami/nvme/glossapi/glossAPI/dependency_setup/deepseek_uv/dependency_setup/.venvs/deepseek/bin/python \
  --output-dir runs/runtime_tasks/repair_box
```

## Safety

- Start with one or two collections before scaling out
- Validate stage reports before promoting to the next stage
- Treat repeated `blocked` results as a routing problem, not a cue for blind retries
- Use the generated progress and improvement artifacts to inspect exact completeness, ETA health, and the latest review decision:
  - `progress_evaluation.json`
  - `improvement_plan.json`
