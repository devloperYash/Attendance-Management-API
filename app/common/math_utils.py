from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def round_half_up(val: Decimal | str | float | int, decimals: int = 2) -> Decimal:
    """Exact half-up rounding using Python's Decimal (avoiding banker's rounding)."""
    d = Decimal(str(val)) if not isinstance(val, Decimal) else val
    fmt = "0." + "0" * decimals if decimals > 0 else "0"
    return d.quantize(Decimal(fmt), rounding=ROUND_HALF_UP)


def compute_work_hours(punch_in_ms: int, punch_out_ms: int) -> float:
    """
    Rule R4: (punch_out - punch_in) in seconds / 3600, rounded to 2 decimals half-up.
    """
    total_seconds = Decimal((punch_out_ms - punch_in_ms) // 1000)
    hours = total_seconds / Decimal("3600")
    return float(round_half_up(hours, 2))


def is_half_day(rounded_work_hours: float | None) -> bool:
    """
    Rule R5: After punch-out, half_day = true when the rounded work_hours < 4.50.
    """
    if rounded_work_hours is None:
        return False
    return rounded_work_hours < 4.50


def compute_attendance_pct(present_days: float | int, working_days: int) -> Optional[float]:
    """
    Rule R8: attendance_pct = (present_days / working_days) * 100, 2 decimals half-up.
    Null if working_days == 0.
    """
    if working_days <= 0:
        return None
    pct = (Decimal(str(present_days)) / Decimal(str(working_days))) * Decimal("100")
    return float(round_half_up(pct, 2))


def compute_attendance_rate(present_count: float | int, headcount: int) -> Optional[float]:
    """
    Rule R8: attendance_rate = present_count / headcount, 4 decimals half-up.
    Only on working days with headcount > 0, otherwise None.
    """
    if headcount <= 0:
        return None
    rate = Decimal(str(present_count)) / Decimal(str(headcount))
    return float(round_half_up(rate, 4))


def compute_moving_avg(window_rates: list[Optional[Decimal]]) -> Optional[float]:
    """
    Rule R8: moving_avg_7d = mean of non-null attendance_rate values in the window,
    4 decimals half-up. Null if the window holds no non-null rate.
    """
    non_null = [r for r in window_rates if r is not None]
    if not non_null:
        return None
    avg = sum(non_null) / Decimal(str(len(non_null)))
    return float(round_half_up(avg, 4))


def compute_avg_work_hours(total_hours: float | Decimal, count: int) -> Optional[float]:
    """Computes average work hours rounded to 2 decimals half-up."""
    if count <= 0:
        return None
    avg = Decimal(str(total_hours)) / Decimal(str(count))
    return float(round_half_up(avg, 2))
