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
            "block": __import__("app.core.config", fromlist=["settings"]).settings.ML_THRESHOLD_BLOCK,
            "review": __import__("app.core.config", fromlist=["settings"]).settings.ML_THRESHOLD_REVIEW,
        },
    }
