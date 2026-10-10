from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db
from app.models.admin import ExplainResult
from app.pipelines.department_summary import build_department_summary_pipeline
from app.pipelines.department_trend import build_department_trend_pipeline
from app.pipelines.employee_monthly import build_employee_monthly_pipeline
from app.pipelines.leaderboard import build_leaderboard_pipeline

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ENDPOINTS = {
    "attendance_list",
    "employee_monthly",
    "department_summary",
    "late_leaderboard",
    "department_trend"
}


@router.get("/explain/{endpoint}", response_model=ExplainResult)
def explain_endpoint(
    endpoint: str,
    emp_code: Optional[str] = None,
    month: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    if endpoint not in VALID_ENDPOINTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid endpoint. Must be one of {sorted(VALID_ENDPOINTS)}"
        )

    db = get_db()

    if endpoint == "attendance_list":
        collection = "attendance_logs"
        q: dict[str, Any] = {}
        if emp_code:
            q["emp_code"] = emp_code
        if status:
            q["status"] = status
        if date_from or date_to:
            q["date"] = {}
            if date_from:
                q["date"]["$gte"] = date_from
            if date_to:
                q["date"]["$lte"] = date_to

        skip = (page - 1) * page_size
        explain_output = db.command(
            "explain",
            {
                "find": collection,
                "filter": q,
                "sort": {"date": -1, "emp_code": 1},
                "skip": skip,
                "limit": page_size
            },
            verbosity="executionStats"
        )

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(
                status_code=422,
                detail="emp_code and month query parameters are required for employee_monthly explain"
            )
        collection = "attendance_logs"
        pipeline = build_employee_monthly_pipeline(emp_code, month)
        explain_output = db.command(
            "explain",
            {
                "aggregate": collection,
                "pipeline": pipeline,
                "cursor": {}
            },
            verbosity="executionStats"
        )

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(
                status_code=422,
                detail="month query parameter is required for department_summary explain"
            )
        collection = "employees"
        pipeline = build_department_summary_pipeline(month, department)
        explain_output = db.command(
            "explain",
            {
                "aggregate": collection,
                "pipeline": pipeline,
                "cursor": {}
            },
            verbosity="executionStats"
        )

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(
                status_code=422,
                detail="month query parameter is required for late_leaderboard explain"
            )
        collection = "attendance_logs"
        pipeline = build_leaderboard_pipeline(month, limit, department)
        explain_output = db.command(
            "explain",
            {
                "aggregate": collection,
                "pipeline": pipeline,
                "cursor": {}
            },
            verbosity="executionStats"
        )

    elif endpoint == "department_trend":
        if not department or not from_date or not to_date:
            raise HTTPException(
                status_code=422,
                detail="department, from, and to parameters are required for department_trend explain"
            )
        collection = "employees"
        dept_emp_codes = [
            e["emp_code"]
            for e in db.employees.find({"department": department}, {"emp_code": 1})
        ]
        pipeline = build_department_trend_pipeline(
            department, from_date, to_date, dept_emp_codes
        )
        explain_output = db.command(
            "explain",
            {
                "aggregate": collection,
                "pipeline": pipeline,
                "cursor": {}
            },
            verbosity="executionStats"
        )

    return {
        "endpoint": endpoint,
        "collection": collection,
        "explain": explain_output
    }
