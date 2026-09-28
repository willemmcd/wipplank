"""MCP server - lets your IA read/send on your behalf."""
# Run with: wipplank mcp [--backend imap]
# Requires: pip install wipplank[mcp]
import os


def _resolve() -> tuple[str | None, str]:
    """Returns (account, backend_kind). Account wins; env WIPPLANK_ACCOUNT next."""
    try:
        from .config import load_config
    except Exception:
        return None, os.environ.get("WIPPLANK_BACKEND", "demo")
    cfg = load_config()
    acct = os.environ.get("WIPPLANK_ACCOUNT") or cfg.get("default_account")
    if acct and acct != "demo" and acct in cfg.get("accounts", {}):
        return acct, "demo"
    return None, os.environ.get("WIPPLANK_BACKEND") or cfg.get("default_backend", "demo")


def run(backend_kind: str | None = None, account: str | None = None):
    try:
        from fastmcp import FastMCP
    except ImportError:
        raise SystemExit("fastmcp not installed. Run: pip install 'wipplank[mcp]'")

    from .backends import get_backend

    if account:
        acct, kind = account, "demo"
    elif backend_kind and backend_kind != "demo":
        acct, kind = None, backend_kind
    else:
        acct, kind = _resolve()
    mcp = FastMCP("wipplank")

    def _be():
        # resolve per-call so config changes don't need a server restart
        if account:
            return get_backend("demo", account=account)
        a, k = _resolve()
        return get_backend(k, account=a)

    @mcp.tool()
    def list_emails(limit: int = 20) -> list[dict]:
        """List recent emails. IDs are stable 'UIDVALIDITY:UID' for imap, plain for demo."""
        return [m.to_dict() for m in _be().list_messages(limit)]

    @mcp.tool()
    def read_email(msg_id: str, decrypt: bool = False) -> dict:
        """Read a full email by id (read-only, does not mark seen)."""
        m = _be().get_message(msg_id)
        d = m.to_dict()
        if decrypt:
            from . import pgp as pgpmod

            if pgpmod.detect(m.body) == "encrypted":
                d["body"] = pgpmod.decrypt(m.body)
                d["pgp"] = "PGP decrypted."
        return d

    @mcp.tool()
    def search_emails(query: str, limit: int = 20) -> list[dict]:
        """Search emails server-side."""
        return [m.to_dict() for m in _be().search(query, limit)]

    @mcp.tool()
    def send_email(
        to: str, subject: str, body: str, attachments: list[str] | None = None,
        sign: bool = False, encrypt_to: list[str] | None = None,
    ) -> dict:
        """Send an email. attachments = list of local file paths. sign/encrypt_to use server PGP keys."""
        from . import pgp as pgpmod

        if encrypt_to:
            body = pgpmod.encrypt(body, encrypt_to, sign=True if sign else None)
        elif sign:
            body = pgpmod.sign(body)
        return _be().send(to, subject, body, attachments=attachments).to_dict()

    @mcp.tool()
    def reply_email(msg_id: str, body: str, attachments: list[str] | None = None) -> dict:
        """Reply with quoting + threading headers."""
        from . import compose as comp

        be = _be()
        orig = be.get_message(msg_id)
        full = f"{body}{comp.quote_body(orig)}"
        dest = comp.reply_address(orig, "")
        in_reply_to, refs = comp.thread_headers(orig)
        return be.send(
            dest, comp.reply_subject(orig.subject), full,
            attachments=attachments, in_reply_to=in_reply_to,
            references=refs).to_dict()

    @mcp.tool()
    def forward_email(msg_id: str, to: str, body: str = "") -> dict:
        """Forward a message."""
        from . import compose as comp

        be = _be()
        orig = be.get_message(msg_id)
        fwd = (f"{body}\n\n---------- Forwarded message ----------\n"
               f"From: {orig.from_}\nDate: {orig.date}\n"
               f"Subject: {orig.subject}\n\n{orig.body}")
        return be.send(to, comp.forward_subject(orig.subject), fwd).to_dict()

    @mcp.tool()
    def backend_status() -> dict:
        """Which account/backend the MCP server is using."""
        a, k = (account, kind) if account or kind != "demo" else _resolve()
        return {"account": a, "backend": k}

    @mcp.tool()
    def mark_emails(msg_ids: list[str], read: bool | None = None,
                    flagged: bool | None = None) -> dict:
        """Mark read-state / stars. Pass read True/False and/or flagged True/False."""
        be = _be()
        out: dict = {}
        if read is not None:
            out["seen"] = be.mark_seen(msg_ids, read)
        if flagged is not None:
            out["flagged"] = be.mark_flagged(msg_ids, flagged)
        return out

    @mcp.tool()
    def list_attachments(msg_id: str) -> list[dict]:
        """List attachment names + sizes without downloading."""
        return [{"name": n, "size": len(b)}
                for n, b in _be().get_attachments(msg_id)]

    # resolved now so startup failures are loud, not silent demo fallback
    get_backend(kind, account=acct)
    mcp.run()
