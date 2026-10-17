"""Value object for one HTTP GET."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpResponse:
    """Outcome of a GET. status is 0 and error is set when no response arrived (DNS, timeout, TLS...).

    url is the final URL after redirects, which matters: a /careers page often redirects straight to the board.
    """

    url: str
    status: int
    text: str
    error: str | None = None
