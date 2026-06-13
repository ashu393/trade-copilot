# Loom walkthrough script (5–10 min)

A tight running order for the screen recording. Have a terminal + the repo open.
Set your real key in `.env` first so Claude runs live (otherwise the offline stub
is shown — still fine, just call it out).

## 0. Setup (15s)
> "This is the Trade Intelligence Copilot — Text-to-SQL + RAG with an agent, plus
> a churn model. The theme throughout is *trust*: it shows its work and knows its
> limits."

```bash
pip install -e ".[dev]"
copilot build-db
```

## 1. The data is a trap — that's the point (45s)
Open `writeup.md` §0 and §3 data issues. Say:
> "I treated this as an imperfect production export. The interesting work is
> judgment — net vs gross, what 'approved' means, ambiguous and unanswerable
> questions, and a leaky feature in Part C."

## 2. Part A — a clean SQL answer (60s)
```bash
copilot ask "What were gross sales (before discount) for account ACC0001?"
```
> "Gross isn't a stored column — note it computed qty×unit_price, $23,847.48, not
> the net figure. And it shows the SQL and the source, so it's auditable."

## 3. Safety — show the guard (45s)
Open `src/copilot/sql/guard.py` briefly, then:
```bash
python -c "from copilot.db import Database; from copilot.sql.execute import run_guarded; print(run_guarded(Database().build(), 'SELECT 1; DROP TABLE fact_orders').error)"
```
> "Generated SQL is parsed to an AST: single read-only SELECT, table/column
> allowlist, no DML, no file functions, plus a read-only connection and timeouts."

## 4. Part B — the agent decides *not* to answer (90s)
```bash
copilot ask "Show me our underperforming accounts."        # -> CLARIFY
copilot ask "What is our projected net revenue for next quarter?"  # -> REFUSE
```
> "These are the two behaviours that matter most. 'Underperforming' has no single
> definition, so it asks for metric and period. The forecast question has no
> source table, so it declines instead of fabricating — both cite the KB."

Show `ARCHITECTURE.md` mermaid graph:
> "Here's the graph — classify, route to SQL or KB, validate, compose. The only
> loop is bounded SQL-repair; low confidence routes to clarify."

## 5. Part A eval — all 10 at once (45s)
```bash
copilot eval
```
> "All ten questions with routing, answers, and SQL written to a report. Q8
> normalises per month because the periods are unequal — the raw comparison would
> mislead."

## 6. Part C — model selection & honesty (90s)
```bash
python -m partc.score
```
> "I dropped `offboarding_ticket_flag` — it's basically the label and isn't in the
> serve feed; that's the leak. I reconciled the `payment_terms` encoding mismatch
> by frequency alignment. Four models compared on PR-AUC — and LogReg actually
> beat XGBoost, so I deployed LogReg. I let the metric decide."

Open `outputs/at_risk_serve.csv`:
> "Calibrated, ranked at-risk list for the 240 serve accounts."

## 7. Impact & production (60s)
Open `writeup.md` §3 impact + production:
> "A ranked list isn't impact — I'd measure protected revenue with a randomised
> holdout and explicitly *not* claim credit for accounts that would've stayed.
> In production I watch input drift (PSI), score drift, and label-delayed
> performance, with champion/challenger retraining and a human in the loop for
> schema changes — exactly the one that bit us here."

## 8. Close (15s)
```bash
pytest -q   # 27 passing
```
> "Everything's tested and runs end-to-end. Happy to go deeper on any choice."
```
