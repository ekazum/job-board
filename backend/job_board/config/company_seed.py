"""Value object for one company to discover."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanySeed:
    """A company to discover (from config.yaml, the Companies view or a pasted posting). domain is bare ("acme.com");
    careers_url, when set, is fetched before the standard /careers, /jobs and /join-us paths. A company without a
    domain is discovered from its careers_url alone."""

    name: str
    domain: str | None
    careers_url: str | None = None
