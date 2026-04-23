# Admin System

> **Module:** `app.py` admin routes + `luxscale/ai_routes.py`  
> **Dashboard:** `admin/dashboard.html`

---

## 1. Overview

The admin system provides protected access to:

- **App settings** — maintenance factor, max solutions, ceiling bounds, UI pagination
- **Fixture map** — IES fixture → file path mappings (editable without code changes)
- **AI account management** — Gemini API keys, quota status, Ollama status
- **Snapshot management** — list, view, restore AI analysis snapshots

---

## 2. Authentication

### Login

```http
POST /api/admin/login
Content-Type: application/json

{ "username": "luxscale", "password": "LuxScaleAdmin2026" }
```

Credentials come from environment variables:

```dotenv
LUXSCALE_ADMIN_USER=luxscale
LUXSCALE_ADMIN_PASSWORD=LuxScaleAdmin2026
```

**Always change the default password in production.**

### Response

```json
{ "status": "success", "token": "v8K2mX9..." }
```

Two auth mechanisms are set simultaneously:
- Session cookie (`session["admin"] = True`) — for same-origin browser access
- Bearer token in response — for cross-origin dashboard or API access

### Using the bearer token

```http
GET /api/admin/settings
X-Admin-Token: v8K2mX9...
```

### Token lifetime

Default: 7 days. Configure via:

```dotenv
LUXSCALE_ADMIN_TOKEN_TTL_S=604800
```

### Logout

```http
POST /api/admin/logout
X-Admin-Token: <token>
```

Clears both the session and the bearer token.

---

## 3. App Settings

### GET `/api/admin/settings`

Returns current settings (from `assets/app_settings.json`):

```json
{
  "maintenance_factor": 0.63,
  "max_solutions_total": 12,
  "interior_height_max_m": 5.0,
  "min_spacing_m": 0.8,
  "result_page_size": 5,
  "reflectance_presets": {
    "ceiling": 0.7,
    "walls": 0.5,
    "floor": 0.2
  }
}
```

### PUT `/api/admin/settings`

Update any settings field:

```http
PUT /api/admin/settings
X-Admin-Token: <token>

{ "maintenance_factor": 0.70, "max_solutions_total": 8 }
```

Changes take effect on the next calculation request — no restart needed.

---

## 4. Fixture Map

### GET `/api/admin/fixture-map`

Returns the active fixture map (`fixture_map.json` or `fixture_map_SC_IES_Fixed_v3.json` — determined by `ies_dataset_config.py`).

### PUT `/api/admin/fixture-map`

Update the fixture map. After saving, `clear_fixture_map_cache()` is called to flush the in-memory cache so the next calculation uses the new map.

```http
PUT /api/admin/fixture-map
X-Admin-Token: <token>

{ "SC triproof 36W": "path/to/SC_triproof_36W.ies", ... }
```

---

## 5. Dashboard (`admin/dashboard.html`)

The dashboard is a static HTML file served either:
- From Flask at `/admin/dashboard.html` (when both are on the same server)
- From XAMPP (different origin — requires `X-Admin-Token` bearer auth)

### Dashboard API base URL

The dashboard reads its API base URL from `/api/public-config`:

```json
{ "api_base": "http://127.0.0.1:5000" }
```

Override with:

```dotenv
LUXSCALE_DASHBOARD_API_BASE=https://your-production-domain.com
```

The value is also mirrored to `assets/dashboard_config.json` for XAMPP-hosted dashboard access.

---

## 6. Fixture Dataset Selection

`luxscale/ies_dataset_config.py` controls which fixture map and catalog files are active:

```python
def active_fixture_map_basename() -> str:
    # Returns "fixture_map_SC_IES_Fixed_v3.json" or "fixture_map.json"
    # based on IES_DATASET env var or auto-detection
```

Switch datasets without code changes:

```dotenv
IES_DATASET=SC_IES_Fixed_v3
```

---

Next: [pdf-report-generator.md](./pdf-report-generator.md)
