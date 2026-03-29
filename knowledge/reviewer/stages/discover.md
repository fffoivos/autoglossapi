Stage goal: identify the repository shape and the highest-value crawl lane quickly, without pretending that weak evidence is enough.

Push for:
- a canonical repo URL
- platform/API identification
- page-level traversal from home to collection to item to file
- explicit repository-wide and per-collection count claims
- a conservative request-capacity note

Common recovery ideas:
- switch from HTML scraping to public APIs, OAI-PMH, RSS, sitemap, or JSON endpoints
- focus on one high-value subcollection instead of the whole site tree
- separate metadata-route tolerance from file-download tolerance
- if file probes trigger `429`, slow down and probe reset-window behavior instead of hammering harder
- if the repo hides counts in the UI, compare website claims, API totals, and observed list counts explicitly

Escalate to `decision_pending_user` when:
- the only next move involves proxies, identity changes, or paid scraping infrastructure
- ETA already looks incompatible with the 48-hour target and the only remedies are large parallelism or paid access
- the repository seems to require a strategic choice between completeness and staying within safe request patterns
