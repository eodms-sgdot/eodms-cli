from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        dt_val = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone.utc)

    return dt_val.astimezone(timezone.utc)


def _format_rapi_datetime(dt_val: datetime) -> str:
    return dt_val.strftime("%Y%m%d_%H%M%S")


def _build_rapi_dates_from_stac_item(stac_item: Dict[str, Any], span_days: int = 1) -> Optional[List[Dict[str, str]]]:
    props = stac_item.get("properties") if isinstance(stac_item, dict) else None
    if not isinstance(props, dict):
        return None

    start_dt = _parse_iso_datetime(
        props.get("start_datetime")
        or props.get("startDateTime")
        or props.get("acquisition_start")
        or props.get("acquisitionStart")
    )
    end_dt = _parse_iso_datetime(
        props.get("end_datetime")
        or props.get("endDateTime")
        or props.get("acquisition_end")
        or props.get("acquisitionEnd")
    )

    if start_dt is None and end_dt is None:
        center_dt = _parse_iso_datetime(
            props.get("datetime")
            or props.get("acquisition_datetime")
            or props.get("acquisitionDateTime")
        )
        if center_dt is None:
            return None
        start_dt = center_dt
        end_dt = center_dt + timedelta(days=span_days)
    elif start_dt is None and end_dt is not None:
        start_dt = end_dt - timedelta(days=span_days)
    elif end_dt is None and start_dt is not None:
        end_dt = start_dt + timedelta(days=span_days)

    if start_dt is None or end_dt is None:
        return None

    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    return [{"start": _format_rapi_datetime(start_dt), "end": _format_rapi_datetime(end_dt)}]
