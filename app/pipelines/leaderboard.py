import calendar
from typing import Any, Optional


def build_leaderboard_pipeline(
    month: str,
    limit: int = 10,
    department: Optional[str] = None
) -> list[dict[str, Any]]:
    """Builds MongoDB aggregation pipeline for late leaderboard with competition ranking."""
    year, m = map(int, month.split("-"))
    last_day = calendar.monthrange(year, m)[1]
    first_day_of_month = f"{month}-01"
    last_day_of_month = f"{month}-{last_day:02d}"

    pipeline: list[dict[str, Any]] = [
        {
            "$match": {
                "date": {"$gte": first_day_of_month, "$lte": last_day_of_month},
                "late_minutes": {"$gt": 0}
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1}
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "emp"
            }
        },
        {"$unwind": "$emp"}
    ]

    if department:
        pipeline.append({"$match": {"emp.department": department}})

    pipeline.extend([
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$emp.name",
                "department": "$emp.department",
                "total_late_minutes": 1,
                "late_count": 1
            }
        },
        {"$sort": {"total_late_minutes": -1, "emp_code": 1}},
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}}
            }
        },
        {"$match": {"rank": {"$lte": limit}}},
        {"$sort": {"rank": 1, "emp_code": 1}}
    ])

    return pipeline
