"""
Shefa Dairies — PDF Sales Report Generator
==========================================
Generates a professional PDF sales report.

Requirements:
    pip install reportlab

Usage:
    python generate_pdf_report.py
    → outputs: sales_report_YYYY-MM-DD.pdf
"""

from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from analytics import full_report

# ── COLOURS ───────────────────────────────────────────────────
BLUE       = colors.HexColor("#3B5BDB")
DARK       = colors.HexColor("#1a1a2e")
MUTED      = colors.HexColor("#6b7280")
GREEN      = colors.HexColor("#1a7f4b")
AMBER      = colors.HexColor("#d97706")
RED        = colors.HexColor("#dc2626")
LIGHT_BLUE = colors.HexColor("#EEF2FF")
LIGHT_GREY = colors.HexColor("#f0f4ff")
WHITE      = colors.white


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", fontSize=22, textColor=DARK,
            fontName="Helvetica-Bold", spaceAfter=4
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontSize=10, textColor=MUTED,
            fontName="Helvetica", spaceAfter=16
        ),
        "section": ParagraphStyle(
            "section", fontSize=11, textColor=DARK,
            fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=8
        ),
        "body": ParagraphStyle(
            "body", fontSize=9, textColor=DARK,
            fontName="Helvetica", spaceAfter=4
        ),
        "caption": ParagraphStyle(
            "caption", fontSize=8, textColor=MUTED,
            fontName="Helvetica", spaceAfter=2
        ),
        "right": ParagraphStyle(
            "right", fontSize=9, textColor=DARK,
            fontName="Helvetica", alignment=TA_RIGHT
        ),
    }


def stat_table(stats: dict) -> Table:
    """3-column summary statistics table."""
    data = [
        ["Metric", "Value", ""],
        ["Mean Daily Revenue",   f"KES {stats['mean']:,.2f}",   ""],
        ["Min Daily Revenue",    f"KES {stats['min']:,.2f}",    ""],
        ["Max Daily Revenue",    f"KES {stats['max']:,.2f}",    ""],
        ["Total Revenue",        f"KES {stats['total_revenue']:,.2f}", ""],
        ["Total Units Sold",     f"{stats['total_quantity']:,} units",  ""],
    ]
    t = Table(data, colWidths=[7*cm, 5*cm, 4.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e9f5")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0,0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def top_products_table(products: list) -> Table:
    """Ranked product table."""
    header = ["#", "Product", "Units Sold", "Revenue (KES)"]
    rows = [header]
    for p in products:
        rows.append([
            str(p["rank"]),
            p["product_name"],
            f"{p['total_quantity']:,}",
            f"{p['total_revenue']:,.2f}",
        ])
    t = Table(rows, colWidths=[1*cm, 8*cm, 4*cm, 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e9f5")),
        ("ALIGN",       (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0,0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def seven_day_table(daily: list) -> Table:
    """7-day daily breakdown table."""
    header = ["Date", "Revenue (KES)", "Units Sold"]
    rows = [header]
    for d in daily:
        rows.append([d["date"], f"{d['revenue']:,.2f}", f"{d['quantity']:,}"])
    t = Table(rows, colWidths=[5*cm, 6*cm, 5.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e9f5")),
        ("ALIGN",       (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0,0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def generate_pdf(output_path: str = None):
    report = full_report()

    if "error" in report:
        print(f"ERROR: {report['error']}")
        return

    if output_path is None:
        output_path = f"sales_report_{date.today()}.pdf"

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
    )

    styles  = build_styles()
    story   = []
    s       = report["summary"]
    w       = report["last_7_days"]

    # ── Header ──
    story.append(Paragraph("Shefa Dairies", styles["title"]))
    story.append(Paragraph("Sales Analytics Report", styles["subtitle"]))
    story.append(Paragraph(
        f"Period: {s['date_start']} to {s['date_end']}  |  "
        f"Generated: {date.today()}  |  "
        f"Total Days: {s['total_days']}",
        styles["caption"]
    ))
    story.append(HRFlowable(width="100%", thickness=1.5,
                             color=BLUE, spaceAfter=16))

    # ── Overview KPIs ──
    kpi_data = [
        ["Total Revenue", "Total Units", "Analysis Period"],
        [
            f"KES {s['total_revenue']:,.2f}",
            f"{s['total_quantity']:,} units",
            f"{s['total_days']} days",
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  DARK),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, 0),  8),
        ("BACKGROUND",     (0, 1), (-1, 1),  BLUE),
        ("TEXTCOLOR",      (0, 1), (-1, 1),  WHITE),
        ("FONTNAME",       (0, 1), (-1, 1),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 1), (-1, 1),  13),
        ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",     (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 10),
        ("GRID",           (0, 0), (-1, -1), 0.5, WHITE),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 16))

    # ── Summary Statistics ──
    story.append(Paragraph("1. Daily Revenue — Summary Statistics", styles["section"]))
    story.append(stat_table(s))
    story.append(Spacer(1, 8))

    # ── Top Products ──
    story.append(Paragraph("2. Top-Selling Products (by quantity)", styles["section"]))
    story.append(top_products_table(report["top_products"]))
    story.append(Spacer(1, 8))

    # ── 7-Day Analysis ──
    story.append(Paragraph(
        f"3. Last 7 Days  ({w['date_start']} → {w['date_end']})",
        styles["section"]
    ))

    # 7-day KPIs
    kpi7_data = [
        ["7-Day Revenue", "7-Day Units"],
        [f"KES {w['total_revenue']:,.2f}", f"{w['total_qty']:,} units"],
    ]
    kpi7 = Table(kpi7_data, colWidths=[8.25*cm, 8.25*cm])
    kpi7.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("BACKGROUND",    (0, 1), (-1, 1),  GREEN),
        ("TEXTCOLOR",     (0, 1), (-1, 1),  WHITE),
        ("FONTNAME",      (0, 1), (-1, 1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 1), (-1, 1),  12),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, WHITE),
    ]))
    story.append(kpi7)
    story.append(Spacer(1, 10))
    story.append(seven_day_table(w["daily"]))

    # ── Footer ──
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=MUTED, spaceAfter=6))
    story.append(Paragraph(
        f"Shefa Dairies Inventory System  •  Report generated {date.today()}",
        styles["caption"]
    ))

    doc.build(story)
    print(f"PDF saved → {output_path}")
    return output_path


if __name__ == "__main__":
    generate_pdf()