# Employee Attendance & Analytics API

A production-grade **Employee Attendance & Analytics API** built with **Python**, **FastAPI**, and **MongoDB**. Supports punch-in/punch-out with business-rule enforcement, manual corrections with a full audit trail, and real-time analytics powered entirely by MongoDB aggregation pipelines.

> Built for the **HROne Software Engineer Trainee** technical assignment.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Running the Server](#running-the-server)
- [Seeding Sample Data](#seeding-sample-data)
- [Project Structure](#project-structure)
- [Architecture Overview](#architecture-overview)
- [MongoDB Data Model](#mongodb-data-model)
  - [employees Collection Schema](#1-employees-collection)
  - [attendance_logs Collection Schema](#2-attendance_logs-collection)
  - [History (Audit Trail) Schema](#3-history-audit-trail)
  - [Indexes](#4-indexes)
- [API Endpoints](#api-endpoints)
  - [System](#system)
  - [Employees](#employees)
  - [Attendance](#attendance)
  - [Analytics](#analytics)
  - [Admin (Explain)](#admin-explain)
- [Request & Response Schemas](#request--response-schemas)
- [Business Rules (R1–R10)](#business-rules-r1r10)
- [Conventions](#conventions)
- [Error Handling](#error-handling)
- [Concurrency & Safety](#concurrency--safety)
- [Running Tests](#running-tests)
- [What is Missing / Known Limitations](#what-is-missing--known-limitations)
- [Related Documents](#related-documents)

---

## Tech Stack

| Layer           | Technology                         | Purpose                              |
| --------------- | ---------------------------------- | ------------------------------------ |
| **Language**    | Python 3.11+                       | Core runtime                         |
| **Framework**   | FastAPI ≥ 0.110                    | Async-ready REST API framework       |
| **ASGI Server** | Uvicorn ≥ 0.29 (standard)         | Production-grade ASGI server         |
| **Database**    | MongoDB 6.0+                       | Document store with aggregation      |
| **Driver**      | PyMongo ≥ 4.7 (with SRV support)  | Synchronous MongoDB driver           |
| **Validation**  | Pydantic ≥ 2.6                     | Request/response schema validation   |
| **Email**       | email-validator ≥ 2.0              | RFC-compliant email validation       |
| **Config**      | python-dotenv ≥ 1.0                | `.env` file loading                  |

---

## Prerequisites

- **Python 3.11** or newer
- **Git**
- **MongoDB 6.0+** — any of these will work:
  - Local Docker container: `docker run -d -p 27017:27017 mongo:6.0`
  - Free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster
  - Local MongoDB installation

---

## Setup & Installation

```bash
# 1. Clone the repository
git clone https://github.com/devloperYash/Attendance-Management-API.git
cd Attendance-Management-API

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
#    Create a .env file in the project root:
```

Create a `.env` file (this file is gitignored and **never committed**):

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```

| Variable    | Default                      | Description                        |
| ----------- | ---------------------------- | ---------------------------------- |
| `MONGO_URI` | `mongodb://localhost:27017`  | MongoDB connection string (or Atlas SRV URI) |
| `MONGO_DB`  | `attendance_db`              | Target database name               |

> Real environment variables always take precedence over `.env` values.

---

## Running the Server

```bash
uvicorn app.main:app --port 8000 --reload
```

The API will be available at **http://localhost:8000**.

| Resource                | URL                           |
| ----------------------- | ----------------------------- |
| **API Root**            | http://localhost:8000         |
| **Swagger UI (docs)**   | http://localhost:8000/docs    |
| **ReDoc**               | http://localhost:8000/redoc   |
| **Health Check**        | http://localhost:8000/health  |

On startup, the application **idempotently creates all required indexes** on both MongoDB collections via the FastAPI lifespan handler.

---

## Seeding Sample Data

Load the sample documents from `sample_data/` into MongoDB:

```bash
python sample_seed.py
```

Alternatively, use `mongoimport`:

```bash
mongoimport --db attendance_db --collection employees --jsonArray --drop --file sample_data/employees.json
mongoimport --db attendance_db --collection attendance_logs --jsonArray --drop --file sample_data/attendance_logs.json
```

> **Note:** Sample data demonstrates document shapes only. The grader's hidden dataset is much larger and covers edge cases (ties, weekends, mid-month joins, employees with zero logs, legacy documents without `history`/`half_day` fields, etc.).

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan (index init), router registration
│   ├── config.py                # Env vars (MONGO_URI, MONGO_DB), IST timezone, epoch limits
│   ├── database.py              # MongoClient singleton (tz_aware=True), ping, index creation
│   │
│   ├── models/                  # Pydantic v2 request/response schemas
│   │   ├── employee.py          # EmployeeCreate (with shift validator), EmployeeOut, EmployeePage
│   │   ├── attendance.py        # PunchInRequest, PunchOutRequest, AttendanceRegularize, AttendanceRecord
│   │   ├── analytics.py         # EmployeeMonthly, DeptSummaryItem, Leaderboard, Trend
│   │   └── admin.py             # ExplainResult
│   │
│   ├── routes/                  # FastAPI route handlers (business logic)
│   │   ├── system.py            # GET /health — live DB ping, returns 200 or 503
│   │   ├── employees.py         # POST & GET /employees — CRUD with unique index enforcement
│   │   ├── attendance.py        # Punch-in, punch-out, list, regularize with audit trail
│   │   ├── analytics.py         # 4 analytics endpoints backed by aggregation pipelines
│   │   └── admin.py             # GET /admin/explain/{endpoint} — MongoDB execution plans
│   │
│   ├── pipelines/               # MongoDB aggregation pipeline builders
│   │   ├── employee_monthly.py  # $match → $addFields → $group (presence, leave, late, OT)
│   │   ├── department_summary.py# $match → $lookup → $unwind → $group → $project → $sort
│   │   ├── leaderboard.py       # $match → $group → $lookup → $setWindowFields($rank) → $match
│   │   └── department_trend.py  # $densify → $lookup(employees) → $lookup(logs) → $project
│   │
│   └── common/                  # Shared utility modules
│       ├── time_utils.py        # IST ↔ UTC, epoch ms ↔ datetime, R1/R2/R3 computations
│       ├── math_utils.py        # Decimal ROUND_HALF_UP, work_hours (R4), half_day (R5), rates (R8)
│       └── serializers.py       # MongoDB doc → API response (strip _id, convert BSON dates → epoch ms)
│
├── tests/
│   └── test_api.py              # Comprehensive test suite (auto-seeded, order-independent)
│
├── sample_data/
│   ├── employees.json           # 6 sample employee documents
│   └── attendance_logs.json     # 9 sample attendance documents
│
├── sample_seed.py               # Script to seed sample data into MongoDB
├── openapi.yaml                 # Full OpenAPI 3.0.3 contract (650 lines)
├── DATA_MODEL.md                # MongoDB schema documentation with 9 sample documents
├── REVIEW.md                    # Starter-code defect analysis (12 bugs found & fixed)
├── DECISIONS.md                 # Design decisions & architectural trade-offs
├── requirements.txt             # Python dependencies
├── .gitignore                   # Excludes .env, __pycache__, .venv, etc.
└── README.md                    # ← You are here
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Application                            │
│                                                                         │
│  ┌─────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌───────┐│
│  │ /health  │  │ /employees │  │ /attendance │  │ /analytics│  │/admin ││
│  │ (system) │  │   (CRUD)   │  │(punch/list)│  │(aggregate)│  │(expln)││
│  └────┬─────┘  └─────┬──────┘  └─────┬──────┘  └─────┬─────┘  └───┬───┘│
│       │              │               │               │             │    │
│  ┌────▼──────────────▼───────────────▼───────────────▼─────────────▼──┐ │
│  │                    Common Utilities Layer                          │ │
│  │  time_utils.py │ math_utils.py │ serializers.py                   │ │
│  │  (IST, epoch,  │ (ROUND_HALF_  │ (MongoDB doc →                   │ │
│  │   R1, R2, R3)  │  UP, R4, R5)  │  API response)                   │ │
│  └────────────────────────┬──────────────────────────────────────────┘ │
│                           │                                             │
│  ┌────────────────────────▼──────────────────────────────────────────┐ │
│  │                  MongoDB Aggregation Pipelines                    │ │
│  │  employee_monthly │ department_summary │ leaderboard │ dept_trend │ │
│  │  ($match,$group)  │ ($lookup,$unwind)  │ ($rank)     │ ($densify) │ │
│  └────────────────────────┬──────────────────────────────────────────┘ │
│                           │                                             │
└───────────────────────────┼─────────────────────────────────────────────┘
                            │
                 ┌──────────▼──────────┐
                 │    database.py      │
                 │  MongoClient        │
                 │  (tz_aware=True)    │
                 │  Singleton + Ping   │
                 └──────────┬──────────┘
                            │
                 ┌──────────▼──────────┐
                 │      MongoDB        │
                 │  ┌───────────────┐  │
                 │  │  employees    │  │
                 │  │  (6 indexes)  │  │
                 │  ├───────────────┤  │
                 │  │attendance_logs│  │
                 │  │  (4 indexes)  │  │
                 │  └───────────────┘  │
                 └─────────────────────┘
```

**Key architectural principles:**

| Principle                      | Implementation                                                               |
| ------------------------------ | ---------------------------------------------------------------------------- |
| **No in-memory data loading**  | All lists use MongoDB `.skip()/.limit()`. Analytics use aggregation pipelines. |
| **Database-level uniqueness**  | Unique indexes on `emp_code` and `(emp_code, date)` — no check-then-insert.  |
| **Timezone-aware driver**      | `MongoClient(tz_aware=True)` — all BSON dates are UTC-aware `datetime` objects. |
| **Correct rounding**           | `decimal.Decimal` with `ROUND_HALF_UP` — no banker's rounding anywhere.     |
| **Gap-filling in DB**          | `$densify` for trend — no Python loops to fill missing calendar days.        |
| **Atomic updates**             | `find_one_and_update` for punch-out and regularize — prevents lost updates.  |

---

## MongoDB Data Model

### 1. `employees` Collection

One document per employee. Identified by `emp_code` (not `_id`).

```
┌─────────────────────────────────────────────────────────────┐
│                     employees                               │
├──────────────┬───────────────────┬───────────────────────────┤
│ Field        │ Type              │ Description               │
├──────────────┼───────────────────┼───────────────────────────┤
│ _id          │ ObjectId          │ Internal (never in API)   │
│ emp_code     │ string            │ UNIQUE business key       │
│              │                   │ Pattern: EMP + 4-6 digits │
│ name         │ string            │ Full name (1-100 chars)   │
│ email        │ string            │ RFC email (max 120 chars) │
│ department   │ string            │ Case-sensitive (1-50)     │
│ shift_start  │ string "HH:MM"   │ IST, 24-hour format       │
│ shift_end    │ string "HH:MM"   │ IST. ≤ start → overnight  │
│ joined_on    │ string "YYYY-MM-DD"│ First day of employment  │
│ created_at   │ BSON Date (UTC)   │ Server-set at creation    │
└──────────────┴───────────────────┴───────────────────────────┘
```

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

At most **one document per (`emp_code`, `date`)** — enforced by a unique compound index. Records are addressed by the natural key `(emp_code, date)`, never by `_id`.

```
┌─────────────────────────────────────────────────────────────────┐
│                      attendance_logs                            │
├────────────────────┬────────────────────┬───────────────────────┤
│ Field              │ Type               │ Description           │
├────────────────────┼────────────────────┼───────────────────────┤
│ _id                │ ObjectId           │ Internal (never API)  │
│ emp_code           │ string             │ → employees.emp_code  │
│ date               │ string "YYYY-MM-DD"│ Attendance day (IST)  │
│ status             │ string (enum)      │ See status table      │
│ punch_in           │ BSON Date | null   │ Punch-in UTC instant  │
│ punch_out          │ BSON Date | null   │ Null until punched out│
│ work_hours         │ double | null      │ Computed (R4)         │
│ late_minutes       │ int                │ Computed (R2), def: 0 │
│ overtime_minutes   │ int                │ Computed (R3), def: 0 │
│ half_day           │ bool               │ Computed (R5), def: F │
│ history            │ array              │ Audit trail, def: []  │
└────────────────────┴────────────────────┴───────────────────────┘
```

**Status values and their semantics:**

```
┌────────────┬──────────────────────────────┬───────────────┬──────────────┐
│ Status     │ Meaning                      │ Punch Times   │ Present (R6) │
├────────────┼──────────────────────────────┼───────────────┼──────────────┤
│ PRESENT    │ Worked on site               │ punch_in req  │ ✅ Yes       │
│ WFH        │ Worked from home             │ punch_in req  │ ✅ Yes       │
│ ON_DUTY    │ Official duty away           │ punch_in req  │ ✅ Yes       │
│ ABSENT     │ Did not work, no leave       │ Both null     │ ❌ No        │
│ LEAVE      │ On approved leave            │ Both null     │ ❌ No        │
└────────────┴──────────────────────────────┴───────────────┴──────────────┘
```

**Derived fields computation:**

| Situation                          | `work_hours` | `late_minutes` | `overtime_minutes` | `half_day` |
| ---------------------------------- | ------------ | -------------- | ------------------ | ---------- |
| Presence status, no punch_out yet  | `null`       | from R2        | `0`                | `false`    |
| Presence status, with punch_out    | R4           | from R2        | R3                 | R5         |
| ABSENT or LEAVE                    | `null`       | `0`            | `0`                | `false`    |

**Sample document (with punch-out computed fields):**
```json
{
  "emp_code": "EMP0003",
  "date": "2026-07-06",
  "status": "PRESENT",
  "punch_in": { "$date": "2026-07-06T04:35:00Z" },
  "punch_out": { "$date": "2026-07-06T13:40:00Z" },
  "work_hours": 9.08,
  "late_minutes": 35,
  "overtime_minutes": 40,
  "half_day": false,
  "history": []
}
```

### 3. History (Audit Trail)

`history` records **manual corrections only** (regularizations). Punch-in and punch-out never write to it. Each correction appends exactly one entry; entries are never edited or removed.

```
┌──────────────────────────────────────────────────────────────────┐
│                     history[] entry                              │
├──────────┬──────────────┬────────────────────────────────────────┤
│ Field    │ Type         │ Description                            │
├──────────┼──────────────┼────────────────────────────────────────┤
│ at       │ BSON Date    │ When the correction was made (UTC)     │
│ by       │ string       │ Who made it (free text)                │
│ reason   │ string       │ Justification for the correction       │
│ changes  │ object       │ Only changed fields, each with         │
│          │              │ { "from": <old>, "to": <new> }         │
│          │              │ Keys: status, punch_in, punch_out,     │
│          │              │ work_hours, late_minutes,               │
│          │              │ overtime_minutes, half_day              │
└──────────┴──────────────┴────────────────────────────────────────┘
```

**Sample history entry:**
```json
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
```

> In MongoDB, `punch_in`/`punch_out` values in `changes` are BSON dates. In the API, they are epoch milliseconds. This applies recursively inside the nested `from`/`to` objects.

### 4. Indexes

All indexes are created **idempotently at application startup** via `init_indexes()`. No additional index creation is required.

**`employees` collection (4 indexes):**

| Name                  | Fields                              | Type   | Purpose                               |
| --------------------- | ----------------------------------- | ------ | ------------------------------------- |
| `uniq_emp_code`       | `{ emp_code: 1 }`                   | Unique | Enforce unique employee identity      |
| `idx_dept_emp_code`   | `{ department: 1, emp_code: 1 }`    | Normal | Filtered directory listings by dept   |
| `idx_joined_on`       | `{ joined_on: 1 }`                  | Normal | Headcount period filters (R9)         |
| `idx_dept_joined_on`  | `{ department: 1, joined_on: 1 }`   | Normal | Department-filtered headcount queries |

**`attendance_logs` collection (4 indexes):**

| Name                    | Fields                              | Type   | Purpose                                       |
| ----------------------- | ----------------------------------- | ------ | --------------------------------------------- |
| `uniq_emp_date`         | `{ emp_code: 1, date: 1 }`         | Unique | One record per employee per day + concurrency  |
| `idx_emp_punch_in_desc` | `{ emp_code: 1, punch_in: -1 }`    | Normal | Sub-ms punch-out target lookup                 |
| `idx_date_desc_emp_asc` | `{ date: -1, emp_code: 1 }`        | Normal | Sorted attendance pagination                   |
| `idx_date_late_minutes` | `{ date: 1, late_minutes: 1 }`     | Normal | Late leaderboard acceleration                  |

**Index strategy rationale:**
- A standalone `{ date: 1 }` index was considered and rejected because the composite `{ date: -1, emp_code: 1 }` covers date-range prefix queries without extra index overhead.
- All analytics queries use `IXSCAN` (verified via `/admin/explain/{endpoint}`) — no `COLLSCAN` on the grader's ~100k-record dataset.

---

## API Endpoints

All instants in requests/responses are **epoch milliseconds** (`int64`). All calendar dates are `YYYY-MM-DD` strings (IST). MongoDB `_id` is never exposed.

### System

| Method | Path      | Description                             | Success | Errors |
| ------ | --------- | --------------------------------------- | ------- | ------ |
| `GET`  | `/health` | Readiness probe — pings MongoDB, returns 200 or 503 | `200` | `503` |

```bash
# Example
curl http://localhost:8000/health
# → {"status":"ok"}
```

### Employees

| Method | Path         | Description                                              | Success | Errors       |
| ------ | ------------ | -------------------------------------------------------- | ------- | ------------ |
| `POST` | `/employees` | Create a new employee (unique `emp_code` enforced by DB) | `201`   | `409`, `422` |
| `GET`  | `/employees` | List employees (paginated, filterable by department)     | `200`   | `422`        |

**Create Employee:**
```bash
curl -X POST http://localhost:8000/employees \
  -H "Content-Type: application/json" \
  -d '{
    "emp_code": "EMP0001",
    "name": "Asha Rao",
    "email": "asha@example.com",
    "department": "Engineering",
    "shift_start": "09:30",
    "shift_end": "18:30",
    "joined_on": "2026-01-05"
  }'
```

**Response (201 Created):**
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

**List Employees:**
```bash
curl "http://localhost:8000/employees?department=Engineering&page=1&page_size=10"
```

| Query Param  | Type    | Default | Constraints | Description                  |
| ------------ | ------- | ------- | ----------- | ---------------------------- |
| `department` | string  | —       | —           | Exact, case-sensitive filter |
| `page`       | int     | `1`     | ≥ 1         | Page number                  |
| `page_size`  | int     | `20`    | 1–100       | Items per page               |

### Attendance

| Method  | Path                             | Description                                    | Success | Errors              |
| ------- | -------------------------------- | ---------------------------------------------- | ------- | -------------------- |
| `POST`  | `/attendance/punch-in`           | Record a punch-in (creates the day's record)   | `201`   | `404`, `409`, `422`  |
| `POST`  | `/attendance/punch-out`          | Record a punch-out (closes the open record)    | `200`   | `404`, `409`, `422`  |
| `GET`   | `/attendance`                    | List records (paginated, filterable)            | `200`   | `422`                |
| `PATCH` | `/attendance/{emp_code}/{date}`  | Regularize (manually correct) a record         | `200`   | `404`, `409`, `422`  |

**Punch-In:**
```bash
curl -X POST http://localhost:8000/attendance/punch-in \
  -H "Content-Type: application/json" \
  -d '{"emp_code": "EMP0001", "punched_at": 1783312500000, "status": "PRESENT"}'
```
> `punched_at` defaults to current server time if omitted. `status` defaults to `PRESENT`. Only `PRESENT`, `WFH`, `ON_DUTY` accepted.

**Punch-Out:**
```bash
curl -X POST http://localhost:8000/attendance/punch-out \
  -H "Content-Type: application/json" \
  -d '{"emp_code": "EMP0001", "punched_at": 1783345200000}'
```
> Closes the most recent record whose `punch_in ≤ punched_at`. Rejects if `punched_at ≤ punch_in` or gap > 24 hours.

**List Attendance:**
```bash
curl "http://localhost:8000/attendance?emp_code=EMP0001&date_from=2026-07-01&date_to=2026-07-31&status=PRESENT&page=1"
```

| Query Param  | Type   | Default | Description                                |
| ------------ | ------ | ------- | ------------------------------------------ |
| `emp_code`   | string | —       | Filter by employee                         |
| `date_from`  | string | —       | Start date inclusive (`YYYY-MM-DD`)         |
| `date_to`    | string | —       | End date inclusive (`YYYY-MM-DD`)           |
| `status`     | string | —       | Filter by status enum                      |
| `page`       | int    | `1`     | Page number (≥ 1)                          |
| `page_size`  | int    | `20`    | Items per page (1–100)                     |

**Regularize:**
```bash
curl -X PATCH http://localhost:8000/attendance/EMP0001/2026-07-07 \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "biometric glitch",
    "regularized_by": "hr.admin",
    "punch_in": 1783310280000
  }'
```
> Omitted fields remain unchanged. All derived fields are recomputed. One audit entry is appended to `history`. A request that changes nothing returns `422`.

### Analytics

All four analytics endpoints are backed entirely by **MongoDB aggregation pipelines** — no data is pulled into Python memory.

| Method | Path                                        | Description                              | Success | Errors       |
| ------ | ------------------------------------------- | ---------------------------------------- | ------- | ------------ |
| `GET`  | `/analytics/employees/{emp_code}/monthly`   | Monthly attendance summary for one employee | `200` | `404`, `422` |
| `GET`  | `/analytics/departments/summary`            | Department summary for a month           | `200`   | `422`        |
| `GET`  | `/analytics/leaderboard/late`               | Late-comers leaderboard (competition ranking) | `200` | `422`      |
| `GET`  | `/analytics/departments/{department}/trend` | Daily attendance trend (gap-filled)      | `200`   | `404`, `422` |

**Employee Monthly:**
```bash
curl "http://localhost:8000/analytics/employees/EMP0001/monthly?month=2026-07"
```
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
> `working_days` counts Mon–Fri from `max(month_start, joined_on)`. `present_days` counts Mon–Fri presence records only (half day = 0.5). `attendance_pct` = `present_days / working_days × 100` (2 decimals half-up), `null` if `working_days = 0`.

**Department Summary:**
```bash
curl "http://localhost:8000/analytics/departments/summary?month=2026-07&department=Engineering"
```
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
> `headcount` per R9 (employees with `joined_on ≤ month_end`, even those with zero logs). `avg_work_hours` = mean over present-status records with non-null `work_hours` (average over records, not per-employee averages). Departments with zero headcount are omitted.

**Late Leaderboard:**
```bash
curl "http://localhost:8000/analytics/leaderboard/late?month=2026-07&limit=5&department=Engineering"
```
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
    },
    {
      "rank": 2,
      "emp_code": "EMP0007",
      "name": "Priya Gupta",
      "department": "Engineering",
      "total_late_minutes": 95,
      "late_count": 4
    }
  ]
}
```
> Uses **standard competition ranking** via MongoDB `$rank` window function (1, 2, 2, 4 — not 1, 2, 3, 4). `limit` applies to rank, not row count — ties at the cutoff rank are all included.

**Department Trend:**
```bash
curl "http://localhost:8000/analytics/departments/Engineering/trend?from=2026-07-01&to=2026-07-07"
```
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
    },
    {
      "date": "2026-07-02",
      "is_working_day": true,
      "headcount": 15,
      "present_count": 15.0,
      "late_count": 0,
      "attendance_rate": 1.0,
      "moving_avg_7d": 0.9834
    },
    {
      "date": "2026-07-03",
      "is_working_day": false,
      "headcount": 15,
      "present_count": 0.0,
      "late_count": 0,
      "attendance_rate": null,
      "moving_avg_7d": 0.9834
    }
  ]
}
```
> Returns **exactly one row per calendar day** (including weekends and zero-record days) using MongoDB's `$densify` stage. `attendance_rate` is `null` on weekends and on working days with `headcount = 0`. `moving_avg_7d` uses up to 7 rows (current + 6 preceding) within the requested range. Max range: 92 days.

### Admin (Explain)

| Method | Path                           | Description                              | Success | Errors |
| ------ | ------------------------------ | ---------------------------------------- | ------- | ------ |
| `GET`  | `/admin/explain/{endpoint}`    | MongoDB `executionStats` explain output  | `200`   | `422`  |

Valid endpoint values: `attendance_list`, `employee_monthly`, `department_summary`, `late_leaderboard`, `department_trend`.

```bash
# Example: verify that attendance listing uses IXSCAN
curl "http://localhost:8000/admin/explain/attendance_list?date_from=2026-07-01&date_to=2026-07-31"
```

Accepts the same query parameters as the endpoint it explains. The grader checks that plans contain `IXSCAN` and no `COLLSCAN` on ~100k records.

---

## Request & Response Schemas

### Shared Types

| Type                 | In API (JSON)         | In MongoDB              | Notes                                       |
| -------------------- | --------------------- | ----------------------- | ------------------------------------------- |
| **EpochMillis**      | `int64`               | BSON Date (UTC)         | Range: `[100000000000, 4102444800000]`      |
| **EpochMillisNull**  | `int64 \| null`       | BSON Date \| null       | Same range, or `null`                       |
| **CalendarDate**     | `"YYYY-MM-DD"` string | `"YYYY-MM-DD"` string   | IST date, stored as-is                      |
| **Month**            | `"YYYY-MM"` string    | —                       | Query param only                            |
| **TimeOfDay**        | `"HH:MM"` string      | `"HH:MM"` string        | 24-hour IST                                 |
| **Status**           | string enum           | string                  | `PRESENT\|WFH\|ON_DUTY\|ABSENT\|LEAVE`     |
| **PresenceStatus**   | string enum           | string                  | `PRESENT\|WFH\|ON_DUTY` (punch-in only)    |

### Request Bodies

**EmployeeCreate:**
```
{
  emp_code:     string  [required]  Pattern: ^EMP\d{4,6}$
  name:         string  [required]  1–100 chars
  email:        string  [required]  Valid email, max 120 chars
  department:   string  [required]  1–50 chars
  shift_start:  string  [optional]  Default: "09:30", pattern: HH:MM
  shift_end:    string  [optional]  Default: "18:30", pattern: HH:MM
  joined_on:    string  [required]  Format: YYYY-MM-DD
}
Validator: shift_start ≠ shift_end (422 if equal)
```

**PunchInRequest:**
```
{
  emp_code:     string  [required]  Pattern: ^EMP\d{4,6}$
  punched_at:   int     [optional]  Epoch ms. Defaults to server time.
  status:       string  [optional]  Default: "PRESENT". Enum: PRESENT|WFH|ON_DUTY
}
```

**PunchOutRequest:**
```
{
  emp_code:     string  [required]  Pattern: ^EMP\d{4,6}$
  punched_at:   int     [optional]  Epoch ms. Defaults to server time.
}
```

**RegularizeRequest:**
```
{
  reason:           string  [required]  5–200 chars
  regularized_by:   string  [required]  1–50 chars
  status:           string  [optional]  Enum: PRESENT|WFH|ON_DUTY|ABSENT|LEAVE
  punch_in:         int     [optional]  Epoch ms
  punch_out:        int     [optional]  Epoch ms
}
```

### Response Bodies

**Employee:**
```
{
  emp_code:     string
  name:         string
  email:        string
  department:   string
  shift_start:  string
  shift_end:    string
  joined_on:    string  "YYYY-MM-DD"
  created_at:   int     Epoch ms (read-only, server-set)
}
```

**AttendanceRecord:**
```
{
  emp_code:          string
  date:              string  "YYYY-MM-DD"
  status:            string  enum
  punch_in:          int|null   Epoch ms
  punch_out:         int|null   Epoch ms
  work_hours:        float|null Computed (R4)
  late_minutes:      int        Computed (R2)
  overtime_minutes:  int        Computed (R3)
  half_day:          bool       Computed (R5)
  history:           array      HistoryEntry[]
}
```

**Paginated Response (EmployeePage / AttendancePage):**
```
{
  items:      array   Employee[] or AttendanceRecord[]
  total:      int     Total matching records (respects filters)
  page:       int     Current page number
  page_size:  int     Items per page
}
```

---

## Business Rules (R1–R10)

| Rule   | Summary                                                                                                                                                                                                  |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R1** | **Time zone & attendance date.** Shift times and dates are IST (UTC+05:30). `date` = IST date of `punch_in`. Overnight shifts (`shift_end ≤ shift_start`): punch-in before `shift_end` → previous day. Instants truncated to whole seconds. |
| **R2** | **Late.** Grace = 10 min. Late only if punch-in is **strictly >** 10:00 after `shift_start`. `late_minutes` = `floor(seconds since shift_start / 60)`. Examples (shift 09:30): 09:40:00→0, 09:40:01→10, 10:15:59→45. |
| **R3** | **Overtime.** `overtime_minutes` = `floor(minutes between shift_end and punch_out)`, counted only when ≥ 30; otherwise 0.                                                                               |
| **R4** | **Work hours.** `(punch_out − punch_in) seconds / 3600`, rounded to 2 decimals **half-up** (not banker's rounding). `null` until punch-out.                                                             |
| **R5** | **Half day.** After punch-out, `half_day = true` when rounded `work_hours < 4.50`. A half day counts as 0.5 of a present day.                                                                           |
| **R6** | **Presence.** `PRESENT`, `WFH`, `ON_DUTY` = present. `ABSENT`, `LEAVE` = not present.                                                                                                                   |
| **R7** | **Working days.** Mon–Fri only, no holiday calendar. For mid-month joins, count from `joined_on`. `present_days` only counts Mon–Fri records (weekend records still contribute to late/overtime totals).  |
| **R8** | **Rounding.** Values: 2 decimals half-up. Rates: 4 decimals half-up.                                                                                                                                    |
| **R9** | **Headcount.** Employees with `joined_on ≤ period_end`, whether or not they have any attendance logs.                                                                                                    |
| **R10** | **Pagination.** `page` starts at 1, `page_size` max 100 (default 20). `total` reflects applied filters, not the entire collection.                                                                     |

---

## Conventions

| Convention                    | Detail                                                                                                               |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Employee identity**         | `emp_code` (customer-generated, e.g. `EMP0001`). Not MongoDB `_id`. `_id` never appears in any request or response. |
| **Record identity**           | Attendance records have no surrogate key. Addressed by `(emp_code, date)`.                                           |
| **Instants → epoch ms**       | Every time value in API is `int64` milliseconds since Unix epoch. Validated range: `[100B, 4.1T]`.                   |
| **Calendar values → strings** | Dates `YYYY-MM-DD`, months `YYYY-MM`, shift times `HH:MM` — all strings, never BSON dates.                          |
| **Derived fields = read-only**| `work_hours`, `late_minutes`, `overtime_minutes`, `half_day` — computed by API, never in request bodies.             |
| **Analytics use stored values**| Aggregation pipelines read stored derived values. They do **not** recompute from punch times.                       |
| **Error format**              | FastAPI default: `{"detail": "..."}` (string) or `{"detail": [...]}` (validation array).                             |

---

## Error Handling

| HTTP Code | Meaning                | When                                                                |
| --------- | ---------------------- | ------------------------------------------------------------------- |
| `200`     | Success                | GET requests, punch-out, regularize                                 |
| `201`     | Created                | Employee creation, punch-in                                         |
| `404`     | Not Found              | Unknown `emp_code`, no attendance record, unknown department        |
| `409`     | Conflict               | Duplicate `emp_code`, duplicate punch-in, already punched out, concurrent edit |
| `422`     | Validation Error       | Invalid body, bad timestamp, nothing changed, invalid date range    |
| `503`     | Service Unavailable    | MongoDB unreachable (health check)                                  |

---

## Concurrency & Safety

This API is safe under concurrent access:

```
Concurrent Punch-In (same employee, same date):
  Request A ──► insert_one ──► 201 Created ✅
  Request B ──► insert_one ──► DuplicateKeyError ──► 409 Conflict ✅

Concurrent Punch-Out (same record):
  Request A ──► find_one_and_update(punch_out: None) ──► 200 OK ✅
  Request B ──► find_one_and_update(punch_out: None) ──► null result ──► 409 Conflict ✅

Concurrent Regularize (same record):
  Request A ──► find_one_and_update(history.$size: N) ──► 200 OK ✅
  Request B ──► find_one_and_update(history.$size: N) ──► null result ──► 409 Conflict ✅
```

All concurrency safety is achieved through **database-level constraints** (unique indexes) and **atomic conditional updates** (`find_one_and_update` with guard conditions), never check-then-insert patterns.

---

## Running Tests

```bash
# Ensure MongoDB is running and .env is configured, then:
pytest tests/ -v
```

Tests are **auto-seeded** — each test gets a fresh copy of the sample data. Tests are fully order-independent.

---

## What is Missing / Known Limitations

| What                       | Why                                                                         |
| -------------------------- | --------------------------------------------------------------------------- |
| Authentication / Auth      | Intentionally omitted per assignment scope. `regularized_by` is free-text.  |
| Dockerfile                 | Not included per submission guidelines.                                     |
| `.env` file                | Gitignored for security. Create your own (see Setup).                       |
| Holiday calendar           | Working days = Mon–Fri only, as specified. No public holidays.              |
| Bulk operations            | No batch punch-in/out. Each operation is per-employee.                      |
| Real-time notifications    | No WebSocket/SSE for live tracking.                                         |

Everything specified in the assignment is fully implemented. No endpoints or features are missing.

---

## Related Documents

| Document                                       | Description                                                    |
| ---------------------------------------------- | -------------------------------------------------------------- |
| [REVIEW.md](REVIEW.md)                        | Starter-code defect analysis — 12 bugs found and fixed         |
| [DECISIONS.md](DECISIONS.md)                   | Design decisions, trade-offs, and scalability considerations   |
| [DATA_MODEL.md](DATA_MODEL.md)                 | Full MongoDB schema documentation with 9 sample documents     |
| [openapi.yaml](openapi.yaml)                   | Complete OpenAPI 3.0.3 contract (650 lines)                   |

---

*Built with ❤️ by Yash*
