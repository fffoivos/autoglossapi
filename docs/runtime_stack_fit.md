# Runtime Stack Fit

This note covers the compatibility review that should happen before a host is treated as ready for GlossAPI OCR.

## Why this exists

A machine can have many GPUs and still be the wrong runtime for DeepSeek OCR if the chosen Python, Torch, CUDA, driver, and attention stack do not match the GPU generation.

That means runtime setup must answer two questions before benchmarking:

1. can this runtime actually execute on the target GPU generation?
2. is this runtime a sane performance baseline for the target workload?

Workers-per-GPU tuning only matters after both answers are yes.

## Minimum review

For DeepSeek OCR, collect and review:

- OS release
- instance type and GPU model
- NVIDIA driver version
- selected Python interpreter
- selected Torch version
- selected Torch CUDA build
- Torch CUDA arch list
- whether `torch.cuda.is_available()` is true
- whether a trivial CUDA allocation works
- whether `flash_attn` is importable
- what attention backend the runtime uses when flash-attn is missing
- whether the OCR path is using a heavy layout-preserving markdown mode or a lighter plain OCR mode

## Blackwell rule

Treat Blackwell-class GPUs as a stack-fit risk if the selected OCR runtime is still pinned to an older CUDA build such as `cu118`.

Operationally:

- prefer a modern Torch build on CUDA `12.8+` or `13.0`
- verify that Torch includes the actual GPU architecture in its CUDA arch list
- do not trust throughput results from a runtime that cannot perform a basic CUDA allocation on the selected GPU

## Attention backend rule

If `flash_attn` is not available, `sdpa` is the preferred fallback on modern PyTorch.

Treat `eager` fallback as a throughput warning, not a neutral default.

## OCR mode rule

Keep OCR mode separate from stack fit:

- grounded markdown mode is heavier and may be the right quality choice
- lighter plain OCR mode may be the right throughput choice

Benchmark notes should make this explicit so a slower result is not blamed on worker count when it is actually caused by a heavier OCR mode.

## Planning rule

On AWS and other flexible infrastructure providers, host selection should consider:

- GPU generation and memory
- driver maturity on the chosen AMI or base image
- a clean Torch/CUDA path for that generation
- whether the attention stack is known-good on that hardware
- whether the chosen OCR mode matches the job goal

Only after the stack-fit review passes should the task move on to `workers_per_gpu` estimation and OCR benchmarking.
