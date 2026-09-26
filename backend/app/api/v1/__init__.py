from fastapi import APIRouter

from . import (
    alerts,
    auth,
    cases,
    feedback,
    graph,
    health,
    investigator,
    models,
    reports,
    rules,
    tenants,
    transactions,
    watchlist,
    webhook,
)

router = APIRouter()
from app.api.v1 import auth  # noqa: E402
router.include_router(auth.router, prefix="/auth", tags=["auth"])
from app.api.v1 import transactions  # noqa: E402
router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
from app.api.v1 import alerts  # noqa: E402
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
from app.api.v1 import cases  # noqa: E402
router.include_router(cases.router, prefix="/cases", tags=["cases"])
from app.api.v1 import rules  # noqa: E402
router.include_router(rules.router, prefix="/rules", tags=["rules"])
from app.api.v1 import models  # noqa: E402
router.include_router(models.router, prefix="/models", tags=["models"])
from app.api.v1 import graph  # noqa: E402
router.include_router(graph.router, prefix="/graph", tags=["graph"])
from app.api.v1 import health  # noqa: E402
router.include_router(health.router, tags=["system"])
from app.api.v1 import tenants  # noqa: E402
router.include_router(tenants.router, tags=["tenants"])
from app.api.v1 import webhook  # noqa: E402
router.include_router(webhook.router, tags=["webhook"])
from app.api.v1 import watchlist  # noqa: E402
router.include_router(watchlist.router, tags=["watchlist"])
from app.api.v1 import investigator  # noqa: E402
router.include_router(investigator.router, prefix="/investigator", tags=["investigator"])
from app.api.v1 import reports  # noqa: E402
router.include_router(reports.router, prefix="/reports", tags=["reports"])

from app.api.v1 import feedback  # noqa: E402
router.include_router(feedback.router, tags=["feedback"])

from app.api.v1 import weights  # noqa: E402
router.include_router(weights.router, prefix="/weights", tags=["weights"])
