"""
LuxSCaleAI |  generate_report.py   (redesigned – Short Circuit Brand 2025)
=============================================================================
LOGO CHANGE LOG:
  v1 — SVG renderer: used lxml + pure-Python reportlab path parser to rasterise
       the Inkscape SVG logos at runtime.  Worked locally but failed on servers
       without lxml installed, silently falling back to the hand-drawn bracket logo.

  v2 — stdlib SVG renderer: replaced lxml with xml.etree.ElementTree (built-in).
       Fixed Inkscape namespace stripping so stdlib ET could parse the files.
       Still failed on some server environments where renderPM is broken.

  v3 (CURRENT) — PNG direct read: SVG rendering removed entirely.
       _get_logo_png() now reads pre-exported PNG files from assets/brand/.
       Zero external dependencies — just a file open().
       TO ACTIVATE: export the two SVGs to PNG (≥600 px wide, transparent bg)
       and place them in assets/brand/ next to this script:
           logo-bg-dark.png   ← white text, for cover (dark/red background)
           logo-bg-light.png  ← black text, for body page headers (white background)
       Mono variants are declared below for future use — add the PNGs when ready.

Flask integration (unchanged API):
    from generate_report import build_full_report_pdf, build_solution_pdf

─────────────────────────────────────────────────────────────────
 SIGNATORY CONFIGURATION
─────────────────────────────────────────────────────────────────
 Three modes — uncomment exactly ONE block:

 MODE A: Technical Office Manager only (ACTIVE)
 MODE B: Design Team Leader only (commented out)
 MODE C: Both signatories (commented out)

 To switch, comment out the active block and uncomment the desired one.

─────────────────────────────────────────────────────────────────
 EDIT GUIDE — TWO QUICK TWEAKS
─────────────────────────────────────────────────────────────────
 1. COVER TITLE (the large white text on the dark cover page)
    The cover always shows TOOL_NAME (defined near the top of this file).
    If you want a different title, change TOOL_NAME here:
        TOOL_NAME = "LuxScaleAI"
    The project name (from payload["project_name"]) is intentionally NOT
    shown as the cover headline — it appears on page 2 in the project table.

 2. HEADER RED LINE VERTICAL POSITION
    The red separator line in the running page header is drawn in
    _header_footer(). Find the constant:
        HEADER_LINE_Y_OFFSET = 16 * mm
    Increase this value → line moves DOWN (further from top edge).
    Decrease this value → line moves UP (closer to top edge).
    Current value is 16 mm (was 14 mm in v1).
    Example: 18 * mm moves it ~4 mm lower than the original position.
"""

from __future__ import annotations
import io, json, math, re, sys, os, textwrap
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm, cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether,
)
from reportlab.platypus.flowables import Flowable, CondPageBreak

# ─────────────────────────────────────────────────────────────────
#  BRAND CONSTANTS  (shortcircuit.company/SCbrand)
# ─────────────────────────────────────────────────────────────────
SC_RED       = colors.HexColor("#eb1b26")
SC_DARK_RED  = colors.HexColor("#a40e16")
SC_BLACK     = colors.HexColor("#000000")
SC_DARK_BG   = colors.HexColor("#0a0a0a")
SC_DARK2     = colors.HexColor("#141414")
SC_DARK3     = colors.HexColor("#1e1e1e")
SC_CARD_BG   = colors.HexColor("#1a1a1a")
SC_GREY      = colors.HexColor("#cccccc")
SC_MID_GREY  = colors.HexColor("#666666")
SC_WHITE     = colors.HexColor("#ffffff")
SC_LIGHT_BG  = colors.HexColor("#f5f5f5")
SC_BORDER_L  = colors.HexColor("#dddddd")
SC_GREEN     = colors.HexColor("#27AE60")
SC_ORANGE    = colors.HexColor("#E67E22")
SC_TEXT_MUT  = colors.HexColor("#999999")

PAGE_W, PAGE_H = A4
MARGIN     = 18 * mm
CONTENT_W  = PAGE_W - 2 * MARGIN

COMPANY_NAME    = "Short Circuit Company"
COMPANY_ADDRESS = "188 El-Haram St., TaawonTower, Giza"
COMPANY_PHONE   = "01094839174"
COMPANY_EMAIL   = "SCC@shortcircuitcompany.com"
COMPANY_WEB     = "shortcircuit.company"
TOOL_NAME       = "LuxScaleAI"

# ─────────────────────────────────────────────────────────────────
#  HEADER LINE POSITION — EDIT THIS TO MOVE THE RED LINE
# ─────────────────────────────────────────────────────────────────
# Distance from the TOP of the page to the red separator line.
# Larger value  → line is LOWER on the page (more space above it).
# Smaller value → line is HIGHER on the page (less space above it).
# Original value was 14 * mm. Now set to 16 * mm (2 mm lower).
HEADER_LINE_Y_OFFSET = 16 * mm

# ── Logo file paths ────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent

LOGO_DARK_PATH       = _SCRIPT_DIR / "assets" / "brand" / "logo-bg-dark.png"
LOGO_LIGHT_PATH      = _SCRIPT_DIR / "assets" / "brand" / "logo-bg-light.png"
LOGO_DARK_MONO_PATH  = _SCRIPT_DIR / "assets" / "brand" / "logo-bg-dark-mono-light.png"
LOGO_LIGHT_MONO_PATH = _SCRIPT_DIR / "assets" / "brand" / "logo-bg-light-mono-dark.png"

_SVG_ASPECT = 0.4486   # matches brand ratio 1:0.445 from shortcircuit.company/SCbrand

# ─────────────────────────────────────────────────────────────────
#  SIGNATORY CONFIGURATION
#  Uncomment exactly ONE of the three MODE blocks below.
# ─────────────────────────────────────────────────────────────────

# ── MODE A: Technical Office Manager only (ACTIVE) ────────────
_SIGNATORIES = [
    ("Technical Office Manager", "Maha Monir"),
]

# ── MODE B: Design Team Leader only ──────────────────────────
# _SIGNATORIES = [
#     ("Design Team Leader", "Eng. Noura Anwar"),
# ]

# ── MODE C: Both signatories ──────────────────────────────────
# _SIGNATORIES = [
#     ("Design Team Leader",       "Eng. Noura Anwar"),
#     ("Technical Office Manager", "Maha Monir"),
# ]


# ─────────────────────────────────────────────────────────────────
#  LOGO PNG LOADER
# ─────────────────────────────────────────────────────────────────
_logo_png_cache: dict[str, bytes | None] = {}


def _get_logo_png(dark: bool, target_w_pt: float) -> bytes | None:
    key = "dark" if dark else "light"
    if key in _logo_png_cache:
        return _logo_png_cache[key]

    logo_path = LOGO_DARK_PATH if dark else LOGO_LIGHT_PATH
    png = None
    if logo_path.exists():
        try:
            with open(logo_path, "rb") as fh:
                png = fh.read()
        except Exception:
            png = None

    _logo_png_cache[key] = png
    return png


