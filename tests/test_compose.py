import pytest

from wipplank import compose as comp
from wipplank.models import Message


def _msg(**kw):
    base = dict(id="1", from_="Boss <boss@x>", to="me@x", subject="Report",
                body="line1\nline2", date="today", message_id="<m@x>")
    base.update(kw)
    return Message(**base)


def test_reply_subject_no_double_re():
    assert comp.reply_subject("Report") == "Re: Report"
    assert comp.reply_subject("Re: Report") == "Re: Report"
    assert comp.reply_subject("re: Report") == "re: Report"


def test_forward_subject():
    assert comp.forward_subject("Hi") == "Fwd: Hi"
    assert comp.forward_subject("Fwd: Hi") == "Fwd: Hi"


def test_quote_body():
    q = comp.quote_body(_msg())
    assert "On today, Boss <boss@x> wrote:" in q
    assert "> line1" in q and "> line2" in q


def test_thread_headers_chains_references():
    m = _msg(message_id="<m@x>", references=["<old@x>"])
    ir, refs = comp.thread_headers(m)
    assert ir == "<m@x>"
    assert refs == ["<old@x>", "<m@x>"]


def test_thread_headers_no_message_id():
    ir, refs = comp.thread_headers(_msg(message_id=""))
    assert ir is None and refs == []


@pytest.mark.parametrize("from_,want", [
    ("Boss <boss@x>", "boss@x"),
    ("boss@x", "boss@x"),
    ("", "fallback@x"),
])
def test_reply_address(from_, want):
    assert comp.reply_address(_msg(from_=from_), "fallback@x") == want


@pytest.mark.parametrize("body,att,warn", [
    ("see attached file", None, True),
    ("report.pdf is ready", None, True),
    ("see attached file", ["a.pdf"], False),
    ("hello world", None, False),
])
def test_noattach_guard(body, att, warn):
    assert (comp.needs_attachment_warning(body, att) is not None) == warn


def test_render_unknown_vars_left_alone():
    assert comp.render("Hi {to} {missing}", {"to": "x"}) == "Hi x {missing}"


def test_templates_crud():
    comp.save_template("t", "Sub {to}", "Body {to}")
    assert comp.get_template("t") == {"subject": "Sub {to}", "body": "Body {to}"}
    assert "t" in comp.list_templates()
    comp.delete_template("t")
    with pytest.raises(ValueError):
        comp.get_template("t")


def test_signature_apply_and_clear():
    assert comp.apply_signature("hi") == "hi"  # none set
    comp.set_signature("Sig")
    assert comp.apply_signature("hi") == "hi\n\n-- \nSig"
    comp.clear_signature()
    assert comp.apply_signature("hi") == "hi"


def test_drafts_crud():
    comp.save_draft("d", {"to": "a", "subject": "s", "body": "b"})
    assert "d" in comp.list_drafts()
    assert comp.load_draft("d")["to"] == "a"
    comp.delete_draft("d")
    assert "d" not in comp.list_drafts()
    with pytest.raises(ValueError):
        comp.load_draft("d")


def test_searches_crud():
    comp.save_search("n", "news")
    assert comp.get_search("n") == "news"
    comp.delete_search("n")
    with pytest.raises(ValueError):
        comp.get_search("n")
