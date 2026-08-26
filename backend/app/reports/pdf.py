"""AEGIS PDF report — genuine PDF bytes via ReportLab (not HTML-as-PDF).
Arabic text is reshaped (arabic_reshaper + python-bidi) and rendered with
Amiri font (bundled) with DejaVuSans fallback for Latin.
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_CANDIDATES = [
    "Amiri",
    [
        "/app/app/assets/fonts/Amiri-Regular.ttf",
        "/app/backend/app/assets/fonts/Amiri-Regular.ttf",
        "backend/app/assets/fonts/Amiri-Regular.ttf",
        "app/assets/fonts/Amiri-Regular.ttf",
        str(
            Path(__file__).resolve().parents[2]
            / "backend"
            / "app"
            / "assets"
            / "fonts"
            / "Amiri-Regular.ttf"
        ),
    ],
    "Amiri-Bold",
    [
        "/app/app/assets/fonts/Amiri-Bold.ttf",
        "/app/backend/app/assets/fonts/Amiri-Bold.ttf",
        "backend/app/assets/fonts/Amiri-Bold.ttf",
        "app/assets/fonts/Amiri-Bold.ttf",
        str(
            Path(__file__).resolve().parents[2]
            / "backend"
            / "app"
            / "assets"
            / "fonts"
            / "Amiri-Bold.ttf"
        ),
    ],
    "DejaVuSans",
    [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ],
    "DejaVuSans-Bold",
    [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ],
]


def _register_fonts() -> None:
    it = iter(_FONT_CANDIDATES)
    for name in it:
        paths = next(it)
        for path in paths:
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                break
            except Exception:
                continue


def _ar(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def _fmt(n, digits: int = 0) -> str:
    if n is None:
        return "0"
    try:
        return f"{float(n):,.{digits}f}"
    except Exception:
        return str(n)


def build_report_pdf(report: dict) -> bytes:
    _register_fonts()
    base = "Helvetica"
    bold = "Helvetica-Bold"
    registered = pdfmetrics.getRegisteredFontNames()
    if "Amiri" in registered:
        base, bold = "Amiri", "Amiri-Bold"
    elif "DejaVuSans" in registered:
        base, bold = "DejaVuSans", "DejaVuSans-Bold"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"AEGIS {report.get('period_label', '')} Report",
        author="AEGIS Platform",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Title"],
        fontName=bold,
        fontSize=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A"),
        leading=22,
    )
    sub = ParagraphStyle(
        "sub",
        parent=styles["Normal"],
        fontName=base,
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#64748B"),
        leading=13,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName=bold,
        fontSize=11,
        textColor=colors.HexColor("#0E7490"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body = ParagraphStyle("body", parent=styles["Normal"], fontName=base, fontSize=9, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#475569"))

    tz = report.get("tenant_timezone", "Asia/Aden")
    gen_local = report.get("generated_at_local", "-")
    hijri = report.get("hijri_date", "")

    story = []
    story.append(Paragraph(_ar("AEGIS — تقرير مخاطر المعاملات"), h1))
    story.append(
        Paragraph(
            _ar(
                f"المؤسسة: {report.get('tenant_name', '-')} · {report.get('tenant_type', '-')} · "
                f"{report.get('tenant_country', '-')} · خطة {report.get('tenant_plan', '-')}"
            ),
            sub,
        )
    )
    story.append(
        Paragraph(
            _ar(
                f"الفترة: {report.get('period_label', '-')} | من {report.get('start_local', '-')} "
                f"إلى {report.get('end_local', '-')} | المنطقة الزمنية: {tz}"
            ),
            sub,
        )
    )
    story.append(
        Paragraph(
            _ar(
                f"تاريخ الميلادي: {report.get('gregorian_date', '-')} | الهجري: {hijri} | "
                f"التوليد: {gen_local}"
            ),
            sub,
        )
    )
    story.append(Spacer(1, 4 * mm))

    # 1 — Executive summary
    story.append(Paragraph(_ar("1) الملخص التنفيذي"), h2))
    story.append(Paragraph(_ar(report.get("executive_summary", "-")), body))

    # 2 — Volume
    story.append(Paragraph(_ar("2) حجم العمليات والقرارات"), h2))
    v = report.get("volume", {})
    vol_table = Table(
        [
            [_ar("المؤشر"), _ar("القيمة")],
            [_ar("عدد العمليات"), _fmt(v.get("transactions"))],
            [_ar("إجمالي المبالغ"), _fmt(v.get("amount_sum"), 2)],
            [_ar("القرارات"), _fmt(v.get("decisions"))],
            [_ar("سماح ALLOW"), f"{_fmt(v.get('allow'))} ({v.get('allow_pct', '0')}%)"],
            [_ar("حظر BLOCK"), f"{_fmt(v.get('block'))} ({v.get('block_pct', '0')}%)"],
            [_ar("مراجعة REVIEW"), f"{_fmt(v.get('review'))} ({v.get('review_pct', '0')}%)"],
        ],
        colWidths=[90 * mm, 70 * mm],
    )
    vol_table.setStyle(_table_style())
    story.append(vol_table)

    # 3 — Risk
    story.append(Paragraph(_ar("3) توزيع المخاطر"), h2))
    risk = report.get("risk", {})
    bands = risk.get("bands", {})
    band_lines = [[_ar("النطاق"), _ar("العدد")]] + [[_ar(k), _fmt(v)] for k, v in bands.items()]
    band_lines.append([_ar("متوسط درجة الخطر"), _fmt(risk.get("avg_score"), 3)])
    risk_table = Table(band_lines, colWidths=[90 * mm, 70 * mm])
    risk_table.setStyle(_table_style())
    story.append(risk_table)

    # 4 — Top reasons
    reasons = report.get("top_reasons", [])
    if reasons:
        story.append(Paragraph(_ar("4) أهم أسباب المخاطر"), h2))
        reason_lines = [[_ar("السبب"), _ar("مرات الظهور")]] + [
            [_ar(r.get("reason", "-")), _fmt(r.get("count"))] for r in reasons
        ]
        reason_table = Table(reason_lines, colWidths=[120 * mm, 40 * mm])
        reason_table.setStyle(_table_style())
        story.append(reason_table)

    # 5 — Alerts & cases
    story.append(Paragraph(_ar("5) التنبيهات والحالات"), h2))
    alerts = report.get("alerts", {})
    cases = report.get("cases", {})
    ac_lines = [
        [_ar("التنبيهات"), _ar("إجمالي"), _ar("مفتوح")],
        [
            _ar(""),
            _fmt(alerts.get("total")),
            _fmt(
                sum(
                    v
                    for k, v in alerts.get("by_status", {}).items()
                    if k in ("open", "assigned", "in_review", "escalated")
                )
            ),
        ],
        [_ar("الحالات"), _ar("إجمالي"), _ar("مفتوح")],
        [
            _ar(""),
            _fmt(cases.get("total")),
            _fmt(sum(v for k, v in cases.get("by_status", {}).items() if k != "closed")),
        ],
    ]
    ac_table = Table(ac_lines, colWidths=[40 * mm, 40 * mm, 40 * mm])
    ac_table.setStyle(_table_style())
    story.append(ac_table)

    # 6 — Manual reviews
    story.append(Paragraph(_ar("6) المراجعات اليدوية"), h2))
    mr = report.get("manual_reviews", {})
    story.append(
        Paragraph(
            _ar(
                f"عدد العمليات المعالجة يدويًا: {_fmt(mr.get('total'))} — "
                f"متوسط مدة المراجعة: {_fmt(mr.get('avg_duration_min'), 1)} دقيقة — "
                f"تجاوز SLA (+24 ساعة): {_fmt(mr.get('sla_breach_over_24h'))}"
            ),
            body,
        )
    )

    # 7 — Investigator activity
    act = report.get("investigator_activity", [])
    if act:
        story.append(Paragraph(_ar("7) نشاط المحققين"), h2))
        act_lines = [[_ar("المحقق"), _ar("الإجراءات")]] + [
            [_ar(a.get("actor", "-")), _fmt(a.get("actions"))] for a in act
        ]
        act_table = Table(act_lines, colWidths=[120 * mm, 40 * mm])
        act_table.setStyle(_table_style())
        story.append(act_table)

    # 8 — System health
    story.append(Paragraph(_ar("8) صحة النظام والتكامل"), h2))
    sysinfo = report.get("system", {})
    health_lines = [
        [_ar("حالة المؤسسة"), _ar(str(sysinfo.get("integration_status", "-")))],
        [_ar("القواعد المحملة"), _fmt(sysinfo.get("rules_loaded"))],
        [_ar("التعلم الآلي"), _ar("جاهز" if sysinfo.get("ml_ready") else "وضع احتياطي")],
        [_ar("عقد الرسم البياني"), _fmt(sysinfo.get("graph_nodes"))],
        [_ar("الإصدار"), _ar(str(sysinfo.get("aegis_version", "-")))],
    ]
    health_table = Table(health_lines, colWidths=[90 * mm, 70 * mm])
    health_table.setStyle(_table_style())
    story.append(health_table)

    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            _ar(
                "تم إنشاء هذا التقرير آليًا بواسطة منصة AEGIS. جميع الأوقات مخزنة بتوقيت UTC "
                "وتُعرض بالتوقيت المحلي للمؤسسة. التقرير لأغراض إدارة المخاطر الداخلية."
            ),
            small,
        )
    )

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(base, 8)
        canvas.setFillColor(colors.HexColor("#94A3B8"))
        canvas.drawCentredString(
            A4[0] / 2, 8 * mm, _ar(f"AEGIS · صفحة {_doc.page} · وُلد {gen_local}")
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E7490")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
    )
