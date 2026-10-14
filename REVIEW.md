# REVIEW.md

## Code Review: Starter `app/main.py`

A systematic review of the starter template's helpers and endpoints. Each defect is documented with the root cause, how it would surface in production, and how it was fixed.

---

### Summary

| Severity   | Count | Categories                                           |
| ---------- | ----- | ---------------------------------------------------- |
| 🔴 Critical | 4     | Race conditions, data corruption, crash on valid input |
| 🟠 High     | 5     | Wrong calculations, memory issues, broken contract    |
| 🟡 Medium   | 3     | Missing validation, stale health check, legacy crash  |
| **Total**  | **12**|                                                      |

---

### Defects Found

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `POST /attendance/punch-in` | **Concurrency race condition:** used check-then-insert (`find_one` then `insert_one`) without relying on database-level constraints. | Parallel identical punch-in requests created duplicate daily records for the same employee or threw unhandled 500 errors. | Created a compound unique index on `(emp_code, date)` and handled `DuplicateKeyError` directly, returning 409 Conflict. |
| 2 | `compute_late_minutes` | **Incorrect grace-period logic:** subtracted grace period from late minutes (`diff - 10`) and used non-strict inequality (`>= 10`), violating Rule R2. | Shift 09:30 punched in at 09:40:00 returned late (should be 0); punched in at 09:45:00 returned 5 minutes instead of 15. | Checked `diff_seconds > 600` (strictly > 10 min); when true, calculated `diff_seconds // 60` from `shift_start` (not grace end); else 0. |
| 3 | `determine_attendance_date` | **No IST timezone handling or overnight shift logic:** used naive local dates without considering UTC+05:30 offset or overnight shifts (`shift_end <= shift_start`). | An overnight shift (22:00-06:00) punching in at 01:00 AM on July 7 was wrongly logged as 2026-07-07 instead of 2026-07-06. | Converted UTC instants to IST, checked if `shift_end <= shift_start` and current IST time `< shift_end`, attributing date to previous day. |
| 4 | `compute_work_hours` / `compute_attendance_pct` | **Banker's rounding and float imprecision:** used Python's built-in `round()` which performs round-half-to-even (banker's rounding) and suffers floating-point representation inaccuracies. | Values ending in exact half-fractions (e.g. 2.125) rounded down to 2.12 instead of 2.13, failing contract Rule R4/R8. | Implemented `round_half_up` utilizing Python's `decimal.Decimal` with explicit `ROUND_HALF_UP` quantization. |
| 5 | `GET /attendance` | **In-memory pagination:** loaded entire collection into Python memory via `list(cursor)` and sliced `[skip:skip+limit]`. | High memory consumption and severe latency degradation (>2s) on 100k records; `explain` showed COLLSCAN. | Used native MongoDB `.skip(skip).limit(page_size)`, `count_documents(q)`, backed by composite index `{"date": -1, "emp_code": 1}`. |
| 6 | `validate_epoch_ms` | **Missing/weak timestamp validation:** allowed non-millisecond values, floats, and strings without proper rejection. | Sending a 10-digit Unix timestamp (seconds, e.g. 1783312500) was accepted and created dates in 1970 instead of HTTP 422. | Enforced integer type checking and range boundaries `[100000000000, 4102444800000]`, raising HTTP 422 on invalid inputs. |
| 7 | `truncate_to_seconds` | **Sub-second milliseconds preserved in calculations:** fractional milliseconds were not truncated before performing time calculations, violating Rule R1. | Input timestamp `1783312500850` preserved fractional milliseconds, causing rounding drifts in work duration calculations. | Implemented explicit integer truncation `(ms // 1000) * 1000` at API boundary upon ingestion. |
| 8 | Document Serializers | **Internal `_id` leaked in API responses:** MongoDB's `_id` was exposed directly in serialized API response dictionaries. | Response JSON contained `_id: "..."` or raised `TypeError: ObjectId is not JSON serializable`, violating API contract. | Popped `_id` (and any alias `id`) from response payloads in `serialize_employee` and `serialize_attendance_record`. |
| 9 | `GET /health` | **Fake health check:** returned a static hardcoded `{"status": "ok"}` without verifying database connectivity. | Endpoint returned HTTP 200 even when MongoDB daemon was stopped or network connection dropped. | Added `db.command("ping")` within try/except block; returned HTTP 503 if database fails to respond. |
| 10 | `POST /employees` | **Concurrency race condition on employee creation:** duplicate check performed in application logic without unique index enforcement. | Simultaneous creation requests with identical `emp_code` both returned 201 Created, causing corrupted directory state. | Created unique index on `{"emp_code": 1}` at startup; caught `DuplicateKeyError` to return HTTP 409 Conflict. |
| 11 | `POST /employees` | **Zero-duration shift allowed:** no validation preventing identical `shift_start` and `shift_end`, creating an impossible 0-duration shift definition. | POST request with `shift_start: "09:00"` and `shift_end: "09:00"` returned 201 Created instead of 422. | Added Pydantic model validator verifying `shift_start != shift_end`, automatically failing with HTTP 422. |
| 12 | `serialize_attendance_record` | **Legacy document crash:** no fallback defaults for attendance documents missing optional fields (`history`, `late_minutes`, `half_day`). | Querying seeded legacy documents raised `KeyError` and crashed with HTTP 500. | Provided robust defaults (`half_day: False`, `history: []`, `late_minutes: 0`, `overtime_minutes: 0`) during serialization. |

---

### Detailed Analysis

#### Defect 1 — Punch-In Race Condition 🔴

**Root cause:** The starter code used a `find_one` to check if a record already existed, then `insert_one` to create it. Between the check and the insert, a concurrent request could create the same record.

**Before (vulnerable):**
```python
existing = db.attendance_logs.find_one({"emp_code": emp_code, "date": att_date})
if existing:
    raise HTTPException(409, "already punched in")
db.attendance_logs.insert_one(doc)  # Race: another request could insert between check and here
```

**After (safe):**
```python
try:
    db.attendance_logs.insert_one(doc)  # Unique index (emp_code, date) guarantees atomicity
except DuplicateKeyError:
    raise HTTPException(409, "already punched in for this date")
```

#### Defect 2 — Late Minutes Miscalculation 🟠

**Root cause:** Two compounding errors: (a) used `>= 10` instead of `> 10` minutes for the grace check, and (b) subtracted the grace period from the result instead of counting from shift start.

**Contract (R2):** "late only if *strictly more than* 10:00 after shift_start. When late, `late_minutes` = whole minutes since `shift_start`."

| Input (shift 09:30) | Starter result | Correct result | Fixed? |
| -------------------- | -------------- | -------------- | ------ |
| 09:40:00             | 0 (broken)     | 0              | ✅     |
| 09:40:01             | 0 (broken)     | 10             | ✅     |
| 09:45:00             | 5 (wrong)      | 15             | ✅     |
| 10:15:59             | 35 (wrong)     | 45             | ✅     |

#### Defect 3 — Attendance Date Without IST/Overnight 🔴

**Root cause:** Used Python's `datetime.now()` to get a naive local date without converting to IST. No handling of overnight shifts where `shift_end <= shift_start`.

**Impact example:** Employee with 22:00–06:00 shift punches in at 01:00 AM IST on July 7. The punch belongs to the shift that started on July 6, but the starter code logged it as July 7 — creating a duplicate and breaking analytics.

#### Defect 4 — Banker's Rounding 🟠

**Root cause:** Python's `round()` uses "round half to even" (banker's rounding), which rounds 2.125 to 2.12 instead of 2.13.

