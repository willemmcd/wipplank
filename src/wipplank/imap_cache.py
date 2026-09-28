"""Tiny sqlite cache for IMAP envelopes/bodies. stdlib only.

Keyed by (host, username, mailbox, uidvalidity, uid). A UIDVALIDITY
change means the mailbox was regenerated, so rows from other
generations are pruned on write.
"""
import json
import sqlite3
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "wipplank"
DB_FILE = CACHE_DIR / "cache.sqlite"
OLD_DB_FILES = [
    Path.home() / ".cache" / "postbag" / "cache.sqlite",
    Path.home() / ".cache" / "agentmail" / "cache.sqlite",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  host TEXT NOT NULL,
  username TEXT NOT NULL,
  mailbox TEXT NOT NULL,
  uidvalidity TEXT NOT NULL,
  uid TEXT NOT NULL,
  msg_json TEXT NOT NULL,
  updated_at REAL NOT NULL,
  PRIMARY KEY (host, username, mailbox, uidvalidity, uid)
)
"""


def _db() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        for legacy in OLD_DB_FILES:
            if legacy.exists():
                try:
                    import shutil

                    shutil.copy2(legacy, DB_FILE)
                except Exception:
                    pass
                break
    conn = sqlite3.connect(DB_FILE)
    conn.execute(_SCHEMA)
    return conn


def get_many(host: str, username: str, mailbox: str, uidvalidity: str,
             uids: list[str]) -> dict[str, dict]:
    if not uids:
        return {}
    from .models import Message

    out: dict[str, dict] = {}
    with _db() as db:
        q = f"SELECT uid, msg_json FROM messages WHERE host=? AND username=? AND mailbox=? AND uidvalidity=? AND uid IN ({','.join('?' * len(uids))})"
        for uid, blob in db.execute(q, [host, username, mailbox, uidvalidity, *uids]):
            try:
                d = json.loads(blob)
                # validate round-trip
                Message.from_dict(d)
                out[uid] = d
            except Exception:
                continue
    return out


def put_many(host: str, username: str, mailbox: str, uidvalidity: str,
             items: dict[str, dict]) -> None:
    if not items:
        return
    now = time.time()
    with _db() as db:
        db.execute(
            "DELETE FROM messages WHERE host=? AND username=? AND mailbox=? AND uidvalidity!=?",
            [host, username, mailbox, uidvalidity],
        )
        db.executemany(
            "INSERT OR REPLACE INTO messages VALUES (?,?,?,?,?,?,?)",
            [(host, username, mailbox, uidvalidity, uid, json.dumps(d), now)
             for uid, d in items.items()],
        )


def clear() -> None:
    if DB_FILE.exists():
        DB_FILE.unlink()
