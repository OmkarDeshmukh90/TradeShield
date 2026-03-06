from datetime import datetime, timezone

import httpx

from app.connectors.base import BaseConnector, ConnectorEvent
from app.utils import clamp


class OpenSkyConnector(BaseConnector):
    name = "opensky"
    endpoint = "https://opensky-network.org/api/states/all"

    def fetch(self) -> list[ConnectorEvent]:
        response = httpx.get(self.endpoint, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
        total_states = len(payload.get("states") or [])
        generated_at = payload.get("time")
        baseline = 18000
        deviation = abs(total_states - baseline) / baseline
        severity = clamp(0.2 + deviation * 0.7, 0.2, 0.8)
        source_id = f"opensky-{int(generated_at or 0) // 3600}"

        event = ConnectorEvent(
            source="OpenSky",
            source_event_id=source_id,
            title=f"Global air-traffic state sample captured ({total_states} aircraft states)",
            description="OpenSky network signal used as contextual indicator for air lane stress.",
            occurred_at=(
                datetime.fromtimestamp(generated_at, tz=timezone.utc) if isinstance(generated_at, (int, float)) else datetime.now(timezone.utc)
            ),
            event_type="logistics congestion",
            geos=["Global"],
            entities=["air freight", "aviation"],
            severity=severity,
            confidence=0.5,
            evidence=[{"title": "OpenSky API", "url": self.endpoint, "source": "OpenSky"}],
            raw_payload={"time": generated_at, "count": total_states},
        )
        return [event]
