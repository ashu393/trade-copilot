# Part A — Evaluation Results

Each question with its routing decision, answer, generated SQL, and sources.

## Q1. What was total net revenue in the West region for Q4 2024?

- **Status / route:** answered / sql
- **Routing reason:** This is a quantitative question asking for a specific metric (net revenue) filtered by region (West) and time period (Q4 2024). This can be calculated from the fact_orders table joined with dim_account for region filtering.
- **Answer:**

```
50,796.27 (total_net_revenue).
```
- **SQL:**

```sql
SELECT ROUND(SUM(fo.net_revenue), 2) AS total_net_revenue FROM fact_orders fo JOIN dim_account da ON fo.account_id = da.account_id WHERE da.region = 'West' AND fo.order_date >= '2024-10-01' AND fo.order_date <= '2024-12-31'
```
- **Sources:** SQL over dim_account, fact_orders

## Q2. List the top 5 SKUs by total case volume across the full dataset.

- **Status / route:** answered / sql
- **Routing reason:** This is a quantitative question asking for a ranking of SKUs by total case volume, which can be directly answered by querying the fact_orders and dim_product tables to aggregate case volumes and identify the top 5 SKUs.
- **Answer:**

```
sku_id | product_name | brand | category | total_case_volume
SKU0023 | Citra Fizz 6x355ml | Citra Fizz | Seltzer | 830
SKU0020 | Breezy Seltzer 6x355ml | Breezy Seltzer | Seltzer | 811
SKU0022 | Breezy Seltzer 24x355ml | Breezy Seltzer | Seltzer | 810
SKU0015 | Ironwood Bourbon 12x355ml | Ironwood Bourbon | Spirits | 748
SKU0025 | Citra Fizz 24x355ml | Citra Fizz | Seltzer | 742
```
- **SQL:**

```sql
SELECT p.sku_id, p.product_name, p.brand, p.category, SUM(o.quantity_cases) AS total_case_volume FROM fact_orders o JOIN dim_product p ON o.sku_id = p.sku_id GROUP BY p.sku_id, p.product_name, p.brand, p.category ORDER BY total_case_volume DESC LIMIT 5
```
- **Sources:** SQL over dim_product, fact_orders

## Q3. Which 5 accounts have received the highest total approved reimbursement amount?

- **Status / route:** answered / sql
- **Routing reason:** This is a quantitative ranking question asking for top 5 accounts by total approved reimbursement amount. This can be answered by querying the fact_reimbursements table (filtering for approved status) joined with dim_account, aggregating reimbursement amounts by account and ordering by total descending with a limit of 5.
- **Answer:**

```
account_id | account_name | account_type | total_approved_reimbursement
ACC0036 | Harbor Liquors | Retailer | 17,027.12
ACC0041 | Summit Liquors | Retailer | 16,638.36
ACC0006 | Granite Bottle Shop | Retailer | 16,312.15
ACC0047 | Lakeshore Market | Retailer | 15,407.78
ACC0052 | Oak Distributing | Distributor | 15,333.19
```
- **SQL:**

```sql
SELECT a.account_id, a.account_name, a.account_type, ROUND(SUM(r.approved_amount), 2) AS total_approved_reimbursement FROM fact_reimbursements r JOIN dim_account a ON r.account_id = a.account_id WHERE r.status = 'Approved' GROUP BY a.account_id, a.account_name, a.account_type ORDER BY total_approved_reimbursement DESC LIMIT 5
```
- **Sources:** SQL over dim_account, fact_reimbursements

## Q4. Show me our underperforming accounts.

- **Status / route:** clarify / clarify
- **Routing reason:** The question asks for 'underperforming accounts' but does not specify which performance metric to use (sales volume, revenue, order frequency, reimbursement utilization, year-over-year growth, etc.) or the time period for evaluation. Performance is multidimensional and context-dependent in beverage distribution analytics. Without knowing the specific metric and timeframe, I cannot determine which accounts qualify as underperforming.
- **Answer:**

```
I need a bit more detail to answer this correctly. Performance at ABC has no single definition — it's always reported against a specific metric (net revenue, case volume, or margin) and a specific period. Which metric and over what period should I use, and how do you want "underperforming" defined (e.g. bottom decile, or below a threshold)?
```
- **Sources:** KB-01 — Metric & Term Glossary, KB-07 — Reporting Standards

## Q5. What is the maximum line discount that can be approved without director sign-off?

- **Status / route:** answered / kb
- **Routing reason:** This question asks about discount approval limits and authorization policy, which is covered in the knowledge base rather than being a quantitative query from transaction tables.
- **Answer:**

```
15% is the maximum line discount that can be approved without director sign-off. Discounts of 0-10% require no approval, and 11-15% require regional manager approval. Discounts of 16% or higher require director sign-off. (KB-02)
```
- **Sources:** KB-02 — Pricing & Discount Approval Policy, KB-03 — Reimbursement Programs

## Q6. Is a distributor allowed to claim a Display Incentive?

