"""Backend interface + dispatcher."""
from abc import ABC, abstractmethod

from .models import Message


class EmailBackend(ABC):
    name = "base"

    @abstractmethod
    def list_messages(self, limit: int = 20) -> list[Message]:
        raise NotImplementedError

    @abstractmethod
    def get_message(self, msg_id: str) -> Message:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[Message]:
        raise NotImplementedError

    @abstractmethod
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[str] | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> Message:
        raise NotImplementedError

    def mark_seen(self, uids: list[str], seen: bool) -> dict[str, bool]:
        """Mark messages read (seen=True) or unread. Returns {uid: ok}."""
        raise NotImplementedError

    def mark_flagged(self, uids: list[str], flagged: bool) -> dict[str, bool]:
        """Star/unstar messages. Returns {uid: ok}."""
        raise NotImplementedError

    def get_attachments(self, msg_id: str) -> list[tuple[str, bytes]]:
        """Download attachments as (filename, bytes)."""
        raise NotImplementedError


def get_backend(kind: str = "demo", account: str | None = None) -> EmailBackend:
    if account:
        from . import config as cfgmod

        acct = cfgmod.get_account(account)
        if not acct:
            raise ValueError(
                f"unknown account '{account}'. Run `wipplank account list`."
            )
        atype = (acct.get("type") or "imap").lower()
        if atype == "imap":
            from .backends_imap import ImapBackend

            return ImapBackend(account=account)
        if atype == "gmail":
            from .backends_gmail import GmailBackend

            return GmailBackend(account=account)
        raise ValueError(f"account '{account}' has unknown type '{atype}'.")
    kind = (kind or "demo").lower()
    if kind == "demo":
        from .backends_demo import DemoBackend

        return DemoBackend()
    if kind == "gmail":
        from .backends_gmail import GmailBackend

        return GmailBackend()
    if kind in ("imap", "smtp", "generic"):
        from .backends_imap import ImapBackend

        return ImapBackend()
    raise ValueError(f"unknown backend '{kind}'. Choose demo, gmail, or imap.")
