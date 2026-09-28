"""Wipplank CLI - Typer + Rich, --json everywhere for IA access."""
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from typing import List

from . import fun
from .backends import get_backend
from .config import PRESETS, load_config

app = typer.Typer(help="Wipplank ✉️  no boring email allowed", rich_markup_mode="rich")
auth_app = typer.Typer(help="Login / logout / status")
app.add_typer(auth_app, name="auth")

console = Console()


def _out(data, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
    return data


def _table(messages) -> Table:
    t = Table(title="📬 Wipplank Inbox", show_lines=False)
    t.add_column("ID", style="cyan")
    t.add_column("From", style="green")
    t.add_column("Subject", style="bold")
    t.add_column("Date", style="dim")
    for m in messages:
        dot = "● " if m.unread else "  "
        t.add_row(m.id, m.from_, dot + m.subject, m.date)
    return t


@app.callback()
def main(
    ctx: typer.Context,
    backend: Optional[str] = typer.Option(
        None, "--backend", help="demo, gmail, imap (default: configured or demo)"
    ),
    account: Optional[str] = typer.Option(
        None, "--account", help="Named account (overrides --backend)"
    ),
    fun_mode: bool = typer.Option(True, "--fun/--no-fun", help="Toggle fun"),
):
    ctx.ensure_object(dict)
    # resolve default from config so `auth login` sticks
    cfg = load_config()
    if not account and not backend:
        default_acct = cfg.get("default_account")
        if default_acct and default_acct != "demo" and default_acct in cfg.get("accounts", {}):
            account = default_acct
    ctx.obj["account"] = account
    ctx.obj["backend"] = (backend or cfg.get("default_backend") or "demo").lower()
    ctx.obj["fun"] = fun_mode


def _be(ctx: typer.Context):
    acct = ctx.obj.get("account")
    if acct:
        return get_backend("demo", account=acct)
    return get_backend(ctx.obj["backend"])


@app.command()
def check(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-n"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable for IA"),
    fresh: bool = typer.Option(False, "--fresh", help="Bypass local cache"),
):
    """Check your inbox."""
    be = _be(ctx)
    if fresh and hasattr(be, "use_cache"):
        be.use_cache = False
    if ctx.obj["fun"] and not json_output:
        with console.status(fun.random_mood()):
            msgs = be.list_messages(limit)
    else:
        msgs = be.list_messages(limit)
    _out([m.to_dict() for m in msgs], json_output)
    if json_output:
        return
    if not msgs:
        fun.celebrate()
        return
    console.print(_table(msgs))
    for m in msgs:
        warn = fun.boring_patrol(m.subject)
        if warn and ctx.obj["fun"]:
            console.print(f"[yellow]{warn}[/] ({m.id})")


@app.command()
def read(
    ctx: typer.Context,
    msg_id: str = typer.Argument(..., help="Message ID"),
    json_output: bool = typer.Option(False, "--json"),
    fresh: bool = typer.Option(False, "--fresh", help="Bypass local cache"),
    decrypt: bool = typer.Option(False, "--decrypt", help="Decrypt PGP body"),
):
    """Read a full email."""
    be = _be(ctx)
    if fresh and hasattr(be, "use_cache"):
        be.use_cache = False
    m = be.get_message(msg_id)
    pgp_note = ""
    if decrypt or not json_output:
        from . import pgp as pgpmod

        kind = pgpmod.detect(m.body)
        if kind == "signed":
            v = pgpmod.verify(m.body)
            pgp_note = ("PGP signed: VALID"
                        f" ({v['username'] or v['fingerprint']})" if v["valid"]
                        else f"PGP signed: UNVERIFIED ({v['status']})")
        elif kind == "encrypted":
            if decrypt:
                m.body = pgpmod.decrypt(m.body)
                pgp_note = "PGP decrypted."
            elif not json_output:
                pgp_note = "PGP encrypted. Re-run with --decrypt."
    d = m.to_dict()
    if pgp_note:
        d["pgp"] = pgp_note
    _out(d, json_output)
    if json_output:
        return
    console.print(f"[bold]{m.subject}[/] [dim]({m.id})[/]")
    console.print(f"[green]{m.from_}[/] → {m.to} • {m.date}\n")
    console.print(m.body)
    if pgp_note:
        console.print(f"\n[dim]{pgp_note}[/]")


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", "-n"),
    json_output: bool = typer.Option(False, "--json"),
    fresh: bool = typer.Option(False, "--fresh", help="Bypass local cache"),
):
    """Search emails."""
    be = _be(ctx)
    if fresh and hasattr(be, "use_cache"):
        be.use_cache = False
    msgs = be.search(query, limit)
    _out([m.to_dict() for m in msgs], json_output)
    if json_output:
        return
    console.print(_table(msgs))


