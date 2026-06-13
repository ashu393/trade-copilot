"""Natural-language -> SQL generation, grounded in the schema card.

The generator returns a small structured object rather than a bare string so the
agent can reason about it: the SQL, a one-line rationale, and an explicit
`unanswerable` flag for questions the *tables* cannot answer (e.g. forward-looking
projections — there is no forecast table). Routing/clarification lives in the
agent (Part B); this module's job is just "given a data question, write safe SQL
or say the data can't answer it."
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..llm import LLMClient

# A task tag at the top of the system prompt lets the offline stub recognise the
# call type without parsing free text.
TASK_TAG = "[TASK:sql_generation]"

SYSTEM_TEMPLATE = """{tag}
You are a careful analytics engineer for a US beverage three-tier distribution
platform. Translate the user's business question into ONE DuckDB SQL SELECT
statement over the schema below, following the BUSINESS RULES exactly.

{schema_card}

Rules for your output:
- Output ONLY a JSON object, no prose, no markdown fences.
- Shape: {{"sql": <string|null>, "rationale": <string>, "unanswerable": <bool>, "reason": <string>}}
- "sql": a single read-only SELECT (CTEs allowed). No DDL/DML. Round money to 2 dp.
- If the question cannot be answered from these tables (e.g. it asks for a
  forecast/projection, or data that does not exist), set "unanswerable": true,
  "sql": null, and explain in "reason".
- Prefer explicit column lists and clear aliases. Use the exact categorical
  literals given. Respect net-vs-gross and approved-reimbursement rules."""


@dataclass
class SqlPlan:
    sql: str | None
    rationale: str
    unanswerable: bool
    reason: str


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model output: {text[:200]}")
    return json.loads(text[start : end + 1])


def generate_sql(question: str, schema_card: str, llm: LLMClient) -> SqlPlan:
    system = SYSTEM_TEMPLATE.format(tag=TASK_TAG, schema_card=schema_card)
    raw = llm.complete(system=system, user=question, max_tokens=900)
    try:
        data = _parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return SqlPlan(sql=None, rationale="", unanswerable=True,
                       reason=f"Could not parse model output: {e}")
    return SqlPlan(
        sql=data.get("sql"),
        rationale=data.get("rationale", ""),
        unanswerable=bool(data.get("unanswerable", False)),
        reason=data.get("reason", ""),
    )
