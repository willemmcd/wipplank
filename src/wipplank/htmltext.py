"""HTML -> readable text fallback. stdlib only, no w3m/lynx needed."""
import html as _html
import re
from html.parser import HTMLParser

_BLOCKS = {"p", "div", "section", "article", "header", "footer", "br", "hr",
           "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote", "pre"}
_SKIP = {"script", "style", "head"}


class _Textifier(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._skip = 0
        self._link: str | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP:
            self._skip += 1
            return
        if tag in _BLOCKS:
            self.chunks.append("\n")
        if tag == "a":
            href = dict(attrs).get("href", "")
            self._link = href or None

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if tag in _BLOCKS:
            self.chunks.append("\n")
        if tag == "a":
            if self._link and self._link not in ("".join(self.chunks)[-200:]):
                self.chunks.append(f" ({self._link})")
            self._link = None

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            if self.chunks and not self.chunks[-1].endswith(("\n", " ")):
                self.chunks.append(" ")
            self.chunks.append(text)


def html_to_text(html_body: str) -> str:
    """Best-effort readable text. Never raises; empty in -> empty out."""
    if not html_body or "<" not in html_body:
        return html_body or ""
    p = _Textifier()
    try:
        p.feed(html_body)
    except Exception:
        return _html.unescape(re.sub("<[^>]+>", " ", html_body))
    lines = [ln.strip() for ln in "".join(p.chunks).splitlines()]
    # collapse 3+ blank lines, drop leading/trailing blanks
    out: list[str] = []
    blanks = 0
    for ln in lines:
        if ln:
            out.append(ln)
            blanks = 0
        else:
            blanks += 1
            if blanks <= 1 and out:
                out.append("")
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)
