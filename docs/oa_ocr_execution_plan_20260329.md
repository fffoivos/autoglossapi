# OpenArchives OCR Execution Plan

Date: 2026-03-29

## Objective

Provision a new AWS OCR host, install `glossAPI` from the `development` branch, download the OpenArchives metadata needed for OCR remediation, build a 50-PDF benchmark set, improve throughput until the DeepSeek OCR path is close to `1 page / 1 second` at the host level, then run OCR on the OpenArchives subset defined as:

- `needs_ocr == true`
- or `greek_badness_score > 10`

The benchmark stage must validate both throughput and output quality before the full run begins.

## Current Constraints

- All AWS instances are currently stopped.
- The real GlossAPI library changes for multi-worker DeepSeek GPU sharding are already pushed to `eellak/glossAPI` on `development` at commit `efd1698`.
- The automation/runtime harness changes are on `automated-glossapi` branch `codex/runtime-task-execution`.
- The current DeepSeek Transformers path in GlossAPI still has known performance risks:
  - it falls back from `flash_attention_2` to `eager`
  - it uses the heavier grounded markdown prompt by default
  - it hardcodes `base_size=1024`, `image_size=768`, `crop_mode=True`
  - it rasterizes pages locally and does sequential per-page inference inside each worker

## Phase 1: Host Selection

### Recommended first host

- Instance type: `p5en.48xlarge`
- Region: `us-east-1`
- Reason:
  - `8x H200`
  - `192 vCPU`
  - `2 TiB RAM`
  - `~144 GiB` per GPU
  - mature Hopper software stack
  - much lower stack-fit risk than Blackwell for the first stabilization run

### Do not use first

- `g7e.48xlarge`
  - already exposed the Blackwell runtime mismatch trap
- `p6-b200.48xlarge`
  - excellent upside, but only after the software path is stable

### AMI

Use the latest AWS Deep Learning Base OSS Nvidia Driver GPU AMI on Ubuntu 24.04.

Current verified `us-east-1` candidate on 2026-03-29:

- `ami-052266c3e21dff7db`
- `Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) 20260320`

Fallback if we want more preinstalled PyTorch:

- `ami-03bab489cca7eaea1`
- `Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.9 (Amazon Linux 2023) 20260321`

### Storage

- Root: standard DLAMI root
- Data volume: start with `4 TB gp3`
- Keep corpus root and benchmark artifacts on the attached volume
- Push large finished artifacts to S3 rather than keeping everything only on-instance

## Phase 2: Bootstrap Order

1. Launch `p5en.48xlarge`.
2. Attach the `4 TB gp3` volume.
3. Install or verify:
   - `git`
   - `gcc`
   - `rustc`
   - `cargo`
   - `uv`
   - `nvidia-smi`
4. Clone:
   - `eellak/glossAPI`
   - `fffoivos/automated-glossapi`
5. Checkout `glossAPI` `development`.
6. Create a fresh OCR venv for the host.
7. Build Rust extensions in that venv.
8. Run the runtime readiness check.
9. Run the runtime stack-fit review before any benchmark.

## Phase 3: Required GlossAPI Changes Before Benchmarking

These are the minimum software changes worth landing before the real speed run:

1. Change no-`flash_attn` fallback from `eager` to `sdpa`.
2. Add OCR mode selection:
   - `markdown_grounded`
   - `plain_ocr`
3. Expose or parameterize:
   - `base_size`
   - `image_size`
   - `crop_mode`
   - render DPI
4. Extend preflight to record:
   - GPU model
   - driver version
   - Torch version
   - Torch CUDA version
   - Torch arch list
   - CUDA allocation smoke result
   - `flash_attn` presence
   - selected attention fallback
   - selected OCR mode
5. Keep `workers_per_gpu` tuning downstream of stack-fit.

## Phase 4: OpenArchives Data Preparation

### Metadata acquisition

1. Download the OpenArchives metadata tables needed for OCR targeting.
2. Materialize the strict OCR target set:
   - `needs_ocr == true`
   - union `greek_badness_score > 10`
3. Restrict to PDFs only.
4. Keep:
   - filename / source_doc_id
   - collection
   - language metadata
   - page count when available
   - badness scores
   - OCR flags
   - direct extraction text / markdown where available
   - download URL(s)

### Benchmark subset size

- total benchmark sample: `50 PDFs`

### Benchmark subset composition

Split the `50 PDFs` into the following buckets:

1. Polytonic Greek bucket: `15 PDFs`
   - select documents whose direct extraction contains polytonic Greek characters
   - ensure these are real pages with nontrivial text
   - include both cleaner low-quality and direct-extraction readable cases