@app.command()
def send(
    ctx: typer.Context,
    to: str = typer.Option(..., "--to", help="Recipient"),
    subject: str = typer.Option("", "--subject", "-s"),
    body: str = typer.Option("", "--body", "-b"),
    body_file: Optional[str] = typer.Option(None, "--body-file"),
    attach: Optional[List[str]] = typer.Option(
        None, "--attach", "-a", help="Attach file (repeat for multiple)"
    ),
    template: Optional[str] = typer.Option(None, "--template", "-t"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview, do not send"),
    force: bool = typer.Option(False, "--force", help="Bypass attachment guard"),
    save_draft: Optional[str] = typer.Option(None, "--save-draft"),
    no_signature: bool = typer.Option(False, "--no-signature"),
    sign: bool = typer.Option(False, "--sign", help="PGP clearsign body"),
    gpg_key: Optional[str] = typer.Option(None, "--gpg-key", help="Key ID (default key if omitted)"),
    encrypt_to: Optional[List[str]] = typer.Option(None, "--encrypt-to", help="PGP encrypt to (repeatable)"),
    trust: bool = typer.Option(False, "--trust", help="Trust recipient keys (always-trust)"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Send an email."""
    from . import compose as comp

    if template:
        t = comp.get_template(template)
        subject = subject or comp.render(t["subject"], {"to": to})
        t_body = comp.render(t["body"], {"to": to, "subject": subject})
        body = f"{body}\n{t_body}" if body else t_body
    if body_file:
        with open(body_file) as f:
            body = f.read()
    if not body:
        raise typer.BadParameter("Provide --body, --body-file, or --template")
    if not subject:
        raise typer.BadParameter("Provide --subject (or a template with one)")
    if not no_signature:
        body = comp.apply_signature(body)
    warn = comp.needs_attachment_warning(body, attach)
    if warn and not force:
        raise typer.BadParameter(warn)
    body = _maybe_pgp(body, sign, gpg_key, encrypt_to, trust)
    if save_draft:
        p = comp.save_draft(
            save_draft,
            {"kind": "send", "to": to, "subject": subject, "body": body,
             "attachments": list(attach or [])},
        )
        console.print(f"Draft saved: {save_draft} ({p})")
        if dry_run:
            _preview(to, subject, body, attach or [])
        return
    if dry_run:
        _out({"to": to, "subject": subject, "body": body,
              "attachments": [Path(a).name for a in (attach or [])],
              "dry_run": True}, json_output)
        if not json_output:
            _preview(to, subject, body, attach or [])
        return
    be = _be(ctx)
    warn_fun = fun.boring_patrol(subject)
    if warn_fun and ctx.obj["fun"] and not json_output:
        console.print(f"[yellow]{warn_fun}[/]")
    m = be.send(to, subject, body, attachments=attach)
    _out(m.to_dict(), json_output)
    if json_output:
        return
    suffix = f" 📎 {len(m.attachments)} attach" if m.attachments else ""
    console.print(f"[bold green]Sent![/] ✈️  to {to} (id: {m.id}){suffix}")


def _preview(to: str, subject: str, body: str, attach: list):
    console.print("[bold]--- dry run preview ---[/]")
    console.print(f"To: {to}\nSubject: {subject}\n")
    console.print(body)
    if attach:
        console.print(f"\n[dim]Attachments: {', '.join(attach)}[/]")


def _maybe_pgp(body: str, sign: bool, gpg_key: Optional[str],
               encrypt_to: Optional[List[str]], trust: bool) -> str:
    if not sign and not encrypt_to:
        return body
    from . import pgp as pgpmod

    if encrypt_to:
        return pgpmod.encrypt(body, list(encrypt_to),
                              sign=gpg_key or (True if sign else None),
                              trust=trust)
    return pgpmod.sign(body, keyid=gpg_key)


@app.command()
def reply(
    ctx: typer.Context,
    msg_id: str = typer.Argument(...),
    body: str = typer.Option("", "--body", "-b", help="Your reply text above the quote"),
    body_file: Optional[str] = typer.Option(None, "--body-file"),
    to: Optional[str] = typer.Option(None, "--to", help="Override recipient"),
    attach: Optional[List[str]] = typer.Option(None, "--attach", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force: bool = typer.Option(False, "--force"),
    no_quote: bool = typer.Option(False, "--no-quote"),
    sign: bool = typer.Option(False, "--sign", help="PGP clearsign body"),
    gpg_key: Optional[str] = typer.Option(None, "--gpg-key"),
    encrypt_to: Optional[List[str]] = typer.Option(None, "--encrypt-to"),
    trust: bool = typer.Option(False, "--trust"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Reply with quoting + threading headers."""
    from pathlib import Path as _P

    from . import compose as comp

    be = _be(ctx)
    orig = be.get_message(msg_id)
    if body_file:
        with open(body_file) as f:
            body = f.read()
    full = f"{body}{'' if no_quote else comp.quote_body(orig)}" if body else (
        "" if no_quote else comp.quote_body(orig).lstrip()
    )
    if not full.strip():
        raise typer.BadParameter("Empty reply. Provide --body.")
    full = comp.apply_signature(full)
    dest = to or comp.reply_address(orig, "")
    if not dest:
        raise typer.BadParameter("Cannot infer recipient, pass --to")
    subject = comp.reply_subject(orig.subject)
    warn = comp.needs_attachment_warning(full, attach)
    if warn and not force:
        raise typer.BadParameter(warn)
    full = _maybe_pgp(full, sign, gpg_key, encrypt_to, trust)
    if dry_run:
        _out({"to": dest, "subject": subject, "body": full,
              "in_reply_to": orig.message_id,
              "attachments": [_P(a).name for a in (attach or [])],
              "dry_run": True}, json_output)
        if not json_output:
            _preview(dest, subject, full, attach or [])
            console.print(f"[dim]In-Reply-To: {orig.message_id or '(none)'}[/]")
        return
    in_reply_to, refs = comp.thread_headers(orig)
    m = be.send(dest, subject, full, attachments=attach,
                in_reply_to=in_reply_to, references=refs)
    _out(m.to_dict(), json_output)
    if not json_output:
        console.print(f"[bold green]Replied![/] to {dest} (id: {m.id})")


@app.command()
def forward(
    ctx: typer.Context,
    msg_id: str = typer.Argument(...),
    to: str = typer.Option(..., "--to"),
    body: str = typer.Option("", "--body", "-b", help="Intro text above forwarded mail"),
    attach: Optional[List[str]] = typer.Option(None, "--attach", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    sign: bool = typer.Option(False, "--sign", help="PGP clearsign body"),
    gpg_key: Optional[str] = typer.Option(None, "--gpg-key"),
    encrypt_to: Optional[List[str]] = typer.Option(None, "--encrypt-to"),
    trust: bool = typer.Option(False, "--trust"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Forward a message."""
    from pathlib import Path as _P

    from . import compose as comp

    be = _be(ctx)
    orig = be.get_message(msg_id)
    fwd = (
        f"{body}\n\n---------- Forwarded message ----------\n"
        f"From: {orig.from_}\nDate: {orig.date}\nSubject: {orig.subject}\n\n{orig.body}"
    )
    if orig.attachments:
        fwd += f"\n\n[Original had attachments: {', '.join(orig.attachments)} — re-attach manually]"
    fwd = comp.apply_signature(fwd)
    fwd = _maybe_pgp(fwd, sign, gpg_key, encrypt_to, trust)
    subject = comp.forward_subject(orig.subject)
    if dry_run:
        _out({"to": to, "subject": subject, "body": fwd,
              "attachments": [_P(a).name for a in (attach or [])],
              "dry_run": True}, json_output)
        if not json_output:
            _preview(to, subject, fwd, attach or [])
        return
    m = be.send(to, subject, fwd, attachments=attach)
    _out(m.to_dict(), json_output)
    if not json_output:
        console.print(f"[bold green]Forwarded![/] to {to} (id: {m.id})")


@app.command("cache-clear")
def cache_clear():
    """Drop the local IMAP cache (~/.cache/wipplank/)."""
    from . import imap_cache

    imap_cache.clear()
    console.print("Cache cleared.")


@app.command()
def party():
    """Maximum fun demo."""
    fun.banner()
    fun.celebrate()


@auth_app.command("status")
def auth_status(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json"),
):
    """Show auth status."""
    from . import config as cfgmod

    cfg = cfgmod.load_config()
    accounts = cfgmod.list_accounts()
    summary = {}
    for name, a in accounts.items():
        atype = a.get("type", "imap")
        if atype == "gmail":
            has_secret = bool(cfgmod.get_account_password(name))
            ident = a.get("email") or "(oauth pending)"
        else:
            user = a.get("username", "")
            has_secret = bool(cfgmod.get_account_password(name)) or bool(
                user and cfgmod.get_password(user)
            )
            ident = f"{user} @ {a.get('host')}:{a.get('port')}" if user else "(incomplete)"
        summary[name] = {"type": atype, "identity": ident, "secret_in_keyring": has_secret}
    data = {
        "active_account": ctx.obj.get("account"),
        "active_backend": ctx.obj["backend"],
        "default_account": cfg.get("default_account"),
        "accounts": summary,
    }
    _out(data, json_output)
    if json_output:
        return
    if not summary:
        console.print("No accounts. Demo mode. Run `wipplank auth login --help`")
        return
    for name, s in summary.items():
        star = "*" if name == cfg.get("default_account") else " "
        console.print(f"{star} {name} [{s['type']}] {s['identity']} "
                      f"{'secret: yes' if s['secret_in_keyring'] else 'secret: MISSING'}")


account_app = typer.Typer(help="Manage named accounts")
app.add_typer(account_app, name="account")


@account_app.command("list")
def account_list(json_output: bool = typer.Option(False, "--json")):
    from . import config as cfgmod

    cfg = cfgmod.load_config()
    out = {"default": cfg.get("default_account"),
           "accounts": {n: {k: v for k, v in a.items() if k not in ("client_secret",)}
                        for n, a in cfgmod.list_accounts().items()}}
    _out(out, json_output)
    if not json_output:
        for n in out["accounts"]:
            star = "*" if n == out["default"] else " "
            console.print(f"{star} {n} [{out['accounts'][n].get('type')}]")


@account_app.command("show")
def account_show(name: str = typer.Argument(...)):
    from . import config as cfgmod

    a = cfgmod.get_account(name)
    if not a:
        raise typer.BadParameter(f"unknown account '{name}'")
    safe = {k: v for k, v in a.items() if k != "client_secret"}
    safe["secret_in_keyring"] = bool(cfgmod.get_account_password(name))
    _out(safe, True)


@account_app.command("rm")
def account_rm(name: str = typer.Argument(...)):
    from . import config as cfgmod

    if not cfgmod.delete_account(name):
        raise typer.BadParameter(f"unknown account '{name}'")
    console.print(f"Deleted account: {name}")


@account_app.command("default")
def account_default(name: str = typer.Argument(...)):
    from . import config as cfgmod

    if name != "demo" and not cfgmod.get_account(name):
        raise typer.BadParameter(f"unknown account '{name}'")
    cfg = cfgmod.load_config()
    cfg["default_account"] = name
    cfgmod.save_config(cfg)
    console.print(f"Default account: {name}")


@auth_app.command("login")
def auth_login(
    backend: str = typer.Option("imap", "--backend", help="imap or gmail"),
    account: str = typer.Option("default", "--account", help="Account name"),
    preset: Optional[str] = typer.Option(None, "--preset", help="fastmail, icloud, gmail, outlook"),
    host: Optional[str] = typer.Option(None, "--host"),
    imap_port: int = typer.Option(993, "--imap-port"),
    username: Optional[str] = typer.Option(None, "--username", "-u"),
    smtp_host: Optional[str] = typer.Option(None, "--smtp-host"),
    smtp_port: int = typer.Option(587, "--smtp-port"),
    password: Optional[str] = typer.Option(
        None, "--password", help="If omitted, you will be prompted securely"
    ),
    client_id: Optional[str] = typer.Option(None, "--client-id", help="Google OAuth client ID (gmail)"),
    client_secret: Optional[str] = typer.Option(None, "--client-secret", help="Google OAuth secret (gmail)"),
    set_default: bool = typer.Option(True, "--set-default/--no-set-default"),
):
    """Configure an account. Secrets go to OS keyring, never to disk."""
    from . import config as cfgmod

    if backend.lower() == "gmail":
        from .backends_gmail import oauth_login

        if not client_id:
            client_id = typer.prompt("Google OAuth client ID")
        if not client_secret:
            client_secret = typer.prompt("Google OAuth client secret", hide_input=True)
        email = oauth_login(account, client_id, client_secret)
        if set_default:
            cfg = cfgmod.load_config()
            cfg["default_account"] = account
            cfgmod.save_config(cfg)
        console.print(f"[bold green]Gmail connected![/] {email} (account: {account})")
        return
    if backend.lower() != "imap":
        raise typer.BadParameter("Backend must be imap or gmail")
    if preset:
        p = PRESETS.get(preset.lower())
        if not p:
            raise typer.BadParameter(f"unknown preset '{preset}'. Choose {list(PRESETS)}")
        host = host or p["host"]
        smtp_host = smtp_host or p["smtp_host"]
        imap_port = imap_port or p["port"]
        smtp_port = smtp_port or p["smtp_port"]
    if not username:
        username = typer.prompt("Email / username")
    if not host:
        host = typer.prompt("IMAP host", default="imap.fastmail.com")
    if not smtp_host:
        smtp_host = typer.prompt("SMTP host", default=host.replace("imap.", "smtp."))
    if not password:
        password = typer.prompt("Password (app-password)", hide_input=True)

    cfgmod.save_account(
        account,
        {
            "type": "imap",
            "host": host,
            "port": imap_port,
            "username": username,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "from_addr": username,
        },
    )
    cfgmod.save_account_password(account, password)
    if set_default:
        cfg = cfgmod.load_config()
        cfg["default_account"] = account
        cfgmod.save_config(cfg)
    console.print(f"[bold green]Saved![/] account '{account}': {username} @ {host} (secret in keyring)")


@auth_app.command("logout")
def auth_logout():
    """Remove IMAP config + keyring password."""
    from . import config as cfgmod

    imap_cfg = cfgmod.get_imap_config()
    if imap_cfg.get("username"):
        cfgmod.delete_password(imap_cfg["username"])
    cfgmod.clear_imap_config()
    console.print("Logged out 👋 IMAP config + keyring entry cleared.")


@app.command()
def mark(
    ctx: typer.Context,
    ids: List[str] = typer.Argument(..., help="Message IDs"),
    read: bool = typer.Option(False, "--read", help="Mark read"),
    unread: bool = typer.Option(False, "--unread", help="Mark unread"),
    flag: bool = typer.Option(False, "--flag", help="Star"),
    unflag: bool = typer.Option(False, "--unflag", help="Unstar"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Mark read-state / stars. Combine: mark ID1 ID2 --read --flag."""
    if read and unread:
        raise typer.BadParameter("Pick --read or --unread, not both")
    if flag and unflag:
        raise typer.BadParameter("Pick --flag or --unflag, not both")
    if not (read or unread or flag or unflag):
        raise typer.BadParameter("Nothing to do. Pass --read/--unread/--flag/--unflag")
    be = _be(ctx)
    out: dict = {}
    if read:
        out["read"] = be.mark_seen(ids, True)
    if unread:
        out["unread"] = be.mark_seen(ids, False)
    if flag:
        out["flagged"] = be.mark_flagged(ids, True)
    if unflag:
        out["unflagged"] = be.mark_flagged(ids, False)
    _out(out, json_output)
    if not json_output:
        console.print(f"Updated: {out}")


saved_app = typer.Typer(help="Named server-side searches")
app.add_typer(saved_app, name="saved")

attach_app = typer.Typer(help="Download/open attachments")
app.add_typer(attach_app, name="attach")


@saved_app.command("save")
def saved_save(name: str = typer.Argument(...), query: str = typer.Argument(...)):
    from . import compose as comp

    comp.save_search(name, query)
    console.print(f"Saved search: {name} -> {query}")


@saved_app.command("list")
def saved_list(json_output: bool = typer.Option(False, "--json")):
    from . import compose as comp

    _out(comp.list_searches(), json_output)
    if not json_output:
        for n, q in comp.list_searches().items():
            console.print(f"- {n}: {q}")


@saved_app.command("show")
def saved_show(name: str = typer.Argument(...)):
    from . import compose as comp

    console.print(comp.get_search(name))


@saved_app.command("rm")
def saved_rm(name: str = typer.Argument(...)):
    from . import compose as comp

    comp.delete_search(name)
    console.print(f"Deleted saved search: {name}")


@saved_app.command("run")
def saved_run(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", "-n"),
    json_output: bool = typer.Option(False, "--json"),
):
    from . import compose as comp

    msgs = _be(ctx).search(comp.get_search(name), limit)
    _out([m.to_dict() for m in msgs], json_output)
    if not json_output:
        console.print(_table(msgs))


@attach_app.command("list")
def attach_list(
    ctx: typer.Context,
    msg_id: str = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
):
    """List attachment names + sizes without downloading."""
    info = [
        {"name": n, "size": len(b)}
        for n, b in _be(ctx).get_attachments(msg_id)
    ]
    _out(info, json_output)
    if not json_output:
        if not info:
            console.print("(no attachments)")
        for i in info:
            console.print(f"- {i['name']} ({i['size']} bytes)")


@attach_app.command("save")
def attach_save(
    ctx: typer.Context,
    msg_id: str = typer.Argument(...),
    out_dir: str = typer.Option(".", "--dir", help="Destination folder"),
    name: Optional[str] = typer.Option(None, "--name", help="Save single file matching name"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Download attachments to a folder."""
    dest = Path(out_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    taken: set[str] = set()
    for fname, payload in _be(ctx).get_attachments(msg_id):
        if name and fname != name:
            continue
        target = dest / fname
        i = 1
        while target.name in taken or target.exists():
            target = dest / f"{target.stem}-{i}{target.suffix}"
            i += 1
        taken.add(target.name)
        target.write_bytes(payload)
        saved.append(str(target))
    if name and not saved:
        raise typer.BadParameter(f"no attachment named '{name}'")
    _out(saved, json_output)
    if not json_output:
        for p in saved:
            console.print(f"Saved: {p}")


@attach_app.command("open")
def attach_open(
    ctx: typer.Context,
    msg_id: str = typer.Argument(...),
    name: Optional[str] = typer.Option(None, "--name"),
    index: int = typer.Option(0, "--index", help="Which attachment if several"),
):
    """Download to temp and open with the OS default app."""
    import subprocess
    import sys
    import tempfile

    parts = _be(ctx).get_attachments(msg_id)
    if name:
        parts = [(n, b) for n, b in parts if n == name]
    if not parts:
        raise typer.BadParameter("no matching attachment")
    fname, payload = parts[min(index, len(parts) - 1)]
    tmp = Path(tempfile.mkdtemp(prefix="wipplank-")) / fname
    tmp.write_bytes(payload)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(tmp)])
    console.print(f"Opened: {fname}")


template_app = typer.Typer(help="Save/list/render message templates")
app.add_typer(template_app, name="template")

signature_app = typer.Typer(help="Manage sender signature")
app.add_typer(signature_app, name="signature")

draft_app = typer.Typer(help="Save/list/send/delete drafts")
app.add_typer(draft_app, name="draft")


@template_app.command("save")
def template_save(
    name: str = typer.Argument(...),
    subject: str = typer.Option(..., "--subject", "-s"),
    body: str = typer.Option("", "--body", "-b"),
    body_file: Optional[str] = typer.Option(None, "--body-file"),
):
    """Save a template. Use {to} {subject} placeholders."""
    from . import compose as comp

    if body_file:
        with open(body_file) as f:
            body = f.read()
    comp.save_template(name, subject, body)
    console.print(f"Template saved: {name}")


@template_app.command("list")
def template_list(json_output: bool = typer.Option(False, "--json")):
    from . import compose as comp

    _out(comp.list_templates(), json_output)
    if not json_output:
        for n in comp.list_templates():
            console.print(f"- {n}")


@template_app.command("show")
def template_show(name: str = typer.Argument(...)):
    from . import compose as comp

    t = comp.get_template(name)
    console.print(f"[bold]{t['subject']}[/]\n{t['body']}")


@template_app.command("rm")
def template_rm(name: str = typer.Argument(...)):
    from . import compose as comp

    comp.delete_template(name)
    console.print(f"Deleted template: {name}")


@signature_app.command("set")
def signature_set(text: str = typer.Argument(...)):
    from . import compose as comp

    comp.set_signature(text)
    console.print("Signature saved.")


@signature_app.command("show")
def signature_show():
    from . import compose as comp

    console.print(comp.get_signature() or "(none)")


@signature_app.command("clear")
def signature_clear():
    from . import compose as comp

    comp.clear_signature()
    console.print("Signature cleared.")


@draft_app.command("list")
def draft_list(json_output: bool = typer.Option(False, "--json")):
    from . import compose as comp

    _out(comp.list_drafts(), json_output)
    if not json_output:
        for n in comp.list_drafts():
            console.print(f"- {n}")


@draft_app.command("show")
def draft_show(name: str = typer.Argument(...)):
    from . import compose as comp

    _out(comp.load_draft(name), True)


@draft_app.command("rm")
def draft_rm(name: str = typer.Argument(...)):
    from . import compose as comp

    comp.delete_draft(name)
    console.print(f"Deleted draft: {name}")


@draft_app.command("send")
def draft_send(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Send a saved draft."""
    from . import compose as comp

    d = comp.load_draft(name)
    if dry_run:
        _out({**d, "dry_run": True}, json_output)
        if not json_output:
            _preview(d["to"], d["subject"], d["body"], d.get("attachments", []))
        return
    m = _be(ctx).send(d["to"], d["subject"], d["body"],
                      attachments=d.get("attachments"))
    comp.delete_draft(name)
    _out(m.to_dict(), json_output)
    if not json_output:
        console.print(f"[bold green]Sent draft![/] to {d['to']} (id: {m.id})")


@app.command()
def tui(ctx: typer.Context):
    """Full-screen inbox: browse, read, search, flag, compose."""
    from . import tui as _tui

    acct = ctx.obj.get("account")
    if acct:
        _tui.run("demo", account=acct)
    else:
        _tui.run(ctx.obj["backend"])


@app.command()
def mcp(ctx: typer.Context):
    """Start MCP server so your IA can read/send on your behalf."""
    from . import mcp_server

    mcp_server.run(backend_kind=ctx.obj["backend"], account=ctx.obj.get("account"))


if __name__ == "__main__":
    app()
