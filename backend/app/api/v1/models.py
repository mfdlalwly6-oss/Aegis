from fastapi import APIRouter, Depends, Request

from app.api.deps import get_registry, require_owner

router = APIRouter()


@router.get("/")
def list_models(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.ml_scorer.list_models() if registry.ml_scorer else []


@router.get("/status")
def models_status(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Full ML readiness card for the Models screen."""
    scorer = registry.ml_scorer
    if not scorer:
        return {"ready": False, "models": [], "metadata": {}, "mode": "unavailable"}
    return {
        "ready": scorer.ready,
        "mode": "trained" if scorer.ready else "heuristic_fallback",
        "models": scorer.list_models(),
        "metadata": scorer._metadata,
        "models_dir": str(scorer._dir),
        "ml_thresholds": {
            "block": __import__(
                "app.core.config", fromlist=["settings"]
            ).settings.ML_THRESHOLD_BLOCK,
            "review": __import__(
                "app.core.config", fromlist=["settings"]
            ).settings.ML_THRESHOLD_REVIEW,
        },
    }


@router.get("/drift")
def models_drift(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Feature drift proxy: distribution of live decision ml_scores vs model expectations.
    Production-grade PSI/KS drift needs a reference window — this returns the live
    score histogram + feature-mean deltas as the monitoring baseline (SR 11-7)."""
    rows = registry.db.query(
        "SELECT ml_score, risk_score FROM decisions ORDER BY ts DESC LIMIT 500"
    )
    if not rows:
        return {"samples": 0, "status": "insufficient_data"}
    scores = [r["ml_score"] for r in rows if r.get("ml_score") is not None]
    n = len(scores)
    mean = sum(scores) / n
    var = sum((x - mean) ** 2 for x in scores) / n
    high = sum(1 for x in scores if x >= 0.65)
    return {
        "samples": n,
        "ml_score_mean": round(mean, 4),
        "ml_score_std": round(var**0.5, 4),
        "high_risk_share": round(high / n, 4),
        "model_version": getattr(registry.ml_scorer, "_metadata", {}).get("version"),
        "model_mode": "trained"
        if getattr(registry.ml_scorer, "ready", False)
        else "heuristic_fallback",
        "note": "baseline drift proxy; wire PSI/KS against a frozen reference window for production",
    }
