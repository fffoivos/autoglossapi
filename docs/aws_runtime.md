# AWS Runtime

This document covers the runtime lane for GlossAPI hosts used by the automation repo. The goal is to make remote boxes predictable, measurable, and repairable.

## Scope

The runtime lane is responsible for:

- provisioning GlossAPI on AWS or comparable hosts
- verifying that all hard dependencies are present before expensive runs start
- benchmarking OCR throughput and workers-per-GPU choices
- recording known runtime failures so Codex can investigate them instead of retrying blindly
- feeding concrete runtime findings back into GlossAPI and the automation harness

The supporting code lives under [runtime/](/home/foivos/Projects/automated-glossapi/runtime).

## Task-driven triggering

The runtime lane is meant to be triggerable from a specific stored task, not only from free-form chat.

The key entrypoint is [render_runtime_task.py](/home/foivos/Projects/automated-glossapi/runtime/render_runtime_task.py), which builds a task bundle from:

- a task spec
- a stored host profile
- stored runtime knowledge such as prior OCR benchmarks
- a task-specific prompt template

That gives Codex a resolved bundle with:

- what must be true
- which runtime scripts and docs to use
- which host profile applies
- which benchmark knowledge is relevant
- which OCR parameter guess should be tried first

So tasks like these become explicit and repeatable:

- "I need an instance with such and such GPUs and GlossAPI on it."
- "I already have an instance but GlossAPI is not fully set up and I need the right DeepSeek settings."

## Example task bundles

Provision a fresh OCR host:

```bash
python3 runtime/render_runtime_task.py \
  --task-file runtime/examples/provision_g7e_deepseek.json \
  --output-dir runs/runtime_tasks/provision_g7e
```

Repair an existing OCR host:

```bash
python3 runtime/render_runtime_task.py \
  --task-file runtime/examples/repair_existing_ocr_host.json \
  --output-dir runs/runtime_tasks/repair_existing_ocr_host
```

You can also build a task directly from flags:

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

The output directory contains:

- `resolved_task.json`
- `codex_prompt.txt`
- `bundle_manifest.json`

That is the bundle you can hand to `codex exec`. The resolved task also contains an `execution_plan` that can be executed directly.

## Runtime executor

Use [runtime/aws/execute_runtime_task.py](/home/foivos/Projects/automated-glossapi/runtime/aws/execute_runtime_task.py) when you want the repo to execute the runtime task rather than only render a prompt bundle.

Example:

```bash
python3 runtime/aws/execute_runtime_task.py \
  --resolved-task runs/runtime_tasks/repair_existing_ocr_host/resolved_task.json \
  --ssh-key-path /home/foivos/.ssh/foivos-glossapi-dedup-20260327.pem \
  --artifacts-dir runs/runtime_exec/repair_existing_ocr_host
```

This executor:

- copies the runtime tooling to the host
- runs a pre-repair readiness check for repair tasks
- runs the bootstrap or repair flow
- runs a strict post-repair readiness check
- runs an OCR smoke test when the task requires DeepSeek OCR
- saves machine-readable artifacts for each step

The exact contract is in [docs/runtime_execution_spec.md](/home/foivos/Projects/automated-glossapi/docs/runtime_execution_spec.md).

For a controller-managed runtime run directory that keeps the bundle and execution artifacts together, use [controller/launch_runtime_task.py](/home/foivos/Projects/automated-glossapi/controller/launch_runtime_task.py):

```bash
python3 controller/launch_runtime_task.py \
  --task-file runtime/examples/repair_existing_ocr_host.json \
  --output-root runs/runtime_tasks \
  --apply \
  --ssh-key-path /home/foivos/.ssh/foivos-glossapi-dedup-20260327.pem
```

This is currently the preferred path for existing-host repair tasks. For pure provisioning tasks without a known public IP yet, use the runtime task bundle in dry-run mode first.

## Hard requirements

GlossAPI runtime hosts should be treated as failing setup if any of these are missing:

- `git`
- `gcc`
- `rustc`
- `cargo`
- the GlossAPI repo checkout
- the DeepSeek runtime Python environment
- Python modules required for OCR such as `fitz`, `torch`, and `transformers`

Rust is a real dependency, not an optional extra. One concrete failure already observed on the current OCR box is that `Corpus.ocr()` reruns cleaning after OCR and may try to build `glossapi_rs_cleaner`; without Rust, the run completes noisily and leaves the host in a degraded state.

## Bootstrap flow

Use [runtime/aws/bootstrap_glossapi_aws.sh](/home/foivos/Projects/automated-glossapi/runtime/aws/bootstrap_glossapi_aws.sh) on a fresh host after this repo is available there.

