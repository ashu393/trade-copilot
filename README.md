# Trade Intelligence Copilot

A trustworthy AI assistant over a three-tier beverage-distribution dataset (Supplier → Distributor → Retailer), built for the ABC Company technical assessment.

It has three parts:

| Part | What it does |
|------|--------------|
| **A — Conversational analytics** | Text-to-SQL over a DuckDB mini-DB + RAG over a policy/glossary knowledge base. Returns an answer, the generated SQL, and KB citations. |
| **B — Agentic workflow** | A LangGraph agent: classify → route (SQL / KB) → validate → compose. Declines or asks for clarification when not confident. |
| **C — Account-retention model** | A churn model trained on `accounts_train.csv`, scoring `accounts_serve.csv` into a ranked at-risk list, plus impact and production-design notes. |

## Design principles

The dataset is a deliberately imperfect production export. The system is built to **show its work and know its limits**:

- Every analytical answer carries the **SQL it ran** and the **KB source** it grounded in.
- Generated SQL passes a **safety guard** (read-only `SELECT` only, table/column allowlist, no DML/DDL/multi-statement, row + time limits) before execution.
- Ambiguous questions (e.g. "show underperforming accounts") trigger a **clarifying question**; unanswerable ones (e.g. "projected revenue next quarter" — no forecast table exists) are **declined** rather than fabricated.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # then put your real ANTHROPIC_API_KEY in .env

# Ask a single question
copilot ask "What was total net revenue in the West region for Q4 2024?"

# Run the full Part A evaluation (10 questions)
copilot eval

# Train + score the Part C churn model
python -m partc.score
```

Without a real API key the SQL/compose steps fall back to a deterministic offline stub so the pipeline still runs end-to-end.

## Layout

```
src/copilot/      # Part A + B: db, schema card, sql/, kb/, agent/, cli, api
partc/            # Part C: training pipeline, evaluation, scoring
eval/             # pytest regression tests for the 10 questions + SQL guard
data/             # the assessment export (CSVs + knowledge base)
outputs/          # generated SQL log, ranked at-risk list
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the agent graph and design rationale.
