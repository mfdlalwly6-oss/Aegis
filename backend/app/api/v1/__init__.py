from fastapi import APIRouter
from . import (transactions, alerts, cases, rules, models, graph, health, auth,
               tenants, webhook, investigator, reports)

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
router.include_router(cases.router, prefix="/cases", tags=["cases"])
router.include_router(rules.router, prefix="/rules", tags=["rules"])
router.include_router(models.router, prefix="/models", tags=["models"])
router.include_router(graph.router, prefix="/graph", tags=["graph"])
router.include_router(health.router, tags=["system"])
router.include_router(tenants.router, tags=["tenants"])
router.include_router(webhook.router, tags=["webhook"])
router.include_router(investigator.router, prefix="/investigator", tags=["investigator"])
router.include_router(reports.router, prefix="/reports", tags=["reports"])
