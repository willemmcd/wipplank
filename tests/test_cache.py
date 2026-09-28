from wipplank import imap_cache
from wipplank.models import Message

KEY = dict(host="h", username="u", mailbox="INBOX", uidvalidity="4242")


def _d(uid="1"):
    return Message(id=f"4242:{uid}", from_="a@x", subject="s").to_dict()


def test_put_get_round_trip():
    imap_cache.put_many(**KEY, items={"1": _d("1")})
    got = imap_cache.get_many(**KEY, uids=["1", "9"])
    assert list(got) == ["1"]
    assert Message.from_dict(got["1"]).subject == "s"


def test_validity_change_prunes_old_generation():
    imap_cache.put_many(**KEY, items={"1": _d("1")})
    imap_cache.put_many(**{**KEY, "uidvalidity": "9999"}, items={"1": _d("1")})
    assert imap_cache.get_many(**KEY, uids=["1"]) == {}
    assert list(imap_cache.get_many(**{**KEY, "uidvalidity": "9999"}, uids=["1"])) == ["1"]


def test_clear():
    imap_cache.put_many(**KEY, items={"1": _d("1")})
    imap_cache.clear()
    assert imap_cache.get_many(**KEY, uids=["1"]) == {}
