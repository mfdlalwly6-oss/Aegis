"""Investigator API — protected workbench for fraud analysts.
Auth: POST /investigator/login → JWT (role=investigator). All other routes require it.
Covers: review queue, alerts lifecycle, cases lifecycle, notes, assignment,
graph context, live stream (SSE), and personal stats.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_investigator
from app.core.config import settings
from app.security import issue_jwt

router = APIRouter()

ALERT_STATUSES = {"open", "assigned", "in_review", "escalated",
                  "resolved_true_positive", "resolved_false_positive"}
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


class ResolveCaseBody(BaseModel):
    resolution: str
    note: str = ""


class CaseFromAlertBody(BaseModel):
    title: str | None = None
    priority: str = "high"


# ─────────────────────────── Auth ───────────────────────────

@router.post("/login")
def investigator_login(body: InvestigatorLogin, request: Request,
                       registry=Depends(get_registry)):
    inv = registry.investigators.authenticate(body.email, body.password)
    if not inv:
        registry.audit.log(None, body.email[:12], "authentication.failure",
                           "investigator_login", None,
                           getattr(request.state, "request_id", None), {})
        raise HTTPException(401, "invalid_credentials")
    registry.investigators.touch_login(inv["investigator_id"])
    token = issue_jwt(inv["email"], "investigator",
                      settings.JWT_ACCESS_TTL_SEC * 8,
                      {"investigator_id": inv["investigator_id"],
                       "name": inv["name"]})
    registry.audit.log(None, inv["email"], "authentication.success",
                       "investigator_login", inv["investigator_id"],
                       getattr(request.state, "request_id", None), {})
    return {"access_token": token, "token_type": "Bearer",
            "investigator": {"investigator_id": inv["investigator_id"],
                             "email": inv["email"], "name": inv["name"]}}


@router.get("/me")
def me(inv=Depends(require_investigator)):
    return {"email": inv.get("sub"), "name": inv.get("name"),
            "investigator_id": inv.get("investigator_id"), "role": "investigator"}


# ─────────────────────────── Review Queue ───────────────────────────

@router.get("/queue")
def review_queue(limit: int = Query(100, le=500),
                 inv=Depends(require_investigator), registry=Depends(get_registry)):
    """Decisions that need human review (decision=review) joined with alert state."""
    rows = registry.db.query(
        "SELECT d.decision_id, d.tx_id, d.tenant_id, d.ts, d.decision,"
        " d.risk_score, d.risk_band, d.typology, d.reasoning_ar,"
        " t.amount, t.currency, t.sender_account_id, t.beneficiary_account_id,"
        " a.alert_id, a.status AS alert_status, a.assignee AS alert_assignee"
        " FROM decisions d"
        " JOIN transactions t ON t.tx_id = d.tx_id"
        " LEFT JOIN alerts a ON a.decision_id = d.decision_id"
        " WHERE d.decision = 'review'"
        " ORDER BY d.ts DESC LIMIT ?", (limit,))
    return rows


@router.get("/stats")
def my_stats(inv=Depends(require_investigator), registry=Depends(get_registry)):
    email = inv.get("sub", "")
    return {
        "open_alerts": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM alerts WHERE status IN ('open','assigned','in_review','escalated')")["c"],
        "my_alerts": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM alerts WHERE assignee=? AND status NOT LIKE 'resolved%'",
            (email,))["c"],
        "open_cases": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM cases WHERE status != 'closed'")["c"],
        "my_cases": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM cases WHERE assignee=? AND status != 'closed'",
            (email,))["c"],
        "review_pending": registry.db.query_one(
            "SELECT COUNT(*) AS c FROM decisions WHERE decision='review'")["c"],
    }


# ─────────────────────────── Decisions (read) ───────────────────────────

@router.get("/decisions/recent")
def decisions_recent(limit: int = Query(50, le=200),
                     decision: str | None = None,
                     inv=Depends(require_investigator),
                     registry=Depends(get_registry)):
    if decision:
        return registry.db.query(
            "SELECT * FROM decisions WHERE decision=? ORDER BY ts DESC LIMIT ?",
            (decision, limit))
    return registry.decisions.recent(limit=limit)


@router.get("/decisions/{decision_id}")
def decision_detail(decision_id: str, inv=Depends(require_investigator),
                    registry=Depends(get_registry)):
    row = registry.db.query_one(
        "SELECT * FROM decisions WHERE decision_id=?", (decision_id,))
    if not row:
        raise HTTPException(404, "not_found")
    return row


@router.get("/transactions/{tx_id}")
def transaction_detail(tx_id: str, inv=Depends(require_investigator),
                       registry=Depends(get_registry)):
    tx = registry.transactions.get(tx_id)
    if not tx:
        raise HTTPException(404, "not_found")
    dec = registry.decisions.get_by_tx(tx_id)
    return {"transaction": tx, "decision": dec}


# ─────────────────────────── Alerts lifecycle ───────────────────────────

@router.get("/alerts")
def alerts_list(status: str | None = None, severity: str | None = None,
                assignee: str | None = None, limit: int = Query(100, le=500),
                inv=Depends(require_investigator), registry=Depends(get_registry)):
    sql, params = "SELECT * FROM alerts WHERE 1=1", []
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
    rows = registry.db.query(sql, tuple(params))
    for r in rows:
        import json as _json
        r["notes"] = _json.loads(r.pop("notes_json", "[]") or "[]")
    return rows


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: str, inv=Depends(require_investigator),
                 registry=Depends(get_registry)):
    alert = registry.alerts.get(alert_id)
    if not alert:
        raise HTTPException(404, "not_found")
    tx = registry.transactions.get(alert["tx_id"]) if alert.get("tx_id") else None
    dec = registry.decisions.get_by_tx(alert["tx_id"]) if alert.get("tx_id") else None
    linked_case = registry.db.query_one(
        "SELECT case_id, title, status, priority FROM cases "
        "WHERE alert_ids_json LIKE ? ORDER BY created_at DESC LIMIT 1",
        (f"%{alert_id}%",))
    history = registry.audit_repo.list(resource="alert", resource_id=alert_id, limit=50)
    return {"alert": alert, "transaction": tx, "decision": dec,
            "linked_case": linked_case, "history": history}


@router.post("/alerts/{alert_id}/assign")
def alert_assign(alert_id: str, request: Request,
                 inv=Depends(require_investigator), registry=Depends(get_registry)):
    """Self-assignment: investigator claims the alert."""
    alert = registry.alerts.update_status(alert_id, "assigned",
                                          assignee=inv.get("sub"))
    if not alert:
        raise HTTPException(404, "not_found")
    registry.audit.log(alert["tenant_id"], inv.get("sub", "investigator"),
                       "alert.assigned", "alert", alert_id,
                       getattr(request.state, "request_id", None), {})
    return alert


@router.post("/alerts/{alert_id}/status")
def alert_status(alert_id: str, body: StatusBody, request: Request,
                 inv=Depends(require_investigator), registry=Depends(get_registry)):
    if body.status not in ALERT_STATUSES:
        raise HTTPException(400, f"invalid_status: allowed {sorted(ALERT_STATUSES)}")
    alert = registry.alerts.update_status(alert_id, body.status,
                                          assignee=body.assignee)
    if not alert:
        raise HTTPException(404, "not_found")
    registry.audit.log(alert["tenant_id"], inv.get("sub", "investigator"),
                       "alert.status_changed", "alert", alert_id,
                       getattr(request.state, "request_id", None),
                       {"status": body.status})
    return alert


@router.post("/alerts/{alert_id}/notes")
def alert_add_note(alert_id: str, body: NoteBody, request: Request,
                   inv=Depends(require_investigator), registry=Depends(get_registry)):
    alert = registry.alerts.add_note(alert_id, inv.get("sub", "investigator"),
                                     body.text)
    if not alert:
        raise HTTPException(404, "not_found")
    registry.audit.log(alert["tenant_id"], inv.get("sub", "investigator"),
                       "alert.note_added", "alert", alert_id,
                       getattr(request.state, "request_id", None), {})
    return alert


@router.post("/alerts/{alert_id}/resolve")
def alert_resolve(alert_id: str, body: ResolveAlertBody, request: Request,
                  inv=Depends(require_investigator), registry=Depends(get_registry)):
    if body.resolution not in ALERT_RESOLUTIONS:
        raise HTTPException(400, f"invalid_resolution: allowed {sorted(ALERT_RESOLUTIONS)}")
    alert = registry.alerts.resolve(alert_id, body.resolution, body.note,
                                    author=inv.get("sub", "investigator"))
    if not alert:
        raise HTTPException(404, "not_found")
    registry.audit.log(alert["tenant_id"], inv.get("sub", "investigator"),
                       "alert.resolved", "alert", alert_id,
                       getattr(request.state, "request_id", None),
                       {"resolution": body.resolution})
    return alert


@router.post("/alerts/{alert_id}/escalate-to-case")
def alert_escalate(alert_id: str, body: CaseFromAlertBody, request: Request,
                   inv=Depends(require_investigator), registry=Depends(get_registry)):
    alert = registry.alerts.get(alert_id)
    if not alert:
        raise HTTPException(404, "not_found")
    case = registry.cases.create(
        alert["tenant_id"],
        body.title or f"تحقيق: تنبيه {alert_id[:14]}",
        priority=body.priority, narrative=alert.get("description") or "",
        tx_ids=[alert["tx_id"]] if alert.get("tx_id") else [],
        alert_ids=[alert_id])
    registry.alerts.update_status(alert_id, "escalated",
                                  assignee=inv.get("sub"))
    registry.audit.log(alert["tenant_id"], inv.get("sub", "investigator"),
                       "case.created_from_alert", "case", case["case_id"],
                       getattr(request.state, "request_id", None),
                       {"alert_id": alert_id})
    return case


# ─────────────────────────── Cases lifecycle ───────────────────────────

@router.get("/cases")
def cases_list(status: str | None = None, assignee: str | None = None,
               limit: int = Query(100, le=500),
               inv=Depends(require_investigator), registry=Depends(get_registry)):
    rows = registry.cases.list(status=status, limit=limit)
    if assignee == "me":
        rows = [c for c in rows if c.get("assignee") == inv.get("sub")]
    return rows


@router.get("/cases/{case_id}")
def case_detail(case_id: str, inv=Depends(require_investigator),
                registry=Depends(get_registry)):
    case = registry.cases.get(case_id)
    if not case:
        raise HTTPException(404, "not_found")
    txs = [registry.transactions.get(t) for t in case.get("tx_ids", [])]
    txs = [t for t in txs if t]
    alerts = [registry.alerts.get(a) for a in case.get("alert_ids", [])]
    alerts = [a for a in alerts if a]
    history = registry.audit_repo.list(resource="case", resource_id=case_id, limit=50)
    return {"case": case, "transactions": txs, "alerts": alerts,
            "history": history}


@router.post("/cases/{case_id}/assign")
def case_assign(case_id: str, request: Request,
                inv=Depends(require_investigator), registry=Depends(get_registry)):
    case = registry.cases.update_status(case_id, "in_progress",
                                        assignee=inv.get("sub"))
    if not case:
        raise HTTPException(404, "not_found")
    registry.audit.log(case["tenant_id"], inv.get("sub", "investigator"),
                       "case.assigned", "case", case_id,
                       getattr(request.state, "request_id", None), {})
    return case


@router.post("/cases/{case_id}/status")
def case_status(case_id: str, body: StatusBody, request: Request,
                inv=Depends(require_investigator), registry=Depends(get_registry)):
    if body.status not in CASE_STATUSES:
        raise HTTPException(400, f"invalid_status: allowed {sorted(CASE_STATUSES)}")
    case = registry.cases.update_status(case_id, body.status,
                                        assignee=body.assignee)
    if not case:
        raise HTTPException(404, "not_found")
    registry.audit.log(case["tenant_id"], inv.get("sub", "investigator"),
                       "case.status_changed", "case", case_id,
                       getattr(request.state, "request_id", None),
                       {"status": body.status})
    return case


@router.post("/cases/{case_id}/notes")
def case_add_note(case_id: str, body: NoteBody, request: Request,
                  inv=Depends(require_investigator), registry=Depends(get_registry)):
    case = registry.cases.add_note(case_id, inv.get("sub", "investigator"),
                                   body.text)
    if not case:
        raise HTTPException(404, "not_found")
    registry.audit.log(case["tenant_id"], inv.get("sub", "investigator"),
                       "case.note_added", "case", case_id,
                       getattr(request.state, "request_id", None), {})
    return case


@router.post("/cases/{case_id}/resolve")
def case_resolve(case_id: str, body: ResolveCaseBody, request: Request,
                 inv=Depends(require_investigator), registry=Depends(get_registry)):
    if body.resolution not in CASE_RESOLUTIONS:
        raise HTTPException(400, f"invalid_resolution: allowed {sorted(CASE_RESOLUTIONS)}")
    case = registry.cases.resolve(case_id, body.resolution, body.note,
                                  author=inv.get("sub", "investigator"))
    if not case:
        raise HTTPException(404, "not_found")
    # If confirmed fraud, mark sender accounts in the graph engine
    if body.resolution == "confirmed_fraud":
        for tx_id in case.get("tx_ids", []):
            tx = registry.transactions.get(tx_id)
            if tx:
                registry.graph_engine.mark_fraud(tx["sender_account_id"])
    registry.audit.log(case["tenant_id"], inv.get("sub", "investigator"),
                       "case.resolved", "case", case_id,
                       getattr(request.state, "request_id", None),
                       {"resolution": body.resolution})
    return case


# ─────────────────────────── Graph context ───────────────────────────

@router.get("/graph/account/{account_id}")
def graph_account(account_id: str, inv=Depends(require_investigator),
                  registry=Depends(get_registry)):
    return registry.graph_engine.account_context(account_id)


@router.get("/graph/insights")
def graph_insights(inv=Depends(require_investigator), registry=Depends(get_registry)):
    return registry.graph_engine.insights()
