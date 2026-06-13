"""Regression tests: run the agent on all 10 questions, assert against golden.

These double as the Part A evaluation report and the answer-correctness oracle.
They run fully offline (deterministic stub), so they are safe for CI.
"""

from __future__ import annotations

import pytest

from copilot.agent import build_agent, run_agent
from copilot.eval_questions import load_eval_questions
from golden import find_golden


@pytest.fixture(scope="module")
def agent():
    a, _ = build_agent()
    return a


@pytest.mark.parametrize("question", load_eval_questions())
def test_question_matches_golden(agent, question):
    golden = find_golden(question)
    assert golden is not None, f"No golden entry for: {question}"

    r = run_agent(question, agent)

    assert r["status"] == golden["status"], (
        f"{question!r}: status {r['status']} != {golden['status']}"
    )
    assert r["route"] == golden["route"], (
        f"{question!r}: route {r['route']} != {golden['route']}"
    )

    answer = r["answer"]
    for needle in golden.get("contains", []):
        assert needle in answer, f"{question!r}: expected {needle!r} in answer:\n{answer}"
    any_opts = golden.get("contains_any")
    if any_opts:
        assert any(opt in answer for opt in any_opts), (
            f"{question!r}: expected one of {any_opts} in answer:\n{answer}"
        )


def test_sql_answers_carry_sql(agent):
    """Every SQL-routed answer must surface the SQL it ran (auditability)."""
    for q in load_eval_questions():
        r = run_agent(q, agent)
        if r["route"] == "sql" and r["status"] == "answered":
            assert r["sql"], f"SQL-routed answer missing SQL: {q}"


def test_trace_is_bounded(agent):
    """No path should visit more nodes than the bounded graph allows."""
    for q in load_eval_questions():
        r = run_agent(q, agent)
        assert len(r["trace"]) <= 8, f"Unexpectedly long trace for {q}: {r['trace']}"
