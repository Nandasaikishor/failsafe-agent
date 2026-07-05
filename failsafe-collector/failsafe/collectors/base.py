"""Base collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from failsafe.schema import CollectorConfig


@dataclass
class CollectionResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    urls_discovered: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.records) > 0 or len(self.urls_discovered) > 0


class BaseCollector(ABC):
    @abstractmethod
    def execute(self, config: CollectorConfig, **kwargs) -> CollectionResult:
        ...
