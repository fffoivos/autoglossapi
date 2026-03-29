Stage goal: hand the scraper builder a deterministic contract, not vague observations.

Push for:
- exact endpoints/selectors
- access checks and PDF filters
- request pacing and backoff
- metadata mapping
- throughput logging and investigation-trigger rules

Common recovery ideas:
- make the API path primary if the site platform supports it
- define exact fallback order when one route fails
- capture repository-specific failure modes as explicit rules

Escalate to `decision_pending_user` when:
- the adapter would need a brittle workaround that should be reviewed before building it into the scraper