def _draw_sc_logo_fallback(canvas, x, y, w=120, dark=True):
    h   = w * _SVG_ASPECT
    red = "#eb1b26"
    txt = "#ffffff" if dark else "#000000"
    lw  = w * 0.04

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(red))
    canvas.setFillColor(colors.HexColor(red))
    canvas.setLineWidth(lw)

    canvas.line(x + w*0.04, y + h*0.12, x + w*0.04,  y + h*0.88)
    canvas.line(x + w*0.04, y + h*0.88, x + w*0.18,  y + h*0.88)
    canvas.line(x + w*0.04, y + h*0.12, x + w*0.18,  y + h*0.12)
    canvas.line(x + w*0.82, y + h*0.88, x + w*0.96,  y + h*0.88)
    canvas.line(x + w*0.96, y + h*0.88, x + w*0.96,  y + h*0.12)
    canvas.line(x + w*0.82, y + h*0.12, x + w*0.96,  y + h*0.12)
    canvas.rect(x + w*0.35, y + h*0.58, w*0.10, h*0.22, fill=1, stroke=0)
    canvas.rect(x + w*0.55, y + h*0.58, w*0.10, h*0.22, fill=1, stroke=0)

    canvas.setFont("Helvetica-Bold", h * 0.38)
    canvas.setFillColor(colors.HexColor(txt))
    canvas.drawString(x + w*0.22, y + h*0.52, "Short")
    canvas.drawString(x + w*0.22, y + h*0.18, "Circuit")
    canvas.restoreState()


def draw_sc_logo_canvas(canvas, x, y, w=120, dark=True):
    h   = w * _SVG_ASPECT
    png = _get_logo_png(dark=dark, target_w_pt=w)

    if png:
        try:
            canvas.drawImage(
                ImageReader(io.BytesIO(png)),
                x, y, width=w, height=h,
                mask="auto", preserveAspectRatio=True,
            )
            return
        except Exception:
            pass

    _draw_sc_logo_fallback(canvas, x, y, w, dark)


# ─────────────────────────────────────────────────────────────────
#  STYLES
# ─────────────────────────────────────────────────────────────────
def make_styles():
    def S(name, **kw):
        return ParagraphStyle(name=name, **kw)

    return {
        "cover_eyebrow":   S("cover_eyebrow",  fontName="Helvetica", fontSize=8,
                              textColor=SC_RED, letterSpacing=2),
        "cover_title":     S("cover_title",    fontName="Helvetica-Bold", fontSize=30,
                              textColor=SC_WHITE, leading=34, spaceAfter=6),
        "cover_meta_lbl":  S("cover_meta_lbl", fontName="Helvetica-Bold", fontSize=7,
                              textColor=SC_RED, leading=12),
        "cover_meta_val":  S("cover_meta_val", fontName="Helvetica-Bold", fontSize=9.5,
                              textColor=SC_WHITE, leading=13),
        "h1":              S("h1",  fontName="Helvetica-Bold", fontSize=13,
                              textColor=SC_RED, spaceBefore=10, spaceAfter=4),
        "h2":              S("h2",  fontName="Helvetica-Bold", fontSize=10,
                              textColor=SC_DARK_BG, spaceBefore=6, spaceAfter=3),
        "body":            S("body", fontName="Helvetica", fontSize=8.5,
                              textColor=colors.HexColor("#333333"), leading=13, spaceAfter=3),
        "small":           S("small", fontName="Helvetica", fontSize=7.5,
                              textColor=SC_MID_GREY, leading=11),
        "label":           S("label", fontName="Helvetica-Bold", fontSize=7.5,
                              textColor=SC_BLACK, leading=11),
        "white_label":     S("white_label", fontName="Helvetica-Bold", fontSize=7.5,
                              textColor=SC_WHITE, leading=11),
        "footer":          S("footer", fontName="Helvetica", fontSize=7,
                              textColor=SC_MID_GREY, leading=10, alignment=TA_CENTER),
        "section_num":     S("section_num", fontName="Helvetica-Bold", fontSize=9,
                              textColor=SC_RED, spaceBefore=14, spaceAfter=2),
        "tag_pass":        S("tag_pass", fontName="Helvetica-Bold", fontSize=8,
                              textColor=SC_GREEN),
        "tag_fail":        S("tag_fail", fontName="Helvetica-Bold", fontSize=8,
                              textColor=SC_RED),
        "sol_title":       S("sol_title", fontName="Helvetica-Bold", fontSize=14,
                              textColor=SC_RED, spaceBefore=6, spaceAfter=4),
        "metric_val":      S("metric_val", fontName="Helvetica-Bold", fontSize=20,
                              textColor=SC_BLACK, leading=24, alignment=TA_CENTER),
        "metric_lbl":      S("metric_lbl", fontName="Helvetica", fontSize=7.5,
                              textColor=SC_MID_GREY, leading=10, alignment=TA_CENTER),
        "italic":          S("italic", fontName="Helvetica-Oblique", fontSize=7.5,
                              textColor=SC_MID_GREY, leading=11),
        "right":           S("right", fontName="Helvetica", fontSize=8,
                              textColor=SC_MID_GREY, alignment=TA_RIGHT),
    }


# ─────────────────────────────────────────────────────────────────
#  RUNNING HEADER / FOOTER
# ─────────────────────────────────────────────────────────────────
def _header_footer(canvas, doc, title: str, _ref: list):
    """
    Draws the running header and footer on every page except the cover (page 1).

    RED LINE POSITION:
      Controlled by HEADER_LINE_Y_OFFSET (defined near the top of this file).
      The line is drawn at:  PAGE_H - HEADER_LINE_Y_OFFSET
      Logo and text are positioned relative to that same offset.

      To move the line down: increase HEADER_LINE_Y_OFFSET.
      To move the line up:   decrease HEADER_LINE_Y_OFFSET.
    """
    canvas.saveState()
    page_num = canvas.getPageNumber()
    if page_num == 1:
        canvas.restoreState()
        return

    # ── Red separator line ─────────────────────────────────────────────────────
    # Position: PAGE_H - HEADER_LINE_Y_OFFSET
    # Change HEADER_LINE_Y_OFFSET at the top of this file to move it.
    line_y = PAGE_H - HEADER_LINE_Y_OFFSET

    canvas.setFillColor(SC_RED)
    canvas.rect(MARGIN, line_y, CONTENT_W, 1.5, fill=1, stroke=0)

    # ── Logo — sits just above the red line ───────────────────────────────────
    logo_y = line_y + 0.5 * mm          # tiny gap above the line
    draw_sc_logo_canvas(canvas, MARGIN, logo_y, w=72, dark=False)

    # ── Title text — centred, above the red line ──────────────────────────────
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(SC_BLACK)
    canvas.drawCentredString(PAGE_W / 2, line_y + 4 * mm, title)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SC_MID_GREY)
    canvas.drawCentredString(PAGE_W / 2, line_y + 1 * mm,
                             f"{COMPANY_NAME} — {TOOL_NAME}")

    # ── Page number — right-aligned, above red line ───────────────────────────
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SC_MID_GREY)
    canvas.drawRightString(MARGIN + CONTENT_W, line_y + 4 * mm,
                           f"Page {page_num}")

    # ── Footer ─────────────────────────────────────────────────────────────────
    canvas.setFillColor(SC_BORDER_L)
    canvas.rect(MARGIN, 12 * mm, CONTENT_W, 0.75, fill=1, stroke=0)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(SC_MID_GREY)
    canvas.drawString(MARGIN, 9 * mm,
                      f"Short Circuit  ·  {COMPANY_ADDRESS}  ·  {COMPANY_PHONE}")
    canvas.drawRightString(MARGIN + CONTENT_W, 9 * mm,
                           "Confidential — Lighting Design Report")
    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────
