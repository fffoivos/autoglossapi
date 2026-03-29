Stage goal: turn the adapter into robust deterministic code.

Push for:
- bounded repository-specific code
- request logging and rolling ETA metrics
- clear investigation triggers
- tests or fixtures for the risky parts

Common recovery ideas:
- isolate site-specific parsing behind a small adapter surface
- log enough per request to debug throttling and content-type surprises
- prefer minimal retries with explicit backoff rather than silent loops

Escalate to `decision_pending_user` when:
- the code would need infrastructure or paid services not already approved
- throughput remains too weak after conservative engineering fixes
