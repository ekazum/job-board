"""Domain and URL normalization shared by config parsing and the API."""

from urllib.parse import urlsplit


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
