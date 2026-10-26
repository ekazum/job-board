"""Domain and URL normalization shared by config parsing, the API and discovery."""

import re
from urllib.parse import urlsplit

# Second-level labels of two-part public suffixes: acme.co.il -> "acme", not "co".
SECOND_LEVEL_LABELS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


def registrable_domain(host: str) -> str:
    """"careers.acme.io" -> "acme.io", "jobs.acme.co.il" -> "acme.co.il", "www.acme.com" -> "acme.com"."""
    labels = host.lower().removeprefix("www.").split(".")
    if len(labels) >= 3 and labels[-2] in SECOND_LEVEL_LABELS and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def domain_stem(domain: str) -> str:
    """"acme.com" -> "acme", "acme.co.il" -> "acme", "careers.acme.io" -> "acme"."""
    return registrable_domain(domain).split(".")[0]


def same_company(company: str, other: str) -> bool:
    """Names match when one contains the other, ignoring case, spaces and punctuation:
    "Via" ~ "Via Transportation", "Melio" ~ "Melio Payments"; "Orca Security" !~ "ORCA Service Technologies"."""
    mine, theirs = (re.sub(r"[^a-z0-9]", "", name.lower()) for name in (company, other))
    return bool(mine) and bool(theirs) and (mine in theirs or theirs in mine)


def bare_domain(value: str) -> str:
    """"https://www.Acme.com/about" -> "acme.com"; ValueError for anything that is not a dotted host name."""
    text = value.strip()
    host = urlsplit(text if "//" in text else f"//{text}").hostname or ""
    if "." not in host:
        raise ValueError(f"not a domain: {value!r}")
    return host.removeprefix("www.")


def bare_domain_or_none(value: str | None) -> str | None:
    """bare_domain for an optional field: None and blank stay None."""
    if value is None or not value.strip():
        return None
    return bare_domain(value)


def web_url_or_none(value: str | None) -> str | None:
    """A stripped http(s) URL; None and blank stay None; ValueError for any other scheme."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) URL: {value!r}")
    return text
