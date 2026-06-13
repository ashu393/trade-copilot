"""DuckDB loader + schema introspection for the Part A mini-DB.

The four CSVs are loaded into a DuckDB file. Two connection kinds are exposed:

* a **writable** connection used once at build time to load the CSVs, and
* **read-only** connections handed to the query executor.

Engine-level read-only is defence-in-depth: even if a destructive statement
slipped past the SQL guard, a read-only connection would reject it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from .config import DATA_DIR, OUTPUTS_DIR

# Logical table name -> source CSV. This is also the executor's allowlist.
TABLES: dict[str, str] = {
    "dim_account": "dim_account.csv",
    "dim_product": "dim_product.csv",
    "fact_orders": "fact_orders.csv",
    "fact_reimbursements": "fact_reimbursements.csv",
}


@dataclass
class ColumnInfo:
    name: str
    dtype: str


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


class Database:
    """Owns the DuckDB file built from the assessment CSVs."""

    def __init__(self, db_path: Path | None = None, data_dir: Path = DATA_DIR):
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        # Default to a file (not :memory:) so we can open independent
        # read-only connections against the same data.
        self.db_path = db_path or (OUTPUTS_DIR / "mini_db.duckdb")
        self.data_dir = data_dir
        self._schema: dict[str, TableInfo] | None = None

    def build(self, *, force: bool = True) -> "Database":
        """(Re)build the DuckDB file from the CSVs."""
        if force and self.db_path.exists():
            self.db_path.unlink()
        con = duckdb.connect(str(self.db_path))
        try:
            for table, csv_name in TABLES.items():
                csv_path = self.data_dir / csv_name
                if not csv_path.exists():
                    raise FileNotFoundError(f"Missing data file: {csv_path}")
                con.execute(
                    f"CREATE OR REPLACE TABLE {table} AS "
                    f"SELECT * FROM read_csv_auto(?, header=true)",
                    [str(csv_path)],
                )
        finally:
            con.close()
        self._schema = None
        return self

    def _ensure_built(self) -> None:
        if not self.db_path.exists():
            self.build()

    def connect_readonly(self) -> duckdb.DuckDBPyConnection:
        """Open a fresh read-only connection. Caller is responsible for closing."""
        self._ensure_built()
        return duckdb.connect(str(self.db_path), read_only=True)

    def schema(self) -> dict[str, TableInfo]:
        """Introspect column names/types for every allowlisted table."""
        if self._schema is not None:
            return self._schema
        self._ensure_built()
        con = self.connect_readonly()
        try:
            schema: dict[str, TableInfo] = {}
            for table in TABLES:
                rows = con.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = ? ORDER BY ordinal_position",
                    [table],
                ).fetchall()
                schema[table] = TableInfo(
                    name=table,
                    columns=[ColumnInfo(name=r[0], dtype=str(r[1])) for r in rows],
                )
            self._schema = schema
            return schema
        finally:
            con.close()

    def allowlist(self) -> dict[str, set[str]]:
        """Return {table: {columns}} for the SQL guard to validate against."""
        return {name: set(info.column_names) for name, info in self.schema().items()}
