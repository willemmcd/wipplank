# Security

Wipplank handles email credentials. Rules:

- IMAP passwords and Gmail OAuth tokens live in the OS keyring only
  (service `wipplank`, key `account:<name>`). They are never written to disk.
- `~/.config/wipplank/config.json` holds hosts, usernames, and preferences only.
- `auth status --json` / `account list --json` never emit secrets
  (`client_secret` is filtered from output).
- Known exception: Gmail OAuth Desktop-app `client_id` / `client_secret` are stored
  in `config.json` in plaintext (`src/wipplank/backends_gmail.py`). These are public
  client values, not user secrets — but they contradict the "no secrets on disk"
  shorthand, so they are called out here. Planned fix: move them to keyring.
- `read` / `check` use `BODY.PEEK` and never mark mail read as a side effect.
- Do not commit `.env` files, `credentials.json`, `client_secret*.json`, `*.pem`,
  `*.key`, or `*.sqlite` files. They are covered by `.gitignore`.
- To report a vulnerability, open a private security advisory on GitHub
  (or contact the maintainer) rather than filing a public issue.
