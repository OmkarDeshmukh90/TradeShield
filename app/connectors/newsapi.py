from datetime import datetime, timezone

import httpx

from app.config import settings
from app.connectors.base import BaseConnector, ConnectorEvent
from app.utils import parse_datetime


class NewsAPIConnector(BaseConnector):
    name = "newsapi"
    endpoint = "https://newsapi.org/v2/everything"

    def fetch(self) -> list[ConnectorEvent]:
        if not settings.news_api_key:
            return []

        params = {
            "q": "supply chain disruption OR tariff OR shipping blockade OR port congestion",
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 25,
            "apiKey": settings.news_api_key,
        }
        response = httpx.get(self.endpoint, params=params, timeout=20.0)
        response.raise_for_status()
        payload = response.json()

        events: list[ConnectorEvent] = []
        for article in payload.get("articles", []):
            title = article.get("title") or "News signal"
            source_name = (article.get("source") or {}).get("name") or "News API"
            published_at = article.get("publishedAt")
            events.append(
                ConnectorEvent(
                    source="NewsAPI",
                    source_event_id=article.get("url", title)[:180],
                    title=title[:220],
                    description=article.get("description") or "",
                    occurred_at=parse_datetime(published_at) if published_at else datetime.now(timezone.utc),
                    event_type="other",
                    geos=[],
                    entities=[source_name],
                    severity=0.5,
                    confidence=0.6,
                    evidence=[{"title": title[:100], "url": article.get("url", ""), "source": source_name}],
                    raw_payload=article,
                )
            )
        return events

