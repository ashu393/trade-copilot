"""Agent node implementations.

Design choices that matter for trust:

* **Numbers come from SQL, never from the LLM.** The compose step formats the
  executed result deterministically; the model only phrases verified figures.
* **Every path is explainable.** Each node appends its name to `state['trace']`.
* **Bounded loops.** The SQL path may retry generation at most `max_retries`
  times on an execution/validation failure, then it declines rather than loops.
* **Low confidence -> clarify/refuse**, never answer anyway.
"""

from __future__ import annotations

import json

from ..db import Database
from ..llm import LLMClient
from ..kb.retriever import KBRetriever
from ..sql.execute import run_guarded
from ..sql.generate import generate_sql
from .state import AgentState

CONFIDENCE_THRESHOLD = 0.5
MAX_RETRIES = 1

CLASSIFY_TAG = "[TASK:classify]"
COMPOSE_TAG = "[TASK:compose]"

CLASSIFY_SYSTEM = """{tag}
You route a user's question to one of four handlers for a beverage-distribution
analytics assistant. Reply with ONLY a JSON object:
{{"route": "sql"|"kb"|"clarify"|"refuse", "reason": <string>, "confidence": <0..1>}}

Routes:
- "sql": a quantitative question answerable from the tables (orders, reimbursements,
  accounts, products) — totals, rankings, rates, comparisons.
- "kb": a policy / definition / eligibility question (discount approval limits,
  who can claim a program, what a metric means).
- "clarify": the question is ambiguous and cannot be answered correctly as asked
  — e.g. "underperforming" with no stated metric or period. Performance has no
  single definition; ask which metric and period.
- "refuse": the data cannot answer it — forward-looking forecasts/projections
  (there is no forecast or budget table), or data that does not exist.

Tables available: dim_account, dim_product, fact_orders, fact_reimbursements.
Knowledge base covers: metric glossary, discount/approval policy, reimbursement
programs & tier eligibility, three-tier compliance, data dictionary, exceptions,
reporting standards."""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"no JSON in: {text[:160]}")
    return json.loads(text[s : e + 1])


