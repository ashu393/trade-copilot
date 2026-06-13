# Trade Intelligence Copilot — Design Write-up

**Ashutosh Tripathi · Senior AI/ML Architect assessment**

## 0. Thesis

The dataset is a deliberately imperfect production export, so the hard part of
this assignment is **judgment, not plumbing**: knowing when a number is wrong,
when a question is ambiguous, and when the data simply cannot answer. Every
design choice below optimises for *trustworthiness* — the system shows the SQL
it ran and the policy it cited, refuses to fabricate, and asks before it guesses.

---

## 1. Part A — Conversational analytics (Text-to-SQL + RAG)

**Pipeline.** `question → classify → {SQL | KB retrieval} → validate → compose`
(answer + SQL + sources). DuckDB holds the four CSVs; Claude generates SQL; a
TF-IDF retriever grounds policy questions in the 7 KB docs.

**Grounding the model in the schema.** A single *schema card*
(`schema_card.py`) injected into the SQL prompt (with prompt caching) combines
three layers: (1) **structural** — tables/columns/types from DuckDB
introspection; (2) **value** — the distinct literals of categorical columns
(`region ∈ {Midwest…West}`, `status ∈ {Approved,Pending,Rejected}`) so the model
writes correct filters; (3) **semantic** — business rules distilled from
KB-01..07 and tagged with their source (net vs gross, what "approved" means,
calendar quarters, tier eligibility, "there is no forecast table").

**Keeping generated SQL safe to execute.** Generated SQL is never trusted. The
guard (`sql/guard.py`) parses it to an AST and enforces: exactly one statement
(blocks `…; DROP TABLE`), read-only `SELECT` only, table **and** column
allowlist, no DML/DDL/admin verbs, and no IO/table functions (`read_csv`, `glob`).
Execution adds a read-only DuckDB connection, a row cap, and an interrupt-based
time limit — defence in depth. (12 benign/malicious cases covered by tests.)

**How I know an answer is wrong.** Three mechanisms: a *golden-SQL oracle*
(`eval/golden.py`) holds independently-computed correct values and the expected
behaviour for each of the 10 questions; the *validate* node rejects empty results
and implausible values (e.g. negative revenue); and every answer carries its
**SQL/KB source** so a reviewer audits the reasoning, not just the figure.

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

The questions are a graded trap suite; the system passes each: net-vs-gross (7),
approved-only with the right column (3), excluding Pending (10), calendar
quarters and keeping the expected surcharge (1), ambiguity (4), and
unanswerability (9). **Q8** is subtle — raw summer volume is *lower*, but the
18-month span has 6 summer vs 12 other months, so the honest answer normalises
per month and states the asymmetry instead of accepting the question's premise.

---

## 2. Part B — Agentic workflow (LangGraph)

A typed-state graph (diagram + node table in `ARCHITECTURE.md`):
`classify → (sql → gen_sql → execute_validate → compose) | (kb → retrieve_kb →
compose) | clarify | refuse`.

- **State**: question; route + confidence; SQL, result, validation issues; KB
  hits; final answer, citations, status, and an ordered node `trace`.
- **Loops & termination (explicit).** The only cycle is
  `gen_sql ↔ execute_validate`, bounded by a retry counter (≤1 retry → ≤2 SQL
  attempts); on exhaustion it terminates at `refuse`. All other paths are acyclic.
- **Behaviour when not confident.** Classifier confidence < 0.5 on a data/KB
  route is downgraded to **clarify**; forward-looking/out-of-data questions
  **refuse**. The agent never answers on a shaky basis.
- **Trust invariant.** Numbers come *only* from executed SQL; the LLM phrases
  verified figures but never invents them. KB answers are grounded in retrieved
  passages with KB-id citations.

**Worked examples.** *Clarify* — Q4 "underperforming accounts": asks which metric
(net revenue / case volume / margin) and period, citing KB-01/07. *Refuse* — Q9
"projected next quarter": declines (no forecast table), offers historical trend
instead, cites KB-06/07.

---

## 3. Part C — Account-retention model

### Data issues found and handled

