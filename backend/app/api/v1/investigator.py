"""Investigator API — INSTITUTION-SCOPED workbench for fraud analysts.
Auth: POST /investigator/login → JWT (role=investigator, tenant_id required).
Every query is filtered by the caller's tenant_id — cross-tenant data is invisible.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_investigator
from app.core.config import settings
from app.security import issue_jwt

router = APIRouter()

ALERT_STATUSES = {
    "open",
    "assigned",
    "in_review",
    "escalated",
    "resolved_true_positive",
    "resolved_false_positive",
}
CASE_STATUSES = {"open", "in_progress", "escalated", "closed"}
CASE_RESOLUTIONS = {"confirmed_fraud", "false_positive", "inconclusive"}
ALERT_RESOLUTIONS = {"resolved_true_positive", "resolved_false_positive"}


class InvestigatorLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class StatusBody(BaseModel):
    status: str
    assignee: str | None = None


class NoteBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ResolveAlertBody(BaseModel):
    resolution: str
    note: str = ""


def _mark_known_fraud_senders(registry, tenant_id: str, tx_ids) -> int:
    """Mark senders of the given transactions as known-fraud in the graph.

    Called ONLY from investigation-resolution paths (an alert resolved as
    `resolved_true_positive`, or a case resolved as `confirmed_fraud`).
    Searching an account, opening it, or merely having an alert NEVER calls
    this — the evidence bar is a confirmed investigation outcome.
    Tenant-scoped: transactions are read with tenant_id so no cross-tenant
    account can ever be marked. Returns how many accounts were marked.
    """
    marked = 0
    for tx_id in tx_ids or []:
        tx = registry.transactions.get(tx_id, tenant_id=tenant_id)
        if tx and tx.get("sender_account_id"):
            registry.graph_engine.mark_fraud(tx["sender_account_id"])
            marked += 1
    return marked


class ResolveCaseBody(BaseModel):
    resolution: str
    note: str = ""


class CaseFromAlertBody(BaseModel):
    title: str | None = None
    priority: str = "high"


def _parse_notes(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["notes"] = json.loads(r.pop("notes_json", "[]") or "[]")
    return rows


# ─────────────────────────── Auth ───────────────────────────


@router.post("/login")
def investigator_login(body: InvestigatorLogin, request: Request, registry=Depends(get_registry)):
    inv = registry.investigators.authenticate(body.email, body.password)
    if not inv:
        registry.audit.log(
            None,
            body.email[:12],
            "authentication.failure",
            "investigator_login",
            None,
            getattr(request.state, "request_id", None),
            {},
        )
        raise HTTPException(401, "invalid_credentials")
    if inv.get("tenant_id") == "platform" or not inv.get("tenant_id"):
        # Platform-orphaned accounts cannot operate in the tenant model.
        raise HTTPException(403, "investigator_not_tenant_scoped")
    registry.investigators.touch_login(inv["investigator_id"])
    token = issue_jwt(
        inv["email"],
        "investigator",
        settings.JWT_ACCESS_TTL_SEC * 8,
        {"investigator_id": inv["investigator_id"], "name": inv["name"], "tenant_id": inv["tenant_id"]},
    )
    registry.audit.log(
        inv["tenant_id"],
        inv["email"],
        "authentication.success",
        "investigator_login",
        inv["investigator_id"],
        getattr(request.state, "request_id", None),
        {},
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "investigator": {
            "investigator_id": inv["investigator_id"],
            "email": inv["email"],
            "name": inv["name"],
            "tenant_id": inv["tenant_id"],
        },
    }


@router.get("/me")
def me(inv=Depends(require_investigator)):
    return {
        "email": inv.get("sub"),
        "name": inv.get("name"),
        "investigator_id": inv.get("investigator_id"),
        "role": "investigator",
        "tenant_id": inv.get("tenant_id"),
    }


# ─────────────────────────── Review Queue (tenant-scoped) ───────────────────────────


@router.get("/queue")
def review_queue(
    limit: int = Query(100, le=500), inv=Depends(require_investigator), registry=Depends(get_registry)
):
    tid = inv["tenant_id"]
    rows = registry.db.query(
        "SELECT d.decision_id, d.tx_id, d.tenant_id, d.ts, d.decision,"
        " d.risk_score, d.risk_band, d.typology, d.reasoning_ar,"
        " t.amount, t.currency, t.sender_account_id, t.beneficiary_account_id,"
        " a.alert_id, a.status AS alert_status, a.assignee AS alert_assignee"
        " FROM decisions d"
        " JOIN transactions t ON t.tx_id = d.tx_id"
        " LEFT JOIN alerts a ON a.decision_id = d.decision_id"
        " WHERE d.decision = 'review' AND d.tenant_id=?"
        " ORDER BY d.ts DESC LIMIT ?",
        (tid, limit),
    )
    return rows


@router.get("/stats")
def my_stats(inv=Depends(require_investigator), registry=Depends(get_registry)):
    tid = inv["tenant_id"]
    email = inv.get("sub", "")
    return {
        "tenant_id": tid,
        "open_alerts": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM alerts WHERE tenant_id=? "
            "AND status IN ('open','assigned','in_review','escalated')",
            (tid,),
        )["c"],
        "my_alerts": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM alerts WHERE tenant_id=? AND assignee=? "
            "AND status NOT LIKE 'resolved%%'",
            (tid, email),
        )["c"],
        "open_cases": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM cases WHERE tenant_id=? AND status != 'closed'", (tid,)
        )["c"],
        "my_cases": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM cases WHERE tenant_id=? AND assignee=? AND status != 'closed'",
            (tid, email),
        )["c"],
        "review_pending": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM decisions WHERE tenant_id=? AND decision='review'", (tid,)
        )["c"],
    }


# ─────────────────────────── Decisions / Transactions (tenant-scoped) ───────────────────────────


@router.get("/decisions/recent")
def decisions_recent(
    limit: int = Query(50, le=200),
    decision: str | None = None,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    tid = inv["tenant_id"]
    if decision:
        return registry.db.query(
            "SELECT * FROM decisions WHERE tenant_id=? AND decision=? ORDER BY ts DESC LIMIT ?",
            (tid, decision, limit),
        )
    return registry.db.query(
        "SELECT * FROM decisions WHERE tenant_id=? ORDER BY ts DESC LIMIT ?", (tid, limit)
    )


@router.get("/decisions/{decision_id}")
def decision_detail(decision_id: str, inv=Depends(require_investigator), registry=Depends(get_registry)):
    row = registry.db.query_one(
        "SELECT * FROM decisions WHERE decision_id=? AND tenant_id=?", (decision_id, inv["tenant_id"])
    )
    if not row:
        raise HTTPException(404, "not_found")
    return row


@router.get("/transactions/{tx_id}")
def transaction_detail(tx_id: str, inv=Depends(require_investigator), registry=Depends(get_registry)):
    tx = registry.transactions.get(tx_id, tenant_id=inv["tenant_id"])
    if not tx:
        raise HTTPException(404, "not_found")
    dec = registry.decisions.get_by_tx(tx_id)
    return {"transaction": tx, "decision": dec}


# ─────────────────────────── Alerts lifecycle (tenant-scoped) ───────────────────────────


def _get_alert(registry, alert_id: str, tenant_id: str) -> dict:
    alert = registry.db.query_one(
        "SELECT * FROM alerts WHERE alert_id=? AND tenant_id=?", (alert_id, tenant_id)
    )
    if not alert:
        raise HTTPException(404, "not_found")
    alert["notes"] = json.loads(alert.pop("notes_json", "[]") or "[]")
    return alert


@router.get("/alerts")
def alerts_list(
    status: str | None = None,
    severity: str | None = None,
    assignee: str | None = None,
    limit: int = Query(100, le=500),
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    tid = inv["tenant_id"]
    sql, params = "SELECT * FROM alerts WHERE tenant_id=?", [tid]
    if status:
        sql += " AND status=?"
        params.append(status)
    if severity:
        sql += " AND severity=?"
        params.append(severity)
    if assignee == "me":
        sql += " AND assignee=?"
        params.append(inv.get("sub", ""))
    elif assignee:
        sql += " AND assignee=?"
        params.append(assignee)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return _parse_notes(registry.db.query(sql, tuple(params)))


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: str, inv=Depends(require_investigator), registry=Depends(get_registry)):
    tid = inv["tenant_id"]
    alert = _get_alert(registry, alert_id, tid)
    tx = registry.transactions.get(alert["tx_id"], tenant_id=tid) if alert.get("tx_id") else None
    dec = (
        registry.db.query_one(
            "SELECT * FROM decisions WHERE tx_id=? AND tenant_id=? LIMIT 1", (alert["tx_id"], tid)
        )
        if alert.get("tx_id")
        else None
    )
    linked_case = registry.db.query_one(
        "SELECT case_id, title, status, priority FROM cases "
        "WHERE tenant_id=? AND alert_ids_json LIKE ? ORDER BY created_at DESC LIMIT 1",
        (tid, f"%{alert_id}%"),
    )
    history = registry.audit_repo.list(tenant_id=tid, resource="alert", resource_id=alert_id, limit=50)
    return {
        "alert": alert,
        "transaction": tx,
        "decision": dec,
        "linked_case": linked_case,
        "history": history,
    }


@router.post("/alerts/{alert_id}/assign")
def alert_assign(
    alert_id: str, request: Request, inv=Depends(require_investigator), registry=Depends(get_registry)
):
    tid = inv["tenant_id"]
    _get_alert(registry, alert_id, tid)
    alert = registry.alerts.update_status(alert_id, "assigned", assignee=inv.get("sub"))
    registry.audit.log(
        tid,
        inv.get("sub", "investigator"),
        "alert.assigned",
        "alert",
        alert_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return alert


@router.post("/alerts/{alert_id}/status")
def alert_status(
    alert_id: str,
    body: StatusBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    if body.status not in ALERT_STATUSES:
        raise HTTPException(400, f"invalid_status: allowed {sorted(ALERT_STATUSES)}")
    _get_alert(registry, alert_id, inv["tenant_id"])
    alert = registry.alerts.update_status(alert_id, body.status, assignee=body.assignee)
    registry.audit.log(
        inv["tenant_id"],
        inv.get("sub", "investigator"),
        "alert.status_changed",
        "alert",
        alert_id,
        getattr(request.state, "request_id", None),
        {"status": body.status},
    )
    return alert


@router.post("/alerts/{alert_id}/notes")
def alert_add_note(
    alert_id: str,
    body: NoteBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    _get_alert(registry, alert_id, inv["tenant_id"])
    alert = registry.alerts.add_note(alert_id, inv.get("sub", "investigator"), body.text)
    registry.audit.log(
        inv["tenant_id"],
        inv.get("sub", "investigator"),
        "alert.note_added",
        "alert",
        alert_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return alert


@router.post("/alerts/{alert_id}/resolve")
def alert_resolve(
    alert_id: str,
    body: ResolveAlertBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    if body.resolution not in ALERT_RESOLUTIONS:
        raise HTTPException(400, f"invalid_resolution: allowed {sorted(ALERT_RESOLUTIONS)}")
    tid = inv["tenant_id"]
    _get_alert(registry, alert_id, tid)
    alert = registry.alerts.resolve(
        alert_id, body.resolution, body.note, author=inv.get("sub", "investigator")
    )
    if body.resolution == "resolved_true_positive" and alert and alert.get("tx_id"):
        # Confirmed investigation outcome => known-fraud evidence feeds the graph.
        # resolved_false_positive (or any non-confirmed outcome) never reaches here.
        _mark_known_fraud_senders(registry, tid, [alert["tx_id"]])
    registry.audit.log(
        tid,
        inv.get("sub", "investigator"),
        "alert.resolved",
        "alert",
        alert_id,
        getattr(request.state, "request_id", None),
        {"resolution": body.resolution},
    )
    return alert


@router.post("/alerts/{alert_id}/escalate-to-case")
def alert_escalate(
    alert_id: str,
    body: CaseFromAlertBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    tid = inv["tenant_id"]
    alert = _get_alert(registry, alert_id, tid)
    case = registry.cases.create(
        tid,
        body.title or f"تحقيق: تنبيه {alert_id[:14]}",
        priority=body.priority,
        narrative=alert.get("description") or "",
        tx_ids=[alert["tx_id"]] if alert.get("tx_id") else [],
        alert_ids=[alert_id],
    )
    registry.alerts.update_status(alert_id, "escalated", assignee=inv.get("sub"))
    registry.audit.log(
        tid,
        inv.get("sub", "investigator"),
        "case.created_from_alert",
        "case",
        case["case_id"],
        getattr(request.state, "request_id", None),
        {"alert_id": alert_id},
    )
    return case


# ─────────────────────────── Cases lifecycle (tenant-scoped) ───────────────────────────


def _get_case(registry, case_id: str, tenant_id: str) -> dict:
    case = registry.db.query_one("SELECT * FROM cases WHERE case_id=? AND tenant_id=?", (case_id, tenant_id))
    if not case:
        raise HTTPException(404, "not_found")
    case["tx_ids"] = json.loads(case.pop("tx_ids_json", "[]") or "[]")
    case["alert_ids"] = json.loads(case.pop("alert_ids_json", "[]") or "[]")
    case["notes"] = json.loads(case.pop("notes_json", "[]") or "[]")
    return case


@router.get("/cases")
def cases_list(
    status: str | None = None,
    assignee: str | None = None,
    limit: int = Query(100, le=500),
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    tid = inv["tenant_id"]
    rows = registry.db.query(
        "SELECT * FROM cases WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?", (tid, limit)
    )
    rows = _parse_case_rows(rows)
    if status:
        rows = [c for c in rows if c["status"] == status]
    if assignee == "me":
        rows = [c for c in rows if c.get("assignee") == inv.get("sub")]
    return rows


def _parse_case_rows(rows: list[dict]) -> list[dict]:
    for c in rows:
        c["tx_ids"] = json.loads(c.pop("tx_ids_json", "[]") or "[]")
        c["alert_ids"] = json.loads(c.pop("alert_ids_json", "[]") or "[]")
        c["notes"] = json.loads(c.pop("notes_json", "[]") or "[]")
    return rows


@router.get("/cases/{case_id}")
def case_detail(case_id: str, inv=Depends(require_investigator), registry=Depends(get_registry)):
    tid = inv["tenant_id"]
    case = _get_case(registry, case_id, tid)
    txs = [registry.transactions.get(t, tenant_id=tid) for t in case.get("tx_ids", [])]
    txs = [t for t in txs if t]
    alerts = [_get_alert(registry, a, tid) for a in case.get("alert_ids", [])]
    history = registry.audit_repo.list(tenant_id=tid, resource="case", resource_id=case_id, limit=50)
    return {"case": case, "transactions": txs, "alerts": alerts, "history": history}


@router.post("/cases/{case_id}/assign")
def case_assign(
    case_id: str, request: Request, inv=Depends(require_investigator), registry=Depends(get_registry)
):
    _get_case(registry, case_id, inv["tenant_id"])
    case = registry.cases.update_status(case_id, "in_progress", assignee=inv.get("sub"))
    registry.audit.log(
        inv["tenant_id"],
        inv.get("sub", "investigator"),
        "case.assigned",
        "case",
        case_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return case


@router.post("/cases/{case_id}/status")
def case_status(
    case_id: str,
    body: StatusBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    if body.status not in CASE_STATUSES:
        raise HTTPException(400, f"invalid_status: allowed {sorted(CASE_STATUSES)}")
    _get_case(registry, case_id, inv["tenant_id"])
    case = registry.cases.update_status(case_id, body.status, assignee=body.assignee)
    registry.audit.log(
        inv["tenant_id"],
        inv.get("sub", "investigator"),
        "case.status_changed",
        "case",
        case_id,
        getattr(request.state, "request_id", None),
        {"status": body.status},
    )
    return case


@router.post("/cases/{case_id}/notes")
def case_add_note(
    case_id: str,
    body: NoteBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    _get_case(registry, case_id, inv["tenant_id"])
    case = registry.cases.add_note(case_id, inv.get("sub", "investigator"), body.text)
    registry.audit.log(
        inv["tenant_id"],
        inv.get("sub", "investigator"),
        "case.note_added",
        "case",
        case_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return case


@router.post("/cases/{case_id}/resolve")
def case_resolve(
    case_id: str,
    body: ResolveCaseBody,
    request: Request,
    inv=Depends(require_investigator),
    registry=Depends(get_registry),
):
    if body.resolution not in CASE_RESOLUTIONS:
        raise HTTPException(400, f"invalid_resolution: allowed {sorted(CASE_RESOLUTIONS)}")
    tid = inv["tenant_id"]
    case = _get_case(registry, case_id, tid)
    case = registry.cases.resolve(case_id, body.resolution, body.note, author=inv.get("sub", "investigator"))
    if body.resolution == "confirmed_fraud":
        _mark_known_fraud_senders(registry, tid, case.get("tx_ids", []))
    registry.audit.log(
        tid,
        inv.get("sub", "investigator"),
        "case.resolved",
        "case",
        case_id,
        getattr(request.state, "request_id", None),
        {"resolution": body.resolution},
    )
    return case


# ─────────────────────────── Graph (tenant-scoped) ───────────────────────────


@router.get("/graph/account/{account_id}")
def graph_account(account_id: str, inv=Depends(require_investigator), registry=Depends(get_registry)):
    return registry.graph_engine.account_context(account_id)


@router.get("/graph/insights")
def graph_insights(inv=Depends(require_investigator), registry=Depends(get_registry)):
    return registry.graph_engine.insights()
