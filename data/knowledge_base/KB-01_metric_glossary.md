# KB-01 — Metric & Term Glossary

**Net revenue** — revenue after line-level discounts. Stored in `fact_orders.net_revenue`
(= quantity_cases × unit_price × (1 − discount_pct/100)). This is the default meaning of
"revenue" in ABC reporting unless a request explicitly says "gross."

**Gross sales** — quantity_cases × unit_price, before discount. Not stored as a column;
must be computed. Do not conflate with net revenue.

**Active account** — an account with at least one order in the trailing 90 days. Accounts
with no order in 90 days are considered lapsed for reporting.

**Depletion** — case volume sold through from distributor to retailer; in this dataset use
`quantity_cases` as the depletion proxy.

**Approved reimbursement** — only claims with `status = 'Approved'` count toward paid
reimbursement. `Pending` claims have a null `approved_amount` and must be excluded from
paid totals. `Rejected` claims have approved_amount = 0.

**Performance / underperformance** — ABC has no single definition. Performance is always
reported against a stated metric (net revenue, case volume, or margin) and a stated period.
Requests that do not specify both are ambiguous and should be clarified.
