Stage goal: verify the built scraper on a bounded sample before scale-up.

Push for:
- successful listing fetch
- correct item parsing
- correct PDF detection
- emitted request logs, rolling throughput, and ETA snapshot

Common recovery ideas:
- reduce concurrency and confirm correctness first
- compare scraper counts against earlier feasibility counts
- verify that sample outputs match the intended content lane

Escalate to `decision_pending_user` when:
- the smoke test shows correctness only at an ETA that misses the 48-hour target
- the outputs are technically retrievable but strategically low value
