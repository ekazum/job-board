"""Value object for one HTTP request."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpResponse:
    """Outcome of a request. status is 0 and error is set when no response arrived (DNS, TLS, timeout...);
    timed_out marks the timeout case, which is retried.

    url is the final URL after redirects, which matters: a /careers page often redirects straight to the board.
    """

    url: str
    status: int
    text: str
    error: str | None = None
    timed_out: bool = False
