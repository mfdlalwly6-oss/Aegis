"""AEGIS ML Ensemble — loads real trained models from models/trained/.
If no trained model exists, returns a clearly-labeled heuristic fallback
(NOT a trained ML model — see reason_codes).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import structlog

from app.models.schemas import ModelScore

logger = structlog.get_logger(__name__)


def _find_models_dir() -> Path:
    """Locate models/trained by walking up from this file — works in both the repo
    layout (backend/app/ml/ensemble.py) and the container layout (/app/app/ml/...).
    A fixed parent-depth breaks whenever the image layout changes; search instead."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        cand = parent / "models" / "trained"
        if cand.is_dir() and (cand / "metadata.json").exists():
            return cand
    return here.parent.parent.parent.parent / "models" / "trained"


MODELS_DIR = _find_models_dir()


class EnsembleScorer:
    """Loads real GradientBoosting + IsolationForest if available."""

    def __init__(self, models_dir: str | None = None):
        self._dir = Path(models_dir) if models_dir else MODELS_DIR
        self._gb = None
        self._iso = None
        self._metadata: dict = {}
        self.ready = False
        self._load()

    def _load(self) -> None:
        meta_file = self._dir / "metadata.json"
        if meta_file.exists():
            try:
                self._metadata = json.loads(meta_file.read_text())
            except Exception:
                pass
        try:
            import joblib

            gb_path = self._dir / "gradient_boosting.joblib"
            iso_path = self._dir / "isolation_forest.joblib"
            if gb_path.exists() and iso_path.exists():
                self._gb = joblib.load(gb_path)
                self._iso = joblib.load(iso_path)
                self.ready = True
                logger.info("ml.models_loaded", version=self._metadata.get("version", "unknown"))
        except ImportError:
            logger.warning("ml.joblib_missing")
        except Exception as e:
            logger.warning("ml.load_error", error=str(e))

    def score(self, features: list[float]) -> tuple[float, list[ModelScore]]:
        X = np.array(features, dtype=np.float32).reshape(1, -1)

        if self.ready and self._gb is not None and self._iso is not None:
            return self._real_score(X)
        return self._heuristic_score(X)

    def _real_score(self, X: np.ndarray) -> tuple[float, list[ModelScore]]:
        reports: list[ModelScore] = []
        gb_prob = 0.0
        iso_prob = 0.0

        t0 = time.perf_counter()
        try:
            gb_prob = float(self._gb.predict_proba(X)[0][1])
        except Exception as e:
            logger.warning("ml.gb_error", error=str(e))
        reports.append(
            ModelScore(
                model_name="gradient_boosting",
                model_version=self._metadata.get("version", "2.0.0"),
                probability=round(gb_prob, 4),
                reason_codes=[
                    f"latency_ms={(time.perf_counter() - t0) * 1000:.1f}",
                    "trained_model",
                ],
            )
        )

        t0 = time.perf_counter()
        try:
            iso_raw = float(self._iso.decision_function(X)[0])
            iso_prob = max(0.0, min(1.0, (0.5 - iso_raw) * 1.2 + 0.5))
        except Exception as e:
            logger.warning("ml.iso_error", error=str(e))
        reports.append(
            ModelScore(
                model_name="isolation_forest",
                model_version=self._metadata.get("version", "2.0.0"),
                probability=round(iso_prob, 4),
                reason_codes=[
                    f"latency_ms={(time.perf_counter() - t0) * 1000:.1f}",
                    "trained_model",
                ],
            )
        )

        fused = gb_prob * 0.70 + iso_prob * 0.30
        return round(min(1.0, max(0.0, fused)), 4), reports

    def _heuristic_score(self, X: np.ndarray) -> tuple[float, list[ModelScore]]:
        """Deterministic fallback — clearly labeled as heuristic, NOT trained ML."""
        amount = float(X[0][0])
        tx_per_min = float(X[0][3])
        new_device = float(X[0][6])
        shared_dev = float(X[0][7])
        impossible = float(X[0][9])
        high_risk_country = float(X[0][10])
        new_benef = float(X[0][11])
        pw_recent = 1.0 if float(X[0][12]) < 600 else 0.0

        score = (
            min(0.25, amount / 40000)
            + min(0.15, tx_per_min * 0.03)
            + new_device * 0.10
            + min(0.10, shared_dev * 0.05)
            + impossible * 0.20
            + high_risk_country * 0.15
            + new_benef * 0.05
            + pw_recent * 0.15
        )
        score = min(1.0, max(0.0, score))

        reports = [
            ModelScore(
                model_name="heuristic_fallback",
                model_version="0.0.0",
                probability=round(score, 4),
                reason_codes=[
                    "NOT_TRAINED_ML",
                    "deterministic_heuristic",
                    "train_models_to_enable_real_ml",
                ],
            )
        ]
        return round(score, 4), reports

    def list_models(self) -> list[dict]:
        out = []
        if self.ready:
            out.append(
                {
                    "name": "gradient_boosting",
                    "version": self._metadata.get("version", "?"),
                    "type": "trained",
                }
            )
            out.append(
                {
                    "name": "isolation_forest",
                    "version": self._metadata.get("version", "?"),
                    "type": "trained",
                }
            )
        else:
            out.append(
                {"name": "heuristic_fallback", "version": "0.0.0", "type": "fallback_not_trained"}
            )
        return out
