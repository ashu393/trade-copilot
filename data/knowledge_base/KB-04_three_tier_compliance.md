# KB-04 — Three-Tier Compliance Notes

ABC operates under the US three-tier system: Supplier → Distributor → Retailer. A supplier
may not sell directly to a retailer, and a distributor may not sell directly to a consumer.
Reimbursement programs must respect tier eligibility (see KB-03). Account tier is in
`dim_account.account_type` (Retailer or Distributor). `on_premise_flag` indicates a retailer
that sells for on-site consumption (bar/restaurant).
