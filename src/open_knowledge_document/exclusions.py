"""Persistent import exclusions migrated from the original search service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import json
from pathlib import Path
import re
from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator


EXCLUSION_FIELDS = ["doc_id", "document_id", "node_token", "title", "path", "source_url", "space_id", "source_type"]


class ExclusionConfig(BaseModel):
    enabled: bool = True
    patterns: list[str] = Field(default_factory=list)
    updated_at: str = ""

    @field_validator("patterns", mode="before")
    @classmethod
    def normalize(cls, value: object) -> list[str]:
        items = value if isinstance(value, list) else []
        result: list[str] = []
        for item in items:
            cleaned = str(item or "").strip()
            if cleaned and cleaned.casefold() not in {entry.casefold() for entry in result}:
                result.append(cleaned)
        return result


@dataclass(frozen=True)
class ExclusionMatch:
    pattern: str
    field: str
    value: str


class ExclusionMatcher:
    def __init__(self, config: ExclusionConfig) -> None:
        self.patterns = config.patterns if config.enabled else []

    def match(self, fields: Mapping[str, Any]) -> ExclusionMatch | None:
        for pattern in self.patterns:
            for field, raw in fields.items():
                value = " / ".join(map(str, raw)) if isinstance(raw, list) else str(raw or "")
                if pattern_matches(pattern, value):
                    return ExclusionMatch(pattern, field, value)
        return None


def pattern_matches(pattern: str, value: str) -> bool:
    pattern, value = pattern.strip(), value.strip()
    if not pattern or not value:
        return False
    if pattern.startswith("re:"):
        try:
            return re.search(pattern[3:], value, flags=re.IGNORECASE) is not None
        except re.error:
            return False
    pattern, value = pattern.casefold(), value.casefold()
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatchcase(value, pattern)
    return pattern in value


class ExclusionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> ExclusionConfig:
        if not self.path.exists():
            return ExclusionConfig()
        try:
            return ExclusionConfig.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ExclusionConfig()

    def save(self, config: ExclusionConfig) -> ExclusionConfig:
        config.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return config

    def public(self) -> dict[str, Any]:
        return {**self.load().model_dump(), "fields": EXCLUSION_FIELDS, "path": str(self.path)}
