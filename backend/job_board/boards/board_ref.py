"""Value object naming one board."""

from dataclasses import dataclass

from job_board.enums.platform import Platform


@dataclass(frozen=True)
class BoardRef:
    """A board on a platform. slug is the board key: "acme" for Greenhouse/Lever/Ashby,
    "acme/98.008" (company slug / company uid) or "acme" (acme.comeet.co) for Comeet."""

    platform: Platform
    slug: str
