import pathlib
import pytest
from bson import json_util
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, init_indexes

client = TestClient(app)

HERE = pathlib.Path(__file__).parent.parent / "sample_data"
BSON_OPTS = json_util.JSONOptions(tz_aware=True)


def seed_database():
    """Seeds a fresh copy of the sample data into MongoDB before each test."""
    db = get_db()
    init_indexes()
    for name in ("employees", "attendance_logs"):
        raw_text = (HERE / f"{name}.json").read_text(encoding="utf-8")
        docs = json_util.loads(raw_text, json_options=BSON_OPTS)
        db[name].delete_many({})
        db[name].insert_many(docs)


@pytest.fixture(autouse=True)
def run_before_each_test():
    """Fixture ensuring database is freshly seeded and tests are 100% order-independent."""
    seed_database()


# ---------------------------------------------------------------------------
# Test Cases Grounded in Sample Data
# ---------------------------------------------------------------------------

def test_01_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_02_create_employee_duplicate_conflict():
    payload = {
        "emp_code": "EMP0001",
        "name": "Asha Rao Duplicate",
        "email": "ashadup@example.com",
        "department": "Engineering",
        "joined_on": "2026-01-05"
    }
    res = client.post("/employees", json=payload)
    assert res.status_code == 409
    assert res.json()["detail"] == "emp_code already exists"


def test_03_list_employees_pagination_and_filter():
    res = client.get("/employees?department=Engineering&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["emp_code"] == "EMP0001"
    assert data["items"][0]["created_at"] == 1767587400000
    assert data["items"][1]["emp_code"] == "EMP0002"
    assert data["items"][1]["created_at"] == 1783915200000


def test_04_punch_out_lifecycle_and_concurrency():
    # 4a: Punch out open record (EMP0006 on 2026-07-07, punch_in was 04:05 UTC = 1783397100000)
    # Punch out at 13:05 UTC = 1783429500000 -> 9.00 hours
    res = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0006",
        "punched_at": 1783429500000
    })
    assert res.status_code == 200
    doc = res.json()
    assert doc["work_hours"] == 9.0
    assert doc["half_day"] is False
    assert doc["overtime_minutes"] == 0
    assert doc["punch_out"] == 1783429500000

    # 4b: Repeat same punch out -> must return 409 (already punched out)
    res_repeat = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0006",
        "punched_at": 1783429500000
    })
    assert res_repeat.status_code == 409
    assert res_repeat.json()["detail"] == "already punched out"

    # 4c: punched_at before ALL punch_ins -> no record found -> 404
    # (1783397000000 < punch_in of 1783397100000, so query finds nothing)
    res_no_record = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0006",
        "punched_at": 1783397000000
    })
    assert res_no_record.status_code == 404

    # 4d: Genuine 422 test — punched_at == punch_in (exactly equal)
    # EMP0001 Jul 6 punch_in is 1783310280000 (03:58 UTC). Use same value as punch_out.
    res_equal = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0001",
        "punched_at": 1783310280000
    })
    assert res_equal.status_code == 422


def test_05_regularize_attendance_and_history():
    # 5a: Regularize EMP0003 on 2026-07-06.
    # Original punch_in: 04:35 UTC (10:05 IST) = 1783312500000 -> late_minutes = 35
    # New punch_in:       04:00 UTC (09:30 IST) = 1783310400000 -> late_minutes = 0  (exactly on shift start)
    # Punch out is 13:40 UTC (1783345200000). New work_hours = (1783345200000 - 1783310400000)/1000/3600 = 34800/3600 = 9.67
    res = client.patch("/attendance/EMP0003/2026-07-06", json={
        "punch_in": 1783310400000,
        "reason": "Biometric terminal sync issue",
        "regularized_by": "hr.admin"
    })
    assert res.status_code == 200
    doc = res.json()
    assert doc["late_minutes"] == 0
    assert doc["work_hours"] == 9.67
    assert len(doc["history"]) == 1
    assert doc["history"][0]["by"] == "hr.admin"
    assert "late_minutes" in doc["history"][0]["changes"]
    assert "punch_in" in doc["history"][0]["changes"]

    # 5b: Repeat exact same patch (changes nothing) -> must return 422
    res_noop = client.patch("/attendance/EMP0003/2026-07-06", json={
        "punch_in": 1783310400000,
        "reason": "Repeated change",
        "regularized_by": "hr.admin"
    })
    assert res_noop.status_code == 422
    assert "changes nothing" in res_noop.json()["detail"]

    # 5c: Supplying punch times with ABSENT or LEAVE -> must return 422
    res_bad = client.patch("/attendance/EMP0003/2026-07-06", json={
        "status": "LEAVE",
        "punch_in": 1783312200000,
        "reason": "Invalid combination",
        "regularized_by": "hr.admin"
    })
    assert res_bad.status_code == 422


