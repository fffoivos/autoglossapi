# OCR Worker Sizing

This note captures the current sizing model for choosing `workers_per_gpu` and estimating total OCR throughput on a machine.

## What matters most

For the current DeepSeek OCR path, the strongest practical signals are:

- usable VRAM per GPU
- peak VRAM per worker on hard pages
- CPU cores available per GPU
- CPU cores consumed per worker
- steady-state GPU utilization with one worker, excluding cold start
- number of files or pages available to keep each GPU busy

These matter more than theoretical FLOPS in the current pipeline because the runtime is not a pure dense-math loop. It includes:

- model load and cold start
- PDF rasterization
- image preparation
- per-page sequential inference
- variable output lengths
- occasional long-tail pages

## Core calculation

Use these bounds first:

- `w_mem = floor((M - H) / m)`
- `w_cpu = floor(C / c)`
- `w_util = ceil(U_target / U1)`

Where:

- `M`: GPU memory in GiB
- `H`: safety headroom in GiB
- `m`: measured peak worker memory in GiB on hard pages
- `C`: effective CPU cores available per GPU
- `c`: measured CPU cores used per active worker
- `U_target`: desired steady GPU utilization, usually `0.75` to `0.85`
- `U1`: measured steady GPU utilization with one worker

Then choose:

- `workers_per_gpu_guess = min(w_mem, w_cpu, w_util, file_bound, hard_cap)`

And validate it with a small sweep around the guess.

## Role of GPU count

`N_gpu` does not usually change the best `workers_per_gpu` on a single device directly. It mainly changes:

- total cluster throughput
- CPU-per-GPU availability on the host
- the per-GPU file/page backlog

For total throughput, the rough first estimate is:

- `cluster_pages_per_second ≈ N_gpu * pages_per_second_per_gpu`

after picking a per-GPU worker count and measuring a real steady-state rate.

So `N_gpu` is mostly a scaling factor after per-GPU sizing is chosen.

## Role of FLOPS

FLOPS is a weak secondary signal here, not a primary sizing input.

It is useful when:

- comparing two machine families before any benchmark exists
- deciding which GPU family is likely to have better upside
- breaking ties between otherwise similar hosts

It is not a reliable direct formula for `workers_per_gpu`.

For this OCR pipeline, a higher-FLOPS GPU can still underperform expectations if:

- VRAM is too small for multiple workers
- CPU feed is too slow
- page rasterization dominates
- long-tail pages stall generation

So treat FLOPS as a ranking hint, not as the main bound.

## Practical policy

1. Measure `m`, `U1`, and approximate `c` on a small hard sample.
2. Compute `w_mem`, `w_cpu`, and `w_util`.
3. Use the minimum as the initial guess.
4. Sweep a small neighborhood, usually `guess-1`, `guess`, `guess+1`.
5. Prefer the smallest worker count within roughly `5-10%` of the best throughput.
6. Reject settings that push VRAM too close to the edge or increase instability.

## Current `g7e` example

Using the current measured values:

- `M = 97.9 GiB`
- `H = 15 GiB`
- `m = 16.1 GiB`
- `C = 24`
- `c = 6`
- `U_target = 0.8`
- `U1 = 0.187`

We get:

- `w_mem = floor((97.9 - 15) / 16.1) = 5`
- `w_cpu = floor(24 / 6) = 4`
- `w_util = ceil(0.8 / 0.187) = 5`

So the initial guess is:

- `workers_per_gpu_guess = min(5, 4, 5) = 4`

That is why the current runtime bundle recommends `4` with a sweep of `[3, 4, 5]`.

## Current code paths

The calculation is implemented in:

- [worker_planning.py](/home/foivos/Projects/automated-glossapi/runtime/ocr/worker_planning.py)

The current measured benchmark knowledge is stored in:

- [deepseek_ocr_g7e_20260329.json](/home/foivos/Projects/automated-glossapi/runtime/knowledge/deepseek_ocr_g7e_20260329.json)
