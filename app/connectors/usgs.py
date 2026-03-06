from datetime import datetime, timezone

import httpx

from app.connectors.base import BaseConnector, ConnectorEvent
from app.utils import clamp


class USGSConnector(BaseConnector):
    name = "usgs"
    feed_url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

    def fetch(self) -> list[ConnectorEvent]:
        response = httpx.get(self.feed_url, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features", [])

        events: list[ConnectorEvent] = []
        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coordinates = geom.get("coordinates", [None, None])
            magnitude = float(props.get("mag") or 0.0)
            place = props.get("place") or "Unknown location"
            epoch_ms = props.get("time")
            occurred_at = (
                datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc) if epoch_ms else datetime.now(timezone.utc)
            )
            severity = clamp(0.2 + (magnitude / 8.0), 0.2, 1.0)

            events.append(
                ConnectorEvent(
                    source="USGS",
                    source_event_id=str(feature.get("id") or props.get("code") or f"usgs-{epoch_ms}"),
                    title=f"Earthquake detected: M{magnitude:.1f} near {place}",
                    description=props.get("title") or "",
                    occurred_at=occurred_at,
                    event_type="disaster/weather",
                    geos=[place],
                    entities=["earthquake", "natural disaster"],
                    severity=severity,
                    confidence=0.9,
                    evidence=[{"title": "USGS Event", "url": props.get("url", self.feed_url), "source": "USGS"}],
                    industry_tags=[],
                    raw_payload=feature,
                )
            )

        return events

