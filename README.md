# Trade Intelligence Copilot

A trustworthy AI assistant over a three-tier beverage-distribution dataset
(Supplier → Distributor → Retailer), built for the ABC Company Senior AI/ML
Architect assessment.

The dataset is a deliberately imperfect production export, so the hard part is
**judgment, not plumbing**: knowing when a number is wrong, when a question is
ambiguous, and when the data simply cannot answer. Every design choice optimises
for *trustworthiness* — the system shows the SQL it ran and the policy it cited,
refuses to fabricate, and asks before it guesses.

> **Live demo:** https://trade-copilot-production-952f.up.railway.app  ·  health: [`/health`](https://trade-copilot-production-952f.up.railway.app/health)
> *(deployed on Railway from this repo's Dockerfile)*

| Part | What it does |
|------|--------------|
| **A — Conversational analytics** | Text-to-SQL over a DuckDB mini-DB + RAG over a 7-doc policy/glossary knowledge base. Returns an answer, the generated SQL, and KB citations. |
| **B — Agentic workflow** | A LangGraph agent: classify → route (SQL / KB) → validate → compose. Declines or asks for clarification when not confident. |
| **C — Account-retention model** | A churn model trained on `accounts_train.csv`, scoring `accounts_serve.csv` into a ranked at-risk list, plus impact and production-design notes. |

## Submission contents

| Deliverable | Where |
|-------------|-------|
| Code repo | this repository |
| Write-up (≤3 pages): design, trade-offs, data findings | [`writeup.md`](writeup.md) |
| Agent graph diagram + node/edge reference | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Loom walkthrough (5–10 min video) | _link added after recording_ |
| This README answers every Part A/B/C deliverable inline, and links to the docs above for depth. | — |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # then put your real ANTHROPIC_API_KEY in .env

copilot ask "What was total net revenue in the West region for Q4 2024?"
copilot eval                # run all 10 Part A questions, write a report
python -m partc.score       # train + score the Part C churn model
uvicorn copilot.api:app --reload --app-dir src   # web UI at http://localhost:8000
```

Without a real API key the SQL/compose steps fall back to a **deterministic
offline stub**, so the whole pipeline (and the test suite) runs end-to-end with
no key, no network, and no cost.

## Repository layout

```
src/copilot/      # Part A + B
  db.py           #   DuckDB loader + read-only connections + schema introspection
  schema_card.py  #   3-layer grounding card (structure + values + business rules)
  llm.py          #   LLM seam: Anthropic client (prompt-cached) | offline stub
  sql/            #   generate.py (NL→SQL), guard.py (AST allowlist), execute.py (sandbox)
  kb/             #   loader.py (chunking) + retriever.py (TF-IDF RAG)
  agent/          #   state.py (typed state), nodes.py (logic), graph.py (LangGraph wiring)
  cli.py, api.py  #   typer CLI + FastAPI service
  web/            #   single-page UI served at /
partc/            # Part C: data.py, model.py, score.py
eval/             # pytest: 10-question golden oracle + SQL-guard cases (27 tests)
data/             # the assessment export (CSVs + knowledge_base/)
outputs/          # built DuckDB, eval report, ranked at-risk list
Dockerfile, railway.json   # container + deploy config
```

---

# Part A — Conversational analytics (Text-to-SQL + RAG)

**Pipeline.** `question → classify → {SQL | KB retrieval} → validate → compose`,
returning the **answer + the SQL it ran + the KB source(s)**. DuckDB holds the
four CSVs; Claude generates SQL; a TF-IDF retriever grounds policy questions in
the 7 KB docs.

### How the model is grounded in the schema

A single **schema card** (`schema_card.py`) is injected into the SQL prompt (and
prompt-cached). It combines three layers so the model writes *correct* SQL, not
just *syntactic* SQL:

1. **Structural** — tables, columns and types from live DuckDB introspection,
   plus short human notes (`discount_pct` is a percent 0–20, not a fraction).
2. **Value grounding** — the distinct literals of low-cardinality categorical
   columns (`region ∈ {Midwest…West}`, `status ∈ {Approved,Pending,Rejected}`),
   so filters use real values, not guesses.
3. **Semantic** — business rules distilled from KB-01…07 and **tagged with their
   KB source** (net vs gross, what "approved" means, calendar quarters, tier
   eligibility, "there is no forecast table"). The tagging keeps the card
   auditable.

### How generated SQL is kept safe to execute

Generated SQL is never trusted. Defence in depth, three independent layers:

1. **AST allowlist guard** (`sql/guard.py`) — the SQL is parsed to an AST
   (sqlglot, DuckDB dialect) and must pass an *allowlist*, not a blocklist:
   exactly one statement (blocks `…; DROP TABLE`), read-only `SELECT` only,
   table **and** column allowlist, no DML/DDL/admin verbs, no IO/table functions
   (`read_csv`, `glob`).
2. **Engine-level read-only connection** — even a statement that slipped the
   guard is rejected by the read-only DuckDB connection.
3. **Resource caps** (`sql/execute.py`) — a row cap and an interrupt-based time
   limit stop runaway-but-legal queries.

12 benign/malicious cases are covered by tests. Quick check:

```bash
python -c "from copilot.db import Database; from copilot.sql.execute import run_guarded; \
print(run_guarded(Database().build(), 'SELECT 1; DROP TABLE fact_orders').error)"
# -> Blocked by SQL guard: Only a single statement is allowed.
```

### Results on the 10 evaluation questions

| # | Question | Behaviour | Answer (verified) |
|---|----------|-----------|-------------------|
| 1 | West net revenue Q4 2024 | SQL | **$50,796.27** (Oct–Dec; Nov surcharge kept, per KB-06) |
| 2 | Top 5 SKUs by case volume | SQL | SKU0023 (830), SKU0020 (811), SKU0022 (810), SKU0015 (748), SKU0025 (742) |
| 3 | Top 5 accounts by *approved* reimbursement | SQL | ACC0036 ($17,027.12) … — `status='Approved'`, `approved_amount` |
| 4 | "Underperforming accounts" | **Clarify** | No single definition (KB-01/07): asks for metric + period |
| 5 | Max discount without director sign-off | KB | **15%** (KB-02) |
| 6 | Distributor + Display Incentive? | KB | **No** — retailers only (KB-03) |
| 7 | Gross sales for ACC0001 | SQL | **$23,847.48** = Σ(qty×unit_price); ≠ net $23,202.55 |
| 8 | Seltzer summer vs rest | SQL | Raw 2,009 vs 2,382, but periods unequal → **~335 vs 198 cases/mo (≈69% higher per month)** |
| 9 | Projected net revenue next quarter | **Refuse** | No forecast table (KB-06/07) — won't fabricate |
| 10 | Approval rate per program | SQL | Display 87.5%, Price Support 86.7%, Depletion 82.7%, Volume Rebate 77.9% (excl. Pending) |

Regenerate this report any time with `copilot eval` → `outputs/part_a_results.md`.

### How I'd know an answer is wrong

Three independent mechanisms:

- **Golden-SQL oracle** (`eval/golden.py`) — independently-computed correct
  values + expected behaviour for each of the 10 questions, asserted by pytest.
- **Validate node** — rejects empty results and implausible values (e.g.
  negative revenue) before they reach the user.
- **Every answer carries its SQL/KB source** — a reviewer audits the *reasoning*,
  not just the figure.

→ More detail: [`writeup.md` §1](writeup.md).

---

# Part B — Agentic workflow (LangGraph)

### Graph: nodes, edges, and the state that flows

```
classify ─┬─ sql ──▶ gen_sql ─▶ execute_validate ─┬─ ok ─────▶ compose ─▶ END
          │                          ▲             ├─ retry ──▶ gen_sql (bounded)
          │                          └─────────────┘
          │                                        └─ give up ▶ refuse ─▶ END
          ├─ kb ──────▶ retrieve_kb ───────────────────────▶ compose ─▶ END
          ├─ clarify ──────────────────────────────────────────────▶ clarify ─▶ END
          └─ refuse ───────────────────────────────────────────────▶ refuse ─▶ END
```

- **Nodes:** `classify`, `gen_sql`, `execute_validate`, `retrieve_kb`,
  `compose`, `clarify`, `refuse` (`agent/nodes.py`).
- **State** (`agent/state.py`, a typed `TypedDict`): question; route + reason +
  confidence; SQL, execution result, validation issues, retry count; KB hits;
  final answer, citations, status, and an ordered node `trace` for
  explainability.

→ Full node/edge reference + mermaid diagram: [`ARCHITECTURE.md`](ARCHITECTURE.md).

### Loop and termination control (explicit)

The **only** cycle is `gen_sql ↔ execute_validate`. It is bounded by a retry
counter: `execute_validate` increments `retries` on failure, and the conditional
edge only loops back to `gen_sql` while `retries ≤ max_retries` (default 1 → at
most **2 SQL attempts**). On exhaustion it terminates at `refuse`. Every other
path is acyclic. The retry *budget* is bound at graph-compile time; the retry
*count* lives in the flowing state — so termination is provable, not hoped for.

### Behaviour when not confident

- **Low classifier confidence** (< 0.5) on a data/KB route is downgraded to
  **clarify** — it never answers on a shaky basis.
- **Ambiguous** questions → **clarify** with a *specific* follow-up (which metric
  / period / definition), not a generic "please rephrase".
- **Unanswerable** questions (forward-looking, no source table) → **refuse**,
  and the refusal distinguishes *"the data can't"* from *"the system failed
  after retries"*.
- **Trust invariant:** numbers come **only** from executed SQL; the LLM phrases
  verified figures but never invents them. KB answers are grounded in retrieved
  passages with KB-id citations.

### Citations + worked examples

Every answer carries citations (`SQL over <tables>` for data answers, `KB-xx`
for policy answers).

- **Clarify** — *"Show me our underperforming accounts."* → asks which metric
  (net revenue / case volume / margin), which period, and how to define
  "underperforming"; cites KB-01/07.
- **Refuse** — *"What is our projected net revenue for next quarter?"* →
  declines (no forecast table), offers historical trend instead, cites KB-06/07.

→ More detail: [`writeup.md` §2](writeup.md).

---

# Part C — Account-retention model, impact & production

Run `python -m partc.score` → writes `outputs/at_risk_serve.csv` (240 accounts,
ranked) and `outputs/partc_metrics.json` (model comparison).

### Data issues found and handled

1. **Leakage / train-serve skew (the headline).** `offboarding_ticket_flag` is
   in train but **absent from the serve feed**, and is nearly the label itself
   (corr 0.82). Training on it gives great offline numbers and a model that
   *cannot be scored in production*. **Dropped.**
2. **Encoding mismatch.** `payment_terms` is numeric `{0,1,2}` in train but
   strings `{NET30,NET60,COD}` in serve. Marginal frequencies align, so I map
   `{0:NET30,1:NET60,2:COD}` — a documented, inferred assumption.
3. **Missing values.** `competitor_activity_index` missing for 64/240 serve rows
   → median-imputed inside the pipeline (fit on train folds only — no leakage).
4. **Imbalance.** ~7% positives → accuracy is meaningless; selection and
   reporting use **PR-AUC** and **recall@k**, with class weighting.

### Approach, validation, selection

A leakage-safe `Pipeline` (impute+scale numeric, one-hot categorical) wraps each
estimator, so every CV fold preprocesses only on its own training portion. Four
candidates compared on **5-fold cross-validated PR-AUC**:

| Model | PR-AUC | ROC-AUC |
|-------|:------:|:-------:|
| **LogReg (balanced) — deployed** | **0.157** | 0.617 |
| XGBoost (regularised) | 0.142 | 0.641 |
| Random Forest | 0.132 | 0.614 |
| Dummy (floor) | 0.075 | 0.511 |

**LogReg won, so it is deployed — I let the metric decide** rather than default
to a boosted tree. After removing the leak the signal is weak and largely
linear. Probabilities are **sigmoid-calibrated** so the ranking is usable as
risk. Out-of-fold: PR-AUC 0.121, **recall@top-10% = 19%** (precision 13%, 1.9×
lift over a 7% base). Output: 240 accounts ranked; top 20% = 48 flagged.

### Impact — measuring revenue actually protected

A ranked list is not impact. I'd run a **randomised holdout**: among top-k
at-risk accounts, randomly assign treatment (save-offer / AM outreach) vs
control; after 90 days compare retained net revenue between arms. Protected
revenue = (treatment − control) × treated accounts, with a confidence interval.
**What I would *not* claim credit for:** churners who'd have stayed anyway (the
control corrects for this), accounts never at risk, or any uplift without the
randomised control — "was on the list" correlating with "stayed" is not causal.

### Production — deploy, monitor, retrain

- **Deploy:** batch-score the serve feed on a schedule; persist scores + feature
  snapshot + model version; serve the ranked list to the commercial team.
- **Detect silent degradation:** (a) **input drift** — PSI per feature + the
  train/serve encoding check that already caught `payment_terms`; (b) **score
  drift** — shift in predicted-probability distribution; (c) **performance**,
  label-delay-aware — churn is known only after 90 days, so track PR-AUC /
  recall@k on a rolling matured cohort; never assume "no alert = healthy".
- **Respond:** *automatic* — alerts on PSI/score-drift thresholds; scheduled
  retrain behind a **champion/challenger gate** (promote only if the challenger
  beats champion on held-out PR-AUC). *Manual* — a human reviews any schema
  change (new `payment_terms` encoding!), a sustained performance drop, or a
  feature-pipeline break before the model is trusted again.

→ More detail: [`writeup.md` §3](writeup.md).

---

## Testing

```bash
pytest -q     # 27 tests: 10-question golden oracle + 12 SQL-guard cases + agent trace/bounds
```

Tests force the offline stub (`eval/conftest.py`) so they are deterministic,
free, and network-free regardless of any configured key.

## Deployment

The service is containerised (`Dockerfile`) and deploys to Railway via
`railway.json` (Dockerfile builder, `/health` health-check, restart-on-failure).
The image builds the DuckDB at build time so the first request is fast; the
container binds the platform-injected `$PORT`. `ANTHROPIC_API_KEY` is supplied at
runtime (never baked into the image).

```bash
docker build -t trade-copilot .
docker run -p 8000:8000 --env-file .env trade-copilot   # UI at http://localhost:8000
```
