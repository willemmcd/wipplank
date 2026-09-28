"""Local config + keyring helpers. No plaintext passwords."""
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "wipplank"
CONFIG_FILE = CONFIG_DIR / "config.json"

PRESETS = {
    "fastmail": {
        "host": "imap.fastmail.com",
        "port": 993,
        "smtp_host": "smtp.fastmail.com",
        "smtp_port": 587,
    },
    "icloud": {
        "host": "imap.mail.me.com",
        "port": 993,
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
    },
    "gmail": {
        "host": "imap.gmail.com",
        "port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
    },
    "outlook": {
        "host": "outlook.office365.com",
        "port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
    },
}

SERVICE = "wipplank"

# past brands, newest first: read old locations so existing logins survive
LEGACY_CONFIG_FILES = [
    Path.home() / ".config" / "postbag" / "config.json",
    Path.home() / ".config" / "agentmail" / "config.json",
]
LEGACY_SERVICES = ["postbag", "agentmail"]


def _migrate_brand() -> None:
    """One-time copy of a pre-rename config file. Idempotent."""
    try:
        if CONFIG_FILE.exists():
            return
        for legacy in LEGACY_CONFIG_FILES:
            if legacy.exists():
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                CONFIG_FILE.write_text(legacy.read_text())
                return
    except Exception:
        pass


def _read_secret(key: str) -> str | None:
    import keyring

    try:
        hit = keyring.get_password(SERVICE, key)
        if hit:
            return hit
        for legacy_service in LEGACY_SERVICES:  # pre-rename fallbacks
            hit = keyring.get_password(legacy_service, key)
            if hit:
                return hit
        return None
    except Exception:
        return None


def load_config() -> dict:
    _migrate_brand()
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get_imap_config() -> dict:
    cfg = load_config()
    if cfg.get("imap"):
        return cfg["imap"]
    # post-migration: legacy callers read through the default account
    migrate_legacy()
    cfg = load_config()
    default = cfg.get("default_account")
    acct = cfg.get("accounts", {}).get(default or "", {}) if default else {}
    if acct.get("type", "imap") == "imap":
        return acct
    return {}


def set_imap_config(data: dict) -> None:
    cfg = load_config()
    cfg["imap"] = data
    # remember default so plain `check` can use imap once configured
    cfg["default_backend"] = "imap"
    save_config(cfg)


def clear_imap_config() -> None:
    cfg = load_config()
    cfg.pop("imap", None)
    if cfg.get("default_backend") == "imap":
        cfg["default_backend"] = "demo"
    save_config(cfg)


def keyring_key(username: str) -> str:
    return f"imap:{username}"


def save_password(username: str, password: str) -> None:
    import keyring

    keyring.set_password(SERVICE, keyring_key(username), password)


def get_password(username: str) -> str | None:
    return _read_secret(keyring_key(username))


def delete_password(username: str) -> None:
    import keyring

    try:
        keyring.delete_password(SERVICE, keyring_key(username))
    except Exception:
        pass


# --- multi-account (new home) + legacy single-imap import ---

def account_key(name: str) -> str:
    return f"account:{name}"


def save_account_password(name: str, password: str) -> None:
    import keyring

    keyring.set_password(SERVICE, account_key(name), password)


def get_account_password(name: str) -> str | None:
    return _read_secret(account_key(name))


def delete_account_password(name: str) -> None:
    import keyring

    try:
        keyring.delete_password(SERVICE, account_key(name))
    except Exception:
        pass


def migrate_legacy() -> bool:
    """Fold pre-accounts single `imap` section into accounts.default. Idempotent."""
    cfg = load_config()
    if "accounts" in cfg or "imap" not in cfg:
        return False
    section = cfg.pop("imap", {}) or {}
    accounts = cfg.get("accounts", {})
    if "default" not in accounts:
        accounts["default"] = {"type": "imap", **section}
        user = section.get("username")
        if user:
            try:
                pw = get_password(user)
                if pw:
                    save_account_password("default", pw)
            except Exception:
                pass
    cfg["accounts"] = accounts
    if cfg.get("default_backend") == "imap" and not cfg.get("default_account"):
        cfg["default_account"] = "default"
    save_config(cfg)
    return True


def list_accounts() -> dict:
    migrate_legacy()
    return load_config().get("accounts", {})


def get_account(name: str) -> dict | None:
    return list_accounts().get(name)


def save_account(name: str, data: dict) -> None:
    migrate_legacy()
    cfg = load_config()
    accounts = cfg.get("accounts", {})
    accounts[name] = data
    cfg["accounts"] = accounts
    if not cfg.get("default_account"):
        cfg["default_account"] = name
    save_config(cfg)


def delete_account(name: str) -> bool:
    cfg = load_config()
    accounts = cfg.get("accounts", {})
    if name not in accounts:
        return False
    del accounts[name]
    cfg["accounts"] = accounts
    if cfg.get("default_account") == name:
        cfg["default_account"] = next(iter(accounts), None) or "demo"
    save_config(cfg)
    delete_account_password(name)
    return True


def get_default_account() -> str | None:
    migrate_legacy()
    return load_config().get("default_account")
