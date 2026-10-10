from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.database import get_db
from app.models.attendance import (
    AttendancePage,
    AttendanceRecord,
    AttendanceRegularize,
    PunchInRequest,
    PunchOutRequest,
)
from app.common.math_utils import compute_work_hours, is_half_day
from app.common.serializers import serialize_attendance_record
from app.common.time_utils import (
    compute_late_minutes,
    compute_overtime_minutes,
    determine_attendance_date,
    dt_to_epoch_ms,
    ms_to_utc_datetime,
    now_epoch_ms,
    validate_epoch_ms,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("/punch-in", status_code=201, response_model=AttendanceRecord)
def punch_in(body: PunchInRequest):
    db = get_db()
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="employee not found")

    raw_ms = body.punched_at if body.punched_at is not None else now_epoch_ms()
    punched_at_ms = validate_epoch_ms(raw_ms)
    dt_utc_in = ms_to_utc_datetime(punched_at_ms)

    att_date = determine_attendance_date(dt_utc_in, emp["shift_start"], emp["shift_end"])
    late_min = compute_late_minutes(dt_utc_in, att_date, emp["shift_start"])

    doc = {
        "emp_code": body.emp_code,
        "date": att_date,
        "status": body.status,
        "punch_in": dt_utc_in,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": late_min,
        "overtime_minutes": 0,
        "half_day": False,
        "history": []
    }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="already punched in for this date")

    return serialize_attendance_record(doc)


