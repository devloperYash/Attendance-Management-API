from datetime import date, datetime, time, timedelta, timezone
from fastapi import HTTPException
from app.config import IST, MIN_EPOCH_MS, MAX_EPOCH_MS


def validate_epoch_ms(val: int | None) -> int:
    """Validates that epoch ms is an integer within the acceptable range."""
    if val is None:
        raise HTTPException(status_code=422, detail="Timestamp is required")
    if isinstance(val, bool) or not isinstance(val, int):
        raise HTTPException(status_code=422, detail="Timestamp must be an integer (epoch milliseconds)")
    if val < MIN_EPOCH_MS or val > MAX_EPOCH_MS:
        raise HTTPException(
            status_code=422,
            detail=f"Timestamp must be between {MIN_EPOCH_MS} and {MAX_EPOCH_MS} (epoch ms)"
        )
    return truncate_to_seconds(val)


def truncate_to_seconds(ms: int) -> int:
    """Truncates epoch ms to whole seconds (Rule R1)."""
    return (ms // 1000) * 1000


def ms_to_utc_datetime(ms: int) -> datetime:
    """Converts epoch ms to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def dt_to_epoch_ms(dt: datetime | None) -> int | None:
    """Converts a datetime (UTC or naive) to epoch ms."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return truncate_to_seconds(int(dt.timestamp() * 1000))


def now_epoch_ms() -> int:
    """Returns current UTC time in truncated epoch ms."""
    return truncate_to_seconds(int(datetime.now(timezone.utc).timestamp() * 1000))


def determine_attendance_date(dt_utc: datetime, shift_start_str: str, shift_end_str: str) -> str:
    """
    Rule R1: A record's date is the IST calendar date of its punch_in instant.
    Overnight exception: if shift_end <= shift_start and punch_in IST time is earlier than shift_end,
    the record belongs to the shift that started the previous calendar day.
    """
    dt_ist = dt_utc.astimezone(IST)
    start_h, start_m = map(int, shift_start_str.split(":"))
    end_h, end_m = map(int, shift_end_str.split(":"))

    is_overnight = (end_h, end_m) <= (start_h, start_m)
    current_time = (dt_ist.hour, dt_ist.minute, dt_ist.second)
    shift_end_time = (end_h, end_m, 0)

    if is_overnight and current_time < shift_end_time:
        return (dt_ist.date() - timedelta(days=1)).isoformat()
    return dt_ist.date().isoformat()


def compute_late_minutes(dt_utc_in: datetime, attendance_date_str: str, shift_start_str: str) -> int:
    """
    Rule R2: Grace period is 10 minutes.
    A punch-in is late only if strictly more than 10:00 (600 seconds) after shift_start.
    When late, late_minutes = floor(seconds elapsed since shift_start / 60).
    """
    dt_ist_in = dt_utc_in.astimezone(IST)
    sh_h, sh_m = map(int, shift_start_str.split(":"))
    att_date = date.fromisoformat(attendance_date_str)
    shift_start_dt = datetime.combine(att_date, time(sh_h, sh_m), tzinfo=IST)

    diff_seconds = (dt_ist_in - shift_start_dt).total_seconds()
    if diff_seconds > 600:  # strictly more than 10:00
        return int(diff_seconds // 60)
    return 0


def compute_overtime_minutes(
    dt_utc_out: datetime,
    attendance_date_str: str,
    shift_start_str: str,
    shift_end_str: str
) -> int:
    """
    Rule R3: overtime_minutes = whole minutes (floor) between shift_end and punch_out,
    counted only when >= 30; otherwise 0.
    For overnight shifts, shift_end falls on the next calendar day.
    """
    dt_ist_out = dt_utc_out.astimezone(IST)
    start_h, start_m = map(int, shift_start_str.split(":"))
    end_h, end_m = map(int, shift_end_str.split(":"))
    att_date = date.fromisoformat(attendance_date_str)

    is_overnight = (end_h, end_m) <= (start_h, start_m)
    shift_end_date = att_date + timedelta(days=1) if is_overnight else att_date
    shift_end_dt = datetime.combine(shift_end_date, time(end_h, end_m), tzinfo=IST)

    diff_seconds = (dt_ist_out - shift_end_dt).total_seconds()
    minutes = int(diff_seconds // 60)
    return minutes if minutes >= 30 else 0
