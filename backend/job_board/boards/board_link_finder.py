"""Find an applicant-tracking-system board link in a careers page."""

import re
from collections.abc import Sequence

from job_board.boards.board_ref import BoardRef
from job_board.enums.platform import Platform

COMEET_UID = r"[0-9A-Za-z]{2}\.[0-9A-Za-z]{3}"


def _pattern(regex: str) -> re.Pattern[str]:
    """Board URLs are matched case-insensitively."""
    return re.compile(regex, re.IGNORECASE)


DEFAULT_PATTERNS: tuple[tuple[Platform, re.Pattern[str]], ...] = (
    # Greenhouse embeds carry the slug in ?for= (boards.greenhouse.io/embed/job_board/js?for=acme).
    (Platform.GREENHOUSE, _pattern(r"(?:job-)?boards\.greenhouse\.io/embed/[^\s\"'<>]*?[?&;]for=([\w-]+)")),
    (Platform.GREENHOUSE, _pattern(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)")),
    (Platform.GREENHOUSE, _pattern(r"(?:job-)?boards\.greenhouse\.io/([\w-]+)")),
    (Platform.LEVER, _pattern(r"jobs\.lever\.co/([\w-]+)")),
    (Platform.LEVER, _pattern(r"api\.lever\.co/v0/postings/([\w-]+)")),
    (Platform.ASHBY, _pattern(r"jobs\.ashbyhq\.com/([\w.-]+)")),
    (Platform.ASHBY, _pattern(r"api\.ashbyhq\.com/posting-api/job-board/([\w.-]+)")),
    (Platform.COMEET, _pattern(rf"comeet\.com?/jobs/([\w-]+)/({COMEET_UID})")),
    (Platform.COMEET, _pattern(r"(?<![\w.-])([\w-]+)\.comeet\.co(?![\w.-])")),
)
# Path segments and subdomains that look like slugs but are not boards.
RESERVED_SLUGS = frozenset({"embed", "www", "api", "app", "v0", "v1", "static", "assets", "careers-api", "jobs", "help"})
CASE_INSENSITIVE_PLATFORMS = frozenset({Platform.GREENHOUSE, Platform.LEVER})


class BoardLinkFinder:
    """Returns the board linked earliest in a page, or None.

    Pass the page's final URL along with its HTML: a /careers path that redirects to jobs.lever.co/acme
    is found from the URL alone. JSON-escaped slashes (https:\\/\\/jobs.lever.co\\/acme, common in
    framework data blobs) are unescaped first.
    """

    def __init__(self, patterns: Sequence[tuple[Platform, re.Pattern[str]]] = DEFAULT_PATTERNS) -> None:
        self._patterns = tuple(patterns)

    def find(self, page: str) -> BoardRef | None:
        """The first board reference by position in the page."""
        unescaped = page.replace("\\/", "/")
        best: tuple[int, BoardRef] | None = None
        for platform, pattern in self._patterns:
            for match in pattern.finditer(unescaped):
                slug = self._slug(platform, match)
                if slug is None:
                    continue
                if best is None or match.start() < best[0]:
                    best = (match.start(), BoardRef(platform=platform, slug=slug))
                break  # later matches of the same pattern start further in
        return None if best is None else best[1]

    @staticmethod
    def _slug(platform: Platform, match: re.Match[str]) -> str | None:
        """Board key from the match groups, or None for reserved words like "embed"."""
        groups = [group.rstrip(".") for group in match.groups()]
        if not groups[0] or groups[0].lower() in RESERVED_SLUGS:
            return None
        slug = "/".join(groups)
        return slug.lower() if platform in CASE_INSENSITIVE_PLATFORMS else slug
