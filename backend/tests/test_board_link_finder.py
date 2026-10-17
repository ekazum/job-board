"""BoardLinkFinder: board links in careers pages."""

import pytest

from job_board.boards.board_link_finder import BoardLinkFinder
from job_board.boards.board_ref import BoardRef
from job_board.enums.platform import Platform


@pytest.fixture
def finder() -> BoardLinkFinder:
    return BoardLinkFinder()


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<a href="https://boards.greenhouse.io/acme">Jobs</a>', BoardRef(Platform.GREENHOUSE, "acme")),
        ('<a href="https://job-boards.greenhouse.io/Acme/jobs/123">', BoardRef(Platform.GREENHOUSE, "acme")),
        ('<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>', BoardRef(Platform.GREENHOUSE, "acme")),
        ('<iframe src="https://job-boards.greenhouse.io/embed/job_board?b=1&amp;for=acme-labs">', BoardRef(Platform.GREENHOUSE, "acme-labs")),
        ('fetch("https://boards-api.greenhouse.io/v1/boards/acme/jobs")', BoardRef(Platform.GREENHOUSE, "acme")),
        ('<a href="https://jobs.lever.co/acme/6ed76ce8-4156">', BoardRef(Platform.LEVER, "acme")),
        ('"https://api.lever.co/v0/postings/acme?mode=json"', BoardRef(Platform.LEVER, "acme")),
        ('<a href="https://jobs.ashbyhq.com/Acme.AI/8fb1615c">', BoardRef(Platform.ASHBY, "Acme.AI")),
        ('{"url":"https:\\/\\/jobs.lever.co\\/acme"}', BoardRef(Platform.LEVER, "acme")),
    ],
)
def test_finds_slug_boards(finder: BoardLinkFinder, html: str, expected: BoardRef) -> None:
    assert finder.find(html) == expected


# --- Comeet -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<a href="https://www.comeet.com/jobs/acme/98.008">',
            BoardRef(Platform.COMEET, "acme/98.008", company_uid="98.008"),
        ),
        (
            '<a href="https://www.comeet.com/jobs/acme/A1.00B/backend-engineer/AC.F50">',
            BoardRef(Platform.COMEET, "acme/A1.00B", company_uid="A1.00B"),
        ),
        ('<a href="https://acme.comeet.co/">', BoardRef(Platform.COMEET, "acme")),
        (
            'fetch("https://www.comeet.co/careers-api/2.0/company/E6.001/positions?details=true&token=ABCDEF0123456789AB")',
            BoardRef(Platform.COMEET, "E6.001", company_uid="E6.001", token="ABCDEF0123456789AB"),
        ),
        (  # the widget as AI21 embeds it (shape of www.ai21.com/careers, token replaced)
            '<script>window.comeetInit = function() { COMEET.init({\n  "token": "6E12000000000000000000000000000000000",\n'
            '  "company-uid": "E6.001",\n  "company-name": "AI21",\n}); };</script>',
            BoardRef(Platform.COMEET, "AI21/E6.001", company_uid="E6.001", token="6E12000000000000000000000000000000000"),
        ),
        (  # the widget as HTML data attributes
            '<div class="comeet-careers" data-company-uid="B3.00C" data-token="0011223344556677AABB"></div>',
            BoardRef(Platform.COMEET, "B3.00C", company_uid="B3.00C", token="0011223344556677AABB"),
        ),
    ],
)
def test_finds_comeet_boards(finder: BoardLinkFinder, html: str, expected: BoardRef) -> None:
    assert finder.find(html) == expected


# --- Workday ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        '<a href="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite">Jobs</a>',
        '<a href="https://NVIDIA.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/x">',
        '"https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs" ... '
        '<a href="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite">',
    ],
)
def test_finds_workday_site(finder: BoardLinkFinder, html: str) -> None:
    assert finder.find(html) == BoardRef(
        Platform.WORKDAY,
        "nvidia/NVIDIAExternalCareerSite",
        tenant="nvidia",
        wd_host="wd5",
        site="NVIDIAExternalCareerSite",
    )


# --- no board, ordering -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        "<p>We are hiring! Email jobs@acme.com</p>",
        '<a href="https://boards.greenhouse.io/embed/job_board">',  # embed without ?for=
        '<a href="https://www.comeet.com/careers">',  # Comeet's own site, not a board
        '<script src="https://www.comeet.co/careers-api/2.0/x.js">',  # www is reserved
        '<a href="https://acme.comeet.com/">',  # .com subdomain is not the .co board host
        '<a href="https://www.myworkdayjobs.com/">',  # no tenant.wdN host
    ],
)
def test_no_board(finder: BoardLinkFinder, html: str) -> None:
    assert finder.find(html) is None


def test_earliest_link_in_the_page_wins(finder: BoardLinkFinder) -> None:
    html = '<a href="https://jobs.ashbyhq.com/acme">new</a> ... <a href="https://boards.greenhouse.io/acme">old</a>'
    assert finder.find(html) == BoardRef(Platform.ASHBY, "acme")


def test_final_url_alone_is_enough(finder: BoardLinkFinder) -> None:
    assert finder.find("https://jobs.lever.co/acme\n<html>No links here</html>") == BoardRef(Platform.LEVER, "acme")