**Fix:** All rounding now uses `decimal.Decimal` with explicit `ROUND_HALF_UP`:
```python
def round_half_up(val, decimals=2):
    d = Decimal(str(val))
    fmt = "0." + "0" * decimals
    return d.quantize(Decimal(fmt), rounding=ROUND_HALF_UP)
```

#### Defect 5 — In-Memory Pagination 🟠

**Root cause:** `list(cursor)` fetched the entire collection into Python memory, then sliced with `[skip:skip+limit]`. On 100k records this consumed hundreds of MB and caused multi-second latency.

**Fix:** Server-side pagination with `.skip().limit()` backed by the `{date: -1, emp_code: 1}` composite index.

---

### Examined and Decided NOT a Defect

1. **Absence of User Authentication / Authorization**: The problem statement explicitly states that the assignment focuses on data modeling, rules, and MongoDB aggregation performance; user authentication is intentionally omitted for this scope.

2. **PyMongo Returning Naive Datetimes**: By default, PyMongo returns naive datetimes. Configuring `tz_aware=True` on `MongoClient` and treating all stored BSON dates as UTC ensures consistent instant conversions to epoch milliseconds without modifying the database driver architecture.

3. **Omitting `_id` on Attendance Records**: Addressing attendance documents by `(emp_code, date)` rather than an ObjectId is an intentional business design pattern specified in the contract; having no surrogate key on attendance logs is not a defect.