def test_06_employee_monthly_analytics_emp0001():
    # EMP0001 July 2026: joined Jan 5, 2026 -> 23 weekdays. 2 present days (Jul 6, Jul 7).
    # attendance_pct = 2.0 / 23 * 100 = 8.70%
    res = client.get("/analytics/employees/EMP0001/monthly?month=2026-07")
    assert res.status_code == 200
    data = res.json()
    assert data["emp_code"] == "EMP0001"
    assert data["month"] == "2026-07"
    assert data["working_days"] == 23
    assert data["present_days"] == 2.0
    assert data["leave_days"] == 0
    assert data["late_count"] == 0
    assert data["total_late_minutes"] == 0
    assert data["total_overtime_minutes"] == 0
    assert data["attendance_pct"] == 8.70


def test_07_employee_monthly_analytics_emp0002_mid_month():
    # EMP0002 July 2026: joined July 13, 2026 -> 15 weekdays. 1 present day (Jul 14).
    # attendance_pct = 1.0 / 15 * 100 = 6.67%
    res = client.get("/analytics/employees/EMP0002/monthly?month=2026-07")
    assert res.status_code == 200
    data = res.json()
    assert data["emp_code"] == "EMP0002"
    assert data["month"] == "2026-07"
    assert data["working_days"] == 15
    assert data["present_days"] == 1.0
    assert data["leave_days"] == 0
    assert data["late_count"] == 0
    assert data["attendance_pct"] == 6.67


def test_08_department_summary_analytics():
    res = client.get("/analytics/departments/summary?month=2026-07")
    assert res.status_code == 200
    items = {item["department"]: item for item in res.json()["items"]}

    # Engineering: EMP0001 (2.0 days), EMP0002 (1.0 day). avg_work_hours = (9.12 + 9.03 + 8.98)/3 = 9.04
    eng = items["Engineering"]
    assert eng["headcount"] == 2
    assert eng["present_days"] == 3.0
    assert eng["avg_work_hours"] == 9.04
    assert eng["late_count"] == 0
    assert eng["leave_count"] == 0

    # Sales: EMP0003 (1.0 day), EMP0004 (0.5 day). avg_work_hours = (9.08 + 3.50)/2 = 6.29
    sales = items["Sales"]
    assert sales["headcount"] == 2
    assert sales["present_days"] == 1.5
    assert sales["avg_work_hours"] == 6.29
    assert sales["late_count"] == 1
    assert sales["total_late_minutes"] == 35
    assert sales["leave_count"] == 1

    # Support: EMP0005 (1.0 day), EMP0006 (1.0 day, punch_out is null). avg_work_hours = 8.75
    sup = items["Support"]
    assert sup["headcount"] == 2
    assert sup["present_days"] == 2.0
    assert sup["avg_work_hours"] == 8.75


def test_09_late_leaderboard():
    res = client.get("/analytics/leaderboard/late?month=2026-07&limit=5")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["rank"] == 1
    assert items[0]["emp_code"] == "EMP0003"
    assert items[0]["name"] == "Neha Iyer"
    assert items[0]["department"] == "Sales"
    assert items[0]["total_late_minutes"] == 35
    assert items[0]["late_count"] == 1


def test_10_department_trend():
    res = client.get("/analytics/departments/Sales/trend?from=2026-07-06&to=2026-07-08")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 3

    # Day 1: Jul 6
    assert items[0]["date"] == "2026-07-06"
    assert items[0]["headcount"] == 2
    assert items[0]["present_count"] == 1.0
    assert items[0]["late_count"] == 1
    assert items[0]["attendance_rate"] == 0.5000
    assert items[0]["moving_avg_7d"] == 0.5000

    # Day 2: Jul 7
    assert items[1]["date"] == "2026-07-07"
    assert items[1]["headcount"] == 2
    assert items[1]["present_count"] == 0.5
    assert items[1]["late_count"] == 0
    assert items[1]["attendance_rate"] == 0.2500
    assert items[1]["moving_avg_7d"] == 0.3750

    # Day 3: Jul 8
    assert items[2]["date"] == "2026-07-08"
    assert items[2]["headcount"] == 2
    assert items[2]["present_count"] == 0.0
    assert items[2]["late_count"] == 0
    assert items[2]["attendance_rate"] == 0.0000
    assert items[2]["moving_avg_7d"] == 0.2500


