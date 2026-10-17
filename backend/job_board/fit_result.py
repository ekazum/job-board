"""Value object for one scoring outcome."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FitResult:
    """fit is 0-10, or None when the posting could not be scored (reason then says why: "no profile",
    "parse error", "llm error: ..."); gaps lists the posting's requirements the candidate does not meet."""

    fit: int | None
    reason: str | None
    gaps: tuple[str, ...] = field(default=())
