"""Train + evaluate fraud models with honest governance.

Guarantees:
- TEMPORAL split (train on earlier days, test on later days) — never random leakage.
- Leakage check: label-correlated near-duplicate columns are flagged.
- Per-currency evaluation (USD/SAR/YER) to expose currency bias.
- Per-typology proxy: reports recall on the structuring-band subset.
- Class-imbalance aware metrics (precision/recall/PR-AUC), NOT accuracy alone.
- Models are versioned with sklearn_version + feature count + dataset hash,
  and labeled "synthetic_not_production" until real labeled data exists.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.metrics import (average_precision_score, precision_score,
                             recall_score, roc_auc_score)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "models" / "synthetic_fraud_dataset.csv"
OUT = ROOT / "models" / "trained"
OUT.mkdir(parents=True, exist_ok=True)

N_FEATURES = 23  # must match FeatureExtractor.vector() length


def load() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    with DATA.open() as f:
        rows = list(csv.DictReader(f))
    features = [c for c in rows[0].keys() if c not in ("label", "currency", "day")]
    assert len(features) == N_FEATURES, f"expected {N_FEATURES} features, got {len(features)}"
    X = np.array([[float(r[c]) for c in features] for r in rows], dtype=np.float32)
    y = np.array([int(r["label"]) for r in rows], dtype=np.int8)
    ccy = np.array([r["currency"] for r in rows])
    day = np.array([int(r["day"]) for r in rows])
    return X, y, ccy, day, features


def temporal_split(day: np.ndarray, holdout_frac: float = 0.25):
    """Train on earlier days, test on the most recent slice — mimics production."""
    cutoff = np.quantile(day, 1.0 - holdout_frac)
    return day <= cutoff, day > cutoff


def leakage_check(X: np.ndarray, y: np.ndarray, features: list[str]) -> list[str]:
    """Flag any feature whose |corr| with the label is suspiciously near 1."""
    flags = []
    for i, name in enumerate(features):
        col = X[:, i]
        if col.std() == 0:
            continue
        c = abs(np.corrcoef(col, y)[0, 1])
        if c > 0.98:
            flags.append(f"{name} (|corr|={c:.3f})")
    return flags


def main() -> None:
    X, y, ccy, day, features = load()
    tr, te = temporal_split(day)
    X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]

    leaks = leakage_check(X_tr, y_tr, features)

    gb = GradientBoostingClassifier(random_state=42)
    gb.fit(X_tr, y_tr)
    probs = gb.predict_proba(X_te)[:, 1]
    preds = (probs >= 0.5).astype(int)

    iso = IsolationForest(random_state=42, contamination=float(max(0.02, y_tr.mean())))
    iso.fit(X_tr)

    # Overall metrics (class-imbalance aware)
    metrics = {
        "precision": round(float(precision_score(y_te, preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, preds, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, probs)), 4),
        "pr_auc": round(float(average_precision_score(y_te, probs)), 4),
    }

    # Per-currency evaluation (currency bias check). Slice the TEST-aligned views:
    # y_te/preds/probs are length = len(test); align currency via ccy[te].
    ccy_te = ccy[te]
    per_ccy = {}
    for c in sorted(set(ccy_te)):
        m = ccy_te == c
        if m.sum() < 10 or y_te[m].sum() == 0:
            continue
        per_ccy[c] = {
            "n": int(m.sum()),
            "precision": round(float(precision_score(y_te[m], preds[m], zero_division=0)), 4),
            "recall": round(float(recall_score(y_te[m], preds[m], zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(y_te[m], probs[m])), 4) if len(set(y_te[m])) > 1 else None,
        }

    # Per-typology proxy: recall within the structuring band (9k–10k ref) on test set.
    X_te = X[te]
    band = (X_te[:, 0] >= 9000) & (X_te[:, 0] < 10000)
    struct_recall = None
    if band.sum() and y_te[band].sum():
        struct_recall = round(float(recall_score(y_te[band], preds[band], zero_division=0)), 4)

    joblib.dump(gb, OUT / "gradient_boosting.joblib")
    joblib.dump(iso, OUT / "isolation_forest.joblib")

    data_hash = hashlib.sha256(DATA.read_bytes()).hexdigest()[:16]
    metadata = {
        "version": datetime.now(timezone.utc).strftime("v%Y%m%d"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "n_features": N_FEATURES,
        "features": features,
        "dataset": "synthetic_not_production",
        "dataset_sha256_16": data_hash,
        "split": "temporal (train=earlier days, test=latest 25%)",
        "class_balance_train": round(float(y_tr.mean()), 4),
        "leakage_flags": leaks,
        "metrics": metrics,
        "per_currency": per_ccy,
        "per_typology": {"structuring_band_recall": struct_recall},
        "status": "EXPERIMENTAL — synthetic data; do NOT treat as production-grade",
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(json.dumps({"metrics": metrics, "per_currency": per_ccy,
                      "leakage_flags": leaks, "status": metadata["status"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
