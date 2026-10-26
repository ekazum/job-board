"""Targeted edits to config.yaml that keep its comments and layout."""

import re
from pathlib import Path

LLM_SECTION = re.compile(r"^llm:\s*(#.*)?$")
TOP_LEVEL_KEY = re.compile(r"^\S")
PROVIDER_LINE = re.compile(r"^(\s+provider:\s*)([^\s#]+)(.*)$")


class ConfigEditor:
    """Rewrites single values in config.yaml in place; YAML re-serialization would drop every comment."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def set_llm_provider(self, provider: str) -> None:
        """Replace the value of llm.provider; ValueError when the file has no such line."""
        lines = self._path.read_text(encoding="utf-8").splitlines(keepends=True)
        in_llm = False
        for index, line in enumerate(lines):
            if LLM_SECTION.match(line):
                in_llm = True
                continue
            if in_llm and TOP_LEVEL_KEY.match(line):
                break
            match = PROVIDER_LINE.match(line) if in_llm else None
            if match is not None:
                newline = "\n" if line.endswith("\n") else ""
                lines[index] = f"{match.group(1)}{provider}{match.group(3).rstrip()}{newline}"
                self._path.write_text("".join(lines), encoding="utf-8")
                return
        raise ValueError(f"{self._path} has no 'provider:' line under 'llm:'")
