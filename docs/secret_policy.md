# Secret Policy

No live secrets belong in this repository.

## Must never be committed

- GitHub tokens
- AWS access keys
- Hugging Face tokens
- Codex auth files
- SSH private keys
- browser cookies
- presigned S3 URLs
- `.env` files with real values

## Allowed

- `.env.example`
- redacted config examples
- non-secret bucket names
- non-secret hostnames
- instance ids
- operator instructions for injecting secrets at runtime

## Runtime model

- Keep `gh` auth in the user's home directory, not in the repo.
- Keep Codex auth in a dedicated `CODEX_HOME` outside the repo.
- Prefer IAM roles for AWS access.
- Use out-of-repo env files or secret stores for anything IAM cannot cover.

## Git hygiene

- Review `git status` before every commit.
- Do not stage generated runs or local caches by default.
- Treat `runs/` as disposable local execution state unless a compact summary is explicitly exported.
