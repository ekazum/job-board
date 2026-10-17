"""AppConfig loading."""

from pathlib import Path

import pytest

from job_board.app_config import AppConfig
from job_board.company_seed import CompanySeed


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_relative_db_path_resolved_against_config_folder(tmp_path: Path) -> None:
    config = AppConfig.from_yaml(_write(tmp_path, "db_path: data/x.db\n"))
    assert config.db_path == (tmp_path / "data" / "x.db").resolve()


def test_missing_keys_use_defaults(tmp_path: Path) -> None:
    config = AppConfig.from_yaml(_write(tmp_path, ""))
    assert config.db_path == (tmp_path / "data" / "job_board.db").resolve()
    assert (config.include_keywords, config.exclude_keywords, config.companies) == ((), (), ())


def test_keyword_lists_are_read_and_blank_entries_dropped(tmp_path: Path) -> None:
    content = "keywords:\n  include: [python, ' backend ', '']\n  exclude: [intern]\n"
    config = AppConfig.from_yaml(_write(tmp_path, content))
    assert config.include_keywords == ("python", "backend")
    assert config.exclude_keywords == ("intern",)


def test_companies_are_read_with_bare_domains(tmp_path: Path) -> None:
    content = (
        "companies:\n"
        "  - {name: ' Acme ', domain: acme.com}\n"
        "  - {name: Globex, domain: 'https://www.Globex.co.il/about', careers_url: 'https://globex.co.il/jobs'}\n"
    )
    assert AppConfig.from_yaml(_write(tmp_path, content)).companies == (
        CompanySeed(name="Acme", domain="acme.com"),
        CompanySeed(name="Globex", domain="globex.co.il", careers_url="https://globex.co.il/jobs"),
    )


@pytest.mark.parametrize(
    ("companies", "message"),
    [
        ("[Acme]", r"companies\[0\]' must be a mapping"),
        ("[{domain: acme.com}]", r"companies\[0\].name"),
        ("[{name: Acme}]", r"companies\[0\].domain"),
        ("[{name: Acme, domain: localhost}]", "not a domain"),
        ("[{name: Acme, domain: acme.com, careers_url: 5}]", "careers_url"),
        ("acme.com", "must be a list"),
    ],
)
def test_invalid_companies_rejected(tmp_path: Path, companies: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AppConfig.from_yaml(_write(tmp_path, f"companies: {companies}\n"))


def test_non_list_keywords_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="keywords.include"):
        AppConfig.from_yaml(_write(tmp_path, "keywords:\n  include: python\n"))


def test_repo_config_loads() -> None:
    repo_config = Path(__file__).resolve().parents[2] / "config.yaml"
    assert AppConfig.from_yaml(repo_config).db_path.name == "job_board.db"
