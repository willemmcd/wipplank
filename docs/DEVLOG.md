# Wipplank dev log

Historical agent working notes (pre-open-source). Kept for context; the
curated contributor guide is `AGENTS.md` at the repo root.

> Note (2026-09-18): `website/` below means `wipplank-landing/`;
> `website-v1-fun/` was an earlier archived build and is not in this repo.

## Project

- Name: Wipplank (AgentMail → Postbag → Wipplank; Wipplank=Afrikaans seesaw, zero collision hits)
- Goal: fun CLI for email (no boring email), human + AI access
- Domain: wipplank.org.za. Open source, no vendor references.
- Stack: Python >=3.11, `uv`, `typer`, `rich`, `keyring`, `fastmcp` (optional)
- Must run on macOS + Linux via `uv tool install` / `uv run`

## Status (2026-09-16)

- P0 trio shipped: BODY.PEEK reads (no Seen flip), stable IDs `UIDVALIDITY:UID` + message_id (legacy UID resolves, stale fails loud), MCP uses configured backend (was demo-only) + reply/forward tools + backend_status
- Compose trio shipped: `reply`/`forward` with quoting + threading, `--dry-run` + noattach guard (`--force` bypass), templates/signatures/drafts (`src/wipplank/compose.py`)
- `send` extended: --template, --save-draft, --dry-run, --force, --no-signature; backends carry in_reply_to/references
- Live verified vs a private IMAP account (host redacted): stable IDs, reply dry-run threads correctly; test template/draft cleaned up
- Website v2 minimal flat (no emojis), spec table current; README covers compose + P0
- Session efficiency shipped: sqlite cache `~/.cache/wipplank/cache.sqlite` keyed by UIDVALIDITY:UID (`src/wipplank/imap_cache.py`); warm check = STATUS+SEARCH+FLAGS, no body FETCH; `--fresh` bypass + `cache-clear`; stale-validity still fails loud; demo unaffected
- Organize trio shipped: `mark` read/unread/flag via STORE + cache patch; `saved` named searches in config; `attach list/save/open` (PEEK fetch, temp+OS-open); live round-trip verified, flags restored; Message gained `flagged`
- Multi-account + Gmail OAuth shipped: `accounts:{name:{type}}` in config with legacy `imap` auto-migrate to `accounts.default` (live-migrated, fields+secret preserved); `--account` flag + default_account resolution; GmailBackend real (OAuth browser flow, list/get/search/send/mark/attachments, stable Gmail IDs); JMAP explicitly out of scope
- TUI shipped (`src/wipplank/tui.py`, `pip install wipplank[tui]`): inbox table + reader + search + read/star toggles + compose modal (ctrl+s); headless pilot-tested on demo (3 rows, search→1, modal open/close)
- HTML→text shipped (`src/wipplank/htmltext.py`, stdlib): IMAP + Gmail prefer text/plain, convert text/html fallback (links kept as `text (url)`, script/style dropped); fixed Gmail walker dropping html parts
- PGP shipped (`src/wipplank/pgp.py`, `pip install wipplank[openpgp]`): body-only inline sign/encrypt on send/reply/forward, verify footer + `--decrypt` on read, MCP send/read support; round-tripped with throwaway keys (sign→verify, encrypt→decrypt); attachments explicitly out of scope v1
- Test framework shipped (`tests/`, 60 passed): pytest + asyncio-auto + cov, conftest isolation (tmp config/cache/keyring, brand-migration pinned), FakeIMAPConn/FakeGmailService, TUI pilot, `live` marker (3 live tests green, flags restored); caught real bugs: forward_subject prefix, duplicate password block in ImapBackend, gpg socket-path length
- Rename Postbag→Wipplank shipped: package `src/wipplank`, `wipplank` entry, `~/.config/wipplank` + `~/.cache/wipplank` + keyring service `wipplank`, migration chain wipplank→postbag→agentmail; live account carried over untouched

## Standing rules

- Update README on every product change (pretty much always) — commands, flags, ID format, config paths
- Update website only when the contract changes (new commands, spec rows, start sequence, status) — keep edits surgical, style untouched

## Baseline (2026-09-11)

- Scaffold done: `pyproject.toml`, `src/wipplank/` (cli, models, fun, backends, config, mcp_server)
- Commands: `check`, `read`, `search`, `send`, `party`, `auth login|logout|status`, `mcp`
- Every command supports `--json` for IA access
- Backend flag is callback-level: `wipplank --backend imap check` (not `check --backend`)
- `demo` backend works with zero setup, includes Boredom Patrol demo
- `imap` backend implemented (stdlib `imaplib` + `smtplib`): list/read/search/send, UID as ID, TEXT search, Seen→unread
- Config: `~/.config/wipplank/config.json` (hosts only), password in OS keyring service `wipplank`, key `imap:<username>`
- Presets: fastmail, icloud, gmail, outlook
- `auth login` sets `default_backend=imap`, `auth logout` clears config + keyring — tested full cycle
- `gmail` backend still stub, `mcp` needs `pip install wipplank[mcp]`

## User preferences

- Wants flipping fun, no boring email: keep `fun.py` moods, celebrations, Boredom Patrol
- Chose Python after Go recommendation
- Wants IA to read/send on behalf via MCP + `--json`

## Next (backlog, high → low)

- Publish: Homebrew tap / pipx, single binary (tests green-gate it)
- JMAP support (new protocol backend; no claims made anywhere — verified)
- Only if mailbox grows painful: persistent session daemon (sirup model) — cache covers it for now
