# DECISIONS.md

## Design Decisions

This document explains the key architectural and implementation decisions, the trade-offs considered, and the reasoning behind each choice.

---

### 1. Indexes

**`employees` collection:**
- **`{ emp_code: 1 }` (unique):** Guarantees employee identity at the database level. Concurrent `POST /employees` with the same `emp_code` results in exactly one `201` and the rest `409`, without application-level locking.
- **`{ department: 1, emp_code: 1 }`:** Serves filtered directory listings (`GET /employees?department=X`) with a covered query — the leading `department` key satisfies the filter, and `emp_code` satisfies the `sort("emp_code", 1)` without an in-memory sort.
- **`{ joined_on: 1 }`:** Enables efficient `joined_on <= month_end` headcount filters used by department summary and trend analytics (R9).
- **`{ department: 1, joined_on: 1 }`:** Compound index for department-filtered headcount queries inside the `$lookup` subpipeline in the trend aggregation, allowing MongoDB to do an index-bounded scan per day.

**`attendance_logs` collection:**
- **`{ emp_code: 1, date: 1 }` (unique):** Enforces one record per employee per day. This is the core concurrency mechanism for punch-in — `DuplicateKeyError` replaces check-then-insert. Also accelerates `PATCH /{emp_code}/{date}` lookups and the `$match` stage of the employee monthly pipeline.
- **`{ emp_code: 1, punch_in: -1 }`:** Enables sub-millisecond punch-out target lookup — `find({"emp_code": X, "punch_in": {"$lte": Y}}).sort("punch_in", -1).limit(1)` uses a backward index scan bounded by the compound key.
- **`{ date: -1, emp_code: 1 }`:** Backs the `GET /attendance` sorted pagination (date desc, emp_code asc). The descending date order matches the API sort contract, and the trailing emp_code serves as a tiebreaker without an in-memory sort stage.
- **`{ date: 1, late_minutes: 1 }`:** Accelerates the late leaderboard aggregation pipeline's initial `$match` stage (`date` range + `late_minutes > 0`). The compound key allows MongoDB to combine the date range scan with the late-minutes filter in a single index pass.

**Rejected:** A standalone `{ date: 1 }` index was considered and rejected because the composite `{ date: -1, emp_code: 1 }` already covers date-range prefix queries without extra index overhead. Adding a redundant index would increase write amplification on every `insert_one` and `find_one_and_update`.

---

### 2. Punch-In Race Condition

Both concurrent requests execute `insert_one` directly against MongoDB. The first write commits successfully (HTTP 201). The second write violates the unique index on `(emp_code, date)`, triggering a `DuplicateKeyError` which our service catches and translates to HTTP 409 Conflict. This approach is:

- **Simpler** than distributed locks or optimistic version fields.
- **Correct by construction** — the database is the single source of truth for uniqueness.
- **Fast** — a single round-trip for the success path, no pre-check query needed.

The same pattern is used for `POST /employees` with the unique `emp_code` index.

---

### 3. Ties in the Late Leaderboard

We calculate ranks using MongoDB's `$rank` window function (standard competition ranking: 1, 2, 2, 4). Applying `rank <= limit` returns all candidates within that rank threshold — even if ties push total returned rows above `limit` — sorting tied rows by `emp_code` ascending for deterministic output.

**Why `$rank` and not `$denseRank`:** The contract specifies standard competition ranking where the next rank after a tie is skipped. `$denseRank` would produce 1, 2, 2, 3 which is incorrect per the specification.

**Why filter after ranking:** Ranking is applied as a `$setWindowFields` stage before the `$match` on `rank <= limit`. This ensures that employees tied at the cutoff rank are all included, even if the result set grows beyond `limit` rows.

---

### 4. Headcount Calculation

The aggregation pipeline queries `employees` where `joined_on <= month_end` (or `<= current_day` for trend), performs a `$lookup` onto `attendance_logs`, and uses `$unwind` with `preserveNullAndEmptyArrays: True`. Headcount is computed via `$size` on the `$addToSet` of employee codes, ensuring zero-log employees are counted.

**Why start from `employees`:** Starting the aggregation from the `employees` collection (rather than `attendance_logs`) guarantees that employees with no attendance records in the period are still included in the headcount. This is critical for R9 compliance.

