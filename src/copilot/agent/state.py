"""Typed state that flows between agent nodes.

LangGraph threads a single state dict through the graph. Keeping it a typed
TypedDict documents exactly what each node may read and write, which is the
"what state flows between them" the Part B brief asks for.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Route = Literal["sql", "kb", "clarify", "refuse"]


class AgentState(TypedDict, total=False):
    # --- input ---
    question: str

    # --- classify node ---
    route: Route
    route_reason: str
    confidence: float

    # --- sql path ---
    sql: str | None
    sql_rationale: str
    sql_unanswerable: bool
    sql_unanswerable_reason: str
    exec_ok: bool
    exec_error: str | None
    result_columns: list[str]
    result_rows: list[tuple[Any, ...]]
    result_records: list[dict[str, Any]]
    retries: int

    # --- kb path ---
    kb_hits: list[dict[str, Any]]   # [{chunk_id, doc_id, citation, text, score}]

    # --- validation ---
    validation_ok: bool
    validation_issues: list[str]

    # --- output ---
    answer: str
    citations: list[str]
    status: Literal["answered", "clarify", "refused", "error"]
    trace: list[str]                # ordered node names, for explainability
