from pymongo import MongoClient
from pymongo.database import Database
from app.config import MONGO_URI, MONGO_DB

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, tz_aware=True)
    return _client


def get_db() -> Database:
    client = get_client()
    return client[MONGO_DB]


def ping_db() -> bool:
    try:
        db = get_db()
        db.command("ping")
        return True
    except Exception:
        return False


def init_indexes() -> None:
    db = get_db()

    # 1. employees indexes
    db.employees.create_index([("emp_code", 1)], unique=True, name="uniq_emp_code")
    db.employees.create_index([("department", 1), ("emp_code", 1)], name="idx_dept_emp_code")
    db.employees.create_index([("joined_on", 1)], name="idx_joined_on")
    db.employees.create_index([("department", 1), ("joined_on", 1)], name="idx_dept_joined_on")

    # 2. attendance_logs indexes
    db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True, name="uniq_emp_date")
    db.attendance_logs.create_index([("emp_code", 1), ("punch_in", -1)], name="idx_emp_punch_in_desc")
    db.attendance_logs.create_index([("date", -1), ("emp_code", 1)], name="idx_date_desc_emp_asc")
    db.attendance_logs.create_index([("date", 1), ("late_minutes", 1)], name="idx_date_late_minutes")
