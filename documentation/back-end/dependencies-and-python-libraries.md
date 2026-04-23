# Dependencies and Python Libraries

> **File:** `requirements.txt`  
> **Last updated:** April 2026

---

## Current `requirements.txt`

```
flask
flask-cors
fpdf
numpy
matplotlib
reportlab
Pillow
scipy
python-dotenv
openai
gunicorn
```

---

## Package Reference

| Package | Purpose |
|---------|---------|
| `flask` | HTTP framework, routing, session, Blueprint |
| `flask-cors` | CORS headers for cross-origin dashboard and admin UI |
| `fpdf` | Legacy simple PDF route (`POST /pdf`) — not branded |
| `numpy` | Photometric grid calculations, uniformity arrays |
| `matplotlib` | Heatmaps and IES plots (server-side Agg backend) |
| `reportlab` | **Primary PDF engine** — branded A4 reports in `generate_report.py` |
| `Pillow` | PNG logo loading for ReportLab (`ImageReader`) |
| `scipy` | Advanced IES analysis in `ies_analyzer.py` |
| `python-dotenv` | Loads `.env` secrets at startup |
| `openai` | **Optional / legacy** — `ai_lux.py` only; not used in production AI path |
| `gunicorn` | Production WSGI server (Railway / Linux deployment) |

---

## AI Pipeline — No Extra Dependencies

The Gemini and Ollama integrations use **Python's built-in `urllib`** only. No Gemini SDK, `requests`, or `httpx` required. This was intentional:

- Smaller dependency surface
- Works in any Python 3.x environment
- No version conflicts

---

## OpenAI Note

`openai` is listed in `requirements.txt` but is only used by the **legacy** `luxscale/lighting_calc/ai_lux.py` (`ask_ai_lux()`). This module is not called in the active pipeline. It can be removed if you want a smaller install.

The active AI pipeline uses Gemini (via `urllib`) and Ollama (via `urllib`).

---

## matplotlib Backend

All matplotlib usage sets `matplotlib.use("Agg")` before any other import — required for server-side rendering without a display. Set in `generate_report.py` and `luxscale/ies_routes.py`.

---

## Production Install

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:$PORT
```

---

Next: [deployment-local-and-production.md](./deployment-local-and-production.md)