Example:

```bash
bash runtime/aws/bootstrap_glossapi_aws.sh
```

Useful overrides:

```bash
TARGET_DIR=/srv/glossapi/glossAPI \
TARGET_BRANCH=development \
DOWNLOAD_DEEPSEEK_MODEL=1 \
EXPECT_GPU=1 \
bash runtime/aws/bootstrap_glossapi_aws.sh
```

The script installs system packages, installs `uv` and exposes it on the default host `PATH`, ensures a current stable Rust toolchain via `rustup`, updates the GlossAPI checkout to `development`, runs the DeepSeek setup script, builds `glossapi_rs_cleaner` and `glossapi_rs_noise` into the DeepSeek venv, and then runs the readiness checker.

## Readiness check

Use [runtime/aws/check_glossapi_runtime.py](/home/foivos/Projects/automated-glossapi/runtime/aws/check_glossapi_runtime.py) before OCR or cleaner-heavy runs.

Example:

```bash
python3 runtime/aws/check_glossapi_runtime.py \
  --repo /opt/dlami/nvme/glossapi/glossAPI \
  --python /opt/dlami/nvme/glossapi/glossAPI/dependency_setup/deepseek_uv/dependency_setup/.venvs/deepseek/bin/python \
  --needs-rust \
  --needs-cleaner \
  --needs-deepseek-ocr \
  --expect-gpu \
  --strict
```

If a host is not ready and you want Codex to investigate automatically:

```bash
python3 runtime/aws/check_glossapi_runtime.py \
  --repo /opt/dlami/nvme/glossapi/glossAPI \
  --python /opt/dlami/nvme/glossapi/glossAPI/dependency_setup/deepseek_uv/dependency_setup/.venvs/deepseek/bin/python \
  --needs-rust \
  --needs-cleaner \
  --needs-deepseek-ocr \
  --expect-gpu \
  --launch-investigation \
  --artifact-dir runs/runtime_investigations
```

The readiness checker is now requirement-aware. It only hard-fails on the parts of the runtime that the task actually needs, and for cleaner-heavy tasks it validates Cargo against the repo's real Rust manifests rather than treating any `cargo` binary as good enough.

## OCR tuning

The planning helper is [runtime/ocr/worker_planning.py](/home/foivos/Projects/automated-glossapi/runtime/ocr/worker_planning.py).

The underlying sizing model and the role of VRAM, CPU, utilization, GPU count, and FLOPS are documented in [docs/ocr_worker_sizing.md](/home/foivos/Projects/automated-glossapi/docs/ocr_worker_sizing.md).

Example using the current `g7e` benchmark values:

```bash
python3 runtime/ocr/worker_planning.py \
  --gpu-memory-gib 97.9 \
  --peak-worker-memory-gib 16.1 \
  --headroom-gib 15 \
  --single-worker-utilization 0.187 \
  --cpu-cores-per-gpu 24 \
  --cpu-cores-per-worker 6
```

The point is not to predict the exact optimum. The point is to get a good starting guess and then run a tiny sweep around it.

When a task bundle uses a host profile with stored OCR benchmark inputs, the runtime task renderer will precompute the initial worker guess and include it in `resolved_task.json`.

## Current measured lessons

These came from the current DeepSeek OCR benchmarking work and should be treated as operational guidance until superseded:

- For multi-GPU DeepSeek workers, isolate each worker with `CUDA_VISIBLE_DEVICES=<gpu>` and pass `--device cuda`.
- Avoid explicit `cuda:N` for multi-worker sharding in the current DeepSeek path.
- On `g7e`-class `~98 GiB` GPUs, `workers_per_gpu=2` materially improved utilization and throughput over `1`.
- Measured on the native `Corpus.ocr()` path over the same 8 PDFs / 16 pages:
  - `workers_per_gpu=1`: `241.2s`, `15.08 s/page`, avg util `18.7%`, max mem `16.1 GiB`
  - `workers_per_gpu=2`: `150.6s`, `9.41 s/page`, avg util `58.2%`, max mem `32.3 GiB`
- The current DeepSeek v2 path still pays significant cold-start cost from model load, page rasterization, and per-page inference.

## Known upstream improvement targets

The automation repo should keep surfacing these back into GlossAPI:

- keep the runtime smoke test aligned with the real `Corpus.ocr()` plus cleaner refresh path
- support `workers_per_gpu="auto"` using measured VRAM, CPU, and single-worker utilization
- add better timeout and failure handling for pathological OCR pages
- keep runtime preflight and benchmark reporting structured enough for Codex follow-up
