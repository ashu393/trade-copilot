"""Guarded SQL execution against a read-only DuckDB connection.

Execution adds the runtime half of the safety story:

* a fresh **read-only** connection (engine refuses writes);
* a **row cap** so a runaway query can't return millions of rows; and
* a **time limit** enforced by interrupting the connection from a watchdog
  thread (DuckDB has no statement_timeout, so we interrupt cooperatively).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..db import Database
from .guard import GuardResult, check_sql


@dataclass
class ExecutionResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    elapsed_s: float = 0.0
    error: str | None = None
    sql: str | None = None

    def to_records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, r)) for r in self.rows]


def run_guarded(
    db: Database,
    sql: str,
    *,
    max_rows: int | None = None,
    timeout_s: int | None = None,
) -> ExecutionResult:
    """Guard then execute `sql`. A failed guard short-circuits before any query runs."""
    guard: GuardResult = check_sql(sql, db.allowlist())
    if not guard.ok:
        return ExecutionResult(ok=False, error=f"Blocked by SQL guard: {guard.reason}", sql=sql)
    return _execute(db, guard.normalized_sql or sql, max_rows=max_rows, timeout_s=timeout_s)


def _execute(
    db: Database, sql: str, *, max_rows: int | None, timeout_s: int | None
) -> ExecutionResult:
    max_rows = max_rows or settings.copilot_max_result_rows
    timeout_s = timeout_s or settings.copilot_sql_timeout_s

    con = db.connect_readonly()
    result: dict[str, Any] = {}
    done = threading.Event()

    def _worker() -> None:
        import time

        start = time.perf_counter()
        try:
            cur = con.execute(sql)
            columns = [d[0] for d in (cur.description or [])]
            fetched = cur.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            rows = fetched[:max_rows]
            result.update(
                ok=True, columns=columns, rows=rows, row_count=len(rows),
                truncated=truncated, elapsed_s=time.perf_counter() - start,
            )
        except Exception as e:  # noqa: BLE001
            result.update(ok=False, error=str(e), elapsed_s=time.perf_counter() - start)
        finally:
            done.set()

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    finished = done.wait(timeout=timeout_s)
    if not finished:
        # Cooperatively cancel the running query, then report a timeout.
        try:
            con.interrupt()
        except Exception:  # noqa: BLE001
            pass
        worker.join(timeout=2)
        con.close()
        return ExecutionResult(
            ok=False, error=f"Query exceeded {timeout_s}s time limit and was cancelled.", sql=sql
        )

    con.close()
    return ExecutionResult(
        ok=result.get("ok", False),
        columns=result.get("columns", []),
        rows=result.get("rows", []),
        row_count=result.get("row_count", 0),
        truncated=result.get("truncated", False),
        elapsed_s=result.get("elapsed_s", 0.0),
        error=result.get("error"),
        sql=sql,
    )
