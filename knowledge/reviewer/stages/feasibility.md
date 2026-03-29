Stage goal: prove that deterministic crawling is actually possible.

Push for:
- deterministic collection entry and list traversal
- stable pagination or cursor logic
- exact count reconciliation
- real PDF detection versus notice/login/placeholder pages
- measured metadata/file throughput plus ETA

Common recovery ideas:
- validate API counts first, then HTML counts
- benchmark metadata and file routes separately
- reduce request frequency before reducing parallelism; measure the result
- if the API can list bitstreams directly, prefer it over HTML item-page scraping
- if count reconciliation fails, record the discrepancy precisely and find whether hidden filters or access restrictions explain it

Escalate to `decision_pending_user` when:
- best-case ETA remains above 48 hours after conservative tuning
- the site requires non-routine anti-bot workarounds
- completeness requires accessing content that is not openly published