#  COVER PAGE
# ─────────────────────────────────────────────────────────────────
def build_cover(canvas, payload: dict, report_title: str,
                is_solution=False, sol_index=0, sol_data=None):
    """
    Renders the full-bleed cover page.

    COVER TITLE (the large white text on the dark left panel):
      Always shows TOOL_NAME — defined at the top of this file as:
          TOOL_NAME = "LuxScaleAI"
      The project name (payload["project_name"]) is intentionally NOT used
      as the cover headline. It appears on page 2 in the project info table.
      To change what is shown, edit TOOL_NAME or replace `title_text` below.
    """
    canvas.saveState()
    W, H = PAGE_W, PAGE_H

    # ── Background ────────────────────────────────────────────────────────────
    canvas.setFillColor(SC_DARK_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Dark-red accent bar at very top (left 64%) ───────────────────────────
    canvas.setFillColor(SC_DARK_RED)
    canvas.rect(0, H - 4 * mm, W * 0.64, 4 * mm, fill=1, stroke=0)

    # ── Red right panel ───────────────────────────────────────────────────────
    canvas.setFillColor(SC_RED)
    canvas.rect(W * 0.64, 0, W * 0.36, H, fill=1, stroke=0)

    # ── Large "SC" watermark ─────────────────────────────────────────────────
    canvas.setFillColor(colors.HexColor("#1a0000"))
    canvas.setFont("Helvetica-Bold", 210)
    canvas.drawString(W * 0.02, H * 0.08, "SC")

    # ── Logo top-left ─────────────────────────────────────────────────────────
    draw_sc_logo_canvas(canvas, MARGIN, H - MARGIN - 15 * mm, w=150, dark=True)

    # ── Right panel content ───────────────────────────────────────────────────
    rp_x = W * 0.665
    canvas.setFillColor(SC_WHITE)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(rp_x, H * 0.85, TOOL_NAME)

    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#ffe0e1"))
    canvas.drawString(rp_x, H * 0.82, "AI-Powered Lighting Design")

    canvas.setStrokeColor(colors.HexColor("#ffffff44"))
    canvas.setLineWidth(0.5)
    canvas.line(rp_x, H * 0.805, W - MARGIN * 0.8, H * 0.805)

    about = [
        "LuxScaleAI is Short Circuit Company's",
        "intelligent lighting calculation platform.",
        "",
        "Powered by AI, it delivers EN 12464-1",
        "compliant fixture selections, IES-based",
        "beam photometry, simulated illuminance",
        "grids, and complete PDF design reports",
        "— generated in minutes.",
        "",
        "LuxScaleAI automates the full lighting",
        "design workflow: from space input and",
        "standard lookup to fixture selection,",
        "layout optimisation, and compliance",
        "verification — no specialist software",
        "required.",
        "",
        "Built for lighting engineers, electrical",
        "contractors, and architects who need",
        "fast, accurate, presentation-ready results.",
    ]
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(colors.HexColor("#ffeaea"))
    ay = H * 0.79
    for ln in about:
        canvas.drawString(rp_x, ay, ln)
        ay -= 10.5

    canvas.setFillColor(colors.HexColor("#ffd0d2"))
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(rp_x, H * 0.19, COMPANY_NAME.upper())
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(SC_WHITE)
    for i, ln in enumerate([COMPANY_ADDRESS, f"T: {COMPANY_PHONE}", COMPANY_WEB]):
        canvas.drawString(rp_x, H * 0.16 - i * 9, ln)

    # ── Left panel — report type badge ───────────────────────────────────────
    canvas.setFillColor(SC_RED)
    canvas.setFont("Helvetica-Bold", 8)
    lbl = "SOLUTION DESIGN REPORT" if is_solution else "LIGHTING DESIGN REPORT"
    canvas.drawString(MARGIN, H * 0.71, lbl)

    # ── Cover main title — ALWAYS TOOL_NAME ──────────────────────────────────
    # FIX: title_text is hardcoded to TOOL_NAME.
    # The project name must NOT appear here; it lives on page 2.
    # If you need to change this text, edit TOOL_NAME at the top of this file.
    title_text = TOOL_NAME   # ← always "LuxScaleAI" (or whatever TOOL_NAME is set to)

    canvas.setFillColor(SC_WHITE)
    canvas.setFont("Helvetica-Bold", 28)
    lines = textwrap.wrap(title_text, 20)
    ty = H * 0.63
    for ln in lines:
        canvas.drawString(MARGIN, ty, ln)
        ty -= 34

    # ── Category / task subtitle ──────────────────────────────────────────────
    cat  = payload.get("standard_category", "")
    task = payload.get("standard_task_or_activity", "")
    canvas.setFillColor(colors.HexColor("#AAAAAA"))
    canvas.setFont("Helvetica", 10)
    canvas.drawString(MARGIN, ty - 4, cat)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(MARGIN, ty - 17, f"Task: {task}" if task else "")

    # ── Solution sub-title (solution PDFs only) ───────────────────────────────
    if is_solution and sol_data:
        lum = sol_data.get("Luminaire", sol_data.get("luminaire", ""))
        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(SC_RED)
        canvas.drawString(MARGIN, ty - 33, f"Solution {sol_index + 1} — {lum}")

    # ── Horizontal rule ───────────────────────────────────────────────────────
    canvas.setStrokeColor(SC_RED)
    canvas.setLineWidth(1.2)
    canvas.line(MARGIN, H * 0.35, W * 0.60, H * 0.35)

    # ── Meta rows ─────────────────────────────────────────────────────────────
    def meta_row(label, value, rx, ry):
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(SC_RED)
        canvas.drawString(rx, ry + 11, label.upper())
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.setFillColor(SC_WHITE)
        canvas.drawString(rx, ry, value or "—")

    left_x  = MARGIN
    right_x = W * 0.32

    meta_row("DESIGNED BY",  "Short Circuit Company",               left_x,  H * 0.28)
    meta_row("DIVISION",     "Technical Office",                    right_x, H * 0.28)
    meta_row("REPORT DATE",  datetime.now().strftime("%B %d, %Y"), left_x,  H * 0.20)
    meta_row("STANDARD",
             f"EN 12464-1 · Ref {payload.get('standard_ref_no', '')}",
             right_x, H * 0.20)
    meta_row("EMAIL",  COMPANY_EMAIL,  left_x,  H * 0.12)
    meta_row("PHONE",  COMPANY_PHONE,  left_x,  H * 0.05)

    # ── Bottom bar ────────────────────────────────────────────────────────────
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(MARGIN, 18,
                      f"Short Circuit  ·  {COMPANY_ADDRESS}  ·  {COMPANY_PHONE}")
    canvas.setFillColor(SC_RED)
    canvas.drawString(MARGIN, 9, COMPANY_WEB)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawRightString(W * 0.62, 9, "Confidential — Lighting Design Report")
    canvas.setFillColor(colors.HexColor("#7a0009"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(W * 0.665, 9, f"Designed by {TOOL_NAME}")

    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────
#  TECHNICAL ROOM DRAWING  (matplotlib → PNG bytes)
# ─────────────────────────────────────────────────────────────────
def make_room_drawing(payload: dict,
                      width_pt: float = 460, height_pt: float = 310) -> io.BytesIO:
    sides   = payload.get("sides", [6, 8, 6, 8])
    room_w  = float(sides[1] if len(sides) > 1 else sides[0])
    room_l  = float(sides[3] if len(sides) > 3 else sides[0])
    ceil_h  = float(payload.get("height", 3.0))
    mount_h = float(
        payload.get("mounting_height") or
        (payload.get("project_info") or {}).get("mounting_height") or
        (ceil_h * 0.90))
    mount_h = min(mount_h, ceil_h)

    results = payload.get("results", [])
    chosen  = next((r for r in results if r.get("is_compliant")), None) \
              or (results[0] if results else None)

    DIM   = "#1a1a1a"
    RED   = "#eb1b26"
    BLUE  = "#1a44aa"
    HATCH = "#c8c8c8"

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(width_pt / 72, height_pt / 72),
                                   facecolor="white")
    fig.subplots_adjust(left=0.06, right=0.97, top=0.91, bottom=0.11, wspace=0.32)

    ax.set_facecolor("white")
    ax.set_aspect("equal")
    pad = max(room_w, room_l) * 0.30
    ax.set_xlim(-pad * 0.6, room_w + pad * 1.1)
    ax.set_ylim(-pad * 0.5, room_l + pad * 0.8)

    from matplotlib.patches import Rectangle as MRect
    lw_wall = max(room_w, room_l) * 0.028

    ax.add_patch(MRect((-lw_wall, -lw_wall), room_w + 2 * lw_wall, room_l + 2 * lw_wall,
                        lw=1.5, ec=DIM, fc=HATCH, hatch="////", zorder=2))
    ax.add_patch(MRect((0, 0), room_w, room_l, lw=2.0, ec=DIM, fc="white", zorder=3))

    if chosen:
        nx  = int(chosen.get("layout_nx", 2) or 2)
        ny  = int(chosen.get("layout_ny", 2) or 2)
        sx  = float(chosen.get("Spacing X (m)") or chosen.get("spacing_x") or room_w / max(nx, 1))
        sy  = float(chosen.get("Spacing Y (m)") or chosen.get("spacing_y") or room_l / max(ny, 1))
        ox  = (room_w - sx * (nx - 1)) / 2
        oy  = (room_l - sy * (ny - 1)) / 2
        beam_deg = abs(float(chosen.get("beam_angle_deg") or
                             chosen.get("Beam Angle (deg)", 60) or 60))
        beam_r = mount_h * math.tan(math.radians(beam_deg / 2))
        for i in range(nx):
            for j in range(ny):
                fx, fy = ox + i * sx, oy + j * sy
                ax.plot(fx, fy, "s", color=RED, markersize=5, zorder=5)
                cr = min(beam_r, sx * 0.46, sy * 0.46)
                ax.add_patch(plt.Circle((fx, fy), cr, fc=RED + "20", ec=RED,
                                        lw=0.55, ls="--", zorder=4))

    d_yh = room_l + pad * 0.28
    ax.annotate("", xy=(room_w, d_yh), xytext=(0, d_yh),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.9))
    ax.plot([0, 0],           [room_l, d_yh], color=DIM, lw=0.5, ls=":")
    ax.plot([room_w, room_w], [room_l, d_yh], color=DIM, lw=0.5, ls=":")
    ax.text(room_w / 2, d_yh + pad * 0.12, f"W = {room_w:.2f} m",
            ha="center", va="bottom", fontsize=6.5, color=DIM, fontfamily="monospace")

    d_xv = room_w + pad * 0.32
    ax.annotate("", xy=(d_xv, room_l), xytext=(d_xv, 0),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.9))
    ax.plot([room_w, d_xv], [0, 0],           color=DIM, lw=0.5, ls=":")
    ax.plot([room_w, d_xv], [room_l, room_l], color=DIM, lw=0.5, ls=":")
    ax.text(d_xv + pad * 0.08, room_l / 2, f"L = {room_l:.2f} m",
            ha="left", va="center", fontsize=6.5, color=DIM,
            fontfamily="monospace", rotation=90)

    ax.annotate("", xy=(-pad * 0.25, room_l * 1.12), xytext=(-pad * 0.25, room_l * 0.88),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.2, mutation_scale=9))
    ax.text(-pad * 0.25, room_l * 1.17, "N", ha="center", fontsize=7,
            color=RED, fontweight="bold")

    ax.set_title("FLOOR PLAN  (Top View)", fontsize=8, color=DIM,
                 fontweight="bold", pad=5)
    ax.axis("off")

    ax2.set_facecolor("white")
    ax2.set_aspect("equal")
    pad2 = ceil_h * 0.55
    ax2.set_xlim(-pad2 * 0.55, room_w + pad2 * 1.3)
    ax2.set_ylim(-pad2 * 0.35, ceil_h + pad2 * 0.85)

    lw2 = room_w * 0.025
    lh2 = ceil_h * 0.025

    ax2.add_patch(MRect((-lw2, -lh2 * 2), room_w + 2 * lw2, lh2 * 2,
                         lw=1, ec=DIM, fc=HATCH, hatch="////", zorder=2))
    ax2.add_patch(MRect((-lw2, ceil_h), room_w + 2 * lw2, lh2 * 2,
                         lw=1, ec=DIM, fc=HATCH, hatch="////", zorder=2))
    ax2.add_patch(MRect((-lw2, 0), lw2, ceil_h,
                         lw=1, ec=DIM, fc=HATCH, hatch="////", zorder=2))
    ax2.add_patch(MRect((room_w, 0), lw2, ceil_h,
                         lw=1, ec=DIM, fc=HATCH, hatch="////", zorder=2))
    ax2.add_patch(MRect((0, 0), room_w, ceil_h, lw=0, fc="white", zorder=3))

    if chosen:
        nx  = int(chosen.get("layout_nx", 2) or 2)
        sx  = float(chosen.get("Spacing X (m)") or chosen.get("spacing_x") or room_w / max(nx, 1))
        ox  = (room_w - sx * (nx - 1)) / 2
        beam_deg = abs(float(chosen.get("beam_angle_deg") or
                             chosen.get("Beam Angle (deg)", 60) or 60))
        half_rad = math.radians(beam_deg / 2)
        cone_h   = ceil_h - mount_h
        cone_r   = cone_h * math.tan(half_rad)
        if nx > 1:
            cone_r = min(cone_r, sx * 0.46)
        fw = sx * 0.18 if nx > 1 else room_w * 0.10
        for i in range(nx):
            fx = ox + i * sx
            ax2.add_patch(MRect((fx - fw / 2, ceil_h - lh2 * 3), fw, lh2 * 3,
                                 fc=RED, ec=DIM, lw=0.5, zorder=5))
            ax2.plot([fx, fx - cone_r], [ceil_h, mount_h],
                     color=RED, lw=0.7, ls="--", alpha=0.55, zorder=4)
            ax2.plot([fx, fx + cone_r], [ceil_h, mount_h],
                     color=RED, lw=0.7, ls="--", alpha=0.55, zorder=4)

    d_r = room_w + pad2 * 0.42
    ax2.annotate("", xy=(d_r, ceil_h), xytext=(d_r, 0),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.9))
    ax2.plot([room_w, d_r], [0, 0],            color=DIM, lw=0.5, ls=":")
    ax2.plot([room_w, d_r], [ceil_h, ceil_h],  color=DIM, lw=0.5, ls=":")
    ax2.text(d_r + pad2 * 0.06, ceil_h / 2, f"H = {ceil_h:.2f} m",
             ha="left", va="center", fontsize=6.5, color=DIM, fontfamily="monospace")

    d_l = -pad2 * 0.38
    ax2.annotate("", xy=(d_l, mount_h), xytext=(d_l, 0),
                arrowprops=dict(arrowstyle="<->", color=BLUE, lw=0.9))
    ax2.plot([0, d_l], [0, 0],              color=BLUE, lw=0.5, ls=":")
    ax2.plot([0, d_l], [mount_h, mount_h],  color=BLUE, lw=0.5, ls=":")
    ax2.text(d_l - pad2 * 0.04, mount_h / 2, f"Mh={mount_h:.2f} m",
             ha="right", va="center", fontsize=6.5, color=BLUE, fontfamily="monospace")

    d_t = ceil_h + pad2 * 0.46
    ax2.annotate("", xy=(room_w, d_t), xytext=(0, d_t),
                arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.9))
    ax2.plot([0, 0],           [ceil_h, d_t], color=DIM, lw=0.5, ls=":")
    ax2.plot([room_w, room_w], [ceil_h, d_t], color=DIM, lw=0.5, ls=":")
    ax2.text(room_w / 2, d_t + pad2 * 0.12, f"W = {room_w:.2f} m",
             ha="center", va="bottom", fontsize=6.5, color=DIM, fontfamily="monospace")

    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=RED, markersize=6, label="Fixture"),
        Line2D([0], [0], ls="--", color=RED, alpha=0.6, lw=0.9, label="Beam cone"),
        Line2D([0], [0], ls="-",  color=BLUE, lw=0.9, label=f"Mount H={mount_h:.2f} m"),
    ]
    ax2.legend(handles=handles, loc="lower right", fontsize=6,
               framealpha=0.9, edgecolor=DIM, facecolor="white")

    ax2.set_title("FRONT ELEVATION  (Section View)", fontsize=8, color=DIM,
                  fontweight="bold", pad=5)
    ax2.axis("off")

    fig.text(0.5, 0.02,
             f"Project: {payload.get('project_name', '—')}   |   "
             f"Room: {room_w:.2f}×{room_l:.2f}×{ceil_h:.2f} m   |   "
             f"Scale: NTS   |   Drawn by: {TOOL_NAME} / {COMPANY_NAME}",
             ha="center", fontsize=6, color="#555555", style="italic")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────
