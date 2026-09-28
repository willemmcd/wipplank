"""Gmail backend: OAuth2 + Gmail REST API. stdlib + google-api-python-client."""
import base64
import uuid
from email.message import EmailMessage

from . import config as cfgmod
from .backends import EmailBackend
from .models import Message

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _decode_headers(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers:
        n = (h.get("name") or "").lower()
        if n in ("from", "to", "subject", "date", "message-id", "references"):
            out[n] = h.get("value", "")
    return out


def _walk_parts(payload: dict):
    """Yield (is_attachment, filename, mime, b64data) for leaf parts."""
    stack = [payload]
    while stack:
        part = stack.pop()
        subs = part.get("parts")
        if subs:
            stack.extend(subs)
            continue
        filename = part.get("filename", "")
        body = part.get("body", {}) or {}
        data = body.get("data", "")
        attach_id = body.get("attachmentId", "")
        mime = part.get("mimeType", "")
        if filename:
            yield True, filename, mime, data, attach_id
        elif mime in ("text/plain", "text/html") and data:
            yield False, "", mime, data, ""


def _b64d(s: str) -> bytes:
    import base64 as _b

    return _b.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class GmailBackend(EmailBackend):
    name = "gmail"

    def __init__(self, account: str | None = None):
        if account:
            acct = cfgmod.get_account(account)
            if not acct or acct.get("type") != "gmail":
                raise SystemExit(f"No Gmail account '{account}'. Run `wipplank account list`.")
            self.account = account
            self._acct = acct
        else:
            # default gmail account, else helpful setup error
            name = None
            for n, a in cfgmod.list_accounts().items():
                if a.get("type") == "gmail":
                    name = n
                    break
            if not name:
                raise SystemExit(
                    "No Gmail account configured. Run:\n"
                    "  wipplank auth login --backend gmail --account personal\n"
                    "Needs a Google Cloud OAuth client (Desktop app) — client ID + secret."
                )
            self.account = name
            self._acct = cfgmod.get_account(name)

    # -- auth --

    def _creds(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError:
            raise SystemExit("Gmail libs missing. Run: pip install 'wipplank[gmail]'")
        import json as _json

        stored = cfgmod.get_account_password(self.account) or ""
        try:
            data = _json.loads(stored) if stored.startswith("{") else {"refresh_token": stored}
        except Exception:
            data = {"refresh_token": stored}
        if not data.get("refresh_token"):
            raise SystemExit(
                f"Gmail account '{self.account}' never completed OAuth. Run:\n"
                f"  wipplank auth login --backend gmail --account {self.account}"
            )
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._acct.get("client_id"),
            client_secret=self._acct.get("client_secret"),
            scopes=SCOPES,
        )
        if not creds.valid:
            creds.refresh(Request())
            cfgmod.save_account_password(
                self.account,
                _json.dumps({"token": creds.token, "refresh_token": creds.refresh_token}),
            )
        return creds

    def _service(self):
        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise SystemExit("Gmail libs missing. Run: pip install 'wipplank[gmail]'")
        return build("gmail", "v1", credentials=self._creds())

    # -- mapping --

    @staticmethod
    def _to_message(meta: dict, full: dict | None = None) -> Message:
        gid = meta["id"]
        labels = meta.get("labelIds", []) if full is None else full.get("labelIds", meta.get("labelIds", []))
        src = full or meta
        headers = _decode_headers(
            src.get("payload", {}).get("headers", []) if "payload" in src else meta.get("payload", {}).get("headers", [])
        )
        body, html_fallback, attachments = "", "", []
        if full and "payload" in full:
            for is_att, fname, mime, data, _aid in _walk_parts(full["payload"]):
                if is_att:
                    attachments.append(fname)
                elif data and mime == "text/plain" and not body:
                    body = _b64d(data).decode(errors="replace")
                elif data and mime == "text/html" and not html_fallback:
                    html_fallback = _b64d(data).decode(errors="replace")
            if not body.strip() and html_fallback.strip():
                from .htmltext import html_to_text

                body = "[HTML mail — converted to text]\n" + html_to_text(html_fallback)
        return Message(
            id=gid,
            from_=headers.get("from", ""),
            to=headers.get("to", ""),
            subject=headers.get("subject", "") or "(no subject)",
            snippet=(full.get("snippet", "") if full else meta.get("snippet", "")) or body[:120].replace("\n", " "),
            body=body,
            date=headers.get("date", ""),
            unread="UNREAD" in labels,
            flagged="STARRED" in labels,
            attachments=attachments,
            message_id=headers.get("message-id", ""),
            references=headers.get("references", "").split() if headers.get("references") else [],
        )

    # -- ops --

    def list_messages(self, limit: int = 20) -> list[Message]:
        svc = self._service().users().messages()
        resp = svc.list(userId="me", maxResults=min(limit, 50)).execute()
        ids = [m["id"] for m in resp.get("messages", [])][:limit]
        out = []
        for gid in ids:
            meta = svc.get(userId="me", id=gid, format="metadata",
                           metadataHeaders=["From", "To", "Subject", "Date", "Message-ID"]).execute()
            out.append(self._to_message(meta))
        return out

    def get_message(self, msg_id: str) -> Message:
        svc = self._service().users().messages()
        full = svc.get(userId="me", id=msg_id, format="full").execute()
        return self._to_message({"id": msg_id}, full)

    def search(self, query: str, limit: int = 20) -> list[Message]:
        svc = self._service().users().messages()
        resp = svc.list(userId="me", q=query, maxResults=min(limit, 50)).execute()
        ids = [m["id"] for m in resp.get("messages", [])][:limit]
        return [self.get_message(gid) for gid in ids]

    def send(self, to: str, subject: str, body: str,
             attachments: list[str] | None = None,
             in_reply_to: str | None = None,
             references: list[str] | None = None) -> Message:
        import mimetypes
        from pathlib import Path

        msg = EmailMessage()
        msg["From"] = self._acct.get("email", "me")
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = " ".join(references)
        msg.set_content(body)
        names = []
        for p in attachments or []:
            path = Path(p).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"attachment not found: {p}")
            ctype, _ = mimetypes.guess_type(str(path))
            mt, st = (ctype or "application/octet-stream").split("/", 1)
            msg.add_attachment(path.read_bytes(), maintype=mt, subtype=st, filename=path.name)
            names.append(path.name)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = self._service().users().messages().send(
            userId="me", body={"raw": raw}).execute()
        return Message(
            id=sent.get("id", f"gmail-{uuid.uuid4().hex[:8]}"),
            from_=self._acct.get("email", "me"), to=to, subject=subject,
            snippet=body[:120], body=body, date="now", unread=False,
            labels=["sent"], attachments=names,
            in_reply_to=in_reply_to or "", references=list(references or []),
        )

    def mark_seen(self, uids: list[str], seen: bool) -> dict[str, bool]:
        svc = self._service().users().messages()
        out = {}
        for gid in uids:
            try:
                svc.modify(userId="me", id=gid, body={
                    "addLabelIds": [] if seen else ["UNREAD"],
                    "removeLabelIds": ["UNREAD"] if seen else [],
                }).execute()
                out[gid] = True
            except Exception:
                out[gid] = False
        return out

    def mark_flagged(self, uids: list[str], flagged: bool) -> dict[str, bool]:
        svc = self._service().users().messages()
        out = {}
        for gid in uids:
            try:
                svc.modify(userId="me", id=gid, body={
                    "addLabelIds": ["STARRED"] if flagged else [],
                    "removeLabelIds": [] if flagged else ["STARRED"],
                }).execute()
                out[gid] = True
            except Exception:
                out[gid] = False
        return out

    def get_attachments(self, msg_id: str) -> list[tuple[str, bytes]]:
        svc = self._service().users().messages()
        full = svc.get(userId="me", id=msg_id, format="full").execute()
        out = []
        for is_att, fname, _mime, data, aid in _walk_parts(full.get("payload", {})):
            if not is_att:
                continue
            if not data and aid:
                att = svc.attachments().get(userId="me", messageId=msg_id, id=aid).execute()
                data = att.get("data", "")
            out.append((fname, _b64d(data) if data else b""))
        return out


def oauth_login(account: str, client_id: str, client_secret: str) -> str:
    """Run browser OAuth flow, store refresh token in keyring. Returns email."""
    import json as _json

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit("Gmail libs missing. Run: pip install 'wipplank[gmail]'")
    flow = InstalledAppFlow.from_client_config(
        {"installed": {"client_id": client_id, "client_secret": client_secret,
                       "redirect_uris": ["http://localhost"],
                       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": "https://oauth2.googleapis.com/token"}},
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    cfgmod.save_account(
        account, {"type": "gmail", "email": "", "client_id": client_id,
                  "client_secret": client_secret})
    cfgmod.save_account_password(
        account, _json.dumps({"token": creds.token, "refresh_token": creds.refresh_token}))
    svc = build("gmail", "v1", credentials=creds)
    email = svc.users().getProfile(userId="me").execute().get("emailAddress", "")
    acct = cfgmod.get_account(account) or {}
    acct["email"] = email
    cfgmod.save_account(account, acct)
    return email
