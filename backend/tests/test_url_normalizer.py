"""UrlNormalizer: one canonical URL per job."""

import pytest

from job_board.utils.url_normalizer import UrlNormalizer


@pytest.fixture
def normalizer() -> UrlNormalizer:
    return UrlNormalizer()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://acme.com/careers/123", "https://acme.com/careers/123"),
        ("  HTTPS://WWW.Acme.com/careers/123/  ", "https://acme.com/careers/123"),
        ("HTTP://acme.com/careers/123", "https://acme.com/careers/123"),  # plain http upgraded, scheme lower-cased
        ("https://acme.com/careers/123?utm_source=x&utm_medium=y", "https://acme.com/careers/123"),
        ("https://acme.com/careers/123#apply", "https://acme.com/careers/123"),
        ("https://acme.com/jobs?b=2&a=1&gclid=z", "https://acme.com/jobs?a=1&b=2"),
        ("https://job-boards.greenhouse.io/acme/jobs/42?gh_src=abc", "https://job-boards.greenhouse.io/acme/jobs/42"),
        ("https://acme.com/careers?gh_jid=42&gh_src=abc", "https://acme.com/careers?gh_jid=42"),
        ("https://acme.com:8443/jobs/1", "https://acme.com:8443/jobs/1"),
    ],
)
def test_generic_urls(normalizer: UrlNormalizer, raw: str, expected: str) -> None:
    assert normalizer.normalize(raw) == expected


def test_hash_route_fragment_is_kept_because_it_identifies_the_job(normalizer: UrlNormalizer) -> None:
    assert normalizer.normalize("https://careers.acme.com/#/jobs/77") == "https://careers.acme.com#/jobs/77"
    assert normalizer.normalize("https://careers.acme.com/#/jobs/77") != normalizer.normalize(
        "https://careers.acme.com/#/jobs/78"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.linkedin.com/jobs/view/4012345678/",
        "https://www.linkedin.com/jobs/view/4012345678/?refId=abc&trackingId=def",
        "https://il.linkedin.com/jobs/view/backend-engineer-at-acme-4012345678",
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678",
        "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=python",
    ],
)
def test_linkedin_variants_collapse_to_view_url(normalizer: UrlNormalizer, raw: str) -> None:
    assert normalizer.normalize(raw) == "https://linkedin.com/jobs/view/4012345678"


def test_linkedin_without_job_id_falls_back_to_generic(normalizer: UrlNormalizer) -> None:
    assert normalizer.normalize("https://www.linkedin.com/company/acme/") == "https://linkedin.com/company/acme"


@pytest.mark.parametrize("raw", ["", "acme.com/jobs/1", "ftp://acme.com/jobs", "javascript:alert(1)", "https://"])
def test_non_http_urls_rejected(normalizer: UrlNormalizer, raw: str) -> None:
    with pytest.raises(ValueError):
        normalizer.normalize(raw)


def test_custom_tracking_params(normalizer: UrlNormalizer) -> None:
    custom = UrlNormalizer(tracking_params=frozenset({"Source"}))
    assert custom.normalize("https://acme.com/jobs/1?source=x") == "https://acme.com/jobs/1"
    assert normalizer.normalize("https://acme.com/jobs/1?source=x") == "https://acme.com/jobs/1?source=x"
