# Wipplank - no boring email allowed

Fun CLI for email on macOS + Linux. Human-friendly output + `--json` everywhere + MCP server so your IA can read/send on your behalf.

## Quick start

```bash
# 1. install (from repo root)
uv sync --python 3.11 --all-extras

# 2. try demo (zero setup)
uv run wipplank --backend demo check
uv run wipplank party

# 3. configure accounts (IMAP and/or Gmail)
uv run wipplank auth login --account work --preset fastmail --username you@fastmail.com
# presets: fastmail, icloud, gmail, outlook
# custom IMAP:
# uv run wipplank auth login --account other --host imap.example.com --smtp-host smtp.example.com --username you@example.com
# Gmail OAuth (needs Google Cloud Desktop-app client ID + secret, browser flow):
# uv run wipplank auth login --backend gmail --account personal --client-id ID --client-secret SECRET

uv run wipplank account list
uv run wipplank account default work
# use: --account NAME, or plain commands hit the default account
uv run wipplank --account personal check

# 4. use it (defaults to imap after login)
uv run wipplank check
uv run wipplank check --limit 5
uv run wipplank read 1789539853:1
uv run wipplank search "invoice"
uv run wipplank send --to bob@example.com -s "hi" --body "hello"
uv run wipplank send --to bob@example.com -s "files" --body "see attached" -a ./report.pdf -a ./photo.png
uv run wipplank reply 1789539853:1 --body "Thanks!" --dry-run
uv run wipplank forward 1789539853:1 --to team@example.com --dry-run
uv run wipplank auth status --json
```

Note: `--backend` is a global flag, so `wipplank --backend imap check` (not `check --backend`).
IDs are stable `UIDVALIDITY:UID` (legacy plain UID still resolves; stale IDs fail loud). Reads use `BODY.PEEK` — `check` never marks mail read.

## Attachments

- `-a / --attach` is repeatable, absolute paths work: `-a /Users/you/Documents/test.pdf`
- Only basenames are sent as attachment names
- `check` / `read --json` include `attachments: [...]`

## Compose

```bash
# reply / forward with quoting + threading
uv run wipplank reply 1789539853:1 --body "On it." --dry-run
uv run wipplank forward 1789539853:1 --to team@example.com --body "FYI"

# dry-run + attachment guard (mentions of attach/.pdf with no -a abort unless --force)
uv run wipplank send --to x -s y --body "see attached" --dry-run
uv run wipplank send --to x -s y --body "see attached" -a ./f.pdf

# templates + signature + drafts
uv run wipplank template save standup --subject "Standup {to}" --body "Hi {to}, ..."
uv run wipplank send --to x --template standup --dry-run
uv run wipplank signature set "Your Name"
uv run wipplank send --to x -s t --body b --save-draft d1
uv run wipplank draft list && uv run wipplank draft send d1
```

## Reading

- HTML-only mail auto-converts to text (stdlib, no w3m needed); `text/plain` wins when present
- Converted bodies are marked `[HTML mail — converted to text]`

## OpenPGP (body-only)

```bash
pip install 'wipplank[openpgp]'   # needs gpg binary + existing keys
uv run wipplank send --to x -s t --body b --sign [--gpg-key KEYID]
uv run wipplank send --to x -s t --body b --encrypt-to x [--trust]
uv run wipplank read 1789539853:1            # shows PGP status footer
uv run wipplank read 1789539853:1 --decrypt  # decrypt (pinentry via gpg-agent)
```

Attachments are never encrypted/signed in v1. Key gen/import stays in `gpg`.

## Organize + attachments
```bash
uv run wipplank mark 1789539853:1 --read --flag
uv run wipplank mark 1789539853:1 --unread --unflag
uv run wipplank saved save news "biggest news"
uv run wipplank saved run news
uv run wipplank attach list 1789539853:1
uv run wipplank attach save 1789539853:1 --dir ./downloads
uv run wipplank attach open 1789539853:1 --index 0
```

## TUI

```bash
pip install 'wipplank[tui]'
uv run wipplank tui                  # default account
uv run wipplank --account work tui
```

Keys: `enter` open · `/` search · `u` read/unread · `s` star · `c` compose (`ctrl+s` send) · `r` reload · `q` quit.

## IA access

```bash
uv run wipplank check --limit 5 --json
uv run wipplank read 1789539853:1 --json
uv run wipplank send --to x -s y --body z --json
uv run wipplank reply 1789539853:1 --body "Ack." --dry-run --json
# MCP server uses your configured backend (demo/imap), honors --backend + WIPPLANK_BACKEND:
uv run wipplank mcp                       # needs `pip install wipplank[mcp]`
uv run wipplank --backend imap mcp
```

## Config

- Accounts: `~/.config/wipplank/config.json` → `accounts: {name: {type: imap|gmail, ...}}` (no secrets on disk)
- Secrets: OS keyring, service `wipplank`, key `account:<name>` (OAuth tokens for gmail, passwords for imap). Exception: Gmail OAuth Desktop-app `client_id`/`client_secret` stay in config (public client values, see `SECURITY.md`)
- Legacy single `imap` section auto-migrates to `accounts.default` on first run
- `auth logout` clears legacy single-account state; `account rm NAME` removes one account

## Speed (local cache)
- Repeat `check`/`read`/`search` are served from `~/.cache/wipplank/cache.sqlite` — warm checks cost STATUS + SEARCH + one FLAGS refresh, no body re-fetch
- Cache is keyed by `UIDVALIDITY:UID`; a regenerated mailbox auto-invalidates
- `--fresh` bypasses the cache; `wipplank cache-clear` drops it entirely

## Troubleshooting

- `No IMAP account configured` → run `auth login`
- `No password in keyring` → re-run `auth login`
- Gmail/iCloud need an app-specific password, not your normal login

## Testing

```bash
uv sync --python 3.11 --all-extras  # base + gmail/mcp/tui/openpgp/test deps
uv run pytest                       # 60 tests green, ~4s, no network/secrets
uv run pytest --cov=wipplank       # coverage (~65%)
WIPPLANK_LIVE=1 uv run pytest -m live   # real mailbox: read-only + flag round-trip (restores state)
```

- Layout follows pytest convention: `tests/` outside `src/`, shared fixtures in `tests/conftest.py`
- Every test is isolated: temp config/cache dirs + in-memory keyring (autouse fixture); `live` tests opt out
- Markers: `live` (real mailbox, skipped by default), `slow` (gpg keygen)
- Missing optional deps (gmail libs, textual) skip gracefully instead of failing

## Contributing

See `AGENTS.md` (agent + contributor guide) and `docs/DEVLOG.md` (history).
Landing site lives in `wipplank-landing/` — replace the placeholder
`https://github.com/` URLs in `app/page.tsx` with the real repo URL.

## License

MIT — see `LICENSE`.

