"""Reports API — tenant-scoped report generation (JSON + real PDF)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_merchant
from app.reports.pdf import build_report_pdf
from app.reports.service import ReportBuilder

router = APIRouter()


class GenerateBody(BaseModel):
    period: str = Field(pattern="^(daily|weekly|monthly)$")
    timezone: str | None = None


@router.post("/generate")
def generate_report(body: GenerateBody, merchant=Depends(require_merchant), registry=Depends(get_registry)):
    builder = ReportBuilder(registry)
    try:
        report = builder.compute(merchant["tenant_id"], body.period, body.timezone)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return report


@router.get("/pdf")
def report_pdf(
    period: str = Query(pattern="^(daily|weekly|monthly)$"),
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    builder = ReportBuilder(registry)
    try:
        report = builder.compute(merchant["tenant_id"], period)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    try:
        pdf_bytes = build_report_pdf(report)
    except Exception as exc:
        raise HTTPException(500, f"pdf_generation_failed:{exc}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=aegis_report_{period}.pdf",
            "X-Report-Period": period,
            "X-Report-Tenant": merchant["tenant_id"],
        },
    )
