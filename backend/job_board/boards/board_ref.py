"""Value object naming one board."""

from dataclasses import dataclass

from job_board.enums.platform import Platform


@dataclass(frozen=True)
class BoardRef:
    """A board on a platform.

    slug is the board key shown in the UI: "acme" for Greenhouse/Lever/Ashby, "Acme/98.008" or "acme" for a
    Comeet hosted page, "tenant/site" for Workday. Comeet boards found through the careers widget also carry
    company_uid and token (read through the careers API); Workday boards carry tenant, wd_host ("wd5") and site.
    An Eightfold board's slug is the careers site's host ("jobs.amdocs.com") and its tenant the domain its API asks for
    ("amdocs.com"). A HiBob board's slug is its careers site's subdomain ("hibob-fa0ad69d0cb34a").
    """

    platform: Platform
    slug: str
    company_uid: str | None = None
    token: str | None = None
    tenant: str | None = None
    wd_host: str | None = None
    site: str | None = None
