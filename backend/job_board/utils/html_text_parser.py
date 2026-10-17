"""HTML to readable plain text for posting descriptions."""

import re
from html.parser import HTMLParser

BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}
)
SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template"})
SPACES = re.compile(r"[ \t\f\v ]+")
EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


class HtmlTextParser(HTMLParser):
    """Collects text from HTML: block tags become line breaks, list items get "- ", scripts are dropped.

    Character references (&amp;, &nbsp;) are decoded by HTMLParser itself (convert_charrefs=True).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    @staticmethod
    def to_text(html: str) -> str:
        """Convert an HTML fragment to plain text with at most one blank line between blocks."""
        parser = HtmlTextParser()
        parser.feed(html)
        parser.close()
        return parser.text

    @property
    def text(self) -> str:
        """Text collected so far, whitespace-normalized."""
        lines = (SPACES.sub(" ", line).strip() for line in "".join(self._parts).split("\n"))
        return EXTRA_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Open a block or skipped region."""
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self._parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag: str) -> None:
        """Close a block or skipped region; </li> adds nothing so list items stay on consecutive lines."""
        if tag in SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BLOCK_TAGS and tag != "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Keep text outside script/style."""
        if self._skip_depth == 0:
            self._parts.append(data)
