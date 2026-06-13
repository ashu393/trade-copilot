"""Data loading, auditing, and preprocessing for the churn model.

The dataset is a deliberately imperfect export. The three issues we handle:

1. **Leakage / train-serve skew** — `offboarding_ticket_flag` is present in train
   but NOT in the serve feed, and it is almost a copy of the label (corr ~0.82;
   76.5% churn when set vs 0.7% when not). Training on it would inflate offline
   metrics and produce a model that cannot be scored at serve time. We DROP it.

2. **Encoding mismatch** — `payment_terms` is numeric {0,1,2} in train but
   strings {NET30, NET60, COD} in serve. The marginal frequencies align almost
   exactly (0~NET30 50.5/52.5%, 1~NET60 34.5/35.4%, 2~COD 15.0/12.1%), so we map
   the train codes to the serve labels: {0:NET30, 1:NET60, 2:COD}. This is an
   inferred assumption, documented as such.

3. **Missing values** — `competitor_activity_index` is missing for 64/240 serve
   rows; imputed in the pipeline (median).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from copilot.config import DATA_DIR

TARGET = "churned_90d"
ID = "account_id"

# Dropped because it leaks the label and is absent from the serve feed.
LEAKAGE_COLS = ["offboarding_ticket_flag"]

# Inferred from marginal-frequency alignment between train and serve.
PAYMENT_TERMS_MAP = {0: "NET30", 1: "NET60", 2: "COD"}

NUMERIC_FEATURES = [
    "tenure_months", "avg_monthly_cases", "num_active_skus", "avg_discount_pct",
    "reimbursement_participation", "support_tickets_90d", "recency_days",
    "competitor_activity_index",
]
CATEGORICAL_FEATURES = ["account_type", "region", "payment_terms"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass
class Dataset:
    X: pd.DataFrame
    y: pd.Series | None
    ids: pd.Series


def _canonicalize_payment_terms(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    pt = df["payment_terms"]
    if pd.api.types.is_numeric_dtype(pt):
        df["payment_terms"] = pt.map(PAYMENT_TERMS_MAP).astype("object")
    else:
        df["payment_terms"] = pt.astype("object")
    return df


def load_train(path: Path | None = None) -> Dataset:
    df = pd.read_csv(path or DATA_DIR / "accounts_train.csv")
    df = df.drop(columns=[c for c in LEAKAGE_COLS if c in df.columns])
    df = _canonicalize_payment_terms(df)
    return Dataset(X=df[FEATURES].copy(), y=df[TARGET].astype(int), ids=df[ID])


def load_serve(path: Path | None = None) -> Dataset:
    df = pd.read_csv(path or DATA_DIR / "accounts_serve.csv")
    df = df.drop(columns=[c for c in LEAKAGE_COLS if c in df.columns], errors="ignore")
    df = _canonicalize_payment_terms(df)
    return Dataset(X=df[FEATURES].copy(), y=None, ids=df[ID])


def audit(path: Path | None = None) -> dict:
    """Return a structured audit of the train data (used in the write-up/notebook)."""
    df = pd.read_csv(path or DATA_DIR / "accounts_train.csv")
    n = len(df)
    pos = int(df[TARGET].sum())
    leak_corr = float(df["offboarding_ticket_flag"].corr(df[TARGET]))
    return {
        "rows": n,
        "positives": pos,
        "churn_rate": round(pos / n, 4),
        "offboarding_flag_corr_with_label": round(leak_corr, 3),
        "churn_rate_flag_1": round(df[df.offboarding_ticket_flag == 1][TARGET].mean(), 3),
        "churn_rate_flag_0": round(df[df.offboarding_ticket_flag == 0][TARGET].mean(), 3),
        "dropped_for_leakage": LEAKAGE_COLS,
        "payment_terms_mapping_inferred": PAYMENT_TERMS_MAP,
    }
