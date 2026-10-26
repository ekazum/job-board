"""Recognize companies that run their own careers site instead of an applicant-tracking system."""

from urllib.parse import urlsplit

from job_board.boards.board_ref import BoardRef
from job_board.config.company_seed import CompanySeed
from job_board.enums.platform import Platform

# Company domains and careers-site hosts; a host matches itself and its subdomains.
SITE_HOSTS: dict[str, Platform] = {
    "google.com": Platform.GOOGLE,
    "careers.google.com": Platform.GOOGLE,
    "microsoft.com": Platform.MICROSOFT,
    "apple.com": Platform.APPLE,
    "amazon.com": Platform.AMAZON,
    "amazon.jobs": Platform.AMAZON,
    "meta.com": Platform.META,
    "metacareers.com": Platform.META,
    "facebook.com": Platform.META,
}


class CareersSiteFinder:
    """Google, Microsoft, Apple, Amazon and Meta each have one careers site with its own search API, so the board is
    known from the company's domain or careers URL alone (slug = the platform name, e.g. "google")."""

    @staticmethod
    def find(seed: CompanySeed) -> BoardRef | None:
        """The company's own careers site, or None for everyone else."""
        hosts = [seed.domain.lower()] if seed.domain else []
        if seed.careers_url:
            hosts.append((urlsplit(seed.careers_url).hostname or "").lower())
        for host in hosts:
            for site_host, platform in SITE_HOSTS.items():
                if host == site_host or host.endswith(f".{site_host}"):
                    return BoardRef(platform, platform.value)
        return None