def test_10b_department_trend_zero_logs_in_range():
    # Engineering department has zero logs between Jul 1 and Jul 3.
    # Must still return exactly 3 daily rows with attendance_rate 0.0000
    res = client.get("/analytics/departments/Engineering/trend?from=2026-07-01&to=2026-07-03")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 3
    for row in items:
        assert row["headcount"] == 1  # Only EMP0001 had joined
        assert row["present_count"] == 0.0
        assert row["attendance_rate"] == 0.0000
        assert row["moving_avg_7d"] == 0.0000


def test_10c_department_trend_unknown_department():
    res = client.get("/analytics/departments/NonExistentDept/trend?from=2026-07-01&to=2026-07-03")
    assert res.status_code == 404
    assert res.json()["detail"] == "department not found"


def test_11_admin_explain():
    res = client.get(
        "/admin/explain/department_trend?department=Sales&from=2026-07-06&to=2026-07-08"
    )
    assert res.status_code == 200
    data = res.json()
    assert data["endpoint"] == "department_trend"
    assert data["collection"] == "employees"
    assert "explain" in data


def test_12_shift_times_identical_fails_422():
    payload = {
        "emp_code": "EMP9999",
        "name": "Invalid Shift Emp",
        "email": "invalidshift@example.com",
        "department": "Engineering",
        "shift_start": "09:00",
        "shift_end": "09:00",
        "joined_on": "2026-01-01"
    }
    res = client.post("/employees", json=payload)
    assert res.status_code == 422


def test_13_punch_in_concurrency_race_condition():
    import concurrent.futures
    # Attempt 5 simultaneous punch-in requests for EMP0002 on July 15 (unpunched day)
    # 2026-07-15 04:00:00 UTC = 1784088000000
    payload = {
        "emp_code": "EMP0002",
        "punched_at": 1784088000000,
        "status": "PRESENT"
    }
    status_codes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(client.post, "/attendance/punch-in", json=payload) for _ in range(5)]
        for f in concurrent.futures.as_completed(futures):
            status_codes.append(f.result().status_code)

    assert status_codes.count(201) == 1
    assert status_codes.count(409) == 4


def test_14_rules_r1_overnight_and_r2_late_grace():
    # Test R2 exact grace period values on a new day (2026-07-20)
    # EMP0001 shift is 09:30 to 18:30 IST.
    # 2026-07-20 09:40:00 IST = 04:10:00 UTC = 1784520600000 ms -> inside grace -> late_minutes = 0
    res_exact_grace = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": 1784520600000
    })
    assert res_exact_grace.status_code == 201
    assert res_exact_grace.json()["late_minutes"] == 0

    # 2026-07-21 09:40:01 IST = 04:10:01 UTC = 1784607001000 ms -> strictly > 10 min -> late_minutes = 10
    res_late_1s = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": 1784607001000
    })
    assert res_late_1s.status_code == 201
    assert res_late_1s.json()["late_minutes"] == 10

    # 2026-07-22 10:15:59 IST = 04:45:59 UTC = 1784695559000 ms -> floor(45m 59s) = 45 min
    res_late_45m = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": 1784695559000
    })
    assert res_late_45m.status_code == 201
    assert res_late_45m.json()["late_minutes"] == 45

    # Test R1 Overnight shift attribution:
    # EMP0005 shift is 22:00 to 06:00 IST.
    # Punch-in on 2026-07-09 at 02:00:00 IST (earlier than 06:00 shift end)
    # 2026-07-09 02:00:00 IST = 2026-07-08 20:30:00 UTC = 1783542600000 ms.
    # Must be attributed to attendance date 2026-07-08!
    res_overnight = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0005",
        "punched_at": 1783542600000
    })
    assert res_overnight.status_code == 201
    assert res_overnight.json()["date"] == "2026-07-08"


