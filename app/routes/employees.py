from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import DuplicateKeyError
from app.database import get_db
from app.models.employee import EmployeeCreate, EmployeePage
from app.common.serializers import serialize_employee

router = APIRouter(prefix="/employees", tags=["employees"])


@router.post("", status_code=201)
def create_employee(body: EmployeeCreate):
    db = get_db()
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="emp_code already exists")

    return serialize_employee(doc)


@router.get("", response_model=EmployeePage)
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    db = get_db()
    q = {}
    if department:
        q["department"] = department

    total = db.employees.count_documents(q)
    skip = (page - 1) * page_size
    cursor = db.employees.find(q).sort("emp_code", 1).skip(skip).limit(page_size)

    items = [serialize_employee(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
