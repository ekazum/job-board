"""Application settings loaded from config.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from job_board.company_seed import CompanySeed
from job_board.utils.domains import bare_domain
from job_board.utils.json_values import as_dict, as_list

DEFAULT_DB_PATH = "data/job_board.db"


@dataclass(frozen=True)
class AppConfig:
    """Settings read from config.yaml; relative paths are resolved against the config file's folder."""

    db_path: Path
    include_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    companies: tuple[CompanySeed, ...]

    @classmethod
    def from_yaml(cls, path: Path) -> AppConfig:
        """Construct AppConfig from a YAML file; missing keys fall back to empty lists and the default DB path."""
        with path.open(encoding="utf-8") as handle:
            raw: object = yaml.safe_load(handle)
        data = cls._mapping(raw, str(path))
        keywords = cls._mapping(data.get("keywords"), "keywords")
        db_value = data.get("db_path") or DEFAULT_DB_PATH
        if not isinstance(db_value, str):
            raise ValueError("config 'db_path' must be a string")
        db_path = Path(db_value)
        if not db_path.is_absolute():
            db_path = path.parent / db_path
        return cls(
            db_path=db_path.resolve(),
            include_keywords=cls._strings(keywords.get("include"), "keywords.include"),
            exclude_keywords=cls._strings(keywords.get("exclude"), "keywords.exclude"),
            companies=cls._seeds(data.get("companies")),
        )

    @staticmethod
    def _mapping(value: object, key: str) -> dict[str, object]:
        """Validate an optional YAML mapping and return its string-keyed entries."""
        if value is None:
            return {}
        mapping = as_dict(value)
        if mapping is None:
            raise ValueError(f"config '{key}' must be a mapping")
        return mapping

    @staticmethod
    def _strings(value: object, key: str) -> tuple[str, ...]:
        """Validate an optional YAML list of strings; entries are stripped and blank ones dropped."""
        if value is None:
            return ()
        items = as_list(value)
        if items is None:
            raise ValueError(f"config '{key}' must be a list of strings")
        strings: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise ValueError(f"config '{key}' must be a list of strings")
            if item.strip():
                strings.append(item.strip())
        return tuple(strings)

    @staticmethod
    def _seeds(value: object) -> tuple[CompanySeed, ...]:
        """Validate the companies list: each entry is {name, domain, careers_url?}."""
        if value is None:
            return ()
        entries = as_list(value)
        if entries is None:
            raise ValueError("config 'companies' must be a list of {name, domain} mappings")
        seeds: list[CompanySeed] = []
        for index, entry in enumerate(entries):
            key = f"companies[{index}]"
            item = AppConfig._mapping(entry, key)
            name = AppConfig._required_text(item.get("name"), f"{key}.name")
            domain = AppConfig._bare_domain(AppConfig._required_text(item.get("domain"), f"{key}.domain"), key)
            careers_url = item.get("careers_url")
            if careers_url is not None and not isinstance(careers_url, str):
                raise ValueError(f"config '{key}.careers_url' must be a string")
            seeds.append(CompanySeed(name=name, domain=domain, careers_url=careers_url.strip() if careers_url else None))
        return tuple(seeds)

    @staticmethod
    def _required_text(value: object, key: str) -> str:
        """A non-blank string, stripped."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config '{key}' must be a non-empty string")
        return value.strip()

    @staticmethod
    def _bare_domain(value: str, key: str) -> str:
        """"https://www.Acme.com/about" -> "acme.com", with the config key in the error."""
        try:
            return bare_domain(value)
        except ValueError as error:
            raise ValueError(f"config '{key}.domain' is {error}") from error
