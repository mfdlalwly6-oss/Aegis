from fastapi import APIRouter, Depends, Request

from app.api.deps import get_registry, require_owner

router = APIRouter()


@router.get("/rings")
def rings(
    min_size: int = 5,
    request: Request = None,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    return registry.graph_engine.find_rings(min_size=min_size)


@router.get("/stats")
def graph_stats(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    ge = registry.graph_engine
    return {
        "nodes": ge.node_count,
        "edges": ge.edge_count,
        "known_fraud_accounts": len(ge._known_fraud),
    }


@router.get("/insights")
def graph_insights(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.graph_engine.insights()
