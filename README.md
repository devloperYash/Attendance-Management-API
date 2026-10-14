# Employee Attendance & Analytics API

A production-grade **Employee Attendance & Analytics API** built with **Python**, **FastAPI**, and **MongoDB**. Supports punch-in/punch-out with business-rule enforcement, manual corrections with a full audit trail, and analytics powered by MongoDB aggregation pipelines.

> Built for the **HROne Software Engineer Trainee** assignment.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Running the Server](#running-the-server)
- [Seeding Sample Data](#seeding-sample-data)
- [Project Structure](#project-structure)
- [MongoDB Data Model](#mongodb-data-model)
  - [employees Collection](#1-employees-collection)
  - [attendance_logs Collection](#2-attendance_logs-collection)
  - [Indexes](#3-indexes)
- [API Endpoints](#api-endpoints)
  - [System](#system)
  - [Employees](#employees)
  - [Attendance](#attendance)
  - [Analytics](#analytics)
  - [Admin](#admin)
- [Business Rules (R1–R10)](#business-rules-r1r10)
- [Conventions](#conventions)
- [Architecture & Design Decisions](#architecture--design-decisions)
- [What is Missing / Known Limitations](#what-is-missing--known-limitations)

---

## Tech Stack

| Layer        | Technology                  |
| ------------ | --------------------------- |
| Language     | Python 3.11+                |
| Framework    | FastAPI ≥ 0.110             |
| ASGI Server  | Uvicorn ≥ 0.29              |
| Database     | MongoDB 6.0+                |
| Driver       | PyMongo ≥ 4.7 (with SRV)   |
| Validation   | Pydantic ≥ 2.6              |
| Config       | python-dotenv ≥ 1.0         |

---

## Prerequisites

- **Python 3.11** or newer
- **Git**
- **MongoDB 6.0+** — local Docker container or a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster

---

## Setup & Installation

```bash
# 1. Clone the repository
git clone https://github.com/devloperYash/Attendance-Management-API.git
cd Attendance-Management-API

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
#    Create a .env file in the project root (NOT committed to Git):
echo MONGO_URI=mongodb://localhost:27017 > .env
echo MONGO_DB=attendance_db >> .env
```

| Variable   | Default                      | Description                        |
| ---------- | ---------------------------- | ---------------------------------- |
| `MONGO_URI`| `mongodb://localhost:27017`  | MongoDB connection string          |
| `MONGO_DB` | `attendance_db`              | Database name                      |

---

## Running the Server

```bash
uvicorn app.main:app --port 8000 --reload
```

The API will be available at **http://localhost:8000**.

- **Interactive docs (Swagger UI):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

On startup, the application **idempotently creates all required indexes** on the `employees` and `attendance_logs` collections.

---

## Seeding Sample Data

Load the nine sample documents from `sample_data/` into MongoDB:

```bash
python sample_seed.py
```

Alternatively, use `mongoimport`:

```bash
mongoimport --db attendance_db --collection employees --jsonArray --file sample_data/employees.json
mongoimport --db attendance_db --collection attendance_logs --jsonArray --file sample_data/attendance_logs.json
```

> **Note:** The sample data demonstrates document shapes only. The grader's dataset is much larger and covers edge cases (ties, weekends, mid-month joins, employees with zero logs, etc.).

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application & lifespan (index creation)
│   ├── config.py                # Environment variables & constants (IST, limits)
│   ├── database.py              # MongoClient singleton, ping, index initialization
│   ├── models/
│   │   ├── employee.py          # Pydantic: EmployeeCreate, EmployeeOut, EmployeePage
│   │   ├── attendance.py        # Pydantic: PunchIn/Out, Regularize, AttendanceRecord
│   │   ├── analytics.py         # Pydantic: EmployeeMonthly, DeptSummary, Leaderboard, Trend
│   │   └── admin.py             # Pydantic: ExplainResult
│   ├── routes/
│   │   ├── system.py            # GET /health
│   │   ├── employees.py         # POST & GET /employees
│   │   ├── attendance.py        # Punch-in, punch-out, list, regularize
│   │   ├── analytics.py         # Monthly, dept summary, leaderboard, trend
│   │   └── admin.py             # GET /admin/explain/{endpoint}
│   ├── pipelines/
│   │   ├── employee_monthly.py  # Aggregation: per-employee monthly stats
│   │   ├── department_summary.py# Aggregation: department-level summary
│   │   ├── leaderboard.py       # Aggregation: late-comers ranking with $rank
│   │   └── department_trend.py  # Aggregation: daily trend with $densify
│   └── common/
│       ├── time_utils.py        # IST conversion, epoch ↔ datetime, late/overtime
│       ├── math_utils.py        # round_half_up, work_hours, half_day, attendance %
│       └── serializers.py       # MongoDB doc → API response (strip _id, convert dates)
├── tests/
│   └── test_api.py              # Automated test suite
├── sample_data/                 # Sample JSON for employees & attendance_logs
├── sample_seed.py               # Script to seed sample data into MongoDB
├── openapi.yaml                 # Full OpenAPI 3.0.3 contract
├── DATA_MODEL.md                # MongoDB schema documentation
├── REVIEW.md                    # Starter-code defect review (12 defects found)
├── DECISIONS.md                 # Design decisions & trade-offs
├── requirements.txt             # Python dependencies
├── .gitignore
└── README.md                    # ← You are here
```

---

## MongoDB Data Model

### 1. `employees` Collection

One document per employee. `emp_code` is the business identifier (not `_id`).

| Field          | Type              | Description                                              |
| -------------- | ----------------- | -------------------------------------------------------- |
| `_id`          | ObjectId          | Internal MongoDB identifier. Never exposed via the API.  |
| `emp_code`     | string            | **Primary business key.** Unique, immutable. e.g. `EMP0001` |
| `name`         | string            | Employee full name                                       |
| `email`        | string            | Email address                                            |
| `department`   | string            | Case-sensitive department name                           |
| `shift_start`  | string `"HH:MM"`  | IST shift start time (24-hour)                           |
| `shift_end`    | string `"HH:MM"`  | IST shift end time. `≤ shift_start` → overnight shift    |
| `joined_on`    | string `"YYYY-MM-DD"` | First day of employment                             |
| `created_at`   | BSON Date (UTC)   | Server-set creation timestamp                            |

**Sample document:**
```json
{
  "emp_code": "EMP0001",
  "name": "Asha Rao",
  "email": "asha@example.com",
  "department": "Engineering",
  "shift_start": "09:30",
  "shift_end": "18:30",
  "joined_on": "2026-01-05",
  "created_at": { "$date": "2026-01-05T04:30:00Z" }
}
```

### 2. `attendance_logs` Collection

At most **one document per (`emp_code`, `date`)**. Records are addressed by the natural key `(emp_code, date)`, not by `_id`.

| Field              | Type                    | Description                                           |
| ------------------ | ----------------------- | ----------------------------------------------------- |
| `_id`              | ObjectId                | Internal. Not part of the API.                        |
| `emp_code`         | string                  | References `employees.emp_code`                       |
| `date`             | string `"YYYY-MM-DD"`   | Attendance day in IST (R1)                            |
| `status`           | string (enum)           | `PRESENT` \| `WFH` \| `ON_DUTY` \| `ABSENT` \| `LEAVE` |
| `punch_in`         | BSON Date \| null       | Punch-in instant (UTC). Null for ABSENT/LEAVE.        |
| `punch_out`        | BSON Date \| null       | Null until employee punches out.                      |
| `work_hours`       | double \| null          | **Computed** (R4). Null until punch-out.              |
| `late_minutes`     | int                     | **Computed** (R2). Default 0.                         |
| `overtime_minutes` | int                     | **Computed** (R3). Default 0.                         |
| `half_day`         | bool                    | **Computed** (R5). Default false.                     |
| `history`          | array of HistoryEntry   | Audit trail (corrections only). Default `[]`.         |

**Status values:**

| Status     | Meaning                       | Punch times      | Counts as present |
| ---------- | ----------------------------- | ---------------- | ----------------- |
| `PRESENT`  | Worked on site                | `punch_in` req.  | ✅ Yes            |
| `WFH`      | Worked from home              | `punch_in` req.  | ✅ Yes            |
| `ON_DUTY`  | Official duty away            | `punch_in` req.  | ✅ Yes            |
| `ABSENT`   | Did not work, no leave        | Both null        | ❌ No             |
| `LEAVE`    | On approved leave             | Both null        | ❌ No             |

**History entry (audit trail):**

| Field     | Type        | Description                                             |
| --------- | ----------- | ------------------------------------------------------- |
| `at`      | BSON Date   | When the correction was made                            |
| `by`      | string      | Who made it (free text)                                 |
| `reason`  | string      | Justification for the correction                        |
| `changes` | object      | Changed fields only, each with `{ "from": ..., "to": ... }` |

**Sample document (with history):**
```json
{
  "emp_code": "EMP0001",
  "date": "2026-07-07",
  "status": "PRESENT",
  "punch_in": { "$date": "2026-07-07T03:58:00Z" },
  "punch_out": { "$date": "2026-07-07T13:00:00Z" },
  "work_hours": 9.03,
  "late_minutes": 0,
  "overtime_minutes": 0,
  "half_day": false,
  "history": [
    {
      "at": { "$date": "2026-07-08T05:00:00Z" },
      "by": "hr.admin",
      "reason": "biometric glitch",
      "changes": {
        "punch_in": {
          "from": { "$date": "2026-07-07T04:35:00Z" },
          "to": { "$date": "2026-07-07T03:58:00Z" }
        },
        "late_minutes": { "from": 35, "to": 0 },
        "work_hours": { "from": 8.42, "to": 9.03 }
      }
    }
  ]
}
```

### 3. Indexes

All indexes are created idempotently at application startup:

**`employees` collection:**

| Index                                    | Type   | Purpose                                 |
| ---------------------------------------- | ------ | --------------------------------------- |
| `{ emp_code: 1 }`                        | Unique | Enforce unique employee identity        |
| `{ department: 1, emp_code: 1 }`         | Normal | Filtered directory listings             |
| `{ joined_on: 1 }`                       | Normal | Headcount period filters                |
| `{ department: 1, joined_on: 1 }`        | Normal | Department-filtered headcount queries   |

**`attendance_logs` collection:**

| Index                                    | Type   | Purpose                                              |
| ---------------------------------------- | ------ | ---------------------------------------------------- |
| `{ emp_code: 1, date: 1 }`              | Unique | One record per employee per day, concurrent safety   |
| `{ emp_code: 1, punch_in: -1 }`         | Normal | Fast punch-out target lookup                         |
| `{ date: -1, emp_code: 1 }`             | Normal | Sorted attendance pagination                         |
| `{ date: 1, late_minutes: 1 }`          | Normal | Late leaderboard acceleration                        |

---

## API Endpoints

All instants in requests and responses are **epoch milliseconds** (`int64`). All calendar dates are `YYYY-MM-DD` strings (IST). `_id` is never exposed.

### System

| Method | Path      | Description            | Success | Errors |
| ------ | --------- | ---------------------- | ------- | ------ |
| `GET`  | `/health` | Readiness probe (pings MongoDB) | `200` | `503`  |

### Employees

| Method | Path         | Description                        | Success | Errors       |
| ------ | ------------ | ---------------------------------- | ------- | ------------ |
| `POST` | `/employees` | Create a new employee              | `201`   | `409`, `422` |
| `GET`  | `/employees` | List employees (paginated, filterable by department) | `200` | `422` |

**Create Employee — Request Body:**
```json
{
  "emp_code": "EMP0001",
  "name": "Asha Rao",
  "email": "asha@example.com",
  "department": "Engineering",
  "shift_start": "09:30",
  "shift_end": "18:30",
  "joined_on": "2026-01-05"
}
```

**Create Employee — Response (201):**
```json
{
  "emp_code": "EMP0001",
  "name": "Asha Rao",
  "email": "asha@example.com",
  "department": "Engineering",
  "shift_start": "09:30",
  "shift_end": "18:30",
  "joined_on": "2026-01-05",
  "created_at": 1783312500000
}
```

**List Employees — Query Parameters:**

| Param        | Type    | Default | Description                  |
| ------------ | ------- | ------- | ---------------------------- |
| `department` | string  | —       | Exact, case-sensitive filter |
| `page`       | int     | 1       | Page number (≥ 1)           |
| `page_size`  | int     | 20      | Items per page (1–100)      |

### Attendance

| Method  | Path                           | Description                         | Success | Errors            |
| ------- | ------------------------------ | ----------------------------------- | ------- | ----------------- |
| `POST`  | `/attendance/punch-in`         | Record a punch-in                   | `201`   | `404`, `409`, `422` |
| `POST`  | `/attendance/punch-out`        | Record a punch-out                  | `200`   | `404`, `409`, `422` |
| `GET`   | `/attendance`                  | List records (paginated, filterable)| `200`   | `422`             |
| `PATCH` | `/attendance/{emp_code}/{date}`| Regularize (manually correct) a record | `200` | `404`, `409`, `422` |

**Punch-In — Request Body:**
```json
{
  "emp_code": "EMP0001",
  "punched_at": 1783312500000,
  "status": "PRESENT"
}
```
> `punched_at` defaults to current time if omitted. `status` defaults to `PRESENT`. Only `PRESENT`, `WFH`, `ON_DUTY` accepted.

**Punch-Out — Request Body:**
```json
{
  "emp_code": "EMP0001",
  "punched_at": 1783345200000
}
```
> Closes the most recent record whose `punch_in ≤ punched_at`. Must be within 24 hours of punch-in.

**Regularize — Request Body:**
```json
{
  "reason": "biometric glitch",
  "regularized_by": "hr.admin",
  "status": "PRESENT",
  "punch_in": 1783310280000,
  "punch_out": 1783342800000
}
```
> Omitted fields remain unchanged. Appends one entry to `history` with only the fields that actually changed. A request that changes nothing returns 422.

**Attendance Record — Response:**
```json
{
  "emp_code": "EMP0001",
  "date": "2026-07-07",
  "status": "PRESENT",
  "punch_in": 1783310280000,
  "punch_out": 1783342800000,
  "work_hours": 9.03,
  "late_minutes": 0,
  "overtime_minutes": 0,
  "half_day": false,
  "history": []
}
```

**List Attendance — Query Parameters:**

| Param       | Type   | Default | Description                                |
| ----------- | ------ | ------- | ------------------------------------------ |
| `emp_code`  | string | —       | Filter by employee                         |
| `date_from` | string | —       | Start date inclusive (`YYYY-MM-DD`)         |
| `date_to`   | string | —       | End date inclusive (`YYYY-MM-DD`)           |
| `status`    | string | —       | Filter by status                           |
| `page`      | int    | 1       | Page number (≥ 1)                          |
| `page_size` | int    | 20      | Items per page (1–100)                     |

### Analytics

All analytics are backed by **MongoDB aggregation pipelines** — no in-memory computation.

| Method | Path                                           | Description                              | Success | Errors       |
| ------ | ---------------------------------------------- | ---------------------------------------- | ------- | ------------ |
| `GET`  | `/analytics/employees/{emp_code}/monthly`      | Monthly attendance summary for one employee | `200` | `404`, `422` |
| `GET`  | `/analytics/departments/summary`               | Department summary for a month           | `200`   | `422`        |
| `GET`  | `/analytics/leaderboard/late`                  | Late-comers leaderboard (ranked)         | `200`   | `422`        |
| `GET`  | `/analytics/departments/{department}/trend`    | Daily attendance trend (gap-filled)      | `200`   | `404`, `422` |

**Employee Monthly — `GET /analytics/employees/{emp_code}/monthly?month=2026-07`**
```json
{
  "emp_code": "EMP0001",
  "month": "2026-07",
  "working_days": 23,
  "present_days": 20.5,
  "leave_days": 2,
  "late_count": 3,
  "total_late_minutes": 45,
  "total_overtime_minutes": 120,
  "attendance_pct": 89.13
}
```

**Department Summary — `GET /analytics/departments/summary?month=2026-07`**
```json
{
  "month": "2026-07",
  "items": [
    {
      "department": "Engineering",
      "headcount": 15,
      "present_days": 280.5,
      "avg_work_hours": 8.45,
      "late_count": 12,
      "total_late_minutes": 340,
      "leave_count": 5,
      "on_duty_count": 3
    }
  ]
}
```

**Late Leaderboard — `GET /analytics/leaderboard/late?month=2026-07&limit=5`**
```json
{
  "month": "2026-07",
  "items": [
    {
      "rank": 1,
      "emp_code": "EMP0003",
      "name": "Vikram Singh",
      "department": "Engineering",
      "total_late_minutes": 120,
      "late_count": 5
    }
  ]
}
```
> Uses standard competition ranking (1, 2, 2, 4). `limit` applies to rank, not row count — ties may push results beyond `limit`.

**Department Trend — `GET /analytics/departments/{department}/trend?from=2026-07-01&to=2026-07-31`**
```json
{
  "department": "Engineering",
  "items": [
    {
      "date": "2026-07-01",
      "is_working_day": true,
      "headcount": 15,
      "present_count": 14.5,
      "late_count": 2,
      "attendance_rate": 0.9667,
      "moving_avg_7d": 0.9667
    }
  ]
}
```
> Returns **one row per calendar day** (including weekends/gaps) using MongoDB's `$densify`. Max range: 92 days.

### Admin

| Method | Path                           | Description                              | Success | Errors |
| ------ | ------------------------------ | ---------------------------------------- | ------- | ------ |
| `GET`  | `/admin/explain/{endpoint}`    | MongoDB `executionStats` explain output  | `200`   | `422`  |

Accepts the same query parameters as the endpoint it explains. Valid endpoint values: `attendance_list`, `employee_monthly`, `department_summary`, `late_leaderboard`, `department_trend`.

---

## Business Rules (R1–R10)

| Rule | Summary |
| ---- | ------- |
| **R1** | **Time zone & attendance date.** All shift times and dates are IST (UTC+05:30). Attendance `date` = IST calendar date of `punch_in`. For overnight shifts (`shift_end ≤ shift_start`), a punch-in before `shift_end` belongs to the previous day. Instants are truncated to whole seconds before storage. |
| **R2** | **Late.** Grace period = 10 minutes. Late only if punch-in is **strictly more than** 10:00 after `shift_start`. When late, `late_minutes` = floor minutes since `shift_start` (not since grace end). Examples for 09:30 shift: 09:40:00 → 0, 09:40:01 → 10, 10:15:59 → 45. |
| **R3** | **Overtime.** Floor minutes between `shift_end` and `punch_out`, counted only when ≥ 30; otherwise 0. |
| **R4** | **Work hours.** `(punch_out − punch_in)` in seconds ÷ 3600, rounded to 2 decimals **half-up** (not banker's rounding). `null` until punch-out. |
| **R5** | **Half day.** `half_day = true` when rounded `work_hours < 4.50`. A half day counts as 0.5 of a present day. |
| **R6** | **Presence.** `PRESENT`, `WFH`, `ON_DUTY` count as present. `ABSENT`, `LEAVE` do not. |
| **R7** | **Working days.** Mon–Fri, no holiday calendar. For employees who joined mid-month, count from `joined_on`. `present_days` only counts Mon–Fri records. |
| **R8** | **Rounding.** 2 decimals half-up for values; 4 decimals half-up for rates. |
| **R9** | **Headcount.** Employees with `joined_on ≤ period end`, whether or not they have any logs. |
| **R10** | **Pagination.** `page` starts at 1. `page_size` max 100, default 20. `total` reflects applied filters. |

---

## Conventions

- **Employees are identified by `emp_code`** — a customer-generated business code (e.g., `EMP0001`). It is **not** MongoDB's `_id`. The `_id` field never appears in any request or response.
- **Instants are epoch milliseconds** — every point in time (`punch_in`, `punch_out`, `created_at`, `history[].at`, values inside `history[].changes`) is an `int64` count of milliseconds since Unix epoch. Values that look like seconds (below `100,000,000,000`), floats, or strings are rejected with `422`.
- **Calendar values are strings** — dates are `YYYY-MM-DD`, months are `YYYY-MM`, shift times are `HH:MM` (24-hour, IST).
- **Derived fields are read-only** — `work_hours`, `late_minutes`, `overtime_minutes`, `half_day` are computed by the API from punch times, shift, and rules R2–R5. They never appear in request bodies. For analytics, the **stored values** are read directly — they are not recomputed from punch times.
- **Errors** follow FastAPI's default body: `{"detail": "..."}`. Validation failures return `422`.

---

## Architecture & Design Decisions

1. **Concurrency Safety** — Unique compound indexes (`emp_code + date`) and atomic `find_one_and_update` operations handle concurrent punch-ins, punch-outs, and regularizations. No check-then-insert patterns are used. `DuplicateKeyError` is caught and translated to `409 Conflict`.

2. **Aggregation-First Analytics** — All four analytics endpoints use MongoDB aggregation pipelines (with `$lookup`, `$rank`, `$densify`) instead of pulling data into Python. This keeps the API fast even on 100k+ records.

3. **Audit Trail Integrity** — The `history` array is append-only. Concurrent corrections are detected via `$size`-based optimistic locking on the history array; the loser gets `409 Conflict`.

4. **Timezone-Aware Client** — `MongoClient` is initialized with `tz_aware=True`, ensuring all BSON dates are returned as timezone-aware UTC datetimes. IST conversion is applied explicitly.

5. **Proper Rounding** — Python's `decimal.Decimal` with `ROUND_HALF_UP` quantization is used instead of built-in `round()` (which uses banker's rounding).

For the full list of design decisions, see [DECISIONS.md](DECISIONS.md).

For the full code review of the starter template (12 defects found and fixed), see [REVIEW.md](REVIEW.md).

---

## What is Missing / Known Limitations

- **Authentication & Authorization** — Intentionally omitted per the assignment scope. The `regularized_by` field is free-text with no identity verification.
- **Dockerfile** — Not included per submission guidelines.
- **Holiday Calendar** — Working days are Mon–Fri only; no public holiday support (as specified).
- **Bulk Operations** — No batch punch-in/out endpoint. Each operation is per-employee.
- **Real-time Notifications** — No WebSocket or SSE support for live attendance tracking.

---

## Running Tests

```bash
# Ensure MongoDB is running, then:
pytest tests/ -v
```

---

*Built with ❤️ by Yash*
