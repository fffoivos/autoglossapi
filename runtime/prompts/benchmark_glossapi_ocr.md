You are benchmarking GlossAPI OCR performance on an already prepared host.

Read first:
- `{resolved_task_path}`
- `{host_profile_path}`
- `{aws_runtime_doc_path}`
- `{runtime_readme_path}`
- `{bootstrap_script_path}`
- `{readiness_check_path}`
- `{worker_planning_path}`
{knowledge_paths_block}

Mission:
- verify the runtime is ready before benchmarking
- use the task bundle inputs to choose an initial `workers_per_gpu` guess
- run the smallest benchmark sweep that can validate or reject the guess
- capture throughput, seconds per page, GPU utilization, and peak memory
- recommend the best stable parameter choice for this machine

Hard requirements:
- isolate setup failures from benchmark failures
- preserve all benchmark artifacts under `{output_dir}`
- if the benchmark encounters pathological long-tail failures, report them as runtime issues rather than silently averaging them away

Return:
- the measured benchmark comparison
- the chosen parameter set
- the artifact paths needed to reproduce the decision