@router.post("/punch-out", response_model=AttendanceRecord)
def punch_out(body: PunchOutRequest):
    db = get_db()
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="employee not found")

    raw_ms = body.punched_at if body.punched_at is not None else now_epoch_ms()
    punched_at_ms = validate_epoch_ms(raw_ms)
    dt_utc_out = ms_to_utc_datetime(punched_at_ms)

    # Find the employee's single most recent record where punch_in <= punched_at
    recent = list(
        db.attendance_logs.find({
            "emp_code": body.emp_code,
            "punch_in": {"$lte": dt_utc_out}
        })
        .sort([("punch_in", -1), ("_id", -1)])
        .limit(1)
    )

    if not recent:
        raise HTTPException(status_code=404, detail="no punch-in found")

    target = recent[0]
    in_ms = dt_to_epoch_ms(target["punch_in"])
    if in_ms is None:
        raise HTTPException(status_code=404, detail="no punch-in found")

    if punched_at_ms <= in_ms:
        raise HTTPException(
            status_code=422,
            detail="punch-out time must be strictly after punch-in time"
        )

    if (punched_at_ms - in_ms) > 24 * 3600 * 1000:
        raise HTTPException(
            status_code=422,
            detail="punch-out cannot be more than 24 hours after punch-in"
        )

    work_hrs = compute_work_hours(in_ms, punched_at_ms)
    half_d = is_half_day(work_hrs)
    ot_min = compute_overtime_minutes(
        dt_utc_out, target["date"], emp["shift_start"], emp["shift_end"]
    )

    # Atomic update on targeted record ensuring punch_out is null
    res = db.attendance_logs.find_one_and_update(
        filter={"_id": target["_id"], "punch_out": None},
        update={
            "$set": {
                "punch_out": dt_utc_out,
                "work_hours": work_hrs,
                "overtime_minutes": ot_min,
                "half_day": half_d
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if not res:
        # Document existed but already had punch_out populated
        raise HTTPException(status_code=409, detail="already punched out")

    return serialize_attendance_record(res)


@router.get("", response_model=AttendancePage)
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422, detail="date_from cannot be greater than date_to"
        )

    db = get_db()
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

    total = db.attendance_logs.count_documents(q)
    skip = (page - 1) * page_size
    cursor = (
        db.attendance_logs.find(q)
        .sort([("date", -1), ("emp_code", 1)])
        .skip(skip)
        .limit(page_size)
    )

    items = [serialize_attendance_record(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.patch("/{emp_code}/{date}", response_model=AttendanceRecord)
def regularize_attendance(
    emp_code: str,
    date: str,
    body: AttendanceRegularize
):
    db = get_db()
    existing = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not existing:
        raise HTTPException(status_code=404, detail="attendance record not found")

    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="employee not found")

    # Check ABSENT/LEAVE rule
    target_status = body.status if body.status is not None else existing.get("status")
    if target_status in ("ABSENT", "LEAVE"):
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(
                status_code=422,
                detail="cannot supply punch times with ABSENT or LEAVE status"
            )
        final_punch_in = None
        final_punch_out = None
        final_work_hours = None
        final_late_minutes = 0
        final_overtime_minutes = 0
        final_half_day = False
    else:
        # Presence status (PRESENT, WFH, ON_DUTY) requires punch_in
        in_ms = (
            validate_epoch_ms(body.punch_in)
            if body.punch_in is not None
            else dt_to_epoch_ms(existing.get("punch_in"))
        )
        if in_ms is None:
            raise HTTPException(status_code=422, detail="presence status requires punch_in")

        dt_in = ms_to_utc_datetime(in_ms)
        # Verify punch_in stays on the record's attendance date under R1
        recomputed_date = determine_attendance_date(dt_in, emp["shift_start"], emp["shift_end"])
        if recomputed_date != date:
            raise HTTPException(
                status_code=422,
                detail=f"punch_in belongs to attendance date {recomputed_date}, not {date}"
            )

        final_punch_in = dt_in
        final_late_minutes = compute_late_minutes(dt_in, date, emp["shift_start"])

        # Punch out
        out_ms = (
            validate_epoch_ms(body.punch_out)
            if body.punch_out is not None
            else dt_to_epoch_ms(existing.get("punch_out"))
        )

        if out_ms is not None:
            if out_ms <= in_ms:
                raise HTTPException(
                    status_code=422,
                    detail="punch_out must be strictly after punch_in"
                )
            if (out_ms - in_ms) > 24 * 3600 * 1000:
                raise HTTPException(
                    status_code=422,
                    detail="punch_out cannot be more than 24 hours after punch_in"
                )
            dt_out = ms_to_utc_datetime(out_ms)
            final_punch_out = dt_out
            final_work_hours = compute_work_hours(in_ms, out_ms)
            final_half_day = is_half_day(final_work_hours)
            final_overtime_minutes = compute_overtime_minutes(
                dt_out, date, emp["shift_start"], emp["shift_end"]
            )
        else:
            final_punch_out = None
            final_work_hours = None
            final_half_day = False
            final_overtime_minutes = 0

    # Detect field changes
    changes: dict[str, Any] = {}

    def record_change(field: str, old_val: Any, new_val: Any):
        if old_val != new_val:
            changes[field] = {"from": old_val, "to": new_val}

    if existing.get("status") != target_status:
        record_change("status", existing.get("status"), target_status)

    old_in_ms = dt_to_epoch_ms(existing.get("punch_in"))
    new_in_ms = dt_to_epoch_ms(final_punch_in)
    if old_in_ms != new_in_ms:
        record_change("punch_in", existing.get("punch_in"), final_punch_in)

    old_out_ms = dt_to_epoch_ms(existing.get("punch_out"))
    new_out_ms = dt_to_epoch_ms(final_punch_out)
    if old_out_ms != new_out_ms:
        record_change("punch_out", existing.get("punch_out"), final_punch_out)

    if existing.get("work_hours") != final_work_hours:
        record_change("work_hours", existing.get("work_hours"), final_work_hours)

    if existing.get("late_minutes", 0) != final_late_minutes:
        record_change("late_minutes", existing.get("late_minutes", 0), final_late_minutes)

    if existing.get("overtime_minutes", 0) != final_overtime_minutes:
        record_change("overtime_minutes", existing.get("overtime_minutes", 0), final_overtime_minutes)

    if existing.get("half_day", False) != final_half_day:
        record_change("half_day", existing.get("half_day", False), final_half_day)

    if not changes:
        raise HTTPException(status_code=422, detail="request changes nothing")

    audit_entry = {
        "at": datetime.now(timezone.utc),
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes
    }

    # Handle missing history field in legacy documents
    existing_history = existing.get("history")
    if not existing_history:
        concurrency_filter = {
            "_id": existing["_id"],
            "$or": [
                {"history": {"$exists": False}},
                {"history": {"$size": 0}},
                {"history": None}
            ]
        }
    else:
        concurrency_filter = {
            "_id": existing["_id"],
            "history": {"$size": len(existing_history)}
        }

    updated_fields = {
        "status": target_status,
        "punch_in": final_punch_in,
        "punch_out": final_punch_out,
        "work_hours": final_work_hours,
        "late_minutes": final_late_minutes,
        "overtime_minutes": final_overtime_minutes,
        "half_day": final_half_day
    }

    res = db.attendance_logs.find_one_and_update(
        filter=concurrency_filter,
        update={
            "$set": updated_fields,
            "$push": {"history": audit_entry}
        },
        return_document=ReturnDocument.AFTER
    )

    if not res:
        raise HTTPException(status_code=409, detail="concurrent edit conflict")

    return serialize_attendance_record(res)
