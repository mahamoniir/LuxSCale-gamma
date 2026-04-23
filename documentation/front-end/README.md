# LuxScaleAI — Front-end Documentation

> **Brand:** Short Circuit · `#eb1b26` accent · Fonts: Anton + IBM Plex Sans Arabic  
> **Logo sources:** `assets/brand/logo-bg-dark.svg` / `.png` and light variants  
> **Last updated:** April 2026

---

## Document Map

| # | Document | Contents |
|---|----------|----------|
| 1 | [architecture-and-stack.md](./architecture-and-stack.md) | MPA model, tech stack, build/deploy, browser support |
| 2 | [pages-inventory.md](./pages-inventory.md) | Every HTML page: purpose, UI sections, scripts, user flows |
| 3 | [assets-and-modules.md](./assets-and-modules.md) | `assets/*` JS/CSS/JSON, `standards/`, shared patterns |
| 4 | [api-client-and-state.md](./api-client-and-state.md) | Flask/PHP endpoints, payloads, `localStorage` keys, errors |
| 5 | [threejs-and-maha.md](./threejs-and-maha.md) | Three.js usage, file map, performance, integration with calc |
| 6 | [styling-and-accessibility.md](./styling-and-accessibility.md) | CSS variables, fonts, Bootstrap, a11y checklist |
| 7 | [roadmap-react-and-phases.md](./roadmap-react-and-phases.md) | React decision, Vite, phased plan, quarterly roadmap |
| 8 | [ai-panel.md](./ai-panel.md) | AI analysis panel in result.html — UI, events, approve flow |

---

## Quick Orientation

### Primary user journeys

```
index2.html  (room function picker)   ┐
index3.html  (Egyptian code standard) ┘  → POST /calculate
                                           → POST /api/submit → token
                                           → result.html?token=…
                                                └─ AI panel → POST /api/ai/analyze
                                                └─ PDF → GET /api/report/<token>/full
```

### Page inventory summary

| File | Status | Description |
|------|--------|-------------|
| `index.html` | Legacy | Original landing page with `style.css` |
| `index2.html` | **Active** | Main calculator — room function mode |
| `index3.html` | **Active** | Main calculator — Egyptian code standards mode |
| `index4.html` | Active | Standards-picker variant (extended) |
| `result.html` | **Active** | Study results — all solutions, AI panel, PDF download |
| `openies.html` | **Active** | IES file explorer + polar/3D visualizer |
| `about.html` | Active | About page |
| `charger.html` | Active | EV charger tool (separate calculator) |
| `admin/dashboard.html` | Active | Admin panel (fixtures, AI quota, settings) |
| `ai_panel_for_result_html.html` | Dev tool | Standalone AI panel test harness |
| `results.html` | Legacy | Old results page |
| `result (old).html` | Legacy | Archived |
| `online-result.html` | Legacy | Online-only variant |

---

## Design Tokens

From `styling-and-accessibility.md`:

| CSS Variable | Value | Role |
|-------------|-------|------|
| `--accent` | `#eb1b26` | SC brand red — buttons, highlights, separator lines |
| `--bg-dark` | `#111111` | Page background (dark pages) |
| `--white` | `#ffffff` | Primary text on dark |
| `--muted` | varies | Secondary text |
| `--glass` | `rgba(255,255,255,0.10–0.12)` | Translucent card panels |
| `--fm-heading` | `"Anton", sans-serif` | All headings |
| `--fm-body` | `"IBM Plex Sans Arabic", sans-serif` | Body text (Latin + Arabic) |

---

## Related

- Back-end: [`../back-end/README.md`](../back-end/README.md)
- AI pipeline: [`../ai/README.md`](../ai/README.md)
- Lighting tool behaviour: [`../lighting/README.md`](../lighting/README.md)
- Parent index: [`../README.md`](../README.md)
