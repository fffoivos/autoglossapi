# Tracking

This directory keeps the source backlog separate from the harness logic.

- `generated/`
  - machine-generated inventories derived from collection manifests and run artifacts
  - safe to regenerate with `python3 scripts/generate_tracking_backlogs.py`
- `manual/`
  - human-editable overlays for notes, decisions, and prioritization
  - intentionally not overwritten once created

The main generated files are:

- `generated/potential_sources.csv`
- `generated/active_sources.csv`
- `generated/backlog_summary.md`

`generated/active_sources.csv` now also carries the latest exact progress and review state when available, including:

- `overall_progress_percent`
- `stage_completion_percent`
- `count_completeness_percent`
- `eta_health_percent`
- `review_decision`
- `user_decision_pending`

The manual overlays are:

- `manual/potential_sources_enrichment.csv`
- `manual/active_sources_enrichment.csv`

Regenerate after new manifests or run outputs:

```bash
python3 scripts/generate_tracking_backlogs.py
```
