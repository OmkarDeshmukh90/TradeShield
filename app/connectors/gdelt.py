from datetime import datetime, timezone

import httpx

from app.connectors.base import BaseConnector, ConnectorEvent
from app.utils import clamp, parse_datetime


def _classify_event_type(text: str) -> str:
    t = text.lower()
    if any(word in t for word in ["tariff", "duty", "policy", "trade notice"]):
        return "tariff/policy"
    if any(word in t for word in ["sanction", "restricted party", "embargo"]):
        return "sanctions/compliance"
    if any(word in t for word in ["war", "conflict", "missile", "piracy", "attack"]):
        return "conflict/security"
    if any(word in t for word in ["congestion", "delay", "port", "shipping", "vessel"]):
        return "logistics congestion"
    if any(word in t for word in ["explosion", "fire", "plant outage", "shutdown"]):
        return "operational incidents"
    if any(word in t for word in ["flood", "earthquake", "storm", "cyclone"]):
        return "disaster/weather"
    return "other"


def _severity(text: str) -> float:
    t = text.lower()
    severe_hits = sum(word in t for word in ["blockade", "war", "sanction", "shutdown", "major", "critical"])
    medium_hits = sum(word in t for word in ["delay", "tariff", "strike", "disruption", "congestion"])
    return clamp(0.25 + severe_hits * 0.15 + medium_hits * 0.08, 0.2, 0.95)


class GDELTConnector(BaseConnector):
    name = "gdelt"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def fetch(self) -> list[ConnectorEvent]:
        params = {
            "query": "(tariff OR sanctions OR blockade OR port congestion OR conflict) AND (supply chain OR logistics OR trade)",
            "mode": "artlist",
            "maxrecords": 25,
            "format": "json",
            "sort": "DateDesc",
        }
        response = httpx.get(self.endpoint, params=params, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
        articles = payload.get("articles", [])

        events: list[ConnectorEvent] = []
        for article in articles:
            title = article.get("title", "")
            description = article.get("seendate", "")
            text_blob = f"{title} {description}"
            event_type = _classify_event_type(text_blob)
            published = article.get("seendate")
            occurred_at = parse_datetime(published) if published else datetime.now(timezone.utc)
            source_url = article.get("url", self.endpoint)
            source_domain = article.get("domain", "news")
            source_id = article.get("url", title)[:180]

            events.append(
                ConnectorEvent(
                    source="GDELT",
                    source_event_id=source_id,
                    title=title[:220] or "GDELT trade disruption signal",
                    description=article.get("socialimage", "") or description,
                    occurred_at=occurred_at,
                    event_type=event_type,
                    geos=[article.get("sourcecountry", "")] if article.get("sourcecountry") else [],
                    entities=[source_domain],
                    severity=_severity(text_blob),
                    confidence=0.7,
                    evidence=[{"title": "GDELT Article", "url": source_url, "source": "GDELT"}],
                    raw_payload=article,
                )
            )
        return events

