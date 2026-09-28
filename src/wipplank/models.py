"""Shared email models."""
from dataclasses import asdict, dataclass, field


@dataclass
class Message:
    id: str
    from_: str
    to: str = ""
    subject: str = ""
    snippet: str = ""
    body: str = ""
    date: str = ""
    unread: bool = True
    flagged: bool = False
    labels: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    message_id: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from"] = d.pop("from_")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        d = dict(d)
        if "from" in d:
            d["from_"] = d.pop("from")
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})
