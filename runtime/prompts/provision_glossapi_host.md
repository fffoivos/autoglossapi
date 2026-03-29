You are preparing a remote host to run GlossAPI reliably.

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
- provision or upgrade the target host so it satisfies the resolved task bundle
- use the stored runtime scripts and docs instead of improvising the setup
- ensure GlossAPI is on the requested branch
- ensure Rust, Cargo, and native build prerequisites are present when required
- ensure the DeepSeek runtime is valid when OCR is requested
- run the readiness check after setup and keep the output with the task artifacts
- if OCR benchmarking or auto worker tuning is requested, compute the initial worker guess and run the minimum benchmark needed to validate it

Hard requirements:
- do not mark the task done unless every `what_must_be_true` item in the task bundle is satisfied or explicitly classified as blocked
- preserve structured evidence under `{output_dir}`
- if a failure occurs, write a concise incident note and launch the runtime investigation harness if the task bundle says to do so

Return:
- a concise summary of what was changed
- the exact remaining blockers if not complete
- the readiness-check artifact path
- the selected OCR parameter recommendation if OCR tuning was part of the task
