# Part A — Evaluation Results

Each question with its routing decision, answer, generated SQL, and sources.

## Q1. What was total net revenue in the West region for Q4 2024?

- **Status / route:** answered / sql
- **Routing reason:** Quantitative question answerable from the tables.
- **Answer:**

```
50,796.27 (net_revenue).
```
- **SQL:**

```sql
SELECT ROUND(SUM(o.net_revenue), 2) AS net_revenue
FROM fact_orders o JOIN dim_account a USING (account_id)
WHERE a.region = 'West'
  AND o.order_date BETWEEN DATE '2024-10-01' AND DATE '2024-12-31'
```
- **Sources:** SQL over dim_account, fact_orders

## Q2. List the top 5 SKUs by total case volume across the full dataset.

- **Status / route:** answered / sql
- **Routing reason:** Quantitative question answerable from the tables.
- **Answer:**

```
sku_id | total_cases
SKU0023 | 830
SKU0020 | 811
SKU0022 | 810
SKU0015 | 748
SKU0025 | 742
```
- **SQL:**

```sql
SELECT sku_id, SUM(quantity_cases) AS total_cases
FROM fact_orders
GROUP BY sku_id
ORDER BY total_cases DESC
LIMIT 5
```
- **Sources:** SQL over fact_orders

## Q3. Which 5 accounts have received the highest total approved reimbursement amount?

- **Status / route:** answered / sql
- **Routing reason:** Quantitative question answerable from the tables.
- **Answer:**

```
account_id | total_approved
ACC0036 | 17,027.12
ACC0041 | 16,638.36
ACC0006 | 16,312.15
ACC0047 | 15,407.78
ACC0052 | 15,333.19
```
- **SQL:**

```sql
SELECT account_id, ROUND(SUM(approved_amount), 2) AS total_approved
FROM fact_reimbursements
WHERE status = 'Approved'
GROUP BY account_id
ORDER BY total_approved DESC
LIMIT 5
```
- **Sources:** SQL over fact_reimbursements

## Q4. Show me our underperforming accounts.

- **Status / route:** clarify / clarify
- **Routing reason:** Underperformance has no single definition; metric and period are unspecified.
- **Answer:**

```
I need a bit more detail to answer this correctly. Performance at ABC has no single definition — it's always reported against a specific metric (net revenue, case volume, or margin) and a specific period. Which metric and over what period should I use, and how do you want "underperforming" defined (e.g. bottom decile, or below a threshold)?
```
- **Sources:** KB-01 — Metric & Term Glossary, KB-07 — Reporting Standards

## Q5. What is the maximum line discount that can be approved without director sign-off?

- **Status / route:** answered / kb
- **Routing reason:** Policy/definition question answered from the knowledge base.
- **Answer:**

```
Discounts apply to the order line and are reflected in `discount_pct`. Maximum discount
permitted without director sign-off is therefore 15%.
```
- **Sources:** KB-02 — Pricing & Discount Approval Policy, KB-03 — Reimbursement Programs

## Q6. Is a distributor allowed to claim a Display Incentive?

- **Status / route:** answered / kb
- **Routing reason:** Policy/definition question answered from the knowledge base.
- **Answer:**

```
1. **Depletion Allowance** — per-case allowance on depleted volume. Open to distributors only.
2. **Display Incentive** — payment for in-store displays. Open to retailers only
   (a distributor is NOT eligible for a Display Incentive).
3. **Price Support** — temporary funding to meet a competitor price. Open to both tiers.
4. **Volume Rebate** — retrospective rebate on cumulative case volume. Open to distributors only.
```
- **Sources:** KB-03 — Reimbursement Programs, KB-04 — Three-Tier Compliance Notes

## Q7. What were gross sales (before discount) for account ACC0001?

- **Status / route:** answered / sql
- **Routing reason:** Quantitative question answerable from the tables.
- **Answer:**

```
23,847.48 (gross_sales).
```
- **SQL:**

```sql
SELECT ROUND(SUM(quantity_cases * unit_price), 2) AS gross_sales
FROM fact_orders
WHERE account_id = 'ACC0001'
```
- **Sources:** SQL over fact_orders

## Q8. How much higher is Seltzer case volume in summer (May–Aug) than the rest of the year?

- **Status / route:** answered / sql
- **Routing reason:** Quantitative question answerable from the tables.
- **Answer:**

```
summer_cases = 2,009; rest_cases = 2,382; summer_months = 6; rest_months = 12. Periods are unequal (6 summer months vs 12 other months), so compare per month: summer 335/mo vs rest 198/mo — summer is 136 cases/month higher (69% higher per month)
```
- **SQL:**

```sql
SELECT
  SUM(CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN o.quantity_cases ELSE 0 END) AS summer_cases,
  SUM(CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN 0 ELSE o.quantity_cases END) AS rest_cases,
  COUNT(DISTINCT CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN date_trunc('month', o.order_date) END) AS summer_months,
  COUNT(DISTINCT CASE WHEN EXTRACT(month FROM o.order_date) BETWEEN 5 AND 8
           THEN NULL ELSE date_trunc('month', o.order_date) END) AS rest_months
FROM fact_orders o JOIN dim_product p USING (sku_id)
WHERE p.category = 'Seltzer'
```
- **Sources:** SQL over dim_product, fact_orders

## Q9. What is our projected net revenue for next quarter?

- **Status / route:** refused / refuse
- **Routing reason:** Forward-looking projection; no forecast table exists.
- **Answer:**

```
I can't answer that from the available data. This dataset has no forecast or budget table, so forward-looking figures (projections, next-quarter estimates) can't be derived from it. I won't fabricate a number. I can instead report historical trends (e.g. net revenue by quarter to date) if that would help.
```
- **Sources:** KB-06 — Operational Exception Log, KB-07 — Reporting Standards

## Q10. What is the reimbursement approval rate for each program?

- **Status / route:** answered / sql
- **Routing reason:** Quantitative question answerable from the tables.
- **Answer:**

```
program | approved | rejected | approval_rate_pct
Depletion Allowance | 62 | 13 | 82.70
Display Incentive | 56 | 8 | 87.50
Price Support | 78 | 12 | 86.70
Volume Rebate | 60 | 17 | 77.90
```
- **SQL:**

```sql
SELECT program,
  SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) AS rejected,
  ROUND(100.0 * SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN status IN ('Approved','Rejected') THEN 1 ELSE 0 END), 0), 1)
        AS approval_rate_pct
FROM fact_reimbursements
GROUP BY program
ORDER BY program
```
- **Sources:** SQL over fact_reimbursements
