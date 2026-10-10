from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db
from app.models.analytics import (
    DepartmentSummary,
    DepartmentSummaryItem,
    EmployeeMonthly,
    Leaderboard,
    LeaderboardItem,
    Trend,
    TrendItem,
)
from app.common.math_utils import compute_attendance_pct, round_half_up
from app.config import MAX_TREND_DAYS
from app.pipelines.employee_monthly import (
    build_employee_monthly_pipeline,
    count_working_days,
)
from app.pipelines.department_summary import build_department_summary_pipeline
from app.pipelines.leaderboard import build_leaderboard_pipeline
from app.pipelines.department_trend import (
    build_department_trend_pipeline,
    format_trend_results,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/employees/{emp_code}/monthly", response_model=EmployeeMonthly)
def get_employee_monthly(
    emp_code: str,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$")
):
    db = get_db()
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="employee not found")

    year, m = map(int, month.split("-"))
    working_days = count_working_days(emp["joined_on"], year, m)

    pipeline = build_employee_monthly_pipeline(emp_code, month)
    agg_res = list(db.attendance_logs.aggregate(pipeline))

    if agg_res:
        row = agg_res[0]
        present_days = float(row.get("present_days", 0.0))
        leave_days = int(row.get("leave_days", 0))
        late_count = int(row.get("late_count", 0))
        total_late = int(row.get("total_late_minutes", 0))
        total_ot = int(row.get("total_overtime_minutes", 0))
    else:
        present_days = 0.0
        leave_days = 0
        late_count = 0
        total_late = 0
        total_ot = 0

    attendance_pct = compute_attendance_pct(present_days, working_days)

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": leave_days,
        "late_count": late_count,
        "total_late_minutes": total_late,
        "total_overtime_minutes": total_ot,
        "attendance_pct": attendance_pct
    }


@router.get("/departments/summary", response_model=DepartmentSummary)
def get_department_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    department: Optional[str] = None
):
    db = get_db()
    pipeline = build_department_summary_pipeline(month, department)
    agg_res = list(db.employees.aggregate(pipeline))

    items: list[dict] = []
    for r in agg_res:
        raw_avg = r.get("raw_avg_work_hours")
        avg_wh = (
            float(round_half_up(raw_avg, 2))
            if raw_avg is not None
            else None
        )

        items.append({
            "department": r["department"],
            "headcount": r["headcount"],
            "present_days": float(r["present_days"]),
            "avg_work_hours": avg_wh,
            "late_count": r["late_count"],
            "total_late_minutes": r["total_late_minutes"],
            "leave_count": r["leave_count"],
            "on_duty_count": r["on_duty_count"]
        })

    return {"month": month, "items": items}


@router.get("/leaderboard/late", response_model=Leaderboard)
def get_late_leaderboard(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None
):
    db = get_db()
    pipeline = build_leaderboard_pipeline(month, limit, department)
    agg_res = list(db.attendance_logs.aggregate(pipeline))
    return {"month": month, "items": agg_res}


@router.get("/departments/{department}/trend", response_model=Trend)
def get_department_trend(
    department: str,
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$")
):
    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date format")

    if d_to < d_from:
        raise HTTPException(status_code=422, detail="to cannot be earlier than from")

    num_days = (d_to - d_from).days + 1
    if num_days > MAX_TREND_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"requested date range exceeds maximum allowed limit of {MAX_TREND_DAYS} days"
        )

    db = get_db()
    # Check if department exists (has any employees)
    if db.employees.count_documents({"department": department}) == 0:
        raise HTTPException(status_code=404, detail="department not found")

    dept_emp_codes = [
        e["emp_code"]
        for e in db.employees.find({"department": department}, {"emp_code": 1})
    ]

    pipeline = build_department_trend_pipeline(
        department, from_date, to_date, dept_emp_codes
    )
    raw_rows = list(db.employees.aggregate(pipeline))
    items = format_trend_results(raw_rows)

    return {"department": department, "items": items}
