"""Shared fixtures: isolated config/cache/keyring, demo backend, fakes.

Every test runs against temp dirs + in-memory keyring — nothing touches
~/.config, ~/.cache, or the real OS keychain.
"""
import pytest

from wipplank import config as cfgmod
from wipplank import imap_cache


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch, request):
    """Redirect config + cache + keyring to temp fakes.

    Live-marked tests opt out: they need real credentials + keychain.
    """
    if request.node.get_closest_marker("live"):
        yield None
        return
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cfgmod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", cfg_file)
    # pin pre-rename fallbacks away from the real home so brand
    # migration never leaks real data into isolated tests
    monkeypatch.setattr(cfgmod, "LEGACY_CONFIG_FILES", [tmp_path / "old-config.json"])
    monkeypatch.setattr(imap_cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(imap_cache, "DB_FILE", tmp_path / "cache" / "cache.sqlite")
    monkeypatch.setattr(imap_cache, "OLD_DB_FILES", [tmp_path / "old-cache.sqlite"])

    secrets: dict[str, str] = {}

    def _set(service, key, value):
        secrets[f"{service}:{key}"] = value

    def _get(service, key):
        return secrets.get(f"{service}:{key}")

    def _del(service, key):
        secrets.pop(f"{service}:{key}", None)

    monkeypatch.setattr("keyring.set_password", _set)
    monkeypatch.setattr("keyring.get_password", _get)
    monkeypatch.setattr("keyring.delete_password", _del)
    yield tmp_path


@pytest.fixture()
def demo_backend():
    from wipplank.backends_demo import DemoBackend

    return DemoBackend()


@pytest.fixture()
def cli_runner():
    from typer.testing import CliRunner

    return CliRunner()


class FakeIMAPConn:
    """Minimal imaplib stand-in. UIDs 1..3 exist; UIDVALIDITY 4242."""

    def __init__(self, raws: dict[str, bytes], flags: dict[str, bytes] | None = None):
        self.raws = raws
        self.flags = flags or {}
        self.stored: list[tuple] = []
        self.uid_calls: list[tuple] = []
        self.selected = None

    # -- session --
    def login(self, *a):
        return ("OK", [b"ok"])

    def select(self, mailbox="INBOX"):
        self.selected = mailbox
        return ("OK", [b"3"])

    def close(self):
        return ("OK", [b""])

    def logout(self):
        return ("OK", [b""])

    def status(self, mailbox, query):
        return ("OK", [b"INBOX (UIDVALIDITY 4242)"])

    # -- commands --
    def uid(self, cmd, *args):
        self.uid_calls.append((cmd, args))
        if cmd == "SEARCH":
            return ("OK", [b"1 2 3"])
        if cmd == "FETCH":
            uids, spec = args[0], args[1]
            if "BODY.PEEK" in spec or "RFC822" in spec:
                first = uids.split(",")[0]
                if first not in self.raws:
                    return ("OK", [None])
                items = []
                for u in uids.split(","):
                    if u not in self.raws:
                        continue
                    fl = self.flags.get(u, b"")
                    items.append(
                        (f'{u} (UID {u} FLAGS ({fl.decode()}) BODY[] {{{len(self.raws[u])}}})'.encode(),
                         self.raws[u])
                    )
                return ("OK", items)
            if spec == "(FLAGS)":
                out = []
                for u in uids.split(","):
                    fl = self.flags.get(u, b"").decode()
                    out.append(f'{u} (UID {u} FLAGS ({fl}))'.encode())
                return ("OK", out)
            raise AssertionError(f"unexpected FETCH spec {spec}")
        if cmd == "STORE":
            self.stored.append(args)
            return ("OK", [b""])
        raise AssertionError(f"unexpected UID {cmd}")


def make_email_bytes(from_="a@x", subject="Hi", body="hello",
                     message_id="<m1@x>") -> bytes:
    from email.message import EmailMessage

    m = EmailMessage()
    m["From"] = from_
    m["To"] = "b@x"
    m["Subject"] = subject
    m["Date"] = "Wed, 16 Sep 2026 08:25:00 +0200"
    m["Message-ID"] = message_id
    m.set_content(body)
    return m.as_bytes()


@pytest.fixture()
def imap_backend(monkeypatch):
    """ImapBackend with explicit creds (no config/keyring) + FakeIMAPConn."""
    from wipplank.backends_imap import ImapBackend

    raws = {
        "1": make_email_bytes("boss@x", "Report", "numbers", "<r1@x>"),
        "2": make_email_bytes("pal@x", "Party", "come over", "<p2@x>"),
        "3": make_email_bytes("boss@x", "Report final", "final numbers", "<r3@x>"),
    }
    conn = FakeIMAPConn(raws, flags={"1": b"\\Seen"})
    be = ImapBackend(host="h", port=993, username="u", password="p",
                     smtp_host="s", smtp_port=587)
    monkeypatch.setattr(be, "_connect", lambda: conn)
    be._fake = conn  # type: ignore[attr-defined]
    return be


class FakeGmailService:
    """Chainable users().messages() fake for GmailBackend._service."""

    def __init__(self):
        self.sent: list[dict] = []
        self.modified: list[tuple] = []

    def users(self):
        return self._Users(self)

    class _Users:
        def __init__(self, root):
            self._root = root

        def messages(self):
            return self._root._Messages(self._root)

    class _Messages:
        def __init__(self, root):
            self._root = root

        def list(self, **kw):
            self._root._last_list = kw
            return self._root._Exec({"messages": [{"id": "g1"}, {"id": "g2"}]})

        def get(self, **kw):
            return self._root._Exec({
                "id": kw.get("id", "g1"),
                "threadId": "t1",
                "labelIds": ["INBOX", "UNREAD"],
                "snippet": "snip",
                "payload": {"headers": [
                    {"name": "From", "value": "a@b"},
                    {"name": "Subject", "value": "Hello"},
                    {"name": "Message-ID", "value": "<m@b>"},
                ]},
            })

        def send(self, **kw):
            self._root.sent.append(kw)
            return self._root._Exec({"id": "sent1"})

        def modify(self, **kw):
            self._root.modified.append((kw.get("id"), kw.get("body")))
            return self._root._Exec({})

    class _Exec:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload
