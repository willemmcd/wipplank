"""Gmail mapping + service paths with a fake service (no network)."""
import base64

import pytest

from wipplank.backends_gmail import GmailBackend, _walk_parts


def _b(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def test_walk_parts_keeps_html():
    payload = {"parts": [
        {"mimeType": "text/plain", "filename": "", "body": {"data": _b("p")}},
        {"mimeType": "text/html", "filename": "", "body": {"data": _b("<p>h</p>")}},
        {"mimeType": "application/pdf", "filename": "a.pdf", "body": {"attachmentId": "A1"}},
    ]}
    kinds = [(att, mime) for att, _f, mime, _d, _a in _walk_parts(payload)]
    assert (False, "text/plain") in kinds
    assert (False, "text/html") in kinds
    assert (True, "application/pdf") in kinds


def test_to_message_prefers_plain_falls_back_to_html():
    html_only = {"id": "g1", "labelIds": ["INBOX", "UNREAD"], "payload": {
        "headers": [{"name": "Subject", "value": "H"}, {"name": "From", "value": "a@b"}],
        "parts": [{"mimeType": "text/html", "filename": "",
                   "body": {"data": _b("<p>Hello <b>World</b></p>")}}]}}
    m = GmailBackend._to_message({"id": "g1"}, html_only)
    assert "Hello World" in m.body and "[HTML mail" in m.body
    assert m.unread is True  # UNREAD label
    mixed = {"id": "g2", "labelIds": ["INBOX"], "payload": {
        "headers": [],
        "parts": [{"mimeType": "text/plain", "filename": "", "body": {"data": _b("plain")}},
                  {"mimeType": "text/html", "filename": "", "body": {"data": _b("<p>h</p>")}}]}}
    assert GmailBackend._to_message({"id": "g2"}, mixed).body == "plain"


def _gmail_backend(monkeypatch, service):
    from wipplank import config as cfgmod

    cfgmod.save_account("g", {"type": "gmail", "email": "g@y",
                              "client_id": "id", "client_secret": "s"})
    import json as _json
    cfgmod.save_account_password("g", _json.dumps({"refresh_token": "rt"}))
    be = GmailBackend.__new__(GmailBackend)
    be.account = "g"
    be._acct = cfgmod.get_account("g")
    monkeypatch.setattr(be, "_service", lambda: service)
    return be


def test_list_get_search_send_mark(monkeypatch):
    from conftest import FakeGmailService

    svc = FakeGmailService()
    be = _gmail_backend(monkeypatch, svc)
    msgs = be.list_messages(5)
    assert [m.id for m in msgs] == ["g1", "g2"]
    assert msgs[0].subject == "Hello" and msgs[0].unread is True
    assert be.get_message("g1").id == "g1"
    assert len(be.search("q")) == 2
    sent = be.send("t@x", "s", "b")
    assert sent.id == "sent1" and svc.sent
    assert be.mark_seen(["g1"], True) == {"g1": True}
    assert ("g1", {"addLabelIds": [], "removeLabelIds": ["UNREAD"]}) in [
        (i, b) for i, b in svc.modified]
    assert be.mark_flagged(["g1"], True)["g1"] is True


def test_gmail_needs_oauth_setup(monkeypatch):
    pytest.importorskip("google.auth", reason="needs pip install wipplank[gmail]")
    from wipplank import config as cfgmod

    cfgmod.save_account("g2", {"type": "gmail", "email": "", "client_id": "i", "client_secret": "s"})
    be = GmailBackend.__new__(GmailBackend)
    be.account = "g2"
    be._acct = cfgmod.get_account("g2")
    with pytest.raises(SystemExit, match="never completed OAuth"):
        be._creds()
