import pytest


def test_list_get_search(demo_backend):
    assert [m.id for m in demo_backend.list_messages(2)] == ["demo-1", "demo-2"]
    assert demo_backend.get_message("demo-1").subject.startswith("Welcome")
    with pytest.raises(ValueError):
        demo_backend.get_message("nope")
    assert [m.id for m in demo_backend.search("rocket")] == ["demo-3"]


def test_send_and_mark(demo_backend):
    m = demo_backend.send("t@x", "s", "b", attachments=["/tmp/a.txt"])
    assert m.attachments == ["a.txt"] and m.in_reply_to == ""
    m2 = demo_backend.send("t@x", "Re: s", "b2", in_reply_to="<m>", references=["<m>"])
    assert m2.in_reply_to == "<m>" and m2.references == ["<m>"]
    assert demo_backend.mark_seen([m.id], True) == {m.id: True}
    assert demo_backend.get_message(m.id).unread is False
    assert demo_backend.mark_flagged([m.id], True) == {m.id: True}
    assert demo_backend.get_message(m.id).flagged is True
    assert demo_backend.mark_seen(["ghost"], True) == {"ghost": False}


def test_get_attachments_names_only(demo_backend):
    assert demo_backend.get_attachments("demo-1") == []
