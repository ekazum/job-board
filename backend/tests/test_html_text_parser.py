"""HtmlTextParser: descriptions as readable plain text."""

from job_board.utils.html_text_parser import HtmlTextParser


def test_blocks_lists_entities_and_scripts() -> None:
    html = (
        "<h2>About</h2><p>We build&nbsp;APIs &amp; tools.</p>"
        "<ul><li>Python</li><li>Postgres</li></ul>"
        "<script>track()</script><style>p{}</style><p>Apply<br>today</p>"
    )
    assert HtmlTextParser.to_text(html) == "About\n\nWe build APIs & tools.\n\n- Python\n- Postgres\n\nApply\ntoday"


def test_plain_text_passes_through() -> None:
    assert HtmlTextParser.to_text("  just   text  ") == "just text"


def test_empty() -> None:
    assert HtmlTextParser.to_text("") == ""
