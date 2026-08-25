from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/system/version")
async def version() -> dict:
    from app.core.config import settings

    return {"version": settings.VERSION, "env": settings.ENV}


@router.get("/system/ready")
async def ready(request: Request) -> dict:
    registry = request.app.state.registry
    checks = await registry.readiness()
    ok = checks["database"] and checks["rules"] > 0
    return {"status": "ready" if ok else "degraded", **checks}
