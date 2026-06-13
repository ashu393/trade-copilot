"""SQL safety guard.

Generated SQL is never trusted. Before execution every statement is parsed
into an AST (sqlglot, DuckDB dialect) and checked against a allowlist policy:

* exactly **one** statement (blocks stacked `...; DROP TABLE ...`);
* the statement must be read-only — a `SELECT` (optionally wrapped in `WITH`);
* no DML/DDL/admin verbs (INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/ATTACH/
  COPY/INSTALL/LOAD/PRAGMA/EXPORT/CALL...);
* every referenced table is on the allowlist;
* no file/IO table functions (read_csv, glob, parquet_scan, ...);
* referenced columns are validated against the schema (best-effort).

This is layered with an engine-level read-only connection and a row/time limit
at execution time (see execute.py) — defence in depth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

# Verbs that must never appear anywhere in the statement.
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command,          # catches ATTACH, COPY, PRAGMA, CALL, SET, EXPORT, VACUUM, etc.
    exp.Merge,
)

# Table-valued / IO functions that could read outside the allowlisted tables.
FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset({
    "read_csv", "read_csv_auto", "read_parquet", "parquet_scan", "read_json",
    "read_json_auto", "glob", "read_text", "read_blob", "scan_arrow", "delta_scan",
})


@dataclass
class GuardResult:
    ok: bool
    reason: str | None = None
    normalized_sql: str | None = None
    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)


def check_sql(sql: str, allowlist: dict[str, set[str]]) -> GuardResult:
    """Validate `sql` against the table/column allowlist. Returns a GuardResult."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return GuardResult(ok=False, reason="Empty SQL.")

    # 1) Parse — must be exactly one statement.
    try:
        statements = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
    except Exception as e:  # noqa: BLE001 - surface a clean message
        return GuardResult(ok=False, reason=f"Could not parse SQL: {e}")
    if len(statements) != 1:
        return GuardResult(ok=False, reason="Only a single statement is allowed.")
    tree = statements[0]

    # 2) Root must be a read-only SELECT (optionally a WITH/CTE wrapping a select).
    root = tree
    if isinstance(root, exp.Subquery):
        root = root.this
    is_select = isinstance(tree, (exp.Select, exp.Union)) or (
        isinstance(tree, exp.With) and isinstance(tree.this, (exp.Select, exp.Union))
    )
    if not is_select:
        return GuardResult(ok=False, reason="Only read-only SELECT queries are allowed.")

    # 3) No forbidden statement types anywhere in the tree.
    for node_type in FORBIDDEN_NODES:
        if list(tree.find_all(node_type)):
            return GuardResult(
                ok=False,
                reason=f"Statement type '{node_type.__name__}' is not permitted.",
            )

    # 4) No IO / table-valued functions.
    for fn in tree.find_all(exp.Anonymous):
        name = (fn.name or "").lower()
        if name in FORBIDDEN_FUNCTIONS:
            return GuardResult(ok=False, reason=f"Function '{name}' is not permitted.")
    for fn in tree.find_all(exp.Func):
        name = (fn.sql_name() or "").lower()
        if name in FORBIDDEN_FUNCTIONS:
            return GuardResult(ok=False, reason=f"Function '{name}' is not permitted.")

    # 5) Collect base tables (ignore CTE names) and enforce the table allowlist.
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    referenced_tables: set[str] = set()
    for tbl in tree.find_all(exp.Table):
        tname = tbl.name.lower()
        if tname in cte_names:
            continue  # reference to a CTE, not a base table
        referenced_tables.add(tname)

    allowed_tables = {t.lower() for t in allowlist}
    unknown = referenced_tables - allowed_tables
    if unknown:
        return GuardResult(
            ok=False,
            reason=f"Query references tables outside the allowlist: {sorted(unknown)}",
            tables=referenced_tables,
        )

    # 6) Best-effort column validation: any simple, qualified-or-bare column that
    #    isn't a known column in *any* allowlisted table is flagged. Aliases and
    #    expression outputs are excluded to avoid false positives.
    all_columns = {c.lower() for cols in allowlist.values() for c in cols}
    referenced_columns: set[str] = set()
    bad_columns: set[str] = set()
    alias_names = {a.alias_or_name.lower() for a in tree.find_all(exp.Alias)}
    for col in tree.find_all(exp.Column):
        cname = col.name.lower()
        if not cname or cname == "*":
            continue
        referenced_columns.add(cname)
        if cname in all_columns or cname in alias_names:
            continue
        bad_columns.add(cname)
    if bad_columns:
        return GuardResult(
            ok=False,
            reason=f"Query references unknown columns: {sorted(bad_columns)}",
            tables=referenced_tables,
            columns=referenced_columns,
        )

    normalized = tree.sql(dialect="duckdb", pretty=True)
    return GuardResult(
        ok=True,
        normalized_sql=normalized,
        tables=referenced_tables,
        columns=referenced_columns,
    )