- **Status / route:** answered / kb
- **Routing reason:** Question about program eligibility - specifically whether distributors qualify for Display Incentive reimbursements. This is a policy question about which account types are eligible for specific reimbursement programs.
- **Answer:**

```
No, a distributor is NOT eligible for a Display Incentive. Display Incentives are open to retailers only. (KB-03)
```
- **Sources:** KB-03 — Reimbursement Programs, KB-04 — Three-Tier Compliance Notes

## Q7. What were gross sales (before discount) for account ACC0001?

- **Status / route:** answered / sql
- **Routing reason:** This is a quantitative question asking for gross sales (a calculable metric from order amounts before discounts) for a specific account ACC0001. This can be answered by querying the fact_orders table filtered by account_id and summing the appropriate amount fields.
- **Answer:**

```
23,847.48 (gross_sales).
```
- **SQL:**

```sql
SELECT SUM(quantity_cases * unit_price) AS gross_sales FROM fact_orders WHERE account_id = 'ACC0001'
```
- **Sources:** SQL over fact_orders

## Q8. How much higher is Seltzer case volume in summer (May–Aug) than the rest of the year?

- **Status / route:** refused / sql
- **Routing reason:** This is a quantitative comparison question that requires calculating seltzer case volume for summer months (May-August) versus non-summer months (remaining 8 months of the year). This can be answered by querying the fact_orders and dim_product tables, filtering by product category (Seltzer) and grouping by time periods to compare volumes.
- **Answer:**

```
I wasn't able to produce a query I'm confident in for this question (issue: Negative value in 'volume_difference_cases' (-373) is implausible.). Rather than return a number I can't stand behind, I'm flagging it for a human. Could you rephrase or add detail?
```
- **SQL:**

```sql
WITH summer_volume AS (
  SELECT SUM(o.quantity_cases) AS summer_cases
  FROM fact_orders o
  JOIN dim_product p ON o.sku_id = p.sku_id
  WHERE p.category = 'Seltzer'
    AND EXTRACT(MONTH FROM o.order_date) BETWEEN 5 AND 8
),
non_summer_volume AS (
  SELECT SUM(o.quantity_cases) AS non_summer_cases
  FROM fact_orders o
  JOIN dim_product p ON o.sku_id = p.sku_id
  WHERE p.category = 'Seltzer'
    AND (EXTRACT(MONTH FROM o.order_date) < 5 OR EXTRACT(MONTH FROM o.order_date) > 8)
)
SELECT 
  ROUND(s.summer_cases - n.non_summer_cases, 2) AS volume_difference_cases,
  ROUND(s.summer_cases, 2) AS summer_total_cases,
  ROUND(n.non_summer_cases, 2) AS non_summer_total_cases,
  ROUND(100.0 * (s.summer_cases - n.non_summer_cases) / NULLIF(n.non_summer_cases, 0), 2) AS percent_higher
FROM summer_volume s
CROSS JOIN non_summer_volume n
```

## Q9. What is our projected net revenue for next quarter?

- **Status / route:** refused / refuse
- **Routing reason:** Question requests forward-looking projection for next quarter. The available tables (dim_account, dim_product, fact_orders, fact_reimbursements) contain historical transactional data only, with no forecast, budget, or projection data to support future quarter estimates.
- **Answer:**

```
I can't answer that from the available data. This dataset has no forecast or budget table, so forward-looking figures (projections, next-quarter estimates) can't be derived from it. I won't fabricate a number. I can instead report historical trends (e.g. net revenue by quarter to date) if that would help.
```
- **Sources:** KB-06 — Operational Exception Log, KB-07 — Reporting Standards

## Q10. What is the reimbursement approval rate for each program?

- **Status / route:** answered / sql
- **Routing reason:** This is a quantitative question asking for a rate calculation (approval rate) broken down by program. The fact_reimbursements table contains reimbursement records with program information and approval status, allowing calculation of approval rates per program.
- **Answer:**

```
program | approved_count | rejected_count | total_evaluated | approval_rate_pct
Depletion Allowance | 62 | 13 | 75 | 82.67
Display Incentive | 56 | 8 | 64 | 87.50
Price Support | 78 | 12 | 90 | 86.67
Volume Rebate | 60 | 17 | 77 | 77.92
```
- **SQL:**

```sql
SELECT
  program,
  COUNT(CASE WHEN status = 'Approved' THEN 1 END) AS approved_count,
  COUNT(CASE WHEN status = 'Rejected' THEN 1 END) AS rejected_count,
  COUNT(CASE WHEN status IN ('Approved', 'Rejected') THEN 1 END) AS total_evaluated,
  ROUND(
    COUNT(CASE WHEN status = 'Approved' THEN 1 END)::DOUBLE / 
    NULLIF(COUNT(CASE WHEN status IN ('Approved', 'Rejected') THEN 1 END), 0) * 100,
    2
  ) AS approval_rate_pct
FROM fact_reimbursements
WHERE status IN ('Approved', 'Rejected')
GROUP BY program
ORDER BY program
```
- **Sources:** SQL over fact_reimbursements
