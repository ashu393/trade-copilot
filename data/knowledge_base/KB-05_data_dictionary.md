# KB-05 — Data Dictionary (Part A mini-DB)

**dim_account** — account_id, account_name, account_type, region, state, on_premise_flag, established_date
**dim_product** — sku_id, brand, product_name, category, package_size, supplier_id
**fact_orders** — order_id, order_date, account_id, sku_id, quantity_cases, unit_price, discount_pct, net_revenue
**fact_reimbursements** — claim_id, claim_date, account_id, sku_id, program, claim_amount, approved_amount, status

Joins: fact_* tables join to dim_account on account_id and dim_product on sku_id.
`approved_amount` is null for Pending claims.
