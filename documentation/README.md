# LuxScaleAI — Documentation Index

> **Project:** LuxScaleAI  
> **Brand:** Short Circuit — [shortcircuit.company/SCbrand](http://shortcircuit.company/SCbrand)  
> **Logo sources:** `assets/brand/logo-bg-dark.png` · `assets/brand/logo-bg-light.png`  
> **Brand colours:** `#eb1b26` (SC Red) · `#111111` (Dark BG) · `#ffffff` (White)  
> **Fonts:** Anton (headings) · IBM Plex Sans Arabic (body, Latin + Arabic)  
> **Last updated:** April 2026

---

## What is LuxScaleAI?

LuxScaleAI is a professional lighting design platform developed and branded under **Short Circuit**. It combines:

- A **Flask REST API** for photometric calculation (lumen method + IES grid uniformity)
- A **web frontend** (multi-page, HTML/CSS/JS) for project input, result review, and 3D visualisation
- A **standards database** (EN 12464-1) for compliance-driven room lighting requirements
- A **PDF report generator** (ReportLab) branded with Short Circuit assets
- An **AI analysis pipeline** (Google Gemini + local Ollama) that scores results and provides actionable fixes
- An **admin dashboard** for quota management, fixture-map editing, and snapshot control

---

## Documentation Map

| Folder | Contents |
|--------|----------|
| [`back-end/`](./back-end/README.md) | Flask API, calculation engine, IES integration, logging, deployment |
| [`front-end/`](./front-end/README.md) | Pages, assets, API client, Three.js, styling, roadmap |
| [`lighting/`](./lighting/README.md) | Lumen method, IES photometry, uniformity, compliance |
| [`math/`](./math/README.md) | All equations, symbols, pipeline from request to export |
| [`ai/`](./ai/README.md) | AI pipeline, Gemini, Ollama, prompt engineering, snapshot system, roadmap |
| [`claude/`](./claude/) | Legacy AI pipeline docs (HTML/PDF reference copies) |

---

## Quick Data Flow

```
Browser
  └─ POST /calculate
       └─ validate_ceiling_height_m()
       └─ _resolve_calculate_inputs()  ← standards_cleaned.json OR place
       └─ calculate_lighting()
            └─ determine_zone / determine_luminaire
            └─ lumen-method average lux
            └─ IES grid U₀ uniformity
            └─ compliance rows + fallback sweep
       └─ JSON response  →  result.html?token=…

result.html
  └─ POST /api/submit  → stores study JSON → token
  └─ GET  /api/get?token=…  → loads study
  └─ POST /api/ai/analyze?token=…  → AI quality score + issues
  └─ GET  /api/report/<token>/full  → branded PDF (ReportLab)
```

---

## Project Root Files

| File | Purpose |
|------|---------|
| `app.py` | Main Flask application — all routes, admin auth, CORS |
| `generate_report.py` | ReportLab PDF builder (branded with SC logo PNGs) |
| `requirements.txt` | Python dependencies |
| `CLAUDE.md` | Claude Code guidance file |
| `STRUCTURE.md` | Auto-generated project structure map |
| `DEPLOY.md` | Railway / production deployment steps |
| `.env` | Live secrets (never commit — see `.env.example`) |
| `gemini_config.json` | AI account config, quota counters, model selection |
| `gemini_snapshot.json` | Last approved AI analysis (fallback) |

---

## Brand Assets

| File | Use |
|------|-----|
| `assets/brand/logo-bg-dark.png` | PDF cover pages (white text, dark/red background) |
| `assets/brand/logo-bg-light.png` | PDF body headers (black text, white background) |
| `assets/brand/logo-bg-dark.svg` | Source vector — dark variant |
| `assets/brand/logo-bg-light.svg` | Source vector — light variant |
| `assets/brand/logo-mono-dark.svg` | Single-colour dark variant |
| `assets/brand/logo-mono-light.svg` | Single-colour light variant |
| `assets/favicon.svg` | Browser tab icon |

---

*For contribution guidelines and coding standards, see `CLAUDE.md` at project root.*
