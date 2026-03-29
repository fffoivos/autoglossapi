# Reviewer Knowledge

This folder gives the review agent stage-specific recovery ideas and decision boundaries.

Usage:
- `stages/<stage>.md`: concrete heuristics for success, bounded retries, and when to mark `decision_pending_user`
- `tracking/manual/problem_solution_index.csv`: manually curated problem -> solution -> implementation references
- `tracking/generated/reviewer_recovery_*.{csv,md}`: generated recovery cases and aggregate stats from prior runs

Intent:
- keep the worker focused on exact progress and exact blockers
- let the reviewer suggest better next moves without losing local context
- accumulate reusable knowledge when a lineage finds a good fix
