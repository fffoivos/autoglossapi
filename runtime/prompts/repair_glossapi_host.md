You are repairing an existing remote GlossAPI host.

Read first:
- `{resolved_task_path}`
- `{host_profile_path}`
- `{aws_runtime_doc_path}`
- `{stack_fit_doc_path}`
- `{runtime_readme_path}`
- `{bootstrap_script_path}`
- `{readiness_check_path}`
- `{worker_planning_path}`
{knowledge_paths_block}

Mission:
- inspect the existing host state
- use the stored readiness checks to identify what is missing or broken
- repair the minimal set of runtime issues needed to make GlossAPI usable for the task
- review whether the current OS, driver, Python, Torch, CUDA, and attention stack actually fit the GPU generation
- determine the correct OCR settings for this machine if DeepSeek OCR is in scope

Hard requirements:
- do not rebuild or reinstall blindly before checking the current state
- if DeepSeek OCR is in scope, separate stack-fit problems from worker-count problems before changing tuning parameters
- record the specific missing dependency, environment drift, or GlossAPI bug you found
- if setup succeeds, rerun the readiness check and keep the artifact
- if the host still fails, launch the runtime investigation harness with the failure evidence

Return:
- the exact root cause(s)
- the exact fixes applied
- the readiness-check artifact path
- the stack-fit conclusion, including whether a different host image, CUDA stack, or attention backend is needed
- the selected OCR parameter recommendation if tuning was requested
