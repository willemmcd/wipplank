"""Live mailbox tests. Read-mostly; flag changes are restored.

Run: WIPPLANK_LIVE=1 uv run pytest -m live
Skipped in normal runs (no network, no secrets).
"""
import os

import pytest

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("WIPPLANK_LIVE") != "1",
                                 reason="set WIPPLANK_LIVE=1 to run against real mailbox")]


@pytest.fixture()
def live_backend():
    from wipplank.backends import get_backend

    be = get_backend("imap")
    be.use_cache = False
    return be


def test_live_check_stable_ids(live_backend):
    msgs = live_backend.list_messages(5)
    assert msgs, "expected at least one message"
    assert all(":" in m.id for m in msgs)


def test_live_read_round_trip(live_backend):
    first = live_backend.list_messages(1)[0]
    again = live_backend.get_message(first.id)
    assert again.subject == first.subject


def test_live_mark_restores_flags(live_backend):
    first = live_backend.list_messages(1)[0]
    was_unread, was_flagged = first.unread, first.flagged
    try:
        # seen=True means "mark as seen (read)": pass was_unread to flip state
        live_backend.mark_seen([first.id], was_unread)
        assert live_backend.get_message(first.id).unread == (not was_unread)
    finally:
        live_backend.mark_seen([first.id], not was_unread)
        live_backend.mark_flagged([first.id], was_flagged)
    assert live_backend.get_message(first.id).unread == was_unread
