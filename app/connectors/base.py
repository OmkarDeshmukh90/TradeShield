from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConnectorEvent:
    source: str
    source_event_id: str
    title: str
    description: str
    occurred_at: datetime
    event_type: str
    geos: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    severity: float = 0.4
    confidence: float = 0.6
    evidence: list[dict[str, str]] = field(default_factory=list)
    industry_tags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self) -> list[ConnectorEvent]:
        raise NotImplementedError

