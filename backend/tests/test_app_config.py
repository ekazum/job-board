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


def test_locations_default_to_every_location(tmp_path: Path) -> None:
    assert AppConfig.from_yaml(_write(tmp_path, "")).locations == ()
    assert AppConfig.from_yaml(_write(tmp_path, "locations: [Israel, ' Cyprus ']\n")).locations == ("Israel", "Cyprus")


def test_careers_url_must_be_http(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"companies\[0\].careers_url"):
        AppConfig.from_yaml(_write(tmp_path, "companies:\n  - {name: Acme, domain: acme.com, careers_url: 'acme.com/jobs'}\n"))


def test_llm_defaults_when_sections_are_absent(tmp_path: Path) -> None:
    llm = AppConfig.from_yaml(_write(tmp_path, "")).llm
    assert (llm.provider, llm.model, llm.threshold, llm.max_text_chars) == ("ollama", "qwen2.5:7b", 6, 3000)
    assert [provider.name for provider in llm.providers] == ["ollama", "groq", "github", "anthropic", "openai"]


def test_llm_and_providers_are_read(tmp_path: Path) -> None:
    content = (
        "llm: {provider: groq, model: m, threshold: 7, max_text_chars: 100, request_timeout_s: 30, max_retries: 0}\n"
        "providers:\n"
        "  groq: {base_url: 'https://api.groq.com/openai/v1', api_key_env: GROQ_API_KEY, concurrency: 5, model: g}\n"
    )
    llm = AppConfig.from_yaml(_write(tmp_path, content)).llm
    assert (llm.provider, llm.model, llm.threshold, llm.request_timeout_s, llm.max_retries) == ("groq", "m", 7, 30.0, 0)
    groq = llm.providers[0]
    assert (groq.base_url, groq.api_key_env, groq.concurrency, groq.json_mode, groq.model) == (
        "https://api.groq.com/openai/v1", "GROQ_API_KEY", 5, False, "g"
    )


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("llm: {provider: nope}\n", "not listed under providers"),
        ("llm: {threshold: high}\n", "llm.threshold"),
        ("providers: {x: {api_key_env: NONE}}\nllm: {provider: x}\n", r"providers.x.base_url"),
        ("providers: {x: {base_url: u, api_key_env: NONE, json_mode: yes please}}\nllm: {provider: x}\n", "json_mode"),
    ],
)
def test_invalid_llm_settings_rejected(tmp_path: Path, content: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AppConfig.from_yaml(_write(tmp_path, content))


def test_repo_config_llm_section_loads() -> None:
    llm = AppConfig.from_yaml(Path(__file__).resolve().parents[2] / "config.yaml").llm
    ollama = next(provider for provider in llm.providers if provider.name == "ollama")
    assert (ollama.api_key_env, ollama.concurrency, ollama.json_mode) == ("NONE", 1, True)
