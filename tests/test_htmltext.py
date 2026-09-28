from wipplank.htmltext import html_to_text


def test_basic_blocks_and_links():
    html = ('<h1>Hi</h1><p>See <a href="https://x.y">Why</a> now.</p>'
            '<ul><li>one</li><li>two</li></ul>')
    t = html_to_text(html)
    assert "Hi" in t
    assert "Why (https://x.y)" in t
    assert "one" in t and "two" in t


def test_drops_script_style_head():
    html = ("<head><title>T</title><style>.a{}</style></head>"
            "<script>evil()</script><p>ok</p>")
    t = html_to_text(html)
    assert t == "ok"
    assert "evil" not in t and "T" not in t


def test_plain_passthrough_and_empty():
    assert html_to_text("just text") == "just text"
    assert html_to_text("") == ""