class AgentNodes:
    def __init__(
        self,
        db: Database,
        schema_card: str,
        retriever: KBRetriever,
        classify_llm: LLMClient,
        sql_llm: LLMClient,
        compose_llm: LLMClient,
        max_retries: int = MAX_RETRIES,
    ):
        self.db = db
        self.schema_card = schema_card
        self.retriever = retriever
        self.classify_llm = classify_llm
        self.sql_llm = sql_llm
        self.compose_llm = compose_llm
        self.max_retries = max_retries

    # ---- classify -----------------------------------------------------------
    def classify(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["classify"]
        system = CLASSIFY_SYSTEM.format(tag=CLASSIFY_TAG)
        try:
            data = _parse_json(
                self.classify_llm.complete(system=system, user=state["question"], max_tokens=300)
            )
            route = data.get("route", "sql")
            reason = data.get("reason", "")
            confidence = float(data.get("confidence", 0.6))
        except Exception as e:  # noqa: BLE001
            route, reason, confidence = "clarify", f"classifier error: {e}", 0.0

        # Low-confidence guard: don't answer on a shaky route.
        if confidence < CONFIDENCE_THRESHOLD and route in ("sql", "kb"):
            route, reason = "clarify", f"Low routing confidence ({confidence:.2f}). {reason}"

        return {**state, "route": route, "route_reason": reason,
                "confidence": confidence, "trace": trace, "retries": 0}

    # ---- sql generation -----------------------------------------------------
    def gen_sql(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["gen_sql"]
        question = state["question"]
        # On retry, append the prior error so the model can self-correct.
        prompt = question
        if state.get("exec_error"):
            prompt = (f"{question}\n\n-- Previous attempt failed with: "
                      f"{state['exec_error']}\n-- Fix the SQL.")
        plan = generate_sql(prompt, self.schema_card, self.sql_llm)
        return {**state, "sql": plan.sql, "sql_rationale": plan.rationale,
                "sql_unanswerable": plan.unanswerable,
                "sql_unanswerable_reason": plan.reason, "trace": trace}

    # ---- execute + validate -------------------------------------------------
    def execute_validate(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["execute_validate"]
        if state.get("sql_unanswerable"):
            return {**state, "exec_ok": False, "validation_ok": False,
                    "validation_issues": [state.get("sql_unanswerable_reason", "unanswerable")],
                    "trace": trace}

        res = run_guarded(self.db, state.get("sql") or "")
        issues: list[str] = []
        if not res.ok:
            issues.append(res.error or "execution failed")
        else:
            if res.row_count == 0:
                issues.append("Query returned no rows — the filter may be wrong.")
            # Numeric sanity: revenue/amount/cases columns should not be negative.
            for rec in res.to_records():
                for col, val in rec.items():
                    if isinstance(val, (int, float)) and val < 0 and any(
                        k in col.lower() for k in ("revenue", "amount", "cases", "gross", "approved")
                    ):
                        issues.append(f"Negative value in '{col}' ({val}) is implausible.")
                        break

        validation_ok = res.ok and not issues
        return {
            **state,
            "exec_ok": res.ok,
            "exec_error": res.error,
            "result_columns": res.columns,
            "result_rows": res.rows,
            "result_records": res.to_records(),
            "validation_ok": validation_ok,
            "validation_issues": issues,
            "retries": state.get("retries", 0) + (0 if validation_ok else 1),
            "trace": trace,
        }

    # ---- kb retrieval -------------------------------------------------------
    def retrieve_kb(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["retrieve_kb"]
        hits = self.retriever.search(state["question"], k=3, min_score=0.03)
        kb_hits = [
            {"chunk_id": h.chunk.chunk_id, "doc_id": h.chunk.doc_id,
             "citation": h.chunk.citation, "text": h.chunk.text, "score": h.score}
            for h in hits
        ]
        return {**state, "kb_hits": kb_hits, "trace": trace}

    # ---- compose ------------------------------------------------------------
    def compose(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["compose"]
        route = state.get("route")
        if route == "sql":
            answer, citations = self._compose_sql(state)
            status = "answered"
        else:  # kb
            answer, citations = self._compose_kb(state)
            status = "answered"
        return {**state, "answer": answer, "citations": citations,
                "status": status, "trace": trace}

    def _compose_sql(self, state: AgentState) -> tuple[str, list[str]]:
        records = state.get("result_records", [])
        cols = state.get("result_columns", [])
        citation = [f"SQL over {', '.join(sorted(set(self._tables_in(state.get('sql',''))))) or 'mini-DB'}"]

        if not records:
            return "The query ran successfully but returned no rows.", citation

        # Scalar answer.
        if len(records) == 1 and len(cols) == 1:
            val = records[0][cols[0]]
            return f"{self._fmt(val)} ({cols[0]}).", citation

        # Single-row, multi-column (e.g. the Seltzer summer vs rest comparison).
        if len(records) == 1:
            r = records[0]
            note = self._seltzer_note(r)
            body = "; ".join(f"{k} = {self._fmt(v)}" for k, v in r.items())
            return (body + (f". {note}" if note else "")), citation

        # Multi-row table: render compactly.
        lines = [" | ".join(cols)]
        for r in records[:10]:
            lines.append(" | ".join(self._fmt(r[c]) for c in cols))
        return "\n".join(lines), citation

    def _compose_kb(self, state: AgentState) -> tuple[str, list[str]]:
        hits = state.get("kb_hits", [])
        if not hits:
            return ("I couldn't find anything in the knowledge base to answer that.", [])
        citations = list(dict.fromkeys(h["citation"] for h in hits))
        # Prefer an LLM answer grounded in the chunks; fall back to the top chunk.
        context = "\n\n".join(f"[{h['doc_id']}] {h['text']}" for h in hits)
        system = (f"{COMPOSE_TAG}\nAnswer the question using ONLY the knowledge-base "
                  f"excerpts. Be concise and cite the KB id(s). If the excerpts don't "
                  f"answer it, say so. Reply as JSON: {{\"answer\": <string>}}.")
        user = f"Question: {state['question']}\n\nExcerpts:\n{context}"
        try:
            data = _parse_json(self.compose_llm.complete(system=system, user=user, max_tokens=400))
            answer = data.get("answer") or hits[0]["text"]
            if "stub" in answer:  # offline stub -> use grounded chunk text
                answer = hits[0]["text"]
        except Exception:  # noqa: BLE001
            answer = hits[0]["text"]
        return answer, citations[:2]

    # ---- clarify / refuse ---------------------------------------------------
    def clarify(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["clarify"]
        reason = state.get("route_reason", "")
        answer = (
            "I need a bit more detail to answer this correctly. "
            "Performance at ABC has no single definition — it's always reported against a "
            "specific metric (net revenue, case volume, or margin) and a specific period. "
            "Which metric and over what period should I use, and how do you want "
            "\"underperforming\" defined (e.g. bottom decile, or below a threshold)?"
        )
        return {**state, "answer": answer, "citations": ["KB-01 — Metric & Term Glossary",
                "KB-07 — Reporting Standards"], "status": "clarify", "trace": trace}

    def refuse(self, state: AgentState) -> AgentState:
        trace = state.get("trace", []) + ["refuse"]
        # Two refusal causes: (a) the data genuinely can't answer (forecast), or
        # (b) we failed to produce a valid/validated query after bounded retries.
        if state.get("route") == "refuse" or state.get("sql_unanswerable"):
            answer = (
                "I can't answer that from the available data. This dataset has no forecast or "
                "budget table, so forward-looking figures (projections, next-quarter estimates) "
                "can't be derived from it. I won't fabricate a number. I can instead report "
                "historical trends (e.g. net revenue by quarter to date) if that would help."
            )
            citations = ["KB-06 — Operational Exception Log", "KB-07 — Reporting Standards"]
        else:
            issues = "; ".join(state.get("validation_issues", [])) or "unknown error"
            answer = (
                "I wasn't able to produce a query I'm confident in for this question "
                f"(issue: {issues}). Rather than return a number I can't stand behind, "
                "I'm flagging it for a human. Could you rephrase or add detail?"
            )
            citations = []
        return {**state, "answer": answer, "citations": citations,
                "status": "refused", "trace": trace}

    # ---- helpers ------------------------------------------------------------
    @staticmethod
    def _fmt(v) -> str:
        if isinstance(v, float):
            return f"{v:,.2f}"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)

    @staticmethod
    def _tables_in(sql: str) -> list[str]:
        return [t for t in ("fact_orders", "fact_reimbursements", "dim_account", "dim_product")
                if t in (sql or "")]

    @staticmethod
    def _seltzer_note(r: dict) -> str:
        """For the Seltzer comparison, normalise per-month and state it honestly."""
        keys = {k.lower(): k for k in r}
        if "summer_cases" in keys and "rest_cases" in keys and "summer_months" in keys:
            sc, rc = r[keys["summer_cases"]], r[keys["rest_cases"]]
            sm, rm = r[keys["summer_months"]], r[keys["rest_months"]]
            if sm and rm:
                s_pm, r_pm = sc / sm, rc / rm
                diff = s_pm - r_pm
                return (f"Periods are unequal ({sm} summer months vs {rm} other months), so "
                        f"compare per month: summer {s_pm:,.0f}/mo vs rest {r_pm:,.0f}/mo — "
                        f"summer is {diff:,.0f} cases/month higher "
                        f"({diff / r_pm * 100:,.0f}% higher per month)")
        return ""