2. Math benchmark bucket: `15 PDFs`
   - low `greek_badness_score`
   - visible formula density or math-heavy pages
   - use as quality and hallucination controls

3. General bad-extraction bucket: `15 PDFs`
   - from the strict OA subset
   - medium and high page-count spread
   - multiple collections

4. Long-page / long-output risk bucket: `5 PDFs`
   - pages likely to challenge token/output limits
   - large dense text pages, tables, footnotes, legal formatting, or mixed scripts

### Per-document capture

For every benchmark PDF, store:

- source collection
- page count
- original extraction text
- whether polytonic Greek is present
- whether math is present
- badness metrics
- chosen benchmark bucket

## Phase 5: Throughput Benchmarking

### Stage 0: Stack-fit gate

Do not begin the throughput sweep until all of the following pass:

- Torch imports cleanly
- CUDA is available
- a trivial CUDA allocation succeeds
- driver and Torch CUDA versions look sane for the GPU generation
- `flash_attn` state is known
- selected attention fallback is known

### Stage 1: Single-worker baseline

Measure:

- `plain_ocr`, `workers_per_gpu=1`
- `markdown_grounded`, `workers_per_gpu=1`

Record:

- pages/sec
- sec/page
- avg GPU util
- peak GPU memory
- CPU load
- startup time
- per-page latency distribution

### Stage 2: Workers-per-GPU sweep

Run at least:

- `workers_per_gpu=1`
- `workers_per_gpu=2`
- `workers_per_gpu=3`
- `workers_per_gpu=4`

for both:

- `plain_ocr`
- `markdown_grounded`

### Stage 3: Attention backend check

If `flash_attn` is unavailable:

- benchmark the `sdpa` fallback
- do not accept `eager` as the main production baseline

### Stage 4: Scaling criterion

Choose the smallest `workers_per_gpu` whose throughput is within `5-10%` of the best stable result and does not introduce obvious failures, timeouts, or repeated output bugs.

### Speed target

Target:

- host-level steady-state throughput near `1 page / 1 second`

Interpretation:

- primary decision metric is aggregate host throughput after warmup
- secondary metric is throughput per GPU and stability under load

If plain OCR gets close enough but markdown mode does not, use plain OCR for remediation unless markdown fidelity is explicitly required.

## Phase 6: Quality Validation

For the `50 PDFs`, verify:

1. Polytonic Greek correctness
   - compare OCR against the direct extraction where extraction is readable
   - inspect character preservation
   - inspect accents/breathings
   - detect normalization bugs or script collapse

2. Math correctness
   - inspect formulas, symbols, delimiters, and line ordering
   - detect hallucinated repeated fragments
   - detect markdown corruption or broken delimiters

3. Output pathologies
   - repeated output loops
   - nonsense output
   - empty output
   - page truncation
   - bad page ordering
   - duplicated page text

4. Token/output-limit risk
   - identify pages whose output length is abnormally high
   - identify any truncation signatures
   - keep a per-page output-length distribution

### Quality artifact set

For every benchmark PDF, store:

- OCR markdown output
- page-level intermediate output if possible
- direct extraction text
- summary notes on correctness
- flags for:
  - polytonic bug
  - math bug
  - repeated output
  - nonsense output
  - truncation risk

## Phase 7: Full OA OCR Run

Only start the full OA remediation run after:

- stack-fit passes
- worker sweep is complete
- chosen OCR mode is frozen
- the 50-PDF sample does not show blocking correctness bugs

Then:

1. finalize the strict OA PDF manifest
2. shard by page count and collection
3. run resume-safe OCR jobs
4. maintain:
   - completion manifest
   - failure manifest
   - retry queue
   - collection-level progress summary

## Acceptance Gates

### Gate A: Host ready

- host provisioned
- `glossAPI` `development` installed
- Rust extensions build cleanly
- stack-fit review passes

### Gate B: Throughput ready

- at least one OCR mode produces acceptable throughput
- stable `workers_per_gpu` selected
- no obvious GPU underutilization caused by a broken runtime stack

### Gate C: Quality ready

- no blocking polytonic Greek corruption
- no blocking math corruption
- no repeated-output or nonsense-output failure mode that invalidates the run

### Gate D: Scale ready

- strict OA PDF manifest finalized
- resume and logging paths verified
- benchmark artifacts saved

## Immediate Next Actions

1. Add `p5en.48xlarge` host profile and runtime task example to `automated-glossapi`.
2. Patch `glossAPI` DeepSeek fallback from `eager` to `sdpa`.
3. Add OCR mode and inference-size controls to `glossAPI`.
4. Launch the `p5en.48xlarge`.
5. Bootstrap the host.
6. Download OA metadata.
7. Build the 50-PDF benchmark sample.
8. Run the throughput and quality benchmark.
