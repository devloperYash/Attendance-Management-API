from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional


def build_department_trend_pipeline(
    department: str,
    from_date: str,
    to_date: str,
    dept_emp_codes: list[str]
) -> list[dict[str, Any]]:
    """
    Builds MongoDB aggregation pipeline for department daily trend with $densify gap-filling.
    Guarantees exactly one row per calendar day from from_date to to_date inclusive.
    """
    from_dt = datetime.fromisoformat(from_date)
    to_dt = datetime.fromisoformat(to_date) + timedelta(days=1)

    return [
        {"$match": {"department": department}},
        {"$limit": 1},
        {"$project": {"_id": 0, "date": {"$dateFromString": {"dateString": from_date}}}},
        {
            "$densify": {
                "field": "date",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [from_dt, to_dt]
                }
            }
        },
        {
            "$project": {
                "date": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$date",
                        "timezone": "+05:30"
                    }
                },
                "is_working_day": {
                    "$in": [{"$dayOfWeek": "$date"}, [2, 3, 4, 5, 6]]
                }
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {"cur_date": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$department", department]},
                                    {"$lte": ["$joined_on", "$$cur_date"]}
                                ]
                            }
                        }
                    },
                    {"$count": "count"}
                ],
                "as": "hc"
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"cur_date": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$date", "$$cur_date"]},
                                    {"$in": ["$emp_code", dept_emp_codes]}
                                ]
                            }
                        }
                    }
                ],
                "as": "logs"
            }
        },
        {
            "$project": {
                "date": 1,
                "is_working_day": 1,
                "headcount": {"$ifNull": [{"$first": "$hc.count"}, 0]},
                "present_count": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "l",
                            "in": {
                                "$cond": [
                                    {"$in": ["$$l.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$cond": ["$$l.half_day", 0.5, 1.0]},
                                    0.0
                                ]
                            }
                        }
                    }
                },
                "late_count": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "l",
                            "in": {
                                "$cond": [{"$gt": [{"$ifNull": ["$$l.late_minutes", 0]}, 0]}, 1, 0]
                            }
                        }
                    }
                }
            }
        },
        {"$sort": {"date": 1}}
    ]


def format_trend_results(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Computes attendance_rate and moving_avg_7d using Decimal ROUND_HALF_UP.
    Ensures that moving_avg_7d is the mean of non-null rounded attendance_rate values
    within the current and up to 6 preceding rows inside the requested range.
    """
    trend_items: list[dict[str, Any]] = []
    window_rates: list[Optional[Decimal]] = []

    for row in raw_rows:
        headcount = row["headcount"]
        present_count = Decimal(str(row["present_count"]))
        is_working_day = row["is_working_day"]

        if is_working_day and headcount > 0:
            rate_dec = (present_count / Decimal(str(headcount))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            rate_float: Optional[float] = float(rate_dec)
            window_rates.append(rate_dec)
        else:
            rate_float = None
            window_rates.append(None)

        # 7-day document window (current + up to 6 preceding rows inside requested range)
        window = window_rates[-7:]
        non_null_window = [r for r in window if r is not None]
        if non_null_window:
            mov_avg_dec = (sum(non_null_window) / Decimal(str(len(non_null_window)))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            mov_avg_float: Optional[float] = float(mov_avg_dec)
        else:
            mov_avg_float = None

        trend_items.append({
            "date": row["date"],
            "is_working_day": row["is_working_day"],
            "headcount": headcount,
            "present_count": float(present_count),
            "late_count": row["late_count"],
            "attendance_rate": rate_float,
            "moving_avg_7d": mov_avg_float
        })

    return trend_items
