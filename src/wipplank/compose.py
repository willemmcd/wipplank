"""Compose helpers: quoting, noattach guard, templates, signature, drafts."""
import json
import re
import time
from pathlib import Path

from . import config as cfgmod
from .models import Message

ATTACH_HINT = re.compile(
    r"\b(attach(?:ed|ment|ing)?|enclosed|see (the )?file|find attached)\b"
    r"|\.(pdf|docx?|xlsx?|png|jpe?g|zip|csv)\b",
    re.IGNORECASE,
)


def needs_attachment_warning(body: str, attachments: list[str] | None) -> str | None:
    if attachments:
        return None
    if ATTACH_HINT.search(body or ""):
        return (
            "You mention an attachment but gave no -a/--attach. "
            "Add files or re-run with --force to send anyway."
        )
    return None


def reply_subject(subject: str) -> str:
    s = (subject or "").strip()
    return s if s.lower().startswith("re:") else f"Re: {s}"


def forward_subject(subject: str) -> str:
    s = (subject or "").strip()
    return s if s.lower().startswith(("fwd:", "fw:")) else f"Fwd: {s}"


def quote_body(orig: Message) -> str:
    lines = (orig.body or "").splitlines() or ["(no content)"]
    quoted = "\n".join(f"> {ln}" for ln in lines)
    return f"\n\nOn {orig.date}, {orig.from_} wrote:\n{quoted}"


def thread_headers(orig: Message) -> tuple[str | None, list[str]]:
    in_reply_to = orig.message_id or None
    refs = list(orig.references or [])
    if orig.message_id and orig.message_id not in refs:
        refs.append(orig.message_id)
    return in_reply_to, refs


def reply_address(orig: Message, fallback: str) -> str:
    # orig.from_ may be 'Name <addr>'; prefer the addr in <>
    m = re.search(r"<([^<>@\s]+@[^<>\s]+)>", orig.from_ or "")
    if m:
        return m.group(1)
    if "@" in (orig.from_ or ""):
        return orig.from_.strip()
    return fallback


# --- signature / templates (stored in config.json, no secrets) ---

def get_signature() -> str:
    return cfgmod.load_config().get("signature", "")


def set_signature(text: str) -> None:
    cfg = cfgmod.load_config()
    cfg["signature"] = text
    cfgmod.save_config(cfg)


def clear_signature() -> None:
    cfg = cfgmod.load_config()
    cfg.pop("signature", None)
    cfgmod.save_config(cfg)


def apply_signature(body: str) -> str:
    sig = get_signature()
    if not sig:
        return body
    return f"{body.rstrip()}\n\n-- \n{sig}"


def list_templates() -> dict:
    return cfgmod.load_config().get("templates", {})


def save_template(name: str, subject: str, body: str) -> None:
    cfg = cfgmod.load_config()
    t = cfg.get("templates", {})
    t[name] = {"subject": subject, "body": body}
    cfg["templates"] = t
    cfgmod.save_config(cfg)


def get_template(name: str) -> dict:
    t = list_templates().get(name)
    if not t:
        raise ValueError(f"template '{name}' not found. Run: wipplank template list")
    return t


def delete_template(name: str) -> None:
    cfg = cfgmod.load_config()
    t = cfg.get("templates", {})
    if name not in t:
        raise ValueError(f"template '{name}' not found")
    del t[name]
    cfg["templates"] = t
    cfgmod.save_config(cfg)


def render(text: str, ctx: dict) -> str:
    # safe {var} substitution; unknown vars left as-is
    def repl(m):
        return str(ctx.get(m.group(1), m.group(0)))

    return re.sub(r"\{(\w+)\}", repl, text or "")


# --- saved searches (query-map style, stored in config.json) ---

def list_searches() -> dict:
    return cfgmod.load_config().get("searches", {})


def save_search(name: str, query: str) -> None:
    cfg = cfgmod.load_config()
    s = cfg.get("searches", {})
    s[name] = query
    cfg["searches"] = s
    cfgmod.save_config(cfg)


def get_search(name: str) -> str:
    q = list_searches().get(name)
    if q is None:
        raise ValueError(f"saved search '{name}' not found. Run: wipplank saved list")
    return q


def delete_search(name: str) -> None:
    cfg = cfgmod.load_config()
    s = cfg.get("searches", {})
    if name not in s:
        raise ValueError(f"saved search '{name}' not found")
    del s[name]
    cfg["searches"] = s
    cfgmod.save_config(cfg)


# --- drafts (local JSON, ~/.config/wipplank/drafts/) ---

def _draft_dir() -> Path:
    d = cfgmod.CONFIG_DIR / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_draft(name: str, payload: dict) -> Path:
    payload = {**payload, "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p = _draft_dir() / f"{name}.json"
    p.write_text(json.dumps(payload, indent=2))
    return p


def list_drafts() -> list[str]:
    d = cfgmod.CONFIG_DIR / "drafts"
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def load_draft(name: str) -> dict:
    p = _draft_dir() / f"{name}.json"
    if not p.exists():
        raise ValueError(f"draft '{name}' not found")
    return json.loads(p.read_text())


def delete_draft(name: str) -> None:
    p = _draft_dir() / f"{name}.json"
    if p.exists():
        p.unlink()
