# Employee Attendance & Analytics API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![MongoDB](https://img.shields.io/badge/MongoDB-6.0+-47A248.svg?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![Tests](https://img.shields.io/badge/Tests-20%20Passed-success.svg)]()

Production-grade, asynchronous HR attendance management and analytics backend service built with **FastAPI** and **MongoDB**. The platform handles high-throughput biometric punch-in/out lifecycles, race-safe regularization audit trails, and complex business intelligence aggregation pipelines operating efficiently across collections of 100,000+ records.

---

## Table of Contents
1. [Architecture & Design Principles](#architecture--design-principles)
2. [Project Structure](#project-structure)
3. [Database Schema & Data Model](#database-schema--data-model)
   - [Collection: `employees`](#collection-employees)
   - [Collection: `attendance_logs`](#collection-attendance_logs)
   - [Audit History Schema](#audit-history-schema)
4. [Indexing Strategy & Zero-COLLSCAN Guarantee](#indexing-strategy--zero-collscan-guarantee)
5. [Business Rules (R1 – R10)](#business-rules-r1--r10)
6. [API Endpoints Reference](#api-endpoints-reference)
   - [System & Health](#1-system--health)
   - [Employees Directory](#2-employees-directory)
   - [Attendance & Regularization](#3-attendance--regularization)
   - [Analytics & Aggregation Pipelines](#4-analytics--aggregation-pipelines)
   - [Admin Query Plan Explain](#5-admin-query-plan-explain)
7. [Concurrency & Race Condition Handling](#concurrency--race-condition-handling)
8. [Local Setup & Execution](#local-setup--execution)
9. [Running Test Suite](#running-test-suite)
10. [Submission Files & Verification](#submission-files--verification)

---

## Architecture & Design Principles

```
+---------------------------------------------------------------------------------+
|                                FastAPI Application                              |
+---------------------------------------------------------------------------------+
|                                                                                 |
|   +-------------------+  +--------------------+  +--------------------------+   |
|   | /attendance       |  | /analytics         |  | /employees & /admin      |   |
|   | - Punch-In        |  | - Employee Monthly |  | - CRUD                   |   |
|   | - Punch-Out       |  | - Dept Summary     |  | - Paginated Listing      |   |
|   | - Regularize      |  | - Late Leaderboard |  | - MongoDB Explain        |   |
|   | - List (Filter)   |  | - Dept Trend       |  | - System Health Check    |   |
|   +-------------------+  +--------------------+  +--------------------------+   |
|             |                       |                          |                |
|             v                       v                          v                |
|   +-------------------------------------------------------------------------+   |
|   |                      Validation & Normalization Layer                    |   |
|   |   - Decimal (ROUND_HALF_UP)   - Epoch ms integer range validation       |   |
|   |   - Whole-second truncation   - IST (UTC+05:30) date attribution        |   |
|   +-------------------------------------------------------------------------+   |
|                                     |                                           |
|                                     v                                           |
|   +-------------------------------------------------------------------------+   |
|   |                   MongoDB 6.0+ Aggregation Engine                       |   |
|   |   - $lookup (Unwind with preserveNullAndEmptyArrays)                    |   |
|   |   - $densify (Gap-free daily series over calendar date ranges)          |   |
|   |   - $setWindowFields ($rank for standard competition ranking)           |   |
|   +-------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------+
                                      |
                                      v
                 +-----------------------------------------+
                 |            MongoDB Collections          |
                 |  - employees (Identity & Shifts)        |
                 |  - attendance_logs (Punches & History)  |
                 +-----------------------------------------+
```

### Core Architecture Highlights
- **Decoupled Modularity**: Structured cleanly into `models/`, `pipelines/`, `routes/`, and `common/` utilities, initialised idempotently via FastAPI `lifespan`.
- **Database Boundary Cleanliness**: Client inputs and API outputs interact purely in integer epoch milliseconds. MongoDB stores all instants as native UTC BSON datetimes (`tz_aware=True`). Internal `_id` keys are never leaked to API responses.
- **Precision Arithmetic**: Replaces Python floating-point inaccuracies and banker's rounding (`round()`) with strict `decimal.Decimal` quantisation using `ROUND_HALF_UP`.
- **Database-Engineered Analytics**: All analytics are computed natively inside MongoDB aggregation stages (`$lookup`, `$densify`, `$setWindowFields`), avoiding memory bottlenecks on 100k+ documents.

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py                     # Application entry point & FastAPI setup
│   ├── config.py                   # Environment configuration & constants
│   ├── database.py                 # PyMongo client & idempotent index initialization
│   ├── common/
│   │   ├── __init__.py
│   │   ├── math_utils.py           # Half-up rounding, work hours & rate math
│   │   ├── serializers.py          # MongoDB BSON to API JSON serializers
│   │   └── time_utils.py           # Epoch ms validation, IST timezone & shift calculations
│   ├── models/
│   │   ├── __init__.py
│   │   ├── admin.py                # Pydantic schemas for explain endpoint
│   │   ├── analytics.py            # Pydantic schemas for monthly, summary, leaderboard & trend
│   │   ├── attendance.py           # Pydantic schemas for punch-in/out, logs & regularize
│   │   └── employee.py             # Pydantic schemas for employee CRUD & pagination
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── department_summary.py   # Cross-collection aggregation with zero-log headcount
│   │   ├── department_trend.py     # Gap-filling $densify pipeline
│   │   ├── employee_monthly.py     # Aggregation for employee monthly summary
│   │   └── leaderboard.py          # $setWindowFields competition ranking pipeline
│   └── routes/
│       ├── __init__.py
│       ├── admin.py                # GET /admin/explain/{endpoint}
│       ├── analytics.py            # Analytics endpoints
│       ├── attendance.py           # Punch-in, punch-out, list & regularization
│       ├── employees.py            # Employee creation & paginated directory
│       └── system.py               # GET /health probe
├── sample_data/
│   ├── employees.json              # Sample Extended JSON employee documents
│   └── attendance_logs.json        # Sample Extended JSON attendance logs
├── tests/
│   └── test_api.py                 # Comprehensive automated test suite (20 tests)
├── DATA_MODEL.md                   # Source data model specification
├── DECISIONS.md                    # Architectural decision records & tradeoffs
├── REVIEW.md                       # Comprehensive starter defect analysis & resolutions
├── openapi.yaml                    # OpenAPI 3.0.3 contract specification
├── requirements.txt                # Production dependencies
└── sample_seed.py                  # Seed script for Extended JSON sample data
```

---

## Database Schema & Data Model

The application interfaces with two core MongoDB collections: `employees` and `attendance_logs`.

### Collection: `employees`
Stores employee profile, assigned department, shift parameters, and hire date.

| Field | BSON Type | API Type | Constraints & Description |
|---|---|---|---|
| `_id` | `ObjectId` | *Internal* | Auto-generated by MongoDB. Never exposed in API responses. |
| `emp_code` | `string` | `string` | **Unique Business Key** (`EMP\d{4,6}`). Never changes. Indexed uniquely. |
| `name` | `string` | `string` | Employee full name (1 to 100 characters). |
| `email` | `string` | `string` | Valid corporate email address (max 120 characters). |
| `department`| `string` | `string` | Case-sensitive department name (1 to 50 characters). |
| `shift_start`| `string` | `string` | Scheduled shift start in IST `HH:MM` 24-hr format (e.g. `"09:30"`). |
| `shift_end` | `string` | `string` | Scheduled shift end in IST `HH:MM` 24-hr format (e.g. `"18:30"`). Must not equal `shift_start`. Overnight if `<= shift_start`. |
| `joined_on` | `string` | `string` | First calendar day of employment in `YYYY-MM-DD` (IST). |
| `created_at`| `date` | `integer` | Server clock creation timestamp (BSON Date in UTC, integer epoch ms in API). |

#### Example Document (`employees`)
```json
{
  "_id": {"$oid": "66895e34749f99f928e14b21"},
  "emp_code": "EMP0001",
  "name": "Asha Rao",
  "email": "asha@example.com",
  "department": "Engineering",
  "shift_start": "09:30",
  "shift_end": "18:30",
  "joined_on": "2026-01-05",
  "created_at": {"$date": "2026-01-05T04:30:00.000Z"}
}
```

---

### Collection: `attendance_logs`
Stores daily attendance records. Each document is addressed by the composite natural key `(emp_code, date)`. Exactly one document per employee per attendance date.

| Field | BSON Type | API Type | Constraints & Description |
|---|---|---|---|
| `_id` | `ObjectId` | *Internal* | Auto-generated by MongoDB. Omitted from API response. |
| `emp_code` | `string` | `string` | Foreign key reference to `employees.emp_code`. |
| `date` | `string` | `string` | Attendance calendar date in IST `YYYY-MM-DD` (R1). Natural key component. |
| `status` | `string` | `string` | Enum: `PRESENT`, `WFH`, `ON_DUTY`, `ABSENT`, `LEAVE`. |
| `punch_in` | `date` / `null` | `integer` / `null` | Instant when employee punched in. Null for `ABSENT`/`LEAVE`. |
| `punch_out` | `date` / `null` | `integer` / `null` | Instant when employee punched out. Null until punched out. |
| `work_hours`| `double` / `null` | `number` / `null` | `(punch_out - punch_in)` in seconds / 3600, rounded to 2 decimals half-up (R4). Null until punch-out. |
| `late_minutes`| `int` | `integer` | Whole minutes late relative to `shift_start` after 10-min grace (R2). Default 0. |
| `overtime_minutes`| `int` | `integer` | Whole minutes after `shift_end` if `>= 30`, otherwise 0 (R3). Default 0. |
| `half_day` | `bool` | `boolean` | True if `work_hours < 4.50` after punch out (R5). Default false. |
| `history` | `array` | `array` | Immutable audit log of manual corrections (PATCH). Default `[]`. |

#### Example Document (`attendance_logs`)
```json
{
  "_id": {"$oid": "6689622d749f99f928e14b22"},
  "emp_code": "EMP0003",
  "date": "2026-07-06",
  "status": "PRESENT",
  "punch_in": {"$date": "2026-07-06T04:35:00.000Z"},
  "punch_out": {"$date": "2026-07-06T13:40:00.000Z"},
  "work_hours": 9.08,
  "late_minutes": 35,
  "overtime_minutes": 40,
  "half_day": false,
  "history": []
}
```

---

### Audit History Schema
Audit entries are appended **only** when a record is updated via `PATCH /attendance/{emp_code}/{date}`. Punch-in and punch-out operations do **not** write to history.

```json
{
  "at": 1783400400000,
  "by": "hr.admin",
  "reason": "Biometric terminal sync issue",
  "changes": {
    "punch_in": {
      "from": 1783312500000,
      "to": 1783310400000
    },
    "late_minutes": {
      "from": 35,
      "to": 0
    },
    "work_hours": {
      "from": 9.08,
      "to": 9.67
    }
  }
}
```
*Note: Stored in MongoDB with BSON dates inside `changes` and converted to epoch ms on API serialization.*

---

## Indexing Strategy & Zero-COLLSCAN Guarantee

All indexes are created idempotently at application boot via FastAPI lifespan:

```python
def init_indexes() -> None:
  # employees collection
  db.employees.create_index(
      [("emp_code", 1)], unique=True, name="uniq_emp_code"
  )
  db.employees.create_index(
      [("department", 1), ("emp_code", 1)], name="idx_dept_emp_code"
  )
  db.employees.create_index([("joined_on", 1)], name="idx_joined_on")
  db.employees.create_index(
      [("department", 1), ("joined_on", 1)], name="idx_dept_joined_on"
  )

  # attendance_logs collection
  db.attendance_logs.create_index(
      [("emp_code", 1), ("date", 1)], unique=True, name="uniq_emp_date"
  )
  db.attendance_logs.create_index(
      [("emp_code", 1), ("punch_in", -1)], name="idx_emp_punch_in_desc"
  )
  db.attendance_logs.create_index(
      [("date", -1), ("emp_code", 1)], name="idx_date_desc_emp_asc"
  )
  db.attendance_logs.create_index(
      [("date", 1), ("late_minutes", 1)], name="idx_date_late_minutes"
  )
```

### Purpose of Each Index

| Collection | Index Key | Index Type | Query & Operational Purpose |
|---|---|---|---|
| `employees` | `{"emp_code": 1}` | **Unique** | Enforces employee code uniqueness; accelerates lookups by employee ID. |
| `employees` | `{"department": 1, "emp_code": 1}` | Compound | Backs filtered and sorted employee listings (`GET /employees?department=...`). |
| `employees` | `{"joined_on": 1}` | Single | Eliminates `COLLSCAN` on `department_summary` when querying without a department filter. |
| `employees` | `{"department": 1, "joined_on": 1}` | Compound | Backs `department_summary` with department filter and `department_trend` headcount filters. |
| `attendance_logs` | `{"emp_code": 1, "date": 1}` | **Unique** | Prevents duplicate daily punch-ins under concurrency; backs record lookups. |
| `attendance_logs` | `{"emp_code": 1, "punch_in": -1}` | Compound | Powers $O(1)$ sub-millisecond resolution of open punch-ins during `POST /attendance/punch-out`. |
| `attendance_logs` | `{"date": -1, "emp_code": 1}` | Compound | Serves sorted attendance pagination (`GET /attendance`) and date-range filters. |
| `attendance_logs` | `{"date", 1, "late_minutes", 1}` | Compound | Accelerates `late_leaderboard` aggregation matching by date and non-zero late minutes. |

> **Verification**: All five explainable endpoints (`attendance_list`, `employee_monthly`, `department_summary`, `late_leaderboard`, `department_trend`) demonstrate **100% `IXSCAN` and zero `COLLSCAN`** verified against execution statistics.

---

## Business Rules (R1 – R10)

| Rule | Name | Detailed Implementation Specification |
|---|---|---|
| **R1** | **Time Zone & Attendance Date** | Shift times and dates are in IST (UTC+05:30). A record's date is the IST calendar date of `punch_in`. For overnight shifts (`shift_end <= shift_start`, e.g. 22:00–06:00): a punch-in before `shift_end` IST belongs to the shift that started the previous calendar day. All timestamps are truncated to whole seconds (`ms // 1000 * 1000`) before calculations. |
| **R2** | **Late Minutes** | Grace period is 10 minutes (600 seconds). A punch-in is late **only if strictly more than 10:00** after `shift_start`. If late, `late_minutes = floor(seconds since shift_start / 60)`. Otherwise 0. (Example with shift 09:30: `09:40:00` -> 0; `09:40:01` -> 10; `10:15:59` -> 45). |
| **R3** | **Overtime** | `overtime_minutes = floor(seconds from shift_end to punch_out / 60)`, counted only if that is **at least 30 minutes**; otherwise 0. For overnight shifts, `shift_end` falls on the next calendar day. |
| **R4** | **Work Hours** | `(punch_out - punch_in) in seconds / 3600`, rounded to 2 decimal places **half-up** using Python `Decimal`. Value remains `null` until punch-out occurs. |
| **R5** | **Half Day** | After punch-out, `half_day = true` when the rounded `work_hours < 4.50`. A half day counts as `0.5` of a present day. |
| **R6** | **Presence** | `PRESENT`, `WFH`, and `ON_DUTY` count as present. `ABSENT` and `LEAVE` do not. |
| **R7** | **Working Days** | Monday through Friday only (no holiday calendar). For mid-month joiners, working days count from `max(month_start, joined_on)`. `present_days` counts only Monday–Friday logs; weekend logs still add to total late and overtime minutes. |
| **R8** | **Reported Precision** | Counts and work hours rounded to 2 decimal places half-up; rates (`attendance_rate`, `moving_avg_7d`) rounded to 4 decimal places half-up. |
| **R9** | **Headcount** | Department employees whose `joined_on <= end_of_period`, **whether or not they have attendance logs**. |
| **R10**| **Pagination** | `page` starts at 1. `page_size` defaults to 20, max 100. `total` accurately reflects filtered document count. |

---

## API Endpoints Reference

### 1. System & Health
#### `GET /health`
- **Summary**: Readiness probe.
- **Behavior**: Pings MongoDB using `db.command("ping")`. Returns 200 if connected; returns 503 if unreachable.
- **Response `200`**: `{"status": "ok"}`
- **Response `503`**: `{"detail": "Database connection unavailable"}`

---

### 2. Employees Directory
#### `POST /employees`
- **Summary**: Creates a new employee.
- **Request Body**:
```json
{
  "emp_code": "EMP0007",
  "name": "Kiran Patel",
  "email": "kiran@example.com",
  "department": "Engineering",
  "shift_start": "09:30",
  "shift_end": "18:30",
  "joined_on": "2026-07-01"
}
```
- **Responses**:
  - `201 Created`: Returns created employee document with server-generated `created_at` timestamp.
  - `409 Conflict`: `emp_code` already exists.
  - `422 Unprocessable Entity`: Validation failure (e.g. invalid format, `shift_start == shift_end`).

#### `GET /employees`
- **Summary**: Lists employees paginated, sorted by `emp_code` ascending.
- **Query Parameters**:
  - `department` (optional, string): Case-sensitive filter.
  - `page` (optional, integer, default 1): Page number.
  - `page_size` (optional, integer, default 20, max 100): Page size.
- **Response `200`**:
```json
{
  "items": [
    {
      "emp_code": "EMP0001",
      "name": "Asha Rao",
      "email": "asha@example.com",
      "department": "Engineering",
      "shift_start": "09:30",
      "shift_end": "18:30",
      "joined_on": "2026-01-05",
      "created_at": 1767587400000
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

### 3. Attendance & Regularization

#### `POST /attendance/punch-in`
- **Summary**: Records an employee's punch-in for the day.
- **Request Body**:
```json
{
  "emp_code": "EMP0001",
  "punched_at": 1783310280000,
  "status": "PRESENT"
}
```
- **Behavior**: Determines attendance date under R1 (handling overnight shifts), evaluates late minutes (R2).
- **Concurrency**: Guaranteed race-safe via `(emp_code, date)` unique index. Exactly one request gets 201; concurrent duplicates get 409.
- **Responses**: `201 Created`, `404 Not Found` (unknown employee), `409 Conflict`, `422 Unprocessable Entity`.

#### `POST /attendance/punch-out`
- **Summary**: Closes the most recent open attendance record where `punch_in <= punched_at`.
- **Request Body**:
```json
{
  "emp_code": "EMP0001",
  "punched_at": 1783345200000
}
```
- **Behavior**: Atomically updates the targeted document ensuring `punch_out` was null. Computes `work_hours` (R4), `overtime_minutes` (R3), and `half_day` (R5).
- **Responses**: `200 OK`, `404 Not Found` (unknown employee or no open punch-in), `409 Conflict` (already punched out), `422 Unprocessable Entity` (`punched_at <= punch_in` or `> 24 hours`).

#### `GET /attendance`
- **Summary**: Paginated listing of attendance logs, sorted by `date` descending, then `emp_code` ascending.
- **Query Parameters**: `emp_code`, `date_from`, `date_to`, `status`, `page`, `page_size`.
- **Response `200`**:
```json
{
  "items": [
    {
      "emp_code": "EMP0001",
      "date": "2026-07-06",
      "status": "PRESENT",
      "punch_in": 1783310280000,
      "punch_out": 1783343100000,
      "work_hours": 9.12,
      "late_minutes": 0,
      "overtime_minutes": 0,
      "half_day": false,
      "history": []
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

#### `PATCH /attendance/{emp_code}/{date}`
- **Summary**: Regularizes (corrects) a single day's attendance record.
- **Request Body**:
```json
{
  "punch_in": 1783310400000,
  "reason": "Biometric terminal sync issue",
  "regularized_by": "hr.admin"
}
```
- **Behavior**: Recomputes all derived fields (`late_minutes`, `work_hours`, `overtime_minutes`, `half_day`), validates that punch times match attendance date, and appends a single history audit entry.
- **Concurrency**: Guarded with array size matching to prevent concurrent lost updates.
- **Responses**: `200 OK`, `404 Not Found`, `409 Conflict` (concurrent edit), `422 Unprocessable Entity` (no change, or punch times supplied with ABSENT/LEAVE).

---

### 4. Analytics & Aggregation Pipelines

#### `GET /analytics/employees/{emp_code}/monthly`
- **Summary**: Monthly attendance summary for a specific employee.
- **Query Parameters**: `month` (`YYYY-MM`).
- **Response `200`**:
```json
{
  "emp_code": "EMP0001",
  "month": "2026-07",
  "working_days": 23,
  "present_days": 2.0,
  "leave_days": 0,
  "late_count": 0,
  "total_late_minutes": 0,
  "total_overtime_minutes": 0,
  "attendance_pct": 8.70
}
```

#### `GET /analytics/departments/summary`
- **Summary**: Cross-collection department summary for a month. Includes employees with zero logs in headcount (R9).
- **Query Parameters**: `month` (`YYYY-MM`), `department` (optional).
- **Response `200`**:
```json
{
  "month": "2026-07",
  "items": [
    {
      "department": "Engineering",
      "headcount": 2,
      "present_days": 3.0,
      "avg_work_hours": 9.04,
      "late_count": 0,
      "total_late_minutes": 0,
      "leave_count": 0,
      "on_duty_count": 0
    }
  ]
}
```

#### `GET /analytics/leaderboard/late`
- **Summary**: Ranks late-comers using standard competition ranking (ties share a rank, next rank is skipped: 1, 2, 2, 4).
- **Query Parameters**: `month` (`YYYY-MM`), `limit` (default 10, max 50), `department` (optional).
- **Behavior**: Returns all employees where `rank <= limit`. May return more than `limit` items if boundary ties occur.
- **Response `200`**:
```json
{
  "month": "2026-07",
  "items": [
    {
      "rank": 1,
      "emp_code": "EMP0003",
      "name": "Neha Iyer",
      "department": "Sales",
      "total_late_minutes": 35,
      "late_count": 1
    }
  ]
}
```

#### `GET /analytics/departments/{department}/trend`
- **Summary**: Daily calendar time series with `$densify` gap filling and 7-day moving average.
- **Query Parameters**: `from` (`YYYY-MM-DD`), `to` (`YYYY-MM-DD`). Max 92 days.
- **Response `200`**:
```json
{
  "department": "Sales",
  "items": [
    {
      "date": "2026-07-06",
      "is_working_day": true,
      "headcount": 2,
      "present_count": 1.0,
      "late_count": 1,
      "attendance_rate": 0.5000,
      "moving_avg_7d": 0.5000
    },
    {
      "date": "2026-07-07",
      "is_working_day": true,
      "headcount": 2,
      "present_count": 0.5,
      "late_count": 0,
      "attendance_rate": 0.2500,
      "moving_avg_7d": 0.3750
    }
  ]
}
```

---

### 5. Admin Query Plan Explain

#### `GET /admin/explain/{endpoint}`
- **Summary**: Executes MongoDB `explain("executionStats")` on the exact aggregation pipeline or query for the target endpoint.
- **Supported Endpoints**: `attendance_list`, `employee_monthly`, `department_summary`, `late_leaderboard`, `department_trend`.
- **Query Parameters**: Mirrors parameters of the target endpoint.
- **Response `200`**:
```json
{
  "endpoint": "late_leaderboard",
  "collection": "attendance_logs",
  "explain": {
    "stages": [ ... ],
    "executionStats": { ... }
  }
}
```

---

## Concurrency & Race Condition Handling

1. **Simultaneous Punch-Ins**:
   - Both requests query and validate concurrently.
   - Insert uses `db.attendance_logs.insert_one(doc)`.
   - The unique compound index on `{"emp_code": 1, "date": 1}` guarantees that only one request succeeds (HTTP 201). The second fails with a `DuplicateKeyError`, handled to return HTTP 409 Conflict.
2. **Simultaneous Punch-Outs**:
   - Handled atomically with `find_one_and_update(filter={"_id": target["_id"], "punch_out": None}, ...)`
   - Only the first caller matches `punch_out: None` and updates the record (HTTP 200). The subsequent caller finds no matching document and receives HTTP 409 Conflict.
3. **Concurrent Regularizations**:
   - Utilizes optimistic concurrency control on history length: `{"_id": doc_id, "history": {"$size": len(existing_history)}}`.
   - If two managers attempt to regularize simultaneously, only one succeeds; the second receives HTTP 409 Conflict, preventing lost audit entries.

---

## Local Setup & Execution

### Prerequisites
- Python 3.11+
- MongoDB 6.0+ (Local Community Server, Docker, or MongoDB Atlas M0)

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/devloperYash/Attendance-Management-API.git
cd Attendance-Management-API

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Set `MONGO_URI` and `MONGO_DB` (or create a `.env` file):
```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```
*(If running MongoDB in Docker: `docker run -d -p 27017:27017 --name mongo-attendance mongo:7`)*

### 3. Seed Sample Data
```bash
python sample_seed.py
```

### 4. Start Server
```bash
uvicorn app.main:app --port 8000 --reload
```
Interactive API docs are available at `http://localhost:8000/docs`.

---

## Running Test Suite

Execute the automated test suite with pytest:
```bash
python -m pytest
```

### Test Suite Coverage Highlights
- **Health Check Probe**: Verifies database ping detection.
- **Employee Creation & Duplication**: Validates duplicate rejection and `shift_start != shift_end`.
- **Punch-In Concurrency**: Simulates multi-threaded racing punch-ins yielding exactly one 201 and 409s.
- **Punch-Out Lifecycle**: Tests 24-hr boundaries, overnight rollover, and duplicate punch-out conflicts.
- **Regularization Auditing**: Asserts audit entry generation, unchanged field rejections, and ABSENT/LEAVE rules.
- **Analytics Aggregations**: Tests employee monthly summary, cross-collection department summary with zero-log headcount, and `$densify` department trends.
- **Competition Leaderboard**: Validates standard competition ranking (1, 2, 2, 4) with ties at limit cutoffs.
- **Explain Plans Verification**: Asserts that all five explain queries use index scans (`IXSCAN`) and contain **zero `COLLSCAN`**.

---

## Submission Files & Verification

- `app/main.py`: Main application entry point running with `uvicorn app.main:app --port 8000`.
- `requirements.txt`: Clean dependency list without extraneous packages.
- `REVIEW.md`: Comprehensive review table listing 12 identified starter defects and non-defects.
- `DECISIONS.md`: Concise, plain-language answers (~200 words) addressing all 5 architectural evaluation prompts.
- `README.md`: In-depth system and schema documentation.
