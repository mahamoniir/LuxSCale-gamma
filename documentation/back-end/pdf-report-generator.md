# PDF Report Generator

> **Module:** `generate_report.py` (project root)  
> **Brand:** Short Circuit — logos from `assets/brand/`  
> **Framework:** ReportLab (server-side, no browser dependency)

---

## 1. Overview

`generate_report.py` builds **fully branded A4 PDF reports** from a stored study payload. Reports are served via Flask routes — no client-side PDF generation.

Two report types are available:

| Type | Route | Description |
|------|-------|-------------|
| Full report | `GET /api/report/<token>/full` | All solution options in one PDF |
| Single solution | `GET /api/report/<token>/solution/<int>` | One solution option |

---

## 2. Logo System (v3 — Current)

The logo system has gone through three iterations. **v3 is the current implementation.**

### Version history

| Version | Approach | Status |
|---------|----------|--------|
| v1 | lxml + ReportLab SVG path parser | Deprecated — failed on servers without lxml |
| v2 | stdlib `xml.etree.ElementTree` SVG renderer | Deprecated — failed with renderPM on some servers |
| v3 | Direct PNG file read from `assets/brand/` | **Current** — zero extra dependencies |

### v3 logo file usage

| File | Used on |
|------|---------|
| `assets/brand/logo-bg-dark.png` | PDF cover page (white text, dark/red SC background) |
| `assets/brand/logo-bg-light.png` | PDF body page headers (dark text, white background) |

These PNG files must be pre-exported from the SVG sources at ≥ 600px wide with transparent background.

### Adding the logo to a page

```python
def _get_logo_png(variant="dark"):
    # variant="dark"  → logo-bg-dark.png   (cover)
    # variant="light" → logo-bg-light.png  (headers)
    path = BRAND_DIR / f"logo-bg-{variant}.png"
    if path.exists():
        return ImageReader(str(path))
    return None
```

---

## 3. Report Structure

### Cover page

- Full-bleed dark/red SC background
- SC logo (white variant, top left)
- Tool name: **LuxScaleAI** (large, white, Anton font)
- Report subtitle and date
- Project name on page 2

### Running header (all body pages)

- SC logo (light variant, left)
- Report title and page number (right)
- Red separator line (position: `HEADER_LINE_Y_OFFSET = 16mm`)

### Content pages

1. **Project information table** — name, client, company, contact, standards ref
2. **Room summary** — dimensions, ceiling height, area, standard requirements
3. **Per-solution section** — one section per result option:
   - Fixture details (type, wattage, count, efficacy)
   - Calculated values (lux, U₀, spacing)
   - Compliance status and margins
   - IES-derived metrics (if available)

### Signatory section

Three modes — select by uncommenting in `generate_report.py`:

```
MODE A: Technical Office Manager only  ← CURRENTLY ACTIVE
MODE B: Design Team Leader only
MODE C: Both signatories
```

---

## 4. Flask Integration

```python
# In app.py
from generate_report import build_full_report_pdf, build_solution_pdf

@app.route("/api/report/<token>/full", methods=["GET"])
def api_report_full(token):
    payload   = _load_payload(token)
    pdf_bytes = build_full_report_pdf(payload)
    return Response(pdf_bytes, mimetype="application/pdf", ...)

@app.route("/api/report/<token>/solution/<int:sol_index>", methods=["GET"])
def api_report_solution(token, sol_index):
    payload   = _load_payload(token)
    pdf_bytes = build_solution_pdf(payload, sol_index)
    return Response(pdf_bytes, mimetype="application/pdf", ...)
```

Token validation: only hex tokens `[0-9a-fA-F]+` are accepted — path traversal is blocked by `abort(400)` on invalid format.

---

## 5. Key Configuration

| Constant | Location | Description |
|----------|----------|-------------|
| `TOOL_NAME` | Top of `generate_report.py` | Cover page headline — currently `"LuxScaleAI"` |
| `HEADER_LINE_Y_OFFSET` | `_header_footer()` | Vertical position of red separator line (default: 16mm) |
| `BRAND_DIR` | Top of file | Path to `assets/brand/` |
| Signatory blocks | Signatory config section | MODE A / B / C — uncomment exactly one |

---

## 6. Dependencies

| Package | Use |
|---------|-----|
| `reportlab` | PDF layout engine — pages, frames, templates |
| `matplotlib` | Charts and heatmaps embedded in PDF |
| `numpy` | Numeric data for chart generation |
| `Pillow` (PIL) | PNG logo loading via `ImageReader` |

All are in `requirements.txt`.

---

## 7. Customisation Notes

- **Cover title:** Change `TOOL_NAME = "LuxScaleAI"` — the project name intentionally appears on page 2, not the cover
- **Header line position:** Adjust `HEADER_LINE_Y_OFFSET` in mm — larger value moves line down
- **Logo size:** Adjust `logo_w` / `logo_h` in `_header_footer()` — logos scale proportionally
- **Colour scheme:** SC Red is `colors.HexColor("#eb1b26")` throughout — change here to rebrand
