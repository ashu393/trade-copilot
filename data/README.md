# Trade Intelligence Copilot — Assessment Data

Two independent exports (not joined to each other).

## Part A — mini three-tier DB + knowledge base
- dim_account.csv, dim_product.csv
- fact_orders.csv (~2,600 order lines, 18 months)
- fact_reimbursements.csv (~360 claims)
- knowledge_base/ (KB-01 … KB-07 policy & glossary docs)
- eval_questions_partA.md (10 questions to run the assistant against)

## Part C — account retention export
- accounts_train.csv (~820 accounts, with churned_90d label)
- accounts_serve.csv (~240 accounts, no label — live scoring feed)

Treat as a real, imperfect production export.
