# Snapshot System

> **Module:** `luxscale/gemini_manager.py` — snapshot functions  
> **Files:** `gemini_snapshot.json` · `snapshots/index.json` · `snapshots/snap_<ISO>.json`

---

## 1. Purpose

The snapshot system ensures the AI pipeline **always returns a meaningful response** — even when all AI sources (Gemini accounts + Ollama) are unavailable.

Every approved or high-confidence AI analysis is saved to disk. If a future request cannot reach any AI, the last saved analysis is returned with `source: "snapshot"`.

Old snapshots are **never deleted** — the full history is preserved for audit and restore.

---

## 2. Disk Layout

```
project root/
├── gemini_snapshot.json          ← Latest snapshot (overwritten on each save)
└── snapshots/
    ├── index.json                ← Ordered list of all snapshots (newest first, max 200)
    ├── snap_20260408T143732Z.json
    ├── snap_20260409T113428Z.json
    └── snap_20260415T022538Z.json
```

### `gemini_snapshot.json` format

```json
{
  "saved_at": "2026-04-15T02:26:18Z",
  "label": "auto",
  "source": "gemini:account_1_free",
  "quality_score": 72,
  "confidence": 0.88,
  "analysis": {
    "source": "gemini:account_1_free",
    "confidence": 0.88,
    "quality_score": 72,
    "issues": [...],
    "suggestions": [...],
    "summary": "..."
  }
}
```

### `snapshots/index.json` format

```json
[
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
```

---

## 3. Snapshot Labels

| Label | Trigger | Meaning |
|-------|---------|---------|
| `auto` | After every successful analysis with `confidence ≥ 0.75` | System auto-saved |
| `approved` | User clicks "Approve & Save as Baseline" in UI | Human-approved |
| `restored` | Admin restores an older snapshot via API | Explicit rollback |

---

## 4. Save Flow

`save_snapshot(analysis_result, label)` executes three writes atomically:

```
1. Write snapshots/snap_<timestamp>.json   ← versioned archive
2. Update snapshots/index.json             ← prepend to front, cap at 200
3. Overwrite gemini_snapshot.json          ← latest = current fallback
```

Old snapshots are never touched in steps 1–3. The index cap of 200 only trims the **index metadata** — the actual snapshot files remain.

---

## 5. Auto-Save Threshold

```python
def _auto_save_snapshot(result: dict) -> None:
    confidence = float(result.get("confidence", 0))
    quality_score = result.get("quality_score")
    if confidence >= 0.75 and quality_score is not None:
        save_snapshot(result, label="auto")
```

Only results with `confidence ≥ 0.75` are auto-saved. Lower-confidence results are still returned to the user but not persisted as snapshots.

---

## 6. Snapshot Filename Format

```
snap_YYYYMMDDTHHMMSSZ.json
```

Example: `snap_20260415T022618Z.json`

The filename pattern is validated before any file access:
```python
re.fullmatch(r"snap_\d{8}T\d{6}Z\.json", filename)
```

This prevents path traversal and ensures only valid snapshot files can be requested.

---

## 7. Restore Flow

An admin can restore any past snapshot as the current fallback:

```http
POST /api/ai/snapshots/restore
X-Admin-Token: <token>

{ "filename": "snap_20260408T143732Z.json" }
```

This:
1. Loads the specified snapshot from `snapshots/`
2. Saves it as a **new** snapshot with `label: "restored"` (preserving the original)
3. Overwrites `gemini_snapshot.json` with this content

The original snapshot file is never modified.

---

## 8. Security Notes

- Snapshot filenames are validated against strict regex — no path traversal possible
- `gemini_snapshot.json` is in `.gitignore` — may contain project-specific analysis data
- The `snapshots/` directory should also be in `.gitignore`
- Only admin-authenticated routes can list, retrieve, or restore snapshots
- `/api/ai/approve-fix` (which triggers save) is public — this is intentional: any user can save an approved analysis, not just admins

---

Next: [07-api-reference.md](./07-api-reference.md)