#  POLAR CURVE
# ─────────────────────────────────────────────────────────────────
def make_polar_curve_image(beam_angle_deg, beam_angle_max_deg,
                            luminaire_name, width_pt=160, height_pt=160):
    beam     = abs(float(beam_angle_deg))     if beam_angle_deg     else 104.0
    beam_max = abs(float(beam_angle_max_deg)) if beam_angle_max_deg else 169.0
    half_r   = math.radians(beam / 2)
    max_r    = math.radians(beam_max / 2)

    angles    = np.linspace(0, 2 * math.pi, 360)
    intensity = np.zeros(360)
    for i, a in enumerate(angles):
        an = a if a <= math.pi else 2 * math.pi - a
        if an <= half_r:
            intensity[i] = 1.0
        elif an <= max_r:
            decay = (an - half_r) / (max_r - half_r)
            intensity[i] = max(0.0, 0.5 * (1 - decay))

    fig = plt.figure(figsize=(width_pt / 72, height_pt / 72), facecolor="#1A1A1A")
    ax  = fig.add_subplot(111, polar=True)
    ax.set_facecolor("#1A1A1A")
    ax.plot(angles, intensity, color="#eb1b26", linewidth=1.4)
    ax.fill(angles, intensity, alpha=0.15, color="#eb1b26")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rlim(0, 1.15)
    ax.set_rticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels([], color="white")
    ax.tick_params(colors="white", labelsize=5)
    ax.set_thetagrids([0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330],
                      labels=["0°", "30°", "60°", "90°", "120°", "150°",
                              "180°", "210°", "240°", "270°", "300°", "330°"],
                      fontsize=5, color="#AAAAAA")
    ax.grid(color="#333333", linewidth=0.5)
    ax.spines["polar"].set_color("#444444")
    ax.set_title(f"Beam: {beam:.1f}° | {luminaire_name}", fontsize=6,
                 color="#AAAAAA", pad=4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#1A1A1A")
    plt.close(fig)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────
#  ILLUMINANCE GRID
# ─────────────────────────────────────────────────────────────────
def make_grid_image(result, width_pt=340, height_pt=200):
    nx    = result.get("layout_nx") or result.get("Fixtures", 1)
    ny    = result.get("layout_ny") or 1
    avg   = result.get("e_avg_grid_lx") or result.get("avg_lux") or 200
    e_min = result.get("e_min_grid_lx") or avg * 0.85
    e_max = result.get("e_max_grid_lx") or avg * 1.09

    rows, cols = max(int(ny), 3), max(int(nx), 3)
    grid = np.zeros((rows, cols))
    for r in range(rows):
        for c in range(cols):
            noise = math.sin((c + 0.5) / cols * math.pi) * math.sin((r + 0.5) / rows * math.pi)
            grid[r, c] = e_min + (e_max - e_min) * (0.5 + 0.5 * noise)

    fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72), facecolor="#1A1A1A")
    ax.set_facecolor("#1A1A1A")
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "lux", ["#1A3A5C", "#2196F3", "#4CAF50", "#FFC107", "#FF5722"])
    im = ax.imshow(grid, cmap=cmap, aspect="auto",
                   vmin=e_min * 0.9, vmax=e_max * 1.05)
    for r in range(rows):
        for c in range(cols):
            ax.text(c, r, f"{grid[r, c]:.0f}", ha="center", va="center",
                    fontsize=5.5, color="white", fontweight="bold")
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(colors="#AAAAAA", labelsize=5)
    cbar.set_label("lux", color="#AAAAAA", fontsize=6)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"Min: {e_min:.0f} lx   Avg: {avg:.0f} lx   Max: {e_max:.0f} lx",
                 fontsize=6.5, color="#AAAAAA", pad=4)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333333")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#1A1A1A")
    plt.close(fig)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────
