"""Deterministic responses for the offline StubLLM.

When no real ANTHROPIC_API_KEY is configured, the StubLLM uses these fixtures so
the whole agent (route -> SQL -> guard -> execute -> compose, plus clarify/refuse)
runs end-to-end for tests and demos. The SQL here is the reference ("golden")
SQL for the 10 evaluation questions, verified by hand against the data.

This is explicitly a *fallback*, not the production path: with a real key the
AnthropicLLM generates SQL live. Keeping the golden SQL in one place also makes
it the oracle the eval harness checks the live model against.
"""

from __future__ import annotations

import re

# --- Golden SQL for the answerable evaluation questions -----------------------

Q1 = """SELECT ROUND(SUM(o.net_revenue), 2) AS net_revenue
FROM fact_orders o JOIN dim_account a USING (account_id)
WHERE a.region = 'West'
  AND o.order_date BETWEEN DATE '2024-10-01' AND DATE '2024-12-31'"""

Q2 = """SELECT sku_id, SUM(quantity_cases) AS total_cases
FROM fact_orders
GROUP BY sku_id
ORDER BY total_cases DESC
LIMIT 5"""

Q3 = """SELECT account_id, ROUND(SUM(approved_amount), 2) AS total_approved
FROM fact_reimbursements
WHERE status = 'Approved'
GROUP BY account_id
ORDER BY total_approved DESC
LIMIT 5"""

Q7 = """SELECT ROUND(SUM(quantity_cases * unit_price), 2) AS gross_sales
FROM fact_orders
WHERE account_id = 'ACC0001'"""

Q8 = """SELECT
  SUM(CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN o.quantity_cases ELSE 0 END) AS summer_cases,
  SUM(CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN 0 ELSE o.quantity_cases END) AS rest_cases,
  COUNT(DISTINCT CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN date_trunc('month', o.order_date) END) AS summer_months,
  COUNT(DISTINCT CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN NULL ELSE date_trunc('month', o.order_date) END) AS rest_months
FROM fact_orders o JOIN dim_product p USING (sku_id)
WHERE p.category = 'Seltzer'"""

Q10 = """SELECT program,
  SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) AS rejected,
  ROUND(100.0 * SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN status IN ('Approved','Rejected') THEN 1 ELSE 0 END), 0), 1)
        AS approval_rate_pct
FROM fact_reimbursements
GROUP BY program
ORDER BY program"""


def _match(user: str) -> str:
    """Map a question to a fixture key by keyword. Cheap and deterministic."""
    u = user.lower()
    if "west" in u and "q4" in u:
        return "q1"
    if "top 5 skus" in u or ("top" in u and "case volume" in u):
        return "q2"
    if "approved" in u and "reimbursement" in u and "account" in u:
        return "q3"
    if "underperforming" in u:
        return "q4_ambiguous"
    if "director sign-off" in u or "maximum line discount" in u:
        return "q5_kb"
    if "display incentive" in u and "distributor" in u:
        return "q6_kb"
    if "gross sales" in u or ("gross" in u and "acc0001" in u):
        return "q7"
    if "seltzer" in u and "summer" in u:
        return "q8"
    if "projected" in u or "next quarter" in u:
        return "q9_unanswerable"
    if "approval rate" in u and "program" in u:
        return "q10"
    return "unknown"


_SQL_FIXTURES = {
    "q1": (Q1, "Net revenue (already discounted) for West region orders in calendar Q4 2024."),
    "q2": (Q2, "Total case volume per SKU; quantity_cases is the depletion proxy."),
    "q3": (Q3, "Only status='Approved' claims count, summing approved_amount, not claim_amount."),
    "q7": (Q7, "Gross = quantity_cases*unit_price; not the stored net_revenue."),
    "q8": (Q8, "Seltzer cases split into summer (May-Aug) vs rest, with month counts to normalise."),
    "q10": (Q10, "Approval rate = Approved/(Approved+Rejected) per program, excluding Pending."),
}


def stub_response(*, system: str, user: str) -> dict:
    """Return a deterministic structured response keyed off the system task tag."""
    key = _match(user)

    if "[TASK:sql_generation]" in system:
        if key in _SQL_FIXTURES:
            sql, rationale = _SQL_FIXTURES[key]
            return {"sql": sql, "rationale": rationale, "unanswerable": False, "reason": ""}
        if key == "q9_unanswerable":
            return {"sql": None, "rationale": "", "unanswerable": True,
                    "reason": "No forecast/budget table exists; forward-looking questions "
                              "cannot be answered from this data (KB-06/07)."}
        # Ambiguous or KB questions should not reach SQL generation, but be safe:
        return {"sql": None, "rationale": "", "unanswerable": True,
                "reason": "This question is not a straightforward SQL lookup."}

    if "[TASK:classify]" in system:
        return _stub_classify(key)

    if "[TASK:compose]" in system:
        return {"answer": "(offline stub answer composed from the retrieved evidence)"}

    return {"error": f"stub has no handler for this task; key={key}"}


def _stub_classify(key: str) -> dict:
    """Offline routing decision used by the agent's classify node."""
    routes = {
        "q1": "sql", "q2": "sql", "q3": "sql", "q7": "sql", "q8": "sql", "q10": "sql",
        "q5_kb": "kb", "q6_kb": "kb",
        "q4_ambiguous": "clarify",
        "q9_unanswerable": "refuse",
    }
    route = routes.get(key, "sql")
    reason = {
        "clarify": "Underperformance has no single definition; metric and period are unspecified.",
        "refuse": "Forward-looking projection; no forecast table exists.",
        "kb": "Policy/definition question answered from the knowledge base.",
        "sql": "Quantitative question answerable from the tables.",
    }[route]
    return {"route": route, "reason": reason, "confidence": 0.9}
