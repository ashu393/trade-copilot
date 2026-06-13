"""Golden expectations for the 10 Part A questions — the evaluation oracle.

For each question we assert the *behaviour* (route/status) and, where the answer
is quantitative, the *value* computed independently against the data. This is how
the harness detects a wrong answer rather than just a plausible-looking one.
"""

from __future__ import annotations

# Each entry: question substring -> expected behaviour + checks.
GOLDEN = [
    {  # Q1
        "match": "west region for q4 2024",
        "status": "answered", "route": "sql",
        "contains": ["50,796.27"],
    },
    {  # Q2
        "match": "top 5 skus by total case volume",
        "status": "answered", "route": "sql",
        "contains": ["SKU0023", "830"],
    },
    {  # Q3
        "match": "highest total approved reimbursement",
        "status": "answered", "route": "sql",
        "contains": ["ACC0036", "17,027.12"],
    },
    {  # Q4 — ambiguous -> clarify
        "match": "underperforming accounts",
        "status": "clarify", "route": "clarify",
        "contains": ["metric", "period"],
    },
    {  # Q5 — KB
        "match": "maximum line discount",
        "status": "answered", "route": "kb",
        "contains": ["15%"],
    },
    {  # Q6 — KB
        "match": "distributor allowed to claim a display incentive",
        "status": "answered", "route": "kb",
        "contains_any": ["retailers only", "NOT eligible", "not eligible"],
    },
    {  # Q7 — gross, not net
        "match": "gross sales (before discount) for account acc0001",
        "status": "answered", "route": "sql",
        "contains": ["23,847.48"],
    },
    {  # Q8 — seltzer summer comparison (per-month normalisation)
        "match": "seltzer case volume in summer",
        "status": "answered", "route": "sql",
        "contains": ["2,009", "2,382"],
    },
    {  # Q9 — forward-looking -> refuse
        "match": "projected net revenue for next quarter",
        "status": "refused", "route": "refuse",
        "contains_any": ["no forecast", "can't answer", "cannot"],
    },
    {  # Q10 — approval rate per program
        "match": "approval rate for each program",
        "status": "answered", "route": "sql",
        "contains": ["Volume Rebate", "77.9"],
    },
]


def find_golden(question: str) -> dict | None:
    q = question.lower()
    for g in GOLDEN:
        if g["match"] in q:
            return g
    return None
