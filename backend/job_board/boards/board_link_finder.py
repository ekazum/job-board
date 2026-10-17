"""Find an applicant-tracking-system board link in a careers page."""

import re
from collections.abc import Callable, Sequence

from job_board.boards.board_ref import BoardRef
from job_board.enums.platform import Platform

COMEET_UID = r"[0-9A-Za-z]{2}\.[0-9A-Za-z]{3}"
# Path segments and subdomains that look like slugs but are not boards.
RESERVED_SLUGS = frozenset({"embed", "www", "api", "app", "v0", "v1", "static", "assets", "careers-api", "jobs", "help"})
CASE_INSENSITIVE_PLATFORMS = frozenset({Platform.GREENHOUSE, Platform.LEVER})
# The Comeet widget's token and company name are read only this close to its company uid.
WIDGET_WINDOW = 2000

BoardBuilder = Callable[[re.Match[str]], BoardRef | None]


def _pattern(regex: str) -> re.Pattern[str]:
    """Board URLs are matched case-insensitively."""
    return re.compile(regex, re.IGNORECASE)


def _clean(segment: str) -> str | None:
    """A slug segment without trailing dots, or None for reserved words like "embed"."""
    cleaned = segment.rstrip(".")
    return None if not cleaned or cleaned.lower() in RESERVED_SLUGS else cleaned


def _slug_board(platform: Platform) -> BoardBuilder:
    """Builder for platforms whose board is a single slug."""

    def build(match: re.Match[str]) -> BoardRef | None:
        slug = _clean(match.group(1))
        if slug is None:
            return None
        return BoardRef(platform, slug.lower() if platform in CASE_INSENSITIVE_PLATFORMS else slug)

    return build


def _comeet_hosted(match: re.Match[str]) -> BoardRef | None:
    """comeet.com/jobs/{company}/{uid}: read through the hosted page (no token there)."""
    company = _clean(match.group(1))
    return None if company is None else BoardRef(Platform.COMEET, f"{company}/{match.group(2)}", company_uid=match.group(2))


def _comeet_api(match: re.Match[str]) -> BoardRef | None:
    """careers-api/2.0/company/{uid}/positions?token={token}: read through the API."""
    return BoardRef(Platform.COMEET, match.group(1), company_uid=match.group(1), token=match.group(2))


def _workday(match: re.Match[str]) -> BoardRef | None:
    """{tenant}.{wd host}.myworkdayjobs.com/[{locale}/]{site}."""
    tenant, wd_host, site = match.group(1).lower(), match.group(2).lower(), match.group(3)
    return BoardRef(Platform.WORKDAY, f"{tenant}/{site}", tenant=tenant, wd_host=wd_host, site=site)


DEFAULT_RULES: tuple[tuple[re.Pattern[str], BoardBuilder], ...] = (
    # Greenhouse embeds carry the slug in ?for= (boards.greenhouse.io/embed/job_board/js?for=acme).
    (_pattern(r"(?:job-)?boards\.greenhouse\.io/embed/[^\s\"'<>]*?[?&;]for=([\w-]+)"), _slug_board(Platform.GREENHOUSE)),
    (_pattern(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)"), _slug_board(Platform.GREENHOUSE)),
    (_pattern(r"(?:job-)?boards\.greenhouse\.io/([\w-]+)"), _slug_board(Platform.GREENHOUSE)),
    (_pattern(r"jobs\.lever\.co/([\w-]+)"), _slug_board(Platform.LEVER)),
    (_pattern(r"api\.lever\.co/v0/postings/([\w-]+)"), _slug_board(Platform.LEVER)),
    (_pattern(r"jobs\.ashbyhq\.com/([\w.-]+)"), _slug_board(Platform.ASHBY)),
    (_pattern(r"api\.ashbyhq\.com/posting-api/job-board/([\w.-]+)"), _slug_board(Platform.ASHBY)),
    (_pattern(rf"careers-api/2\.0/company/({COMEET_UID})/positions\?(?:[^\s\"'<>]*?&)?token=([0-9A-Za-z]+)"), _comeet_api),
    (_pattern(rf"comeet\.com?/jobs/([\w-]+)/({COMEET_UID})"), _comeet_hosted),
    (_pattern(r"(?<![\w.-])([\w-]+)\.comeet\.co(?![\w.-])"), _slug_board(Platform.COMEET)),
    (_pattern(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[a-z]{2}/)?(?!wday/)([\w-]+)"), _workday),
)
# The Comeet careers widget: data-company-uid="E6.001" data-token="..." attributes, or COMEET.init({"token": "...",
# "company-uid": "E6.001", "company-name": "AI21"}) in a script.
WIDGET_UID = _pattern(rf"(?:data-company-uid|[\"']company-uid[\"'])\s*[=:]\s*[\"']({COMEET_UID})[\"']")
WIDGET_TOKEN = _pattern(r"(?:data-token|[\"']token[\"'])\s*[=:]\s*[\"']([0-9A-Za-z]{16,})[\"']")
WIDGET_NAME = _pattern(r"(?:data-company-name|[\"']company-name[\"'])\s*[=:]\s*[\"']([^\"']+)[\"']")


class BoardLinkFinder:
    """Returns the board referenced earliest in a page, or None.

    Pass the page's final URL along with its HTML: a /careers path that redirects to jobs.lever.co/acme is found
    from the URL alone. JSON-escaped slashes (https:\\/\\/jobs.lever.co\\/acme, common in framework data blobs)
    are unescaped first.
    """

    def __init__(self, rules: Sequence[tuple[re.Pattern[str], BoardBuilder]] = DEFAULT_RULES) -> None:
        self._rules = tuple(rules)

    def find(self, page: str) -> BoardRef | None:
        """The first board reference by position in the page."""
        unescaped = page.replace("\\/", "/")
        candidates: list[tuple[int, BoardRef]] = []
        for pattern, build in self._rules:
            found = self._first(pattern, build, unescaped)
            if found is not None:
                candidates.append(found)
        widget = self._comeet_widget(unescaped)
        if widget is not None:
            candidates.append(widget)
        if not candidates:
            return None
        _, board = min(candidates, key=lambda candidate: candidate[0])
        return board

    @staticmethod
    def _first(pattern: re.Pattern[str], build: BoardBuilder, page: str) -> tuple[int, BoardRef] | None:
        """The first match of one rule that builds a board (reserved words are skipped)."""
        for match in pattern.finditer(page):
            board = build(match)
            if board is not None:
                return match.start(), board
        return None

    @staticmethod
    def _comeet_widget(page: str) -> tuple[int, BoardRef] | None:
        """A Comeet widget: its company uid, plus the token and company name found near it."""
        uid = WIDGET_UID.search(page)
        if uid is None:
            return None
        window = page[max(0, uid.start() - WIDGET_WINDOW) : uid.end() + WIDGET_WINDOW]
        token = WIDGET_TOKEN.search(window)
        name = WIDGET_NAME.search(window)
        slug = f"{name.group(1).strip()}/{uid.group(1)}" if name else uid.group(1)
        board = BoardRef(Platform.COMEET, slug, company_uid=uid.group(1), token=token.group(1) if token else None)
        return uid.start(), board