def test_15_rule_r3_overtime_threshold():
    # EMP0001 shift ends at 18:30 IST. Punch-in at 09:30 IST on 2026-07-23 (1784779800000 ms)
    client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": 1784779800000
    })
    # Punch out at 18:59:59 IST (29 min 59 sec after shift end) -> under 30 min -> overtime = 0
    # 2026-07-23 18:59:59 IST = 13:29:59 UTC = 1784813399000 ms
    res_ot_under = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0001",
        "punched_at": 1784813399000
    })
    assert res_ot_under.status_code == 200
    assert res_ot_under.json()["overtime_minutes"] == 0

    # Next day 2026-07-24: punch-in at 09:30 IST (1784866200000 ms)
    client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": 1784866200000
    })
    # Punch out at 19:00:00 IST (exactly 30 min after shift end) = 13:30:00 UTC = 1784899800000 ms -> overtime = 30
    res_ot_30 = client.post("/attendance/punch-out", json={
        "emp_code": "EMP0001",
        "punched_at": 1784899800000
    })
    assert res_ot_30.status_code == 200
    assert res_ot_30.json()["overtime_minutes"] == 30


def test_16_rule_r7_weekend_records_handling():
    # 2026-07-11 is a Saturday, 2026-07-12 is a Sunday.
    # Punch in on Saturday 2026-07-11 with 15 min late.
    # 2026-07-11 09:45:00 IST = 04:15:00 UTC = 1783743300000 ms
    res_in = client.post("/attendance/punch-in", json={
        "emp_code": "EMP0001",
        "punched_at": 1783743300000
    })
    assert res_in.status_code == 201
    assert res_in.json()["late_minutes"] == 15

    # Check monthly summary for EMP0001:
    # Present days in sample data was 2.0 (Jul 6, Jul 7).
    # Since Jul 11 is Saturday, present_days must STILL be 2.0 (Mon-Fri only per R7).
    # But late_count and total_late_minutes MUST include Saturday's record per R7!
    res_monthly = client.get("/analytics/employees/EMP0001/monthly?month=2026-07")
    assert res_monthly.status_code == 200
    data = res_monthly.json()
    assert data["present_days"] == 2.0
    assert data["late_count"] == 1
    assert data["total_late_minutes"] == 15


def test_17_leaderboard_competition_ranking_ties_and_limit():
    db = get_db()
    # Add EMP0002 with identical 35 late minutes in July
    from datetime import datetime, timezone
    db.attendance_logs.insert_one({
        "emp_code": "EMP0002",
        "date": "2026-07-20",
        "status": "PRESENT",
        "punch_in": datetime(2026, 7, 20, 4, 35, tzinfo=timezone.utc),
        "punch_out": None,
        "work_hours": None,
        "late_minutes": 35,
        "overtime_minutes": 0,
        "half_day": False,
        "history": []
    })

    # Both EMP0002 and EMP0003 now have 35 late minutes.
    # Query leaderboard with limit=1:
    # Both tie for Rank 1. Since rank <= limit (1 <= 1), BOTH must be returned!
    res = client.get("/analytics/leaderboard/late?month=2026-07&limit=1")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 2
    assert items[0]["rank"] == 1
    assert items[1]["rank"] == 1
    assert items[0]["emp_code"] == "EMP0002"  # Sorted by emp_code ascending on tie
    assert items[1]["emp_code"] == "EMP0003"


def test_18_admin_explain_all_endpoints_no_collscan():
    # Verify that all 5 endpoints produce IXSCAN and zero COLLSCAN
    endpoints_params = [
        ("attendance_list", "/admin/explain/attendance_list?emp_code=EMP0001&date_from=2026-07-01"),
        ("employee_monthly", "/admin/explain/employee_monthly?emp_code=EMP0001&month=2026-07"),
        ("department_summary", "/admin/explain/department_summary?month=2026-07"),
        ("late_leaderboard", "/admin/explain/late_leaderboard?month=2026-07&limit=10"),
        ("department_trend", "/admin/explain/department_trend?department=Sales&from=2026-07-06&to=2026-07-08"),
    ]

    for name, url in endpoints_params:
        res = client.get(url)
        assert res.status_code == 200, f"Explain failed for {name}: {res.text}"
        exp_text = str(res.json()["explain"])
        assert "IXSCAN" in exp_text, f"{name} explain did not contain IXSCAN"
        assert "COLLSCAN" not in exp_text, f"{name} explain contained COLLSCAN"
