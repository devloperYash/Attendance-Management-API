# DECISIONS.md

1. **Indexes.**
On `employees`: unique `{"emp_code": 1}` guarantees employee identity; `{"department": 1, "emp_code": 1}` serves filtered directory listings; `{"joined_on": 1}` serves period headcount filters.
On `attendance_logs`: unique `{"emp_code": 1, "date": 1}` enforces one record per employee daily; `{"emp_code": 1, "punch_in": -1}` enables sub-millisecond punch-out target lookup; `{"date": -1, "emp_code": 1}` backs sorted attendance pagination; `{"date": 1, "late_minutes": 1}` accelerates late leaderboards. We considered and rejected a standalone index on `{"date": 1}` because the composite index covers date-range prefixes without extra index overhead.

2. **Punch-in race.**
Both concurrent requests execute `insert_one` directly against MongoDB. The first write commits successfully (HTTP 201). The second write violates the unique index on `(emp_code, date)`, triggering a `DuplicateKeyError` which our service catches and translates to HTTP 409 Conflict.

3. **Ties.**
We calculate ranks using MongoDB's `$rank` window function (competition ranking: 1, 2, 2, 4). Applying `rank <= limit` returns all candidates within that rank threshold—even if ties push total returned rows above `limit`—sorting tied rows by `emp_code` ascending.

4. **Headcount.**
The aggregation pipeline queries `employees` where `joined_on <= month_end`, performs a `$lookup` onto `attendance_logs`, and uses `$unwind` with `preserveNullAndEmptyArrays: True`. Headcount is computed via `$size` on the `$addToSet` of employee codes, ensuring zero-log employees are counted.

5. **One thing you would change for 100x data.**
Pre-compute daily attendance metrics using MongoDB change streams or asynchronous event workers into a daily summary collection, removing runtime cross-collection `$lookup` and `$densify` bottlenecks.