def hr(color=None, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness,
                      color=color or SC_BORDER_L, spaceAfter=4)

def section_header(num, title, ST):
    return [Paragraph(num, ST["section_num"]),
            Paragraph(title, ST["h1"]),
            hr(SC_RED, 1), Spacer(1, 4)]

def kv_table(rows, ST, col_widths=None):
    if col_widths is None:
        col_widths = [CONTENT_W * 0.40, CONTENT_W * 0.60]
    data = [[Paragraph(str(k), ST["label"]), Paragraph(str(v), ST["body"])]
            for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [SC_LIGHT_BG, SC_WHITE]),
        ("GRID",           (0, 0), (-1, -1), 0.3, SC_BORDER_L),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ]))
    return t

def _grid_label(result):
    lg = result.get("Layout grid", "")
    if lg: return lg
    return f"{result.get('layout_nx', '?')}×{result.get('layout_ny', '?')}"

def _compliance_badge(ok, ST):
    return Paragraph("✔ COMPLIANT" if ok else "✘ NON-COMPLIANT",
                     ST["tag_pass"] if ok else ST["tag_fail"])

def _sel_label(sel):
    m = {"least_fixture_count_compliant": "Least Fixture Count Compliant",
         "uniformity_fixture_sweep_fallback": "Uniformity Sweep Fallback",
         "best_uniformity": "Best Uniformity",
         "closest_non_compliant": "Closest (Non-Compliant)"}
    return m.get(sel, sel.replace("_", " ").title())

