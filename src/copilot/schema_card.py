"""Schema card: the grounding context handed to the SQL generator.

A good Text-to-SQL system does not just dump column names at the model. This
card combines three kinds of grounding:

1. **Structural** — tables, columns, types (introspected from DuckDB).
2. **Value** — the distinct values of low-cardinality categorical columns, so
   the model writes correct literals (`region = 'West'`, not `'west coast'`).
3. **Semantic** — business rules distilled from the knowledge base that change
   how SQL must be written (net vs. gross revenue, what "approved" means,
   calendar quarters, tier eligibility, and what the data simply cannot answer).

The semantic rules are deliberately curated from KB-01..KB-07 and tagged with
their source so the card stays auditable.
"""

from __future__ import annotations

from .db import Database

# Short human descriptions per column — keeps the card compact but informative.
COLUMN_NOTES: dict[str, dict[str, str]] = {
    "dim_account": {
        "account_id": "PK, e.g. ACC0001",
        "account_type": "tier: 'Retailer' or 'Distributor'",
        "on_premise_flag": "1 = retailer selling for on-site consumption (bar/restaurant)",
    },
    "dim_product": {
        "sku_id": "PK, e.g. SKU0001",
        "category": "Beer / Wine / Spirits / Seltzer / Non-Alcoholic",
    },
    "fact_orders": {
        "quantity_cases": "case volume; use as the depletion proxy",
        "unit_price": "price per case before discount",
        "discount_pct": "line discount in PERCENT (0-20), not a fraction",
        "net_revenue": "revenue AFTER discount = quantity_cases*unit_price*(1-discount_pct/100)",
    },
    "fact_reimbursements": {
        "program": "Depletion Allowance / Display Incentive / Price Support / Volume Rebate",
        "claim_amount": "amount claimed (gross of approval)",
        "approved_amount": "amount approved; NULL for Pending, 0 for Rejected",
        "status": "Pending / Approved / Rejected",
    },
}

# Columns to value-ground (low cardinality, frequently used in filters).
VALUE_GROUND_COLUMNS: list[tuple[str, str]] = [
    ("dim_account", "region"),
    ("dim_account", "account_type"),
    ("dim_product", "category"),
    ("fact_reimbursements", "program"),
    ("fact_reimbursements", "status"),
]

# Business semantics distilled from the knowledge base. Each rule cites its KB
# source so the grounding is auditable and traceable in answers.
BUSINESS_RULES: list[tuple[str, str]] = [
    ("KB-01", "'Revenue' means NET revenue (fact_orders.net_revenue) unless the user "
              "explicitly says 'gross'. Net revenue is already discounted — never "
              "re-apply the discount."),
    ("KB-01", "GROSS sales are NOT stored. Compute as SUM(quantity_cases * unit_price). "
              "Do not use net_revenue for a gross question."),
    ("KB-01", "Only claims with status='Approved' count as paid reimbursement, and the "
              "paid value is approved_amount (not claim_amount). Exclude Pending "
              "(approved_amount is NULL)."),
    ("KB-01/05", "'Depletion' / case volume = SUM(quantity_cases)."),
    ("KB-01", "An 'active' account has >=1 order in the trailing 90 days; otherwise it is "
              "'lapsed'."),
    ("KB-02", "Discount approval matrix: 0-10% rep discretion; 11-15% regional manager; "
              "16-20% director sign-off; >20% not permitted on standard orders. Max "
              "discount WITHOUT director sign-off = 15%."),
    ("KB-03", "Reimbursement approval rate = Approved / (Approved + Rejected), EXCLUDING "
              "Pending. Compute per program when asked."),
    ("KB-03/04", "Tier eligibility: Depletion Allowance & Volume Rebate = distributors "
                 "only; Display Incentive = retailers only; Price Support = both."),
    ("KB-06", "Fiscal quarters follow the calendar year: Q1=Jan-Mar, Q2=Apr-Jun, "
              "Q3=Jul-Sep, Q4=Oct-Dec."),
    ("KB-06", "The Nov-2024 West-region holiday surcharge on Spirits is EXPECTED, not a "
              "data error — do not filter it out."),
    ("KB-06/07", "There is NO forecast/budget table. Forward-looking questions (projections, "
                 "'next quarter') CANNOT be answered from this data — do not fabricate."),
    ("KB-05", "Joins: fact_* join to dim_account on account_id and to dim_product on sku_id."),
]


def build_schema_card(db: Database) -> str:
    """Render the full grounding card as text for the SQL-generation prompt."""
    schema = db.schema()
    lines: list[str] = ["# DATABASE SCHEMA (DuckDB)\n"]

    for table, info in schema.items():
        lines.append(f"## {table}")
        for col in info.columns:
            note = COLUMN_NOTES.get(table, {}).get(col.name, "")
            suffix = f"  -- {note}" if note else ""
            lines.append(f"  {col.name} {col.dtype}{suffix}")
        lines.append("")

    # Value grounding
    con = db.connect_readonly()
    try:
        lines.append("# CATEGORICAL VALUES (use these exact literals)")
        for table, col in VALUE_GROUND_COLUMNS:
            vals = [r[0] for r in con.execute(
                f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL ORDER BY 1"
            ).fetchall()]
            lines.append(f"  {table}.{col}: {vals}")
        lines.append("")
    finally:
        con.close()

    lines.append("# BUSINESS RULES (from the knowledge base — follow exactly)")
    for src, rule in BUSINESS_RULES:
        lines.append(f"  [{src}] {rule}")
    lines.append("")

    return "\n".join(lines)
