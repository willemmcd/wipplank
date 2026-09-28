"""Headless Textual pilot on the demo backend."""
import pytest

textual_missing = pytest.importorskip("textual", reason="needs pip install wipplank[tui]")


async def test_inbox_search_compose():
    from textual.widgets import DataTable

    from wipplank.backends_demo import DemoBackend
    from wipplank.tui import make_app

    app = make_app(DemoBackend())
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#inbox", DataTable)
        assert table.row_count == 3
        await pilot.click("#top")
        await pilot.press(*"rocket")
        await pilot.press("enter")
        await pilot.pause()
        assert table.row_count == 1
        await pilot.press("escape")  # back to table focus
        await pilot.press("c")
        await pilot.pause()
        assert type(app.screen).__name__ == "ComposeModal"
        await pilot.press("escape")
        await pilot.pause()
        assert type(app.screen).__name__ != "ComposeModal"
