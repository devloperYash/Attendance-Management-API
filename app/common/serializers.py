from datetime import datetime
from typing import Any
from app.common.time_utils import dt_to_epoch_ms


def serialize_employee(doc: dict[str, Any]) -> dict[str, Any]:
    """Serializes a raw MongoDB employee document into an API response dict."""
    res = dict(doc)
    res.pop("_id", None)
    if isinstance(res.get("created_at"), datetime):
        res["created_at"] = dt_to_epoch_ms(res["created_at"])
    return res


def serialize_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Serializes a single audit history entry."""
    e = dict(entry)
    if isinstance(e.get("at"), datetime):
        e["at"] = dt_to_epoch_ms(e["at"])

    changes = {}
    for field, change in e.get("changes", {}).items():
        if isinstance(change, dict):
            c = dict(change)
            if isinstance(c.get("from"), datetime):
                c["from"] = dt_to_epoch_ms(c["from"])
            if isinstance(c.get("to"), datetime):
                c["to"] = dt_to_epoch_ms(c["to"])
            changes[field] = c
        else:
            changes[field] = change
    e["changes"] = changes
    return e


def serialize_attendance_record(doc: dict[str, Any]) -> dict[str, Any]:
    """Serializes a raw MongoDB attendance_logs document into an API response dict."""
    res = dict(doc)
    res.pop("_id", None)
    res.pop("id", None)  # Ensure internal id is never exposed per openapi spec

    if isinstance(res.get("punch_in"), datetime):
        res["punch_in"] = dt_to_epoch_ms(res["punch_in"])
    if isinstance(res.get("punch_out"), datetime):
        res["punch_out"] = dt_to_epoch_ms(res["punch_out"])

    # Ensure required default fields exist for older/legacy records
    if "late_minutes" not in res or res["late_minutes"] is None:
        res["late_minutes"] = 0
    if "overtime_minutes" not in res or res["overtime_minutes"] is None:
        res["overtime_minutes"] = 0
    if "half_day" not in res or res["half_day"] is None:
        res["half_day"] = False
    if "history" not in res or res["history"] is None:
        res["history"] = []
    else:
        res["history"] = [serialize_history_entry(h) for h in res["history"]]

    return res
