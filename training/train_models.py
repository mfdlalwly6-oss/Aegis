"""Train GradientBoosting + IsolationForest on the synthetic dataset.
Outputs joblib artifacts + metadata.json into models/trained/.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "models" / "synthetic_fraud_dataset.csv"
OUT = ROOT / "models" / "trained"
OUT.mkdir(parents=True, exist_ok=True)


def load() -> tuple[np.ndarray, np.ndarray, list[str]]:
    with DATA.open() as f:
        rows = list(csv.DictReader(f))
    features = [c for c in rows[0].keys() if c != "label"]
    X = np.array([[float(r[c]) for c in features] for r in rows], dtype=np.float32)
    y = np.array([int(r["label"]) for r in rows], dtype=np.int8)
    return X, y, features


def main() -> None:
    X, y, features = load()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    gb = GradientBoostingClassifier(random_state=42)
    gb.fit(X_train, y_train)
    preds = gb.predict(X_test)
    probs = gb.predict_proba(X_test)[:, 1]

    iso = IsolationForest(random_state=42, contamination=0.18)
    iso.fit(X_train)

    joblib.dump(gb, OUT / "gradient_boosting.joblib")
    joblib.dump(iso, OUT / "isolation_forest.joblib")
    metadata = {
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": features,
        "dataset": "synthetic — NOT real fraud data",
        "metrics": {
            "accuracy": round(float(accuracy_score(y_test, preds)), 4),
            "precision": round(float(precision_score(y_test, preds)), 4),
            "recall": round(float(recall_score(y_test, preds)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, probs)), 4),
        },
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(json.dumps(metadata["metrics"], indent=2))


if __name__ == "__main__":
    main()