def _metric_box(label, value, unit, ST):
    t = Table([[Paragraph(label, ST["metric_lbl"])],
               [Paragraph(f'<font size="22"><b>{value}</b></font>', ST["metric_val"])],
               [Paragraph(unit, ST["metric_lbl"])]],
              colWidths=[CONTENT_W * 0.155])
    t.setStyle(TableStyle([("BOX",           (0, 0), (-1, -1), 0.5, SC_BORDER_L),
                            ("BACKGROUND",    (0, 0), (-1, -1), SC_LIGHT_BG),
                            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                            ("TOPPADDING",    (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


# ─────────────────────────────────────────────────────────────────
#  SECTION BUILDERS
# ─────────────────────────────────────────────────────────────────
def sec_project_info(payload, ST):
    story = section_header("01 —", "Project & Space Information", ST)

    sides   = payload.get("sides", [10, 10, 10, 10])
    W_m     = float(sides[1] if len(sides) > 1 else sides[0])
    L_m     = float(sides[3] if len(sides) > 3 else sides[0])
    H_m     = float(payload.get("height", 4))
    area    = W_m * L_m
    mount_h = float(payload.get("mounting_height") or
                    (payload.get("project_info") or {}).get("mounting_height") or
                    H_m * 0.90)
    mount_h = min(mount_h, H_m)
    ri      = (W_m * L_m) / (2 * H_m * (W_m + L_m))

    prepared = payload.get("name", "—")
    if " at " in prepared: prepared = prepared.split(" at ")[0]
    company  = payload.get("company", COMPANY_NAME)
    if " at " in company:  company  = company.split(" at ")[0]

    proj_rows = [("Project Name",  payload.get("project_name", "—")),
                 ("Report Date",   datetime.now().strftime("%B %d, %Y")),
                 ("Prepared By",   prepared),
                 ("Company",       company),
                 ("Email",         payload.get("email", "—")),
                 ("Phone",         payload.get("phone", "—"))]
    if payload.get("notes"):
        proj_rows.append(("Notes", payload["notes"]))

    std_rows = [("Standard",        "EN 12464-1 (Indoor Workplaces)"),
                ("Reference No.",   payload.get("standard_ref_no", "—")),
                ("Category",        payload.get("standard_category", "—")),
                ("Task / Activity", payload.get("standard_task_or_activity", "—"))]

    GUTTER = 6
    HALF_W = (CONTENT_W - GUTTER) / 2
    sub_cw = [HALF_W * 0.42, HALF_W * 0.58]

    proj_t = kv_table(proj_rows, ST, col_widths=sub_cw)
    std_t  = kv_table(std_rows,  ST, col_widths=sub_cw)

    two_col = Table([[proj_t, std_t]], colWidths=[HALF_W, HALF_W])
    two_col.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("RIGHTPADDING", (0, 0), (0, -1),  GUTTER),
        ("LEFTPADDING",  (1, 0), (1, -1),  0),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Space Geometry", ST["h2"]))
    geom_headers = ["Width (X)", "Length (Y)", "Ceiling H", "Mounting H", "Floor Area", "Room Index k"]
    geom_vals    = [f"<b>{W_m:.2f} m</b>", f"<b>{L_m:.2f} m</b>",
                    f"<b>{H_m:.2f} m</b>", f"<b>{mount_h:.2f} m</b>",
                    f"<b>{area:.1f} m²</b>", f"<b>{ri:.2f}</b>"]
    geom = [[Paragraph(h, ST["white_label"]) for h in geom_headers],
            [Paragraph(v, ST["body"])        for v in geom_vals]]
    geom_t = Table(geom, colWidths=[CONTENT_W / 6] * 6)
    geom_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), SC_DARK_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), SC_WHITE),
        ("BACKGROUND",    (0, 1), (-1, 1), SC_LIGHT_BG),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.3, SC_BORDER_L),
    ]))
    story.append(geom_t)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Space Drawing — Orthographic View", ST["h2"]))
    story.append(Spacer(1, 4))
    buf = make_room_drawing(payload, width_pt=CONTENT_W * 1.06, height_pt=CONTENT_W * 0.65)
    story.append(Image(buf, width=CONTENT_W, height=CONTENT_W * 0.60))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "▪ Red squares = fixture positions (compliant solution).  "
        "▪ Dashed circles/lines = beam footprint / cone.  "
        "▪ Blue arrows = mounting height (Mh).  "
        "▪ Gray hatching = structural walls and slabs.",
        ST["small"]))
    return story


def sec_room_drawing(payload, ST):
    token = payload.get("token")
    if not token:
        return []

    upload_dir = os.path.join(os.path.dirname(__file__), "luxscale", "uploads")
    drawing_path = os.path.join(upload_dir, f"{token}_drawing.png")

    if not os.path.exists(drawing_path):
        return []

    story = section_header("DRAW —", "Room Drawing (Box Studio)", ST)
    story.append(Paragraph("Unfolded projection with fixture overlay and physical dimensions.", ST["body"]))
    story.append(Spacer(1, 5 * mm))

    try:
        # Scale image to fit page width roughly
        img = Image(drawing_path, width=160 * mm, height=120 * mm, kind="proportional")
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 10 * mm))
    except Exception as e:
        story.append(Paragraph(f"<i>(Note: Manual drawing attached but could not be rendered: {e})</i>", ST["italic"]))

    return story


def sec_standard_requirements(payload, ST):
    story = section_header("02 —", "Standard Requirements (EN 12464-1)", ST)
    std  = payload.get("standard_lighting", {})
    cat  = payload.get("standard_category", "")
    task = payload.get("standard_task_or_activity", "")
    story.append(Paragraph(f"<b>{cat}</b> — {task}", ST["body"]))
    note = std.get("specific_requirements", "")
    if note:
        story.append(Paragraph(f"<i>Note: {note}</i>", ST["italic"]))
    story.append(Spacer(1, 6))

    headers = ["Parameter", "Symbol", "Required Value", "Description"]
    rows = [
        ("Maintained Illuminance (lower)", "<i>Em_r</i>",    f"<b>{std.get('Em_r_lx', '—')} lx</b>",    "Minimum average maintained illuminance"),
        ("Maintained Illuminance (upper)", "<i>Em_u</i>",    f"<b>{std.get('Em_u_lx', '—')} lx</b>",    "Maximum recommended illuminance"),
        ("Uniformity",                     "<i>Uo</i>",      f"<b>≥ {std.get('Uo', '—')}</b>",           "Min/Avg illuminance ratio"),
        ("Colour Rendering Index",         "<i>Ra</i>",      f"<b>≥ {std.get('Ra', '—')}</b>",            "Minimum CRI requirement"),
        ("Unified Glare Rating",           "<i>RUGB</i>",    f"<b>≤ {std.get('RUGL', '—')}</b>",          "Maximum glare discomfort index"),
        ("Vertical Illuminance",           "<i>Ez</i>",      f"<b>{std.get('Ez_lx', '—')} lx</b>",       "Vertical plane illuminance"),
        ("Wall Illuminance",               "<i>Em_wall</i>", f"<b>{std.get('Em_wall_lx', '—')} lx</b>",  "Average wall illuminance"),
        ("Ceiling Illuminance",            "<i>Em_ceil</i>", f"<b>{std.get('Em_ceiling_lx', '—')} lx</b>", "Average ceiling illuminance"),
    ]
    data = [[Paragraph(h, ST["white_label"]) for h in headers]]
    for nm, sym, val, desc in rows:
        data.append([Paragraph(nm, ST["body"]), Paragraph(sym, ST["body"]),
                     Paragraph(val, ST["body"]), Paragraph(desc, ST["small"])])
    cw = [CONTENT_W * 0.32, CONTENT_W * 0.13, CONTENT_W * 0.18, CONTENT_W * 0.37]
    t  = Table(data, colWidths=cw)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), SC_DARK_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), SC_WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SC_LIGHT_BG, SC_WHITE]),
        ("ALIGN",         (1, 0), (2, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.3, SC_BORDER_L),
    ]))
    story.append(t)
    return story


