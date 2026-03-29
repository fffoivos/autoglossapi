# automated-glossapi

Coordination repository for direct upstream recovery of Greek academic content for GlossAPI.

This repository stores:

- agent prompts and stage definitions
- collection manifests
- stage schemas
- controller, validator, and retry routing logic
- deterministic scraper handoff artifacts
- compact lineage reports and snapshot manifests

This repository does not store:

- Codex auth
- GitHub auth
- AWS credentials
- raw PDF corpora
- bulky extracts
- large logs

Raw PDFs, extracted outputs, and large run artifacts belong in AWS S3.

## Current focus

The current workflow targets direct upstream recovery from university repositories that feed `openarchives.gr`, with priority on:

1. Greek-language fit
2. high-quality academic text
3. easy deterministic traversal
4. low stub / notice pollution

The first execution wave is defined in [wave1_high_quality_easy.json](config/collections/wave1_high_quality_easy.json).

## Layout

- [config/collections](config/collections): collection manifests for direct-recovery work
- [controller](controller): staged Codex harness plus validation and routing logic
- [docs](docs): operator docs, architecture plan, and secret policy
- [schemas](schemas): JSON schemas for stage reports and routing decisions
- [scripts](scripts): deterministic helpers such as manifest generation
- [tracking](tracking): generated source backlogs plus manual enrichment overlays
- [tests](tests): unit and harness dry-run tests

## Quick start

Dry-run the first discover wave without spending tokens:

```bash
python3 controller/launch_codex_exec_harness.py \
  --stage discover \
  --collections-file config/collections/wave1_high_quality_easy.json
```

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

## Key docs

- [docs/architecture_plan.md](docs/architecture_plan.md)
- [docs/secret_policy.md](docs/secret_policy.md)
- [docs/operator_runbook.md](docs/operator_runbook.md)
- [TODO.md](TODO.md)
