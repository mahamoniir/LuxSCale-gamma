# LuxScaleAI — Back-end Documentation

> **Brand:** Short Circuit · `#eb1b26` accent · Logo: `assets/brand/`  
> **Last updated:** April 2026

Split reference for the **Python/Flask server**, **lighting calculation**, **IES photometry**, **compliance**, **logging**, **AI pipeline**, and **deployment**.

---

## Document Map

| # | File | Topic |
|---|------|-------|
| 1 | [architecture-and-runtime.md](./architecture-and-runtime.md) | Repo layout, `luxscale` package, entrypoint, environment variables |
| 2 | [flask-api-and-routes.md](./flask-api-and-routes.md) | Every HTTP route, auth, static files, standards resolution |
| 3 | [calculation-engine.md](./calculation-engine.md) | `calculate_lighting`: lumen method, spacing sweep, fast mode |
| 4 | [compliance-and-standards.md](./compliance-and-standards.md) | Standard rows, lux/U₀ gaps, `is_compliant`, fallback sweeps |
| 5 | [ies-catalog-and-resolution.md](./ies-catalog-and-resolution.md) | `fixture_map.json`, merged catalog, `resolve_ies_path`, folder scan |
| 6 | [ies-parsing-and-photometry.md](./ies-parsing-and-photometry.md) | LM-63 parser, `ies.json` index, JSON blobs, beam angle, caching |
| 7 | [uniformity-grid-and-reports.md](./uniformity-grid-and-reports.md) | `compute_uniformity_metrics`, work-plane grid, `uniformity_reports/*.txt` |
| 8 | [logging-and-artifacts.md](./logging-and-artifacts.md) | `luxscale_app.log`, `calculation_logs/`, traces, uniformity session files |
| 9 | [dependencies-and-python-libraries.md](./dependencies-and-python-libraries.md) | `requirements.txt`, NumPy, Matplotlib, ReportLab, OpenAI note |
| 10 | [deployment-local-and-production.md](./deployment-local-and-production.md) | Local Flask, XAMPP PHP API, CORS, Railway/port, admin dashboard |
| 11 | [pdf-report-generator.md](./pdf-report-generator.md) | `generate_report.py` — ReportLab PDF, SC branding, logo system |
| 12 | [admin-system.md](./admin-system.md) | Session + bearer token auth, admin routes, fixture-map editing |

---

## Quick Data Flow

```
POST /calculate
  → validate_ceiling_height_m()
  → _resolve_calculate_inputs()       ← standards_cleaned.json OR place
  → calculate_lighting(...)
       → determine_zone / determine_luminaire  (catalog options)
       → lumen-method average lux + IES grid U₀
       → compliance rows + optional uniformity fallback sweep
  → JSON + calculation_meta + optional trace file path

POST /api/submit  →  stores study JSON → token
GET  /api/get?token=…  →  loads study JSON → result.html renders

POST /api/ai/analyze  →  AI quality score + issues + suggestions
GET  /api/report/<token>/full  →  branded PDF (ReportLab + SC logos)
```

---

## Module Index

| Module | Path | Role |
|--------|------|------|
| Flask app | `app.py` | All routes, CORS, admin auth, blueprint registration |
| Calculation engine | `luxscale/lighting_calc/calculate.py` | Core lumen method + IES uniformity |
| Geometry | `luxscale/lighting_calc/geometry.py` | Room area, zone detection, spacing grid |
| Constants | `luxscale/lighting_calc/constants.py` | Luminaire catalog, efficacy tables, place definitions |
| IES routes | `luxscale/ies_routes.py` | IES upload, polar plots, 3D surface (Blueprint) |
| IES analyzer | `luxscale/ies_analyzer.py` | LM-63 parsing, beam angle, metrics |
| AI routes | `luxscale/ai_routes.py` | `/api/ai/*` Blueprint |
| Gemini manager | `luxscale/gemini_manager.py` | Waterfall, quota, snapshot |
| Ollama manager | `luxscale/ollama_manager.py` | Local model interface |
| AI prompt | `luxscale/ai_prompt.py` | Shared prompt builder |
| PDF report | `generate_report.py` | ReportLab branded report builder |
| App settings | `luxscale/app_settings.py` | Runtime settings, ceiling bounds, UI config |
| Logging | `luxscale/app_logging.py` | Structured `log_step`, exception logging |
| Calculation trace | `luxscale/calculation_trace.py` | Per-request debug trace files |

---

## Related

- AI pipeline: [`../ai/README.md`](../ai/README.md)
- Front-end: [`../front-end/README.md`](../front-end/README.md)
- Lighting tool behaviour: [`../lighting/README.md`](../lighting/README.md)
- Math formulas: [`../math/README.md`](../math/README.md)
- Parent index: [`../README.md`](../README.md)
