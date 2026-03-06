import csv
import io

from app.schemas import LaneInput, SkuGroupInput, SupplierInput, SupplyMapCsvImportRequest, SupplyMapUpsertRequest


def _float_value(value: str | None, default: float) -> float:
    try:
        return float((value or "").strip())
    except ValueError:
        return default


def _normalize(value: str | None) -> str:
    return (value or "").strip()


def _parse_suppliers(csv_text: str) -> list[SupplierInput]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    suppliers: list[SupplierInput] = []
    for row in rows:
        if not _normalize(row.get("name")):
            continue
        suppliers.append(
            SupplierInput(
                name=_normalize(row.get("name")),
                country=_normalize(row.get("country")) or "Unknown",
                region=_normalize(row.get("region")) or "Unknown",
                commodity=_normalize(row.get("commodity")) or "other",
                criticality=_float_value(row.get("criticality"), 0.5),
                substitution_score=_float_value(row.get("substitution_score"), 0.5),
                lead_time_sensitivity=_float_value(row.get("lead_time_sensitivity"), 0.5),
                inventory_buffer_days=_float_value(row.get("inventory_buffer_days"), 14.0),
            )
        )
    return suppliers


def _parse_lanes(csv_text: str) -> list[LaneInput]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    lanes: list[LaneInput] = []
    for row in rows:
        if not _normalize(row.get("origin")) or not _normalize(row.get("destination")):
            continue
        mode = _normalize(row.get("mode")).lower() or "sea"
        if mode not in {"sea", "air", "road", "rail"}:
            mode = "sea"
        lanes.append(
            LaneInput(
                origin=_normalize(row.get("origin")),
                destination=_normalize(row.get("destination")),
                mode=mode,
                chokepoint=_normalize(row.get("chokepoint")) or None,
                importance=_float_value(row.get("importance"), 0.5),
            )
        )
    return lanes


def _parse_sku_groups(csv_text: str) -> list[SkuGroupInput]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    sku_groups: list[SkuGroupInput] = []
    for row in rows:
        if not _normalize(row.get("name")):
            continue
        sku_groups.append(
            SkuGroupInput(
                name=_normalize(row.get("name")),
                category=_normalize(row.get("category")) or "other",
                monthly_volume=_float_value(row.get("monthly_volume"), 0.0),
                margin_sensitivity=_float_value(row.get("margin_sensitivity"), 0.5),
            )
        )
    return sku_groups


def build_supply_map_request_from_csv(payload: SupplyMapCsvImportRequest) -> SupplyMapUpsertRequest:
    return SupplyMapUpsertRequest(
        suppliers=_parse_suppliers(payload.suppliers_csv),
        lanes=_parse_lanes(payload.lanes_csv),
        sku_groups=_parse_sku_groups(payload.sku_groups_csv),
    )
