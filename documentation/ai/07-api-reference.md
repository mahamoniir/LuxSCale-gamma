# AI API Reference

> **Blueprint:** `luxscale/ai_routes.py` — registered as `ai_bp`  
> **Auth:** Admin routes require `X-Admin-Token` header or active session cookie

---

## Endpoint Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/ai/analyze` | Public | Analyze a study with AI |
| POST | `/api/ai/approve-fix` | Public | Save analysis as fallback snapshot |
| GET | `/api/ai/status` | Admin | Quota status + snapshot info |
| PUT | `/api/ai/account` | Admin | Update account key at runtime |
| GET | `/api/ai/snapshots` | Admin | List snapshot history |
| GET | `/api/ai/snapshots/<filename>` | Admin | Load a specific snapshot |
| POST | `/api/ai/snapshots/restore` | Admin | Restore a snapshot as active fallback |

---

## POST `/api/ai/analyze`

Analyze a lighting study result with AI. The waterfall (Ollama → Gemini → Snapshot → Default) runs automatically.

### Request — by token

```json
{ "token": "bca62ed6b65842ca4efd0e2f527d1246" }
```

### Request — inline payload

```json
{
  "sides": [10, 8, 10, 8],
  "height": 3.2,
  "place": "Office",
  "standard_lighting": { "Em_r_lx": 500, "Uo": 0.6 },
  "results": [
    {
      "Average Lux": 487.3,
      "U0_calculated": 0.542,
      "Fixtures": 24,
      "Standard margin (lux %)": -2.54,
      "Standard margin (U0 %)": -9.67
    }
  ]
}
```

### Response — success

```json
{
  "status": "success",
  "source": "gemini:account_1_free",
  "confidence": 0.9,
  "quality_score": 65,
  "issues": [
    {
      "severity": "high",
      "field": "Average Illuminance (Em)",
      "description": "Calculated lux is 2.6% below required 500 lux",
      "suggested_fix": "Increase fixture count to 26 or use higher efficacy"
    }
  ],
  "suggestions": [
    "Consider SC triproof for better uniformity",
    "Increase mounting height if ceiling allows"
  ],
  "summary": "Design narrowly misses lux and uniformity targets."
}
```

### Response — snapshot fallback

```json
{
  "status": "success",
  "source": "snapshot",
  "snapshot_saved_at": "2026-04-15T02:26:18Z",
  "confidence": 0.88,
  "quality_score": 72,
  "issues": [...],
  "suggestions": [...],
  "summary": "..."
}
```

### Response — error

```json
{ "status": "error", "message": "Payload has no results to analyze" }
```

---

## POST `/api/ai/approve-fix`

Save the current analysis as the fallback snapshot. Called when the user clicks "Approve & Save as Baseline" in the result UI.

### Request

```json
{
  "analysis": {
    "source": "gemini:account_1_free",
    "confidence": 0.9,
    "quality_score": 65,
    "issues": [...],
    "suggestions": [...],
    "summary": "..."
  },
  "fix_index": 0,
  "token": "bca62ed6b65842ca4efd0e2f527d1246"
}
```

`fix_index` and `token` are optional — used only for logging.

### Response

```json
{
  "status": "success",
  "message": "Fix approved and snapshot saved",
  "snapshot_updated": true,
  "snapshot": {
    "filename": "snap_20260415T022618Z.json",
    "saved_at": "2026-04-15T02:26:18Z",
    "label": "approved",
    "quality_score": 65,
    "total_snapshots": 47
  }
}
```

---

## GET `/api/ai/status` *(admin)*

Returns quota status for all configured accounts, plus snapshot information.

### Response

```json
{
  "status": "success",
  "accounts": [
    {
      "name": "account_1_free",
      "enabled": true,
      "has_key": true,
      "used_today": 3,
      "daily_limit": 40,
      "remaining": 37,
      "reset_date": "2026-04-15"
    },
    {
      "name": "account_2_paid",
      "enabled": false,
      "has_key": false,
      "used_today": 0,
      "daily_limit": 800,
      "remaining": 800,
      "reset_date": ""
    }
  ],
  "has_snapshot": true,
  "snapshot_saved_at": "2026-04-15T02:26:18Z",
  "total_snapshots": 47,
  "latest_snapshot": {
    "filename": "snap_20260415T022618Z.json",
    "saved_at": "2026-04-15T02:26:18Z",
    "label": "auto",
    "source": "gemini:account_1_free",
    "quality_score": 72,
    "confidence": 0.88
  }
}
```

---

## PUT `/api/ai/account` *(admin)*

Update an account API key at runtime — no Flask restart needed.

### Request

```json
{
  "name": "account_2_paid",
  "api_key": "AIzaSy_your_new_paid_key",
  "enabled": true
}
```

### Response

```json
{
  "status": "success",
  "message": "Account 'account_2_paid' updated",
  "enabled": true
}
```

---

## GET `/api/ai/snapshots` *(admin)*

List snapshot history (newest first).

### Query parameters

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Return only N most recent (default: all) |
| `label` | string | Filter by label: `auto`, `approved`, `restored` |

### Response

```json
{
  "status": "success",
  "total": 47,
  "snapshots": [
    {
      "filename": "snap_20260415T022618Z.json",
      "saved_at": "2026-04-15T02:26:18Z",
      "label": "auto",
      "source": "gemini:account_1_free",
      "quality_score": 72,
      "confidence": 0.88
    },
    ...
  ]
}
```

---

## GET `/api/ai/snapshots/<filename>` *(admin)*

Load a specific snapshot by filename. Filename must match `snap_YYYYMMDDTHHMMSSZ.json`.

### Response

```json
{
  "status": "success",
  "snapshot": {
    "saved_at": "2026-04-15T02:26:18Z",
    "label": "auto",
    "source": "gemini:account_1_free",
    "quality_score": 72,
    "confidence": 0.88,
    "analysis": { ... full analysis dict ... }
  }
}
```

---

## POST `/api/ai/snapshots/restore` *(admin)*

Restore an older snapshot as the active fallback.

### Request

```json
{ "filename": "snap_20260408T143732Z.json" }
```

### Response

```json
{
  "status": "success",
  "message": "Snapshot 'snap_20260408T143732Z.json' restored as active fallback",
  "original_saved_at": "2026-04-08T14:37:32Z",
  "original_source": "gemini:account_1_free"
}
```

---

Next: [08-key-improvements.md](./08-key-improvements.md)
