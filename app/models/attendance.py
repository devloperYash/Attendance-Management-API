from typing import Any, Optional
from pydantic import BaseModel, Field


class PunchInRequest(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    punched_at: Optional[int] = None
    status: str = Field("PRESENT", pattern=r"^(PRESENT|WFH|ON_DUTY)$")


class PunchOutRequest(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    punched_at: Optional[int] = None


class AttendanceRegularize(BaseModel):
    reason: str = Field(..., min_length=1, max_length=300)
    regularized_by: str = Field(..., min_length=1, max_length=100)
    status: Optional[str] = Field(None, pattern=r"^(PRESENT|WFH|ON_DUTY|ABSENT|LEAVE)$")
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None


class AttendanceRecord(BaseModel):
    emp_code: str
    date: str
    status: str
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None
    work_hours: Optional[float] = None
    late_minutes: int = 0
    overtime_minutes: int = 0
    half_day: bool = False
    history: list[dict[str, Any]] = []


class AttendancePage(BaseModel):
    items: list[AttendanceRecord]
    total: int
    page: int
    page_size: int
