"""Demo backend - fun fake emails, zero setup. Great for IA dev."""
import uuid
from datetime import datetime

from .backends import EmailBackend
from .models import Message

_DEMO = [
    Message(
        id="demo-1",
        from_="party@wipplank.dev",
        to="you@example.com",
        subject="Welcome to Wipplank 🎉",
        snippet="No boring email allowed...",
        body="Welcome! This is a demo inbox.\n\nRun `wipplank send --to friend@example.com --subject hi --body yo` to feel the magic.",
        date="2026-09-11",
        unread=True,
        labels=["welcome"],
    ),
    Message(
        id="demo-2",
        from_="boss@boring.inc",
        to="you@example.com",
        subject="Per my last email: synergy circling back",
        snippet="Boredom Patrol flagged this...",
        body="This email is intentionally boring so you can see Boredom Patrol in action.",
        date="2026-09-10",
        unread=True,
        labels=["work"],
    ),
    Message(
        id="demo-3",
        from_="nasa@mars.dev",
        to="you@example.com",
        subject="Your rocket is ready 🚀",
        snippet="Launch window opens Friday...",
        body="Just kidding. But wouldn't that be a fun email?",
        date="2026-09-09",
        unread=False,
        labels=["fun"],
    ),
]


class DemoBackend(EmailBackend):
    name = "demo"

    def __init__(self):
        self._store = list(_DEMO)

    def list_messages(self, limit: int = 20) -> list[Message]:
        return self._store[:limit]

    def get_message(self, msg_id: str) -> Message:
        for m in self._store:
            if m.id == msg_id:
                return m
        raise ValueError(f"message '{msg_id}' not found in demo backend")

    def search(self, query: str, limit: int = 20) -> list[Message]:
        q = query.lower()
        return [
            m
            for m in self._store
            if q in m.subject.lower() or q in m.body.lower() or q in m.from_.lower()
        ][:limit]

    def mark_seen(self, uids: list[str], seen: bool) -> dict[str, bool]:
        out = {}
        for m in self._store:
            if m.id in uids:
                m.unread = not seen
                out[m.id] = True
        for u in uids:
            out.setdefault(u, False)
        return out

    def mark_flagged(self, uids: list[str], flagged: bool) -> dict[str, bool]:
        out = {}
        for m in self._store:
            if m.id in uids:
                m.flagged = flagged
                out[m.id] = True
        for u in uids:
            out.setdefault(u, False)
        return out

    def get_attachments(self, msg_id: str) -> list[tuple[str, bytes]]:
        # demo messages carry names only, no payload bytes
        for m in self._store:
            if m.id == msg_id:
                return [(name, b"") for name in m.attachments]
        raise ValueError(f"message '{msg_id}' not found in demo backend")

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[str] | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> Message:
        from pathlib import Path

        names = [Path(p).name for p in (attachments or [])]
        msg = Message(
            id=f"demo-{uuid.uuid4().hex[:8]}",
            from_="you@wipplank.dev",
            to=to,
            subject=subject,
            snippet=body[:80],
            body=body,
            date=datetime.now().isoformat(timespec="seconds"),
            unread=False,
            labels=["sent"],
            attachments=names,
            in_reply_to=in_reply_to or "",
            references=list(references or []),
        )
        self._store.insert(0, msg)
        return msg
