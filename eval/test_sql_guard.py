"""Unit tests for the SQL safety guard — the most security-sensitive component."""

from __future__ import annotations

import pytest

from copilot.db import Database
from copilot.sql.execute import run_guarded
from copilot.sql.guard import check_sql


@pytest.fixture(scope="module")
def allowlist():
    return Database().build().allowlist()


@pytest.fixture(scope="module")
def db():
    return Database().build()


VALID = [
    "SELECT region, SUM(net_revenue) FROM fact_orders o JOIN dim_account a USING(account_id) GROUP BY region",
    "WITH s AS (SELECT account_id, SUM(net_revenue) r FROM fact_orders GROUP BY 1) SELECT * FROM s LIMIT 5",
    "SELECT COUNT(*) FROM fact_reimbursements WHERE status = 'Approved'",
]

BLOCKED = [
    ("SELECT 1 FROM fact_orders; DROP TABLE fact_orders", "single statement"),
    ("DELETE FROM fact_orders", "SELECT"),
    ("UPDATE fact_orders SET net_revenue = 0", "SELECT"),
    ("CREATE TABLE x AS SELECT * FROM fact_orders", "SELECT"),
    ("ATTACH 'evil.db' AS e", "SELECT"),
    ("COPY fact_orders TO 'out.csv'", "SELECT"),
    ("SELECT * FROM read_csv_auto('/etc/passwd')", "permitted"),
    ("SELECT * FROM secret_table", "allowlist"),
    ("SELECT ssn FROM dim_account", "unknown column"),
    ("PRAGMA database_list", "SELECT"),
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_sql_passes(sql, allowlist):
    assert check_sql(sql, allowlist).ok


@pytest.mark.parametrize("sql,reason_substr", BLOCKED)
def test_malicious_sql_blocked(sql, reason_substr, allowlist):
    result = check_sql(sql, allowlist)
    assert not result.ok
    assert reason_substr.lower() in (result.reason or "").lower()


def test_blocked_sql_never_executes(db):
    res = run_guarded(db, "DROP TABLE fact_orders")
    assert not res.ok and "guard" in (res.error or "").lower()
    # Table still intact.
    check = run_guarded(db, "SELECT COUNT(*) FROM fact_orders")
    assert check.ok and check.rows[0][0] == 2600


def test_row_cap_truncates(db):
    res = run_guarded(db, "SELECT * FROM fact_orders", max_rows=10)
    assert res.row_count == 10 and res.truncated
