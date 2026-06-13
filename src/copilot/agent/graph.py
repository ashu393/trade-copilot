"""LangGraph wiring for the Trade Intelligence Copilot agent.

Graph shape (Part B):

    classify ─┬─ sql ──▶ gen_sql ─▶ execute_validate ─┬─ ok ──────▶ compose ─▶ END
              │                          ▲             ├─ retry ───▶ gen_sql (bounded)
              │                          └─────────────┤
              │                                        └─ give up ─▶ refuse  ─▶ END
              ├─ kb ──────▶ retrieve_kb ─────────────────────────▶ compose ─▶ END
              ├─ clarify ─────────────────────────────────────────────────▶ clarify ─▶ END
              └─ refuse ──────────────────────────────────────────────────▶ refuse  ─▶ END

Loop/termination control is explicit: `execute_validate` increments a retry
counter, and the conditional edge only loops back to `gen_sql` while
retries <= max_retries. Otherwise it terminates at `refuse`. Low classifier
confidence diverts to `clarify`. Nothing answers on a shaky basis.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ..db import Database
from ..kb.retriever import KBRetriever
from ..llm import make_llm
from ..schema_card import build_schema_card
from .nodes import AgentNodes
from .state import AgentState


def _route_from_classify(state: AgentState) -> str:
    return state.get("route", "clarify")


def _make_validate_router(max_retries: int):
    """Bind the retry budget into the conditional edge (TypedDict state can't carry it)."""

    def _route_after_validate(state: AgentState) -> str:
        if state.get("validation_ok"):
            return "compose"
        if state.get("sql_unanswerable"):
            return "refuse"
        if state.get("retries", 0) <= max_retries:
            return "gen_sql"
        return "refuse"

    return _route_after_validate


def build_agent(
    db: Database | None = None,
    *,
    schema_card: str | None = None,
    retriever: KBRetriever | None = None,
    classify_model: str = "classify",
    sql_model: str = "sql",
    compose_model: str = "compose",
    max_retries: int = 1,
):
    """Compile and return the LangGraph agent plus the AgentNodes deps."""
    db = db or Database().build()
    schema_card = schema_card or build_schema_card(db)
    retriever = retriever or KBRetriever()

    from ..config import settings

    # When a real key exists, use the configured Claude models; offline -> stub.
    cls_llm = make_llm(settings.copilot_compose_model if settings.has_real_api_key else classify_model)
    sql_llm = make_llm(settings.copilot_sql_model if settings.has_real_api_key else sql_model)
    cmp_llm = make_llm(settings.copilot_compose_model if settings.has_real_api_key else compose_model)

    nodes = AgentNodes(db, schema_card, retriever, cls_llm, sql_llm, cmp_llm, max_retries)

    g = StateGraph(AgentState)
    g.add_node("classify", nodes.classify)
    g.add_node("gen_sql", nodes.gen_sql)
    g.add_node("execute_validate", nodes.execute_validate)
    g.add_node("retrieve_kb", nodes.retrieve_kb)
    g.add_node("compose", nodes.compose)
    g.add_node("clarify", nodes.clarify)
    g.add_node("refuse", nodes.refuse)

    g.set_entry_point("classify")
    g.add_conditional_edges("classify", _route_from_classify, {
        "sql": "gen_sql", "kb": "retrieve_kb", "clarify": "clarify", "refuse": "refuse",
    })
    g.add_edge("gen_sql", "execute_validate")
    g.add_conditional_edges("execute_validate", _make_validate_router(max_retries), {
        "compose": "compose", "gen_sql": "gen_sql", "refuse": "refuse",
    })
    g.add_edge("retrieve_kb", "compose")
    g.add_edge("compose", END)
    g.add_edge("clarify", END)
    g.add_edge("refuse", END)

    return g.compile(), nodes


def run_agent(question: str, agent=None, max_retries: int = 1) -> dict[str, Any]:
    """Run one question through the agent and return a clean result dict."""
    if agent is None:
        agent, _ = build_agent(max_retries=max_retries)
    initial: AgentState = {"question": question}
    final = agent.invoke(initial)
    return {
        "question": question,
        "status": final.get("status"),
        "route": final.get("route"),
        "route_reason": final.get("route_reason"),
        "confidence": final.get("confidence"),
        "answer": final.get("answer"),
        "sql": final.get("sql"),
        "citations": final.get("citations", []),
        "validation_issues": final.get("validation_issues", []),
        "trace": final.get("trace", []),
    }
