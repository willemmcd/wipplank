# Wipplank — agent + contributor guide

Fun CLI for email on macOS + Linux. Human-friendly output + `--json` everywhere + MCP server.

## Stack

- Python >= 3.11, `uv`, `typer`, `rich`, `keyring`, `fastmcp` (optional)
- Layout: `src/wipplank/` package, `tests/` outside `src/`
- Must run on macOS + Linux via `uv tool install` / `uv run`

## Commands

```bash
uv sync --python 3.11 --all-extras
uv run wipplank --backend demo check   # zero-setup demo
uv run pytest                          # no network/secrets, ~4s
uv run pytest --cov=wipplank
WIPPLANK_LIVE=1 uv run pytest -m live  # real mailbox only, read-mostly
```

## Conventions

- `--backend` is a global flag: `wipplank --backend imap check` (not `check --backend`)
- Every command supports `--json` for agent access
- Message IDs are stable `UIDVALIDITY:UID` (legacy plain UID resolves; stale IDs fail loud)
- Reads use `BODY.PEEK` — `check` never marks mail read
- Update `README.md` on every product change (commands, flags, ID format, config paths)
- Secrets: OS keyring, service `wipplank`, key `account:<name>` — never plaintext on disk,
  except Gmail OAuth `client_id`/`client_secret` (Desktop-app public client, see `SECURITY.md`)

## Tests

- Shared fixtures in `tests/conftest.py`: temp config/cache dirs + in-memory keyring (autouse)
- `live` tests opt out of isolation and skip unless `WIPPLANK_LIVE=1`
- Markers: `live` (real mailbox), `slow` (gpg keygen)
- Missing optional deps (gmail libs, textual) skip gracefully instead of failing

## History

Long-form dev log lives in `docs/DEVLOG.md` (renames, shipped milestones, backlog).
