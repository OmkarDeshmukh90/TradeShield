import json
from pathlib import Path

from app.connectors.base import ConnectorEvent
from app.utils import parse_datetime

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "demo" / "fixtures"


def _load_fixture(name: str) -> list[dict]:
    path = FIXTURE_DIR / name
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("events", [])


def load_demo_events(scenario: str) -> list[ConnectorEvent]:
    names: list[str]
    if scenario == "tariff":
        names = ["tariff_spike_india_imports.json"]
    elif scenario == "congestion":
        names = ["port_congestion_malacca.json"]
    else:
        names = ["tariff_spike_india_imports.json", "port_congestion_malacca.json"]

    events: list[ConnectorEvent] = []
    for name in names:
        for row in _load_fixture(name):
            events.append(
                ConnectorEvent(
                    source=row["source"],
                    source_event_id=row["source_event_id"],
                    title=row["title"],
                    description=row["description"],
                    occurred_at=parse_datetime(row["occurred_at"]),
                    event_type=row.get("event_type", "other"),
                    geos=row.get("geos", []),
                    entities=row.get("entities", []),
                    severity=float(row.get("severity", 0.5)),
                    confidence=float(row.get("confidence", 0.7)),
                    evidence=row.get("evidence", []),
                    industry_tags=row.get("industry_tags", []),
                    raw_payload=row,
                )
            )
    return events