def sec_all_solutions_summary(results, payload, ST):
    story = section_header("03 —", f"Calculation Results — {len(results)} Solutions Found", ST)
    headers = ["#", "Luminaire", "Fixtures", "Power (W)", "Efficacy", "Avg Lux", "U₀", "Layout", "OK"]
    data = [[Paragraph(h, ST["white_label"]) for h in headers]]
    for i, r in enumerate(results):
        ok  = r.get("is_compliant", False)
        lum = r.get("Luminaire") or r.get("luminaire", "—")
        data.append([
            Paragraph(str(i + 1), ST["body"]),
            Paragraph(lum, ST["body"]),
            Paragraph(str(r.get("Fixtures") or r.get("fixtures", "—")), ST["body"]),
            Paragraph(str(r.get("Power (W)") or r.get("power", "—")), ST["body"]),
            Paragraph(str(r.get("Efficacy (lm/W)") or r.get("efficacy", "—")), ST["body"]),
            Paragraph(f"{r.get('Average Lux') or r.get('avg_lux', 0):.1f}", ST["body"]),
            Paragraph(f"{r.get('U0_calculated') or r.get('u0_calculated', 0):.3f}", ST["body"]),
            Paragraph(_grid_label(r), ST["body"]),
            Paragraph("✔" if ok else "✘", ST["tag_pass"] if ok else ST["tag_fail"]),
        ])
    cw = [CONTENT_W * w for w in [0.05, 0.20, 0.09, 0.10, 0.11, 0.10, 0.09, 0.12, 0.14]]
    t  = Table(data, colWidths=cw)
    ts = [("BACKGROUND",    (0, 0), (-1, 0), SC_DARK_BG),
          ("TEXTCOLOR",     (0, 0), (-1, 0), SC_WHITE),
          ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
          ("TOPPADDING",    (0, 0), (-1, -1), 5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
          ("GRID",          (0, 0), (-1, -1), 0.3, SC_BORDER_L)]
    for i, r in enumerate(results):
        bg = colors.HexColor("#F0FFF0") if r.get("is_compliant") else colors.HexColor("#FFF5F5")
        ts.append(("BACKGROUND", (0, i + 1), (-1, i + 1), bg))
    t.setStyle(TableStyle(ts))
    story.append(t)
    return story


def sec_solution_detail(result, sol_index, payload, ST, include_header=True):
    story   = []
    lum     = result.get("Luminaire") or result.get("luminaire", "—")
    ok      = result.get("is_compliant", False)
    sel     = result.get("Selection", "")
    std     = payload.get("standard_lighting", {})
    n_total = len(payload.get("results", []))

    if include_header:
        story += section_header(f"Solution {sol_index + 1} of {n_total} —", lum, ST)
    story.append(KeepTogether([_compliance_badge(ok, ST),
                                Paragraph(f"  <b>Selection:</b> {_sel_label(sel)}", ST["body"]),
                                Spacer(1, 6)]))

    avg_lux = result.get("e_avg_grid_lx") or result.get("Average Lux") or result.get("avg_lux", 0)
    min_lux = result.get("e_min_grid_lx") or result.get("E_min_grid_lx", 0)
    max_lux = result.get("e_max_grid_lx") or result.get("E_max_grid_lx", 0)
    u0      = result.get("U0_calculated") or result.get("u0_calculated", 0)
    fix_cnt = result.get("Fixtures") or result.get("fixtures", 0)
    tot_pw  = result.get("Total Power (W/H)") or result.get("total_power", 0)
    req_u   = std.get("Uo", 0.4)

    metrics = Table([[
        _metric_box("Avg Lux",    f"{avg_lux:.1f}", "lux",          ST),
        _metric_box("Min Lux",    f"{min_lux:.1f}", "lux",          ST),
        _metric_box("Max Lux",    f"{max_lux:.1f}", "lux",          ST),
        _metric_box("Uniformity", f"{u0:.3f}",      f"req≥{req_u}", ST),
        _metric_box("Fixtures",   str(fix_cnt),     "units",         ST),
        _metric_box("Power",      f"{tot_pw:,.0f}", "W",            ST),
    ]], colWidths=[CONTENT_W / 6] * 6)
    metrics.setStyle(TableStyle([("ALIGN",  (0, 0), (-1, -1), "CENTER"),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(metrics)
    story.append(Spacer(1, 8))

    bd  = result.get("Beam Angle (deg)")     or result.get("beam_angle_deg")     or -104.0
    bm  = result.get("Beam angle max (deg)") or result.get("beam_angle_max_deg") or 169.0
    buf = make_polar_curve_image(bd, bm, lum, 160, 160)
    polar_img = Image(buf, width=140, height=140)

    pwr    = result.get("Power (W)") or result.get("power", "—")
    eff    = result.get("Efficacy (lm/W)") or result.get("efficacy", "—")
    ies_lm = result.get("IES lumens (lm)") or result.get("ies_lumens", "—")
    sx     = result.get("Spacing X (m)") or result.get("spacing_x", "—")
    sy     = result.get("Spacing Y (m)") or result.get("spacing_y", "—")
    u1     = result.get("U1_calculated") or result.get("u1_calculated", "—")

    p_rows = [
        ("Luminaire",               lum),
        ("Power per unit",          f"{pwr} W"),
        ("Luminous efficacy",       f"{eff} lm/W"),
        ("Rated lumens (IES)",
         f"{ies_lm:,} lm" if isinstance(ies_lm, (int, float)) else str(ies_lm)),
        ("Fixture count",           f"{fix_cnt} units"),
        ("Layout grid",             _grid_label(result)),
        ("Spacing X",               f"{sx} m"),
        ("Spacing Y",               f"{sy} m"),
        ("Beam angle (half-power)", f"{bd}°"),
        ("Beam angle (max)",        f"{bm}°"),
        ("U₁ (Emin/Eavg)",          str(u1)),
        ("Total installed power",   f"{tot_pw:,} W"),
        ("Compliance basis",
         result.get("Lux compliance basis") or result.get("lux_compliance_basis", "—")),
    ]
    p_data = [[Paragraph("Parameter", ST["white_label"]), Paragraph("Value", ST["white_label"])]] + \
             [[Paragraph(k, ST["small"]), Paragraph(str(v), ST["body"])] for k, v in p_rows]
    p_cw   = [CONTENT_W * 0.38 - 80, CONTENT_W * 0.62 - 80]
    p_t    = Table(p_data, colWidths=p_cw)
    p_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), SC_RED),
        ("TEXTCOLOR",     (0, 0), (-1, 0), SC_WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SC_LIGHT_BG, SC_WHITE]),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.3, SC_BORDER_L),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
    ]))
    side = Table([[polar_img, p_t]], colWidths=[150, CONTENT_W - 150])
    side.setStyle(TableStyle([("VALIGN",      (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (1, 0), (1, 0),  10)]))
    story.append(side)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Illuminance Distribution (Simulated Grid)", ST["h2"]))
    story.append(Spacer(1, 4))
    gb = make_grid_image(result)
    if gb:
        # Height increased from 0.38 → 0.52 of content width for a taller grid.
        # To adjust: change the 0.52 multiplier (e.g. 0.45 = slightly shorter, 0.60 = taller).
        story.append(Image(gb, width=CONTENT_W, height=CONTENT_W * 0.50))
    story.append(Spacer(1, 6))

    # Only break to a new page if less than 80 mm remains — enough for the
    # compliance table. If the table fits on the same page as the grid it
    # stays there; if it would be squeezed it moves to the next page.
    story.append(CondPageBreak(80 * mm))
    story.append(Paragraph("Compliance Analysis", ST["h2"]))
    em_r, em_u, req_uo = std.get("Em_r_lx", 200), std.get("Em_u_lx", 300), std.get("Uo", 0.4)
    checks = [
        ("Average Illuminance", f"{avg_lux:.1f} lx", f"≥ {em_r} lx", avg_lux >= em_r),
        ("Max Illuminance",     f"{max_lux:.1f} lx", f"≤ {em_u} lx", max_lux <= em_u),
        ("Uniformity U₀",       f"{u0:.3f}",          f"≥ {req_uo}",  u0 >= req_uo),
    ]
    c_data = [[Paragraph(h, ST["white_label"]) for h in ["Check", "Calculated", "Required", "Status"]]] + \
             [[Paragraph(nm, ST["body"]), Paragraph(cal, ST["body"]),
               Paragraph(req, ST["body"]),
               Paragraph("✔ PASS" if chk else "✘ FAIL",
                         ST["tag_pass"] if chk else ST["tag_fail"])]
              for nm, cal, req, chk in checks]
    ct = Table(c_data, colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.22, CONTENT_W * 0.22, CONTENT_W * 0.21])
    ct.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), SC_DARK_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), SC_WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SC_LIGHT_BG, SC_WHITE]),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.3, SC_BORDER_L),
    ]))
    story.append(ct)
    return story


