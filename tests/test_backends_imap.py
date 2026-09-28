"""IMAP backend against FakeIMAPConn — no network."""
from wipplank.models import Message


def test_list_parses_and_flags(imap_backend):
    msgs = imap_backend.list_messages(10)
    assert [m.subject for m in msgs] == ["Report final", "Party", "Report"]  # newest first
    by_id = {m.id: m for m in msgs}
    assert by_id["4242:1"].unread is False  # \Seen in fake
    assert by_id["4242:2"].unread is True
    assert all(m.id.startswith("4242:") for m in msgs)
    assert by_id["4242:1"].message_id == "<r1@x>"


def test_fetch_uses_peek_not_rfc822(imap_backend):
    imap_backend.list_messages(1)
    fetches = [a for c, a in imap_backend._fake.uid_calls if c == "FETCH"]
    assert fetches, "expected FETCH calls"
    for args in fetches:
        spec = args[1]
        # FLAGS-only refresh and PEEK body fetch are both read-only
        assert spec == "(FLAGS)" or "BODY.PEEK" in spec
        assert "RFC822" not in spec


def test_get_legacy_and_stable_ids(imap_backend):
    assert imap_backend.get_message("2").id == "4242:2"
    assert imap_backend.get_message("4242:2").id == "4242:2"


def test_stale_validity_rejected(imap_backend):
    import pytest

    with pytest.raises(ValueError, match="stale"):
        imap_backend.get_message("999:2")


def test_search(imap_backend):
    assert len(imap_backend.search("anything")) == 3  # fake returns all


def test_mark_store_verbs(imap_backend):
    assert imap_backend.mark_seen(["4242:1"], True) == {"4242:1": True}
    op, flags = imap_backend._fake.stored[-1][1], imap_backend._fake.stored[-1][2]
    assert op == "+FLAGS" and flags == "(\\Seen)"
    imap_backend.mark_flagged(["2"], False)
    assert imap_backend._fake.stored[-1][1:] == ("-FLAGS", "(\\Flagged)")


def test_cache_serves_second_list(imap_backend):
    from wipplank import imap_cache

    imap_backend.list_messages(10)
    n_before = len(imap_cache.get_many("h", "u", "INBOX", "4242", ["1", "2", "3"]))
    assert n_before == 3
    # second list reuses cache (same output, still correct flags)
    again = imap_backend.list_messages(10)
    assert [m.id for m in again] == ["4242:3", "4242:2", "4242:1"]


def test_to_message_attachment_names():
    from email.message import EmailMessage

    from wipplank.backends_imap import _to_message

    m = EmailMessage()
    m["Subject"] = "f"
    m.set_content("hi")
    m.add_attachment(b"data", maintype="text", subtype="plain", filename="n.txt")
    parsed = _to_message("4242:9", m.as_bytes(), b"")
    assert parsed.attachments == ["n.txt"]
    assert parsed.body == "hi"


def test_html_fallback():
    from email.message import EmailMessage

    from wipplank.backends_imap import _body_text

    m = EmailMessage()
    m["Subject"] = "h"
    m.set_content("<p>Hello <b>W</b></p>", subtype="html")
    assert "Hello W" in _body_text(m)