1. **Leakage / train-serve skew (the headline).** `offboarding_ticket_flag` is
   in train but **absent from the serve feed**, and it is nearly the label
   itself (corr 0.82; 76.5% churn when set vs 0.7% when not). Training on it
   gives great offline numbers and a model that *cannot be scored in production*.
   **Dropped.** Much of the apparent "signal" lived in this leak.
2. **Encoding mismatch.** `payment_terms` is numeric `{0,1,2}` in train but
   strings `{NET30,NET60,COD}` in serve. Marginal frequencies align almost
   exactly (0↔NET30 50.5/52.5%, 1↔NET60 34.5/35.4%, 2↔COD 15.0/12.1%), so I map
   `{0:NET30,1:NET60,2:COD}` — an **inferred, documented assumption**, not a fact.
3. **Missing values.** `competitor_activity_index` missing for 64/240 serve rows
   → median-imputed inside the pipeline (fit on train folds only — no leakage).
4. **Imbalance.** 57/820 positives (~7%) → accuracy is meaningless; I select and
   report on **PR-AUC** and **recall@k**, with class weighting / `scale_pos_weight`.

### Modelling approach, validation, selection

A leakage-safe `Pipeline` (impute+scale numeric, one-hot categorical) wraps each
estimator so every CV fold preprocesses on its own training portion. Four
candidates compared on **5-fold cross-validated PR-AUC**:

| Model | PR-AUC | ROC-AUC |
|-------|:------:|:-------:|
| **LogReg (balanced) — deployed** | **0.157** | 0.617 |
| XGBoost (regularised) | 0.142 | 0.641 |
| Random Forest | 0.132 | 0.614 |
| Dummy (floor) | 0.075 | 0.511 |

I deliberately excluded SVM (poor probability calibration on mixed tabular) and
CatBoost (redundant with XGBoost here). **LogReg won**, so it is deployed — I let
the metric decide rather than default to a boosted tree. With only 57 positives
the signal is weak and largely linear; a deep XGBoost overfit (ROC ~0.52) until
heavily regularised. Probabilities are **sigmoid-calibrated** so the ranking is
usable as risk. Out-of-fold: PR-AUC 0.121, and **recall@top-10% = 19%
(precision 13%, 1.9× lift)** over a 7% base — modest but real after removing the
leak. Top drivers: low `avg_monthly_cases`, high `recency_days`, short tenure,
plus region/terms effects. Output: `outputs/at_risk_serve.csv` (240 accounts
ranked; top 20% = 48 flagged).

### Impact — measuring revenue actually protected

A ranked list is not impact. To measure protected revenue I'd run a
**randomised holdout**: take the top-k at-risk accounts, randomly assign
treatment (save-offer / AM outreach) vs control, and after 90 days compare
retained net revenue between arms. Protected revenue = (retention/revenue in
treatment − control) × treated accounts, with a confidence interval.
**What I would *not* claim credit for:** churners who would have stayed anyway
(the control corrects for this), revenue from accounts that were never going to
leave, or any uplift without the randomised control — correlation between "was
on the list" and "stayed" is not causal. I'd also pre-register the primary metric
and guard against the model's own selection bias.

### Production — deploy, monitor, retrain

- **Deploy:** batch-score the serve feed on a schedule; persist scores +
  feature snapshot + model version; serve the ranked list to the commercial team.
- **Detect silent degradation:** monitor (a) **input drift** — PSI per feature
  and the train/serve encoding check that already caught `payment_terms`;
  (b) **score drift** — shift in the predicted-probability distribution;
  (c) **performance**, label-delay-aware — churn is known only after 90 days, so
  track PR-AUC/recall@k on a rolling matured cohort, never assume "no alert = healthy".
- **Respond:** *automatic* — alert + dashboard on PSI/score-drift thresholds,
  auto-retrain on a cadence with a champion/challenger gate (promote only if the
  challenger beats champion on held-out PR-AUC). *Manual* — a human reviews any
  schema change (new `payment_terms` encoding!), a sustained performance drop, or
  a feature pipeline break before the model is trusted again.

---

## 4. What I'd add with more time

Dense-embedding KB retrieval (the seam exists) once the KB grows; an LLM-as-judge
eval layer over the golden oracle; SHAP explanations per at-risk account for the
AM; and a small feature store so train/serve features are computed by identical code.
