from __future__ import annotations

import io
import os
from typing import Any
from deeptutor.services.custom.volunteer_table_dao import get_plan

TIER_LABELS = {"reach": "冲刺", "steady": "稳妥", "safe": "保底"}


def _slot_prob(s: dict) -> float:
    return s.get("group_prob", s.get("admission_prob", 0))


def _slot_majors_text(s: dict) -> str:
    majors = s.get("majors", [])
    if not majors:
        return ""
    parts = [f"{m.get('major_name','')}({m.get('tag','')})" for m in majors[:5]]
    return ", ".join(parts)


def _register_cjk_fonts() -> bool:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    CANDIDATES = [
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for p in CANDIDATES:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("CJK-Regular", p))
                pdfmetrics.registerFont(TTFont("CJK-Bold", p))
                return True
            except Exception:
                continue

    for base, dirs, files in os.walk("/usr/share/fonts"):
        for f in files:
            if f.endswith(".ttf") and "cjk" in f.lower():
                p = os.path.join(base, f)
                try:
                    pdfmetrics.registerFont(TTFont("CJK-Regular", p))
                    pdfmetrics.registerFont(TTFont("CJK-Bold", p))
                    return True
                except Exception:
                    continue
    return False


def export_plan_pdf(plan_id: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    CJK_OK = _register_cjk_fonts()
    CJK_REGULAR = "CJK-Regular" if CJK_OK else "Helvetica"
    CJK_BOLD = "CJK-Bold" if CJK_OK else "Helvetica-Bold"

    plan = get_plan(plan_id)
    if not plan:
        raise ValueError("Plan not found")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    styles["Title"].fontName = CJK_BOLD
    styles["Normal"].fontName = CJK_REGULAR
    elements: list[Any] = []

    # Title
    elements.append(Paragraph(f"志愿填报方案", styles["Title"]))
    elements.append(Spacer(1, 6 * mm))

    # Info section
    info_style = styles["Normal"]
    info_lines = [
        f"考生: {plan.get('user_id', 'default')}",
        f"省份: {plan.get('province', '—')}",
        f"科类: {plan.get('exam_category', '—')}",
        f"位次: {plan.get('rank', '—')}",
        f"状态: {plan.get('status', 'draft')}",
    ]
    for line in info_lines:
        elements.append(Paragraph(line, info_style))
    elements.append(Spacer(1, 4 * mm))

    # Slots table
    slots: list[dict] = plan.get("slots", [])
    if slots:
        header = ["序号", "院校", "专业组", "类别", "录取概率", "组内专业", "说明"]
        data = [header]
        for s in slots:
            prob = _slot_prob(s)
            data.append([
                str(s.get("order", "")),
                s.get("college_name", s.get("college_id", "")),
                s.get("group_code", ""),
                TIER_LABELS.get(s.get("tier", ""), s.get("tier", "")),
                f"{prob * 100:.1f}%",
                _slot_majors_text(s),
                s.get("reason", ""),
            ])

        col_widths = [30, 120, 50, 50, 55, 120, 60]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), CJK_BOLD),
            ("FONTNAME", (0, 1), (-1, -1), CJK_REGULAR),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("志愿表为空", styles["Normal"]))

    doc.build(elements)
    return buf.getvalue()


def export_plan_excel(plan_id: str) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, Side, Border

    plan = get_plan(plan_id)
    if not plan:
        raise ValueError("Plan not found")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "志愿表"

    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Title row
    ws.cell(row=1, column=1, value="志愿填报方案").font = Font(bold=True, size=14)
    ws.merge_cells("A1:F1")

    # Info rows
    info = [
        ("考生", plan.get("user_id", "default")),
        ("省份", plan.get("province", "—")),
        ("科类", plan.get("exam_category", "—")),
        ("位次", str(plan.get("rank", "—"))),
        ("状态", plan.get("status", "draft")),
    ]
    for i, (k, v) in enumerate(info, 2):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, size=10)
        ws.cell(row=i, column=2, value=v).font = Font(size=10)

    # Header row
    start_row = len(info) + 3
    headers = ["序号", "院校", "专业组", "类别", "录取概率", "组内专业", "说明"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # Data rows
    for i, s in enumerate(plan.get("slots", []), start_row + 1):
        ws.cell(row=i, column=1, value=s.get("order", "")).border = thin_border
        ws.cell(row=i, column=2, value=s.get("college_name", s.get("college_id", ""))).border = thin_border
        ws.cell(row=i, column=3, value=s.get("group_code", "")).border = thin_border
        tier_label = TIER_LABELS.get(s.get("tier", ""), s.get("tier", ""))
        ws.cell(row=i, column=4, value=tier_label).border = thin_border
        ws.cell(row=i, column=5, value=f"{_slot_prob(s) * 100:.1f}%").border = thin_border
        ws.cell(row=i, column=6, value=_slot_majors_text(s)).border = thin_border
        ws.cell(row=i, column=7, value=s.get("reason", "")).border = thin_border

    # Column widths
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 25
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 30
    ws.column_dimensions["G"].width = 30

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
