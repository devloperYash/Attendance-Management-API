import calendar
from datetime import date, timedelta
from typing import Any
from app.common.math_utils import compute_attendance_pct


def count_working_days(joined_on_str: str, year: int, month: int) -> int:
    """Counts Mon-Fri weekdays between max(month_start, joined_on) and month_end."""
    last_day = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    joined_on = date.fromisoformat(joined_on_str)
    start_date = max(month_start, joined_on)

    if start_date > month_end:
        return 0

    count = 0
    cur = start_date
    while cur <= month_end:
        if cur.weekday() < 5:  # Mon-Fri
            count += 1
        cur += timedelta(days=1)
    return count


def build_employee_monthly_pipeline(emp_code: str, month: str) -> list[dict[str, Any]]:
    """Builds MongoDB aggregation pipeline for employee monthly summary."""
    year, m = map(int, month.split("-"))
    last_day = calendar.monthrange(year, m)[1]
    first_date_str = f"{month}-01"
    last_date_str = f"{month}-{last_day:02d}"

    return [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {"$gte": first_date_str, "$lte": last_date_str}
            }
        },
        {
            "$addFields": {
                "presence_val": {
                    "$cond": [
                        {
                            "$and": [
                                {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                {"$in": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, [2, 3, 4, 5, 6]]}
                            ]
                        },
                        {"$cond": ["$half_day", 0.5, 1.0]},
                        0.0
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {"$sum": "$presence_val"},
                "leave_days": {
                    "$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
                },
                "late_count": {
                    "$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                }
            }
        }
    ]
