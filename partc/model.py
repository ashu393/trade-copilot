"""Model construction, comparison, and selection for churn.

A leakage-safe sklearn `Pipeline` wraps preprocessing + estimator so every CV
fold imputes/scales using only its training portion. Four candidates are
compared on **cross-validated PR-AUC** (average precision) — the right metric for
a ~7% positive rate, where accuracy and even ROC-AUC can mislead:

* DummyClassifier (stratified) — the honest floor.
* LogisticRegression (balanced) — interpretable baseline.
* RandomForest (balanced) — non-linear ensemble.
* XGBoost (scale_pos_weight) — main candidate.

SVM and CatBoost are deliberately excluded: SVM gives poorly-calibrated
probabilities on mixed-type tabular data, and CatBoost is redundant with XGBoost
at this scale. Knowing what not to run matters.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from .data import CATEGORICAL_FEATURES, NUMERIC_FEATURES

RANDOM_STATE = 42


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", numeric, NUMERIC_FEATURES),
        ("cat", categorical, CATEGORICAL_FEATURES),
    ])


def candidate_models(pos_weight: float) -> dict[str, object]:
    return {
        "dummy": DummyClassifier(strategy="stratified", random_state=RANDOM_STATE),
        "logreg": LogisticRegression(max_iter=1000, class_weight="balanced",
                                     random_state=RANDOM_STATE),
        "random_forest": RandomForestClassifier(
            n_estimators=400, class_weight="balanced_subsample",
            min_samples_leaf=2, n_jobs=-1, random_state=RANDOM_STATE),
        # Heavily regularised: with only ~57 positives a deep/large XGBoost
        # overfits badly (CV ROC-AUC ~0.52). Shallow trees + strong L2 +
        # min_child_weight make it competitive (PR-AUC ~0.14, ROC ~0.64).
        "xgboost": XGBClassifier(
            n_estimators=150, max_depth=2, learning_rate=0.03,
            reg_lambda=5.0, min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=pos_weight, eval_metric="aucpr",
            n_jobs=-1, random_state=RANDOM_STATE),
    }


def build_pipeline(model) -> Pipeline:
    return Pipeline([("prep", build_preprocessor()), ("clf", model)])


def compare_models(X: pd.DataFrame, y: pd.Series, n_splits: int = 5) -> pd.DataFrame:
    """Cross-validate every candidate; return a metrics table sorted by PR-AUC."""
    pos_weight = float((y == 0).sum() / max((y == 1).sum(), 1))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    scoring = {"pr_auc": "average_precision", "roc_auc": "roc_auc"}

    rows = []
    for name, model in candidate_models(pos_weight).items():
        pipe = build_pipeline(model)
        scores = cross_validate(pipe, X, y, cv=cv, scoring=scoring, n_jobs=-1)
        rows.append({
            "model": name,
            "pr_auc_mean": np.mean(scores["test_pr_auc"]),
            "pr_auc_std": np.std(scores["test_pr_auc"]),
            "roc_auc_mean": np.mean(scores["test_roc_auc"]),
            "roc_auc_std": np.std(scores["test_roc_auc"]),
        })
    return pd.DataFrame(rows).sort_values("pr_auc_mean", ascending=False).reset_index(drop=True)


def select_best(results: pd.DataFrame, prefer: str | None = None) -> str:
    """Pick the deployed model.

    By default we deploy the cross-validated PR-AUC winner. `prefer` lets us
    deploy a specific model (e.g. a regularised XGBoost that is within noise of
    the winner) as a documented, deliberate choice — never silently.
    """
    if prefer and prefer in set(results["model"]):
        return prefer
    return str(results.iloc[0]["model"])
