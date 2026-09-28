"""Real IMAP for reading + SMTP for sending. stdlib only."""
import imaplib
import smtplib
import uuid
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser

from . import config as cfgmod
from .backends import EmailBackend
from .models import Message


def _decode(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


def _body_text(msg) -> str:
    from .htmltext import html_to_text

    def _part_text(part) -> str:
        try:
            c = part.get_content()
            return c if isinstance(c, str) else ""
        except Exception:
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
            return ""

    if msg.is_multipart():
        html_fallback = ""
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if disp == "attachment":
                continue
            if ctype == "text/plain":
                text = _part_text(part).strip()
                if text:
                    return text
            elif ctype == "text/html" and not html_fallback:
                html_fallback = _part_text(part)
        if html_fallback.strip():
            return "[HTML mail — converted to text]\n" + html_to_text(html_fallback)
        return ""
    try:
        c = msg.get_content()
        text = c if isinstance(c, str) else str(c)
    except Exception:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode(errors="replace")
        else:
            return str(msg.get_payload())
    if msg.get_content_type() == "text/html" and text.strip():
        return "[HTML mail — converted to text]\n" + html_to_text(text)
    return text


def _to_message(uid: str, raw: bytes, flags: bytes = b"") -> Message:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    subject = _decode(parsed["subject"])
    from_ = _decode(parsed["from"])
    to = _decode(parsed["to"])
    date = str(parsed["date"] or "")
    body = _body_text(parsed)
    unread = b"\\Seen" not in flags
    flagged = b"\\Flagged" in flags
    # stable across reads within same mailbox generation; Message-ID kept for cross-check
    message_id = str(parsed["Message-ID"] or "")
    attachments: list[str] = []
    try:
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_disposition() == "attachment":
                    fname = part.get_filename() or "unnamed"
                    attachments.append(str(fname))
    except Exception:
        pass
    return Message(
        id=uid,
        from_=from_,
        to=to,
        subject=subject or "(no subject)",
        snippet=body[:120].replace("\n", " "),
        body=body,
        date=date,
        unread=unread,
        flagged=flagged,
        attachments=attachments,
        message_id=message_id,
    )


class ImapBackend(EmailBackend):
    name = "imap"

    def __init__(
        self,
        host=None,
        port=None,
        username=None,
        password=None,
        smtp_host=None,
        smtp_port=None,
        account: str | None = None,
    ):
        if account:
            acct = cfgmod.get_account(account)
            if not acct:
                raise SystemExit(
                    f"No account '{account}'. Run `wipplank account list`."
                )
            if acct.get("type", "imap") != "imap":
                raise SystemExit(f"Account '{account}' is not an IMAP account.")
            stored = acct
            self.account = account
            resolved_user = username or stored.get("username")
            self.password = password or (
                cfgmod.get_account_password(account) if resolved_user else None
            )
        else:
            stored = cfgmod.get_imap_config()
            self.account = None
            resolved_user = username or stored.get("username")
            self.password = password or (
                cfgmod.get_password(resolved_user) if resolved_user else None
            )
        self.host = host or stored.get("host")
        self.port = int(port or stored.get("port", 993))
        self.username = resolved_user
        self.smtp_host = smtp_host or stored.get("smtp_host")
        self.smtp_port = int(smtp_port or stored.get("smtp_port", 587))
        self.from_addr = stored.get("from_addr") or self.username

        if not self.host or not self.username:
            raise SystemExit(
                "No IMAP account configured. Run:\n"
                "  wipplank auth login --backend imap --preset fastmail --username you@fastmail.com\n"
                "Presets: fastmail, icloud, gmail, outlook"
            )
        if not self.password:
            raise SystemExit(
                f"No password in keyring for {self.username}. Run:\n"
                f"  wipplank auth login --backend imap --username {self.username}"
            )
        self.mailbox = "INBOX"
        self.use_cache = True

    def _connect(self):
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        conn.login(self.username, self.password)
        conn.select(self.mailbox)
        return conn

    def _flags_map(self, conn, uids: list[str]) -> dict[str, bytes]:
        """One round trip for FLAGS across many UIDs. Never touches bodies."""
        import re

        if not uids:
            return {}
        typ, data = conn.uid("FETCH", ",".join(uids), "(FLAGS)")
        out: dict[str, bytes] = {}
        if typ != "OK" or not data:
            return out
        for item in data:
            raw = item[0] if isinstance(item, tuple) else item
            if not isinstance(raw, bytes):
                continue
            text = raw.decode(errors="replace")
            m = re.search(r"UID\s+(\d+)", text)
            f = re.search(r"FLAGS\s*\(([^)]*)\)", text)
            if m:
                out[m.group(1)] = f.group(1).encode() if f else b""
        return out

    def _uidvalidity(self, conn) -> str:
        # cached per-connection; falls back to "0" if server won't tell us
        cached = getattr(conn, "_wipplank_uidvalidity", None)
        if cached:
            return cached
        try:
            typ, data = conn.status(self.mailbox, "(UIDVALIDITY)")
            if typ == "OK" and data and data[0]:
                raw = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
                # e.g. 'INBOX (UIDVALIDITY 12345)'
                digits = "".join(ch for ch in raw if ch.isdigit())
                # last number group is the validity; naive parse: take trailing digits run
                import re

                m = re.search(r"UIDVALIDITY\s+(\d+)", raw)
                if m:
                    conn._wipplank_uidvalidity = m.group(1)
                    return m.group(1)
        except Exception:
            pass
        return "0"

    @staticmethod
    def _split_id(msg_id: str) -> tuple[str | None, str]:
        # stable form "uidvalidity:uid", legacy plain "uid"
        if ":" in msg_id:
            v, u = msg_id.rsplit(":", 1)
            if u.isdigit():
                return v, u
        return None, msg_id

    def _stable_id(self, conn, uid: str) -> str:
        return f"{self._uidvalidity(conn)}:{uid}"

    def _uids(self, conn, criteria="ALL", limit=20) -> list[str]:
        typ, data = conn.uid("SEARCH", None, criteria)
        if typ != "OK":
            return []
        all_uids = data[0].split() if data and data[0] else []
        # newest last -> take tail, reverse for newest-first
        return [u.decode() for u in all_uids[-limit:]][::-1]

    def _fetch(self, conn, uid: str) -> Message:
        # BODY.PEEK[] avoids setting \Seen (read-only list/check)
        typ, data = conn.uid("FETCH", uid, "(FLAGS BODY.PEEK[])")
        if typ != "OK" or not data or data[0] is None:
            raise ValueError(f"message '{uid}' not found")
        # data looks like [(meta, raw), flags...] - find bytes payload
        raw = b""
        flags = b""
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                meta, payload = item
                if isinstance(meta, bytes):
                    flags += meta
                if isinstance(payload, bytes):
                    raw = payload
        if not raw:
            raise ValueError(f"message '{uid}' empty")
        _, uid_part = self._split_id(uid)
        return _to_message(self._stable_id(conn, uid_part), raw, flags)

    def list_messages(self, limit: int = 20) -> list[Message]:
        from . import imap_cache

        conn = self._connect()
        try:
            uids = self._uids(conn, "ALL", limit)
            validity = self._uidvalidity(conn)
            cached: dict[str, dict] = {}
            if self.use_cache:
                cached = imap_cache.get_many(
                    self.host, self.username, self.mailbox, validity, uids
                )
            missing = [u for u in uids if u not in cached]
            fresh: dict[str, dict] = {}
            for u in missing:
                m = self._fetch(conn, u)
                fresh[u] = m.to_dict()
            if fresh and self.use_cache:
                imap_cache.put_many(
                    self.host, self.username, self.mailbox, validity, fresh
                )
            # one cheap FLAGS round trip keeps read-state current for cached rows
            flags = self._flags_map(conn, uids) if uids else {}
            out = []
            for u in uids:
                d = fresh.get(u) or cached.get(u)
                if not d:
                    continue
                m = Message.from_dict(d)
                if u in flags:
                    m.unread = b"\\Seen" not in flags[u]
                out.append(m)
            return out
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()

    def get_message(self, msg_id: str) -> Message:
        from . import imap_cache

        want_validity, uid = self._split_id(msg_id)
        if self.use_cache and want_validity and want_validity != "0":
            hit = imap_cache.get_many(
                self.host, self.username, self.mailbox, want_validity, [uid]
            ).get(uid)
            if hit:
                return Message.from_dict(hit)
        conn = self._connect()
        try:
            if want_validity and want_validity != "0":
                current = self._uidvalidity(conn)
                if current != "0" and current != want_validity:
                    raise ValueError(
                        f"message '{msg_id}' is stale (mailbox regenerated: "
                        f"UIDVALIDITY {want_validity} -> {current}). Re-run check/search."
                    )
            m = self._fetch(conn, uid)
            if self.use_cache:
                imap_cache.put_many(
                    self.host, self.username, self.mailbox,
                    self._uidvalidity(conn), {uid: m.to_dict()},
                )
            return m
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()

    def search(self, query: str, limit: int = 20) -> list[Message]:
        from . import imap_cache

        conn = self._connect()
        try:
            # quote query safely
            safe = query.replace('"', "")
            typ, data = conn.uid("SEARCH", None, "TEXT", f'"{safe}"')
            if typ != "OK":
                return []
            uids = data[0].split() if data and data[0] else []
            latest = [u.decode() for u in uids[-limit:]][::-1]
            out = [self._fetch(conn, u) for u in latest]
            if out and self.use_cache:
                imap_cache.put_many(
                    self.host, self.username, self.mailbox,
                    self._uidvalidity(conn),
                    {u: m.to_dict() for u, m in zip(latest, out)},
                )
            return out
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()

    def _store(self, uids: list[str], op: str, flag: str) -> dict[str, bool]:
        conn = self._connect()
        try:
            bare = [self._split_id(u)[1] for u in uids]
            typ, _ = conn.uid("STORE", ",".join(bare), op, f"({flag})")
            ok = typ == "OK"
            if ok and self.use_cache:
                self._patch_cache(conn, self._uidvalidity(conn), bare, flag,
                                  op == "+FLAGS")
            return {u: ok for u in uids}
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()

    def _patch_cache(self, conn, validity: str, bare_uids: list[str],
                     flag: str, add: bool) -> None:
        from . import imap_cache

        cached = imap_cache.get_many(
            self.host, self.username, self.mailbox, validity, bare_uids
        )
        patched = {}
        for u, d in cached.items():
            m = Message.from_dict(d)
            if flag == "\\Seen":
                m.unread = add is False  # +FLAGS \Seen => read
            elif flag == "\\Flagged":
                m.flagged = add
            patched[u] = m.to_dict()
        if patched:
            imap_cache.put_many(
                self.host, self.username, self.mailbox, validity, patched
            )

    def mark_seen(self, uids: list[str], seen: bool) -> dict[str, bool]:
        return self._store(uids, "+FLAGS" if seen else "-FLAGS", "\\Seen")

    def mark_flagged(self, uids: list[str], flagged: bool) -> dict[str, bool]:
        return self._store(uids, "+FLAGS" if flagged else "-FLAGS", "\\Flagged")

    def get_attachments(self, msg_id: str) -> list[tuple[str, bytes]]:
        _, uid = self._split_id(msg_id)
        conn = self._connect()
        try:
            typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not data:
                raise ValueError(f"message '{msg_id}' not found")
            raw = b""
            for item in data:
                if isinstance(item, tuple) and len(item) == 2:
                    if isinstance(item[1], bytes):
                        raw += item[1]
            if not raw:
                raise ValueError(f"message '{msg_id}' empty")
            parsed = BytesParser(policy=policy.default).parsebytes(raw)
            out: list[tuple[str, bytes]] = []
            if parsed.is_multipart():
                for part in parsed.walk():
                    if part.get_content_disposition() == "attachment":
                        payload = part.get_payload(decode=True) or b""
                        out.append((str(part.get_filename() or "unnamed"), payload))
            return out
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[str] | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> Message:
        import mimetypes
        from pathlib import Path

        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = " ".join(references)
        msg.set_content(body)
        attached_names: list[str] = []
        for path_str in attachments or []:
            p = Path(path_str).expanduser()
            if not p.is_file():
                raise FileNotFoundError(f"attachment not found: {path_str}")
            ctype, _ = mimetypes.guess_type(str(p))
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            msg.add_attachment(
                p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name
            )
            attached_names.append(p.name)
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
            s.starttls()
            s.login(self.username, self.password)
            s.send_message(msg)
        return Message(
            id=f"smtp-{uuid.uuid4().hex[:8]}",
            from_=self.from_addr,
            to=to,
            subject=subject,
            snippet=body[:120],
            body=body,
            date="now",
            unread=False,
            labels=["sent"],
            attachments=attached_names,
            in_reply_to=in_reply_to or "",
            references=list(references or []),
        )