def sec_disclaimers(payload, ST):
    story = section_header("04 —", "Calculation Notes & Disclaimers", ST)
    for note in [
        "Lighting calculations were performed using the LuxScale AI engine based on IES photometric data and EN 12464-1.",
        "Illuminance values represent maintained values (Em) accounting for luminaire maintenance factor and room surface reflectances.",
        "Polar curves are derived from IES half-power beam angle data and represent approximate distribution patterns.",
        "Uniformity (U0  = Emin/Eavg) is calculated on the work plane at floor level (0.00 m) unless otherwise stated.",
        "Energy calculations follow DIN 18599-4. Annual consumption estimates assume standard operating hours.",
        "This report is for design reference only. Final installation must be verified by a qualified lighting engineer on site.",
    ]:
        story.append(Paragraph(f"• {note}", ST["body"]))
    story.append(Spacer(1, 12))
    story.append(hr())

    num_sig = len(_SIGNATORIES)
    col_w   = CONTENT_W / max(num_sig, 1)

    sig_header_row = [Paragraph(role, ST["label"])  for role, _    in _SIGNATORIES]
    sig_name_row   = [Paragraph(name, ST["body"])   for _,    name in _SIGNATORIES]
    sig_space_row  = [Paragraph(" ",  ST["body"])   for _ in _SIGNATORIES]
    sig_line_row   = [Paragraph("_" * 35 + "  Signature / Date", ST["small"]) for _ in _SIGNATORIES]

    sig = Table(
        [sig_header_row, sig_name_row, sig_space_row, sig_line_row],
        colWidths=[col_w] * num_sig,
    )
    sig.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Short Circuit  ·  {COMPANY_ADDRESS}  ·  {COMPANY_PHONE}  ·  {COMPANY_WEB}"
        f"  |  Designed by {TOOL_NAME}",
        ST["footer"]))
    return story


# ─────────────────────────────────────────────────────────────────
#  DOCUMENT BUILDER
# ─────────────────────────────────────────────────────────────────
class _SCDocTemplate(BaseDocTemplate):
    def __init__(self, buf, payload, title, is_solution=False,
                 sol_index=0, sol_data=None, **kw):
        super().__init__(buf, pagesize=A4, **kw)
        self._payload     = payload
        self._title       = title
        self._is_solution = is_solution
        self._sol_index   = sol_index
        self._sol_data    = sol_data
        self._total       = [0]

        cover_f = Frame(0, 0, PAGE_W, PAGE_H, id="cover",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        body_f  = Frame(MARGIN, 16 * mm, CONTENT_W, PAGE_H - 30 * mm, id="body")

        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover_f], onPage=self._on_cover),
            PageTemplate(id="Body",  frames=[body_f],  onPage=self._on_body),
        ])

    def _on_cover(self, c, doc):
        build_cover(c, self._payload, self._title,
                    self._is_solution, self._sol_index, self._sol_data)

    def _on_body(self, c, doc):
        _header_footer(c, doc, self._title, self._total)


def _render_doc(payload, story, title, is_solution=False, sol_index=0, sol_data=None):
    buf = io.BytesIO()
    doc = _SCDocTemplate(buf, payload, title, is_solution=is_solution,
                         sol_index=sol_index, sol_data=sol_data,
                         leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=28 * mm, bottomMargin=20 * mm)
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────
def build_full_report_pdf(payload: dict) -> bytes:
    ST      = make_styles()
    results = payload.get("results", [])
    title   = TOOL_NAME

    story = [NextPageTemplate("Body"), PageBreak()]
    story += sec_project_info(payload, ST);          story.append(PageBreak())
    story += sec_room_drawing(payload, ST);         story.append(PageBreak())
    story += sec_standard_requirements(payload, ST); story.append(PageBreak())
    if results:
        story += sec_all_solutions_summary(results, payload, ST)
        story.append(PageBreak())
        for i, r in enumerate(results):
            story += sec_solution_detail(r, i, payload, ST)
            story.append(PageBreak())
    story += sec_disclaimers(payload, ST)
    return _render_doc(payload, story, title)


def build_solution_pdf(payload: dict, sol_index: int) -> bytes:
    ST      = make_styles()
    results = payload.get("results", [])
    if sol_index >= len(results):
        raise IndexError(f"Solution index {sol_index} out of range")
    result = results[sol_index]
    title  = f"{TOOL_NAME} — Solution {sol_index + 1}"

    story = [NextPageTemplate("Body"), PageBreak()]
    story += sec_project_info(payload, ST);          story.append(PageBreak())
    story += sec_room_drawing(payload, ST);         story.append(PageBreak())
    story += sec_standard_requirements(payload, ST); story.append(PageBreak())
    story += sec_solution_detail(result, sol_index, payload, ST, include_header=True)
    story.append(PageBreak())
    story += sec_disclaimers(payload, ST)
    return _render_doc(payload, story, title,
                       is_solution=True, sol_index=sol_index, sol_data=result)


# ─────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────
def _load_study(token, studies_dir=None):
    if studies_dir is None:
        studies_dir = Path(__file__).parent / "api" / "data" / "studies"
    with open(Path(studies_dir) / f"{token}.json") as f:
        return json.load(f)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="LuxSCaleAIPDF report generator")
    p.add_argument("token")
    p.add_argument("--solution", "-s", type=int, default=None)
    p.add_argument("--out", "-o", default=None)
    p.add_argument("--studies-dir", default=None)
    args = p.parse_args()

    data    = _load_study(args.token, args.studies_dir)
    payload = data["payload"]

    if args.solution is not None:
        pdf = build_solution_pdf(payload, args.solution)
        out = args.out or f"{args.token}_solution_{args.solution + 1}.pdf"
    else:
        pdf = build_full_report_pdf(payload)
        out = args.out or f"{args.token}_full_report.pdf"

    Path(out).write_bytes(pdf)
    print(f"✔ PDF written to: {out}  ({len(pdf):,} bytes)")