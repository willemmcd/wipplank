"""Wipplank TUI - inbox, reader, search, flags, compose. Needs `pip install wipplank[tui]`."""
import asyncio

from .models import Message

CSS = """
#top { height: 3; border-bottom: solid #e3e7ee; }
#cols { height: 1fr; }
#inbox { width: 1fr; }
#reader { width: 1fr; border-left: solid #e3e7ee; padding: 1 2; }
#status { height: 1; color: #5d6672; padding: 0 1; }
DataTable { height: 1fr; }
"""


def _row(m: Message) -> tuple[str, ...]:
    dot = "o" if m.unread else " "
    star = "*" if m.flagged else " "
    subj = m.subject
    if len(subj) > 60:
        subj = subj[:59] + "…"
    return (f"{dot}{star}", m.from_[:28], subj, m.date[:24])


def make_app(be, account: str | None = None):
    """Build the Textual app around a backend instance (demo in tests)."""
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import DataTable, Footer, Header, Input, Static, TextArea

    class ComposeModal(ModalScreen):
        def __init__(self, to: str = "", subject: str = "", body: str = ""):
            super().__init__()
            self._to, self._subject, self._body = to, subject, body

        def compose(self) -> ComposeResult:
            yield Vertical(
                Static("COMPOSE  (ctrl+s send, esc discard)"),
                Input(self._to, placeholder="To", id="c-to"),
                Input(self._subject, placeholder="Subject", id="c-sub"),
                TextArea(self._body, id="c-body"),
                Input(placeholder="Attachments, comma separated", id="c-att"),
            )

        async def on_key(self, event) -> None:  # type: ignore[override]
            from textual.events import Key

            if not isinstance(event, Key):
                return
            if event.key == "escape":
                self.app.pop_screen()
            elif event.key == "ctrl+s":
                to = self.query_one("#c-to", Input).value.strip()
                subject = self.query_one("#c-sub", Input).value.strip()
                body = self.query_one("#c-body", TextArea).text
                raw = self.query_one("#c-att", Input).value.strip()
                attach = [p.strip() for p in raw.split(",") if p.strip()] or None
                if not to or not subject or not body.strip():
                    self.app.notify("To + subject + body required", severity="error")
                    return
                try:
                    m = await asyncio.to_thread(be.send, to, subject, body, attach)
                except Exception as e:  # noqa: BLE001
                    self.app.notify(str(e), severity="error")
                    return
                self.app.notify(f"Sent ({m.id})")
                self.app.pop_screen()

    class MailApp(App):
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "reload", "Reload"),
            ("slash", "focus_search", "Search"),
            ("u", "toggle_read", "Read/unread"),
            ("s", "toggle_flag", "Star"),
            ("c", "compose", "Compose"),
            ("escape", "back", "Back"),
        ]

        def __init__(self):
            super().__init__()
            self.msgs: list[Message] = []
            self.by_id: dict[str, Message] = {}
            self.order: list[str] = []
            self.CSS = CSS

        def compose(self) -> ComposeResult:
            yield Header()
            yield Input(placeholder="Search (enter)  |  enter=open  u=read  s=star  c=compose  q=quit", id="top")
            with Horizontal(id="cols"):
                table = DataTable(id="inbox")
                table.add_column("Fl", width=4)
                table.add_column("From", width=30)
                table.add_column("Subject", width=62)
                table.add_column("Date", width=24)
                yield table
                yield Static("Select a message + enter.", id="reader")
            yield Static("", id="status")
            yield Footer()

        async def on_mount(self) -> None:
            await self.reload()

        async def reload(self) -> None:
            table = self.query_one("#inbox", DataTable)
            self.notify("Loading…")
            try:
                msgs = await asyncio.to_thread(be.list_messages, 50)
            except Exception as e:  # noqa: BLE001
                self.query_one("#status", Static).update(f"ERROR: {e}")
                return
            self.msgs = msgs
            self.by_id = {m.id: m for m in msgs}
            self.order = [m.id for m in msgs]
            table.clear()
            for m in msgs:
                table.add_row(*_row(m), key=m.id)
            self.query_one("#status", Static).update(
                f"{len(msgs)} messages | backend={be.name}"
                + (f" account={account}" if account else "")
            )

        async def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id != "top":
                return
            q = event.value.strip()
            table = self.query_one("#inbox", DataTable)
            try:
                msgs = await asyncio.to_thread(
                    be.search if q else be.list_messages, q if q else 50
                )
            except Exception as e:  # noqa: BLE001
                self.query_one("#status", Static).update(f"ERROR: {e}")
                return
            self.msgs = msgs
            self.by_id = {m.id: m for m in msgs}
            self.order = [m.id for m in msgs]
            table.clear()
            for m in msgs:
                table.add_row(*_row(m), key=m.id)
            self.query_one("#status", Static).update(f"{len(msgs)} results")

        async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            mid = str(event.row_key.value)
            try:
                m = await asyncio.to_thread(be.get_message, mid)
            except Exception as e:  # noqa: BLE001
                self.query_one("#status", Static).update(f"ERROR: {e}")
                return
            self.by_id[m.id] = m
            att = f"\nAttachments: {', '.join(m.attachments)}" if m.attachments else ""
            self.query_one("#reader", Static).update(
                f"{m.subject}\n{m.from_} -> {m.to} | {m.date}{att}\n\n{m.body}"
            )

        async def _selected_id(self) -> str | None:
            table = self.query_one("#inbox", DataTable)
            if table.cursor_row is None:
                return None
            if 0 <= table.cursor_row < len(self.order):
                return self.order[table.cursor_row]
            return None

        async def action_reload(self) -> None:
            await self.reload()

        async def action_focus_search(self) -> None:
            self.query_one("#top", Input).focus()

        async def action_back(self) -> None:
            self.query_one("#inbox", DataTable).focus()

        async def action_toggle_read(self) -> None:
            mid = await self._selected_id()
            if not mid:
                return
            m = self.by_id[mid]
            await asyncio.to_thread(be.mark_seen, [mid], m.unread)
            m.unread = not m.unread
            await self._refresh_row(m)

        async def action_toggle_flag(self) -> None:
            mid = await self._selected_id()
            if not mid:
                return
            m = self.by_id[mid]
            await asyncio.to_thread(be.mark_flagged, [mid], not m.flagged)
            m.flagged = not m.flagged
            await self._refresh_row(m)

        async def _refresh_row(self, m: Message) -> None:
            table = self.query_one("#inbox", DataTable)
            for i, row in enumerate(self.msgs):
                if row.id == m.id:
                    self.msgs[i] = m
                    table.update_cell_at((i, 0), _row(m)[0])
                    break

        def action_compose(self) -> None:
            self.push_screen(ComposeModal())

    return MailApp()


def run(backend_kind: str = "demo", account: str | None = None) -> None:
    try:
        import textual  # noqa: F401
    except ImportError:
        raise SystemExit("TUI needs textual. Run: pip install 'wipplank[tui]'")

    from .backends import get_backend

    make_app(get_backend(backend_kind, account=account), account).run()
