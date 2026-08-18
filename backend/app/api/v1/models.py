from fastapi import APIRouter, Depends, Request

from app.api.deps import get_registry, require_owner

router = APIRouter()


@router.get("/")
def list_models(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.ml_scorer.list_models() if registry.ml_scorer else []
