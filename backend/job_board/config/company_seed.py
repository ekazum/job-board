"""Value object for one company listed in config.yaml."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanySeed:
    """A company to discover. domain is bare ("acme.com"); careers_url, when set, is fetched before the
    standard /careers, /jobs and /join-us paths."""

    name: str
    domain: str
    careers_url: str | None = None
