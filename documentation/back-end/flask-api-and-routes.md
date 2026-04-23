# Flask API and Routes

> **Module:** `app.py` (project root)  
> **Blueprints:** `luxscale/ai_routes.py` (ai_bp) · `luxscale/ies_routes.py` (ies_bp)

---

## 1. Application Setup

```python
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "luxscale-dev-change-in-production")

# Blueprints
from luxscale.ai_routes import register_ai_routes
register_ai_routes(app)           # mounts /api/ai/* routes

from luxscale.ies_routes import ies_bp
app.register_blueprint(ies_bp)    # mounts /ies/* routes
```

### CORS configuration

Origins are configured from `LUXSCALE_CORS_ORIGINS` env var (comma-separated). Default allows:

```
http://localhost, http://127.0.0.1, http://localhost:5000, http://127.0.0.1:5000
http://localhost:80, http://127.0.0.1:80
```

---

## 2. Route Index

### Core calculation routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/calculate` | Public | Main lighting calculation |
| POST | `/pdf` | Public | Legacy simple PDF (FPDF — not branded) |
| GET | `/` | Public | API health check |
| GET | `/places` | Public | Available room types + standard categories |

### Study storage routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/submit` | Public | Store study JSON, returns `{token}` |
| GET | `/api/get?token=…` | Public | Load study by token |

### Report routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/report/<token>/full` | Public | Full branded PDF (all solutions) |
| GET | `/api/report/<token>/solution/<int>` | Public | Single-solution branded PDF |

### Admin routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/admin/login` | — | Returns session cookie + bearer token |
| POST | `/api/admin/logout` | Admin | Revokes bearer token + session |
| GET/PUT | `/api/admin/settings` | Admin | App settings (maintenance factor, max solutions) |
| GET/PUT | `/api/admin/fixture-map` | Admin | Edit `fixture_map.json` |

### Standards routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/standards/resolve` | Public | Resolve a `ref_no` to its full standards row |

### UI / config routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/ui-settings` | Public | Pagination defaults for result UI |
| GET | `/api/public-config` | Public | Dashboard API base URL |

### Static serving routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/assets/<path>` | Serve `assets/` directory |
| GET | `/admin/dashboard.html` | Serve admin dashboard HTML |

### AI routes (Blueprint — `ai_bp`)

See [`../ai/07-api-reference.md`](../ai/07-api-reference.md) for full details.

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/ai/analyze` | Public |
| POST | `/api/ai/approve-fix` | Public |
| GET | `/api/ai/status` | Admin |
| PUT | `/api/ai/account` | Admin |
| GET | `/api/ai/snapshots` | Admin |
| GET | `/api/ai/snapshots/<filename>` | Admin |
| POST | `/api/ai/snapshots/restore` | Admin |

### IES routes (Blueprint — `ies_bp`, prefix `/ies`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ies/upload` | Upload IES file, parse, return session_id |
| GET | `/ies/polar/<session_id>` | Polar plot image (base64 PNG) |
| GET | `/ies/surface/<session_id>` | 3D surface plot (base64 PNG) |
| GET | `/ies/metrics/<session_id>` | Parsed metrics JSON |

---

## 3. `POST /calculate` — Detailed

### Request body

```json
{
  "sides": [10, 8, 10, 8],
  "height": 3.2,
  "place": "Office",
  "project_info": {
    "project_name": "Tower Block Level 5",
    "standard_ref_no": "5.2.1"
  },
  "fast": false
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `sides` | Yes | Four room side lengths (cyclic quadrilateral, metres) |
| `height` | Yes | Ceiling height (metres) |
| `place` | One of these two | Room type key (from `define_places`) |
| `standard_ref_no` | One of these two | EN 12464-1 reference number |
| `project_info` | No | Dict passed through to results |
| `fast` | No | `true` → cap at 3 options, coarser steps |

### Response body

```json
{
  "status": "success",
  "results": [...],
  "length": 10.0,
  "width": 8.0,
  "calculation_meta": {...},
  "calculation_trace_file": "calculation_logs/calculation_steps_....txt",
  "ui_settings": {...},
  "project_info": {...},
  "standard_row": {...}
}
```

---

## 4. Admin Authentication

### Two auth methods supported simultaneously

**Cookie session** (browser login):

```http
POST /api/admin/login
{ "username": "luxscale", "password": "LuxScaleAdmin2026" }
→ Sets session["admin"] = True
→ Returns { "status": "success", "token": "<bearer_token>" }
```

**Bearer token** (cross-origin dashboard / curl):

```http
GET /api/admin/settings
X-Admin-Token: <token_from_login>
```

### Token management

- Tokens stored in `_ADMIN_TOKENS` dict (in-memory)
- TTL: `LUXSCALE_ADMIN_TOKEN_TTL_S` env var (default: 7 days)
- Expired tokens auto-purged on each request
- `POST /api/admin/logout` explicitly revokes the token

### Blueprint auth pattern

The AI Blueprint (`ai_routes.py`) uses `_ai_admin_ok()` which resolves the live `_ADMIN_TOKENS` dict via `sys.modules` — this avoids a classic circular-import / double-module bug where a `from app import X` inside a Blueprint creates a second module instance with an empty token dict.

---

## 5. Standards Resolution

`_resolve_calculate_inputs(data)` tries two input modes:

1. `standard_ref_no` in `project_info` or top-level → looks up `standards_cleaned.json` → returns `standard_row`
2. `place` string → used directly with `define_places[place]`

If neither produces a valid input, the request is rejected with `400 Bad Request`.

---

Next: [calculation-engine.md](./calculation-engine.md)
