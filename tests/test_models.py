from wipplank.models import Message


def test_to_dict_renames_from():
    m = Message(id="1", from_="a@x", subject="Hi")
    d = m.to_dict()
    assert d["from"] == "a@x"
    assert "from_" not in d


def test_from_dict_round_trip():
    m = Message(id="4242:7", from_="a@x", subject="S", body="b",
                attachments=["f.pdf"], message_id="<m@x>",
                references=["<r@x>"], flagged=True, unread=False)
    m2 = Message.from_dict(m.to_dict())
    assert m2 == m


def test_from_dict_ignores_unknown_keys():
    m = Message.from_dict({"id": "1", "from": "a@x", "bogus": 1})
    assert m.id == "1" and m.from_ == "a@x"