**Why `$addToSet` + `$size`:** After `$unwind` with `preserveNullAndEmptyArrays`, a single employee may produce one row per log entry plus one row if they have no logs. Using `$addToSet` on `emp_code` and then `$size` deduplicates the count correctly.

---

### 5. Regularization Concurrency (Audit Trail Safety)

Concurrent corrections to the same attendance record use **optimistic concurrency control** based on the `history` array's length:

```python
concurrency_filter = {
    "_id": existing["_id"],
    "history": {"$size": len(existing_history)}
}
```

If two requests read the same document at the same time (with `history.length == N`), both try `find_one_and_update` with `history.$size: N`. The first succeeds (history grows to N+1), the second fails (history is now N+1, not N) and returns 409 Conflict.

**Why not a version field:** Adding a `version` or `updated_at` field is unnecessary — the `history` array length naturally increments on every correction and serves as a built-in optimistic lock.

**Legacy document handling:** Documents without a `history` field use a `$or` filter matching `{history: {$exists: false}}`, `{history: {$size: 0}}`, or `{history: null}` to handle all possible legacy states.

---

### 6. Rounding Strategy

All numeric rounding uses Python's `decimal.Decimal` with explicit `ROUND_HALF_UP` quantization:

```python
def round_half_up(val, decimals=2):
    d = Decimal(str(val))
    fmt = "0." + "0" * decimals
    return d.quantize(Decimal(fmt), rounding=ROUND_HALF_UP)
```

**Why `Decimal(str(val))`:** Converting through `str` avoids the floating-point representation issue where `Decimal(2.125)` becomes `2.124999999...` but `Decimal("2.125")` is exact.

**Decimal precision by context:**
- Work hours, avg_work_hours, attendance_pct: 2 decimal places
- attendance_rate, moving_avg_7d: 4 decimal places

---

### 7. Department Trend Gap-Filling

The trend endpoint uses MongoDB's `$densify` stage to guarantee exactly one row per calendar day in the requested range, including weekends and days with no attendance records:

```python
{"$densify": {"field": "date", "range": {"step": 1, "unit": "day", "bounds": [from_dt, to_dt]}}}
```

**Why `$densify` over Python loops:** The assignment specifically requires "a gap-filling stage such as `$densify`; do not loop in Python." This keeps the gap-filling logic inside MongoDB's aggregation engine, avoiding O(N) Python iteration and ensuring the pipeline is visible to `explain`.

**Why `format_trend_results` in Python:** `attendance_rate` and `moving_avg_7d` require `ROUND_HALF_UP` rounding with precise decimal arithmetic. MongoDB's `$round` does not support half-up rounding. The trade-off is acceptable because the trend endpoint has a hard limit of 92 days (92 rows), so the Python post-processing is O(92) at worst.

---

### 8. Timezone Handling

- **`MongoClient(tz_aware=True)`:** Ensures all BSON dates are returned as `datetime` objects with `tzinfo=UTC`, preventing accidental naive datetime comparisons.
- **IST = `timezone(timedelta(hours=5, minutes=30))`:** Defined once in `config.py`, used everywhere for UTC → IST conversion.
- **Epoch ms truncation at API boundary:** `(ms // 1000) * 1000` strips sub-second precision before storage, ensuring R1 compliance. This is done in `validate_epoch_ms()` so every path through the system gets truncated input.

---

### 9. One Thing I Would Change for 100× Data

**Pre-compute daily attendance metrics** using MongoDB change streams or asynchronous event workers into a daily summary collection, removing runtime cross-collection `$lookup` and `$densify` bottlenecks.

Specifically:
- A **`daily_department_stats`** collection would hold pre-aggregated `headcount`, `present_count`, `late_count`, `avg_work_hours` per department per day.
- On every punch-in, punch-out, or regularize, a change stream listener would incrementally update the summary for that day.
- Analytics queries would read from the pre-computed collection instead of running multi-stage pipelines across `employees` + `attendance_logs`.
- This eliminates the `$lookup` fan-out (currently O(employees × days)) and the `$densify` gap-fill, reducing query time from O(E × D) to O(D) where D is the number of days requested.

The trade-off is eventual consistency (the summary may lag by milliseconds behind the source data) and increased write amplification, but for a 100× dataset this is a necessary architectural shift from query-time aggregation to write-time materialization.
