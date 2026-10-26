"""Canonical form of a job URL, used as external_id for pasted postings."""

import re
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
        "gh_src", "lever-source", "lever-origin",
        "trk", "trackingid", "refid", "lipi", "ebp",
    }
)
TRACKING_PREFIX = "utm_"
LINKEDIN_HOST = "linkedin.com"
LINKEDIN_VIEW_PATH = re.compile(r"/jobs/view/(?:[^/]*?-)?(\d+)/?$")
LINKEDIN_JOB_ID_PARAM = "currentjobid"


class UrlNormalizer:
    """Reduces the many spellings of one job link to a single canonical URL.

    Lower-cases scheme and host, drops "www.", tracking parameters and the trailing slash, sorts the
    remaining query parameters, and keeps a fragment only when it looks like a client-side route
    ("#/..." or "#!..."). LinkedIn links are rewritten to https://linkedin.com/jobs/view/{id}.
    """

    def __init__(self, tracking_params: frozenset[str] = DEFAULT_TRACKING_PARAMS) -> None:
        self._tracking_params = frozenset(param.lower() for param in tracking_params)

    def normalize(self, url: str) -> str:
        """Return the canonical form of an http(s) URL; raises ValueError for anything else."""
        parts: SplitResult = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").removeprefix("www.")
        if scheme not in ("http", "https") or not host:
            raise ValueError(f"not an http(s) URL: {url!r}")
        query: list[tuple[str, str]] = parse_qsl(parts.query, keep_blank_values=True)
        if host == LINKEDIN_HOST or host.endswith("." + LINKEDIN_HOST):
            job_id = self._linkedin_job_id(parts.path, query)
            if job_id is not None:
                return f"https://{LINKEDIN_HOST}/jobs/view/{job_id}"
        netloc = host if parts.port is None else f"{host}:{parts.port}"
        kept = sorted((key, value) for key, value in query if not self._is_tracking(key))
        fragment: str = parts.fragment if parts.fragment.startswith(("/", "!")) else ""
        path = str(parts.path).rstrip("/")  # str(): PyCharm resolves SplitResult's generic fields to str | bytes
        return urlunsplit(("https", netloc, path, urlencode(kept), fragment))

    def _is_tracking(self, key: str) -> bool:
        """True for analytics parameters that never identify a job."""
        lowered = key.lower()
        return lowered.startswith(TRACKING_PREFIX) or lowered in self._tracking_params

    @staticmethod
    def _linkedin_job_id(path: str, query: list[tuple[str, str]]) -> str | None:
        """Job id from /jobs/view/{id} (optionally slug-prefixed) or from the currentJobId parameter."""
        match = LINKEDIN_VIEW_PATH.search(path)
        if match is not None:
            return match.group(1)
        for key, value in query:
            if key.lower() == LINKEDIN_JOB_ID_PARAM and value.isdigit():
                return value
        return None
