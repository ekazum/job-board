"""ConfigEditor: switching llm.provider keeps every other line, comments included."""

from pathlib import Path

import pytest

from job_board.config_editor import ConfigEditor

CONFIG = """# top comment
db_path: data/job_board.db

llm:
  provider: ollama          # ollama | groq | github | anthropic | openai
  model: qwen2.5:7b

providers:
  ollama: {base_url: http://localhost:11434/v1, api_key_env: NONE}
  groq: {base_url: https://api.groq.com/openai/v1, api_key_env: GROQ_API_KEY}
other:
  provider: untouched
"""


def test_only_the_llm_provider_value_changes(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    ConfigEditor(path).set_llm_provider("groq")
    expected = CONFIG.replace("  provider: ollama          #", "  provider: groq          #")
    assert path.read_text(encoding="utf-8") == expected


def test_file_without_llm_provider_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("db_path: x.db\nother:\n  provider: ollama\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'provider:' line under 'llm:'"):
        ConfigEditor(path).set_llm_provider("groq")
    assert path.read_text(encoding="utf-8") == "db_path: x.db\nother:\n  provider: ollama\n"
