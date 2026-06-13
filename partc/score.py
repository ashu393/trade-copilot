"""Train the selected model, evaluate honestly, and score the serve feed.

Run: ``python -m partc.score``

Outputs (written to ``outputs/``):
* ``at_risk_serve.csv`` — every serve account ranked by churn probability.
* ``partc_metrics.json`` — model comparison, out-of-fold metrics, audit, importances.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from copilot.config import OUTPUTS_DIR

from .data import audit, load_serve, load_train
from .model import RANDOM_STATE, build_pipeline, candidate_models, compare_models, select_best


def recall_precision_at_k(y_true: np.ndarray, scores: np.ndarray, k_frac: float) -> dict:
    """Recall and precision if we action the top k_frac of the ranked list."""
    n = len(y_true)
    k = max(1, int(round(n * k_frac)))
    order = np.argsort(-scores)
    top = order[:k]
    tp = int(y_true[top].sum())
    total_pos = int(y_true.sum())
    return {
        "k_frac": k_frac,
        "k": k,
        "recall_at_k": round(tp / total_pos, 3) if total_pos else 0.0,
        "precision_at_k": round(tp / k, 3),
        "lift_at_k": round((tp / k) / (total_pos / n), 2) if total_pos else 0.0,
    }


def _feature_importances(pipe, top_n: int = 12) -> list[dict]:
    """Map model importances back to readable (one-hot-expanded) feature names."""
    prep = pipe.named_steps["prep"]
    clf = pipe.named_steps["clf"]
    names = list(prep.get_feature_names_out())
    if hasattr(clf, "feature_importances_"):
        vals = clf.feature_importances_
    elif hasattr(clf, "coef_"):
        vals = np.abs(clf.coef_[0])
    else:
        return []
    pairs = sorted(zip(names, vals), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"feature": n.split("__")[-1], "importance": round(float(v), 4)} for n, v in pairs]


def main() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    train = load_train()
    serve = load_serve()
    X, y = train.X, train.y.to_numpy()

    # 1) Compare candidate models on cross-validated PR-AUC.
    results = compare_models(X, train.y)
    print("\n=== Model comparison (5-fold CV) ===")
    print(results.to_string(index=False))
    best_name = select_best(results)
    # If the floor (dummy) somehow wins, fall back to xgboost — a dummy is not a model.
    if best_name == "dummy":
        best_name = "xgboost"
    print(f"\nSelected model: {best_name}")

    pos_weight = float((y == 0).sum() / max((y == 1).sum(), 1))
    best_estimator = candidate_models(pos_weight)[best_name]

    # 2) Honest out-of-fold probabilities for evaluation (no leakage from refit).
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof = cross_val_predict(
        build_pipeline(candidate_models(pos_weight)[best_name]),
        X, y, cv=cv, method="predict_proba", n_jobs=-1,
    )[:, 1]
    oof_metrics = {
        "pr_auc": round(average_precision_score(y, oof), 4),
        "roc_auc": round(roc_auc_score(y, oof), 4),
        "base_rate": round(float(y.mean()), 4),
        "recall_precision_at_k": [
            recall_precision_at_k(y, oof, f) for f in (0.10, 0.20, 0.30)
        ],
    }
    print("\n=== Out-of-fold metrics (selected model) ===")
    print(json.dumps(oof_metrics, indent=2))

    # 3) Fit a calibrated model on all training data for serve scoring.
    #    Platt/sigmoid is safer than isotonic with few positives.
    calibrated = CalibratedClassifierCV(build_pipeline(best_estimator), method="sigmoid", cv=5)
    calibrated.fit(X, train.y)

    # Plain fit (no calibration wrapper) just to read feature importances.
    plain = build_pipeline(candidate_models(pos_weight)[best_name]).fit(X, train.y)
    importances = _feature_importances(plain)

    # 4) Score the serve feed and rank.
    serve_scores = calibrated.predict_proba(serve.X)[:, 1]
    ranked = pd.DataFrame({
        "account_id": serve.ids.to_numpy(),
        "churn_probability": np.round(serve_scores, 4),
    }).sort_values("churn_probability", ascending=False).reset_index(drop=True)
    ranked["rank"] = ranked.index + 1
    ranked["risk_decile"] = pd.qcut(
        ranked["churn_probability"].rank(method="first"), 10,
        labels=[f"D{i}" for i in range(10, 0, -1)],
    )
    out_csv = OUTPUTS_DIR / "at_risk_serve.csv"
    ranked.to_csv(out_csv, index=False)

    print(f"\n=== Top 10 at-risk serve accounts (written to {out_csv.name}) ===")
    print(ranked.head(10).to_string(index=False))

    # 5) Persist everything for the write-up.
    payload = {
        "audit": audit(),
        "model_comparison": results.to_dict(orient="records"),
        "selected_model": best_name,
        "oof_metrics": oof_metrics,
        "top_feature_importances": importances,
        "serve_scored": int(len(ranked)),
        "serve_flagged_top20pct": int((ranked["rank"] <= np.ceil(0.2 * len(ranked))).sum()),
    }
    (OUTPUTS_DIR / "partc_metrics.json").write_text(json.dumps(payload, indent=2))
    print(f"\nMetrics written to {OUTPUTS_DIR / 'partc_metrics.json'}")


if __name__ == "__main__":
    main()
