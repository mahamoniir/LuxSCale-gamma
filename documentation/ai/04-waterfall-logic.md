# AI Waterfall Logic

> **Module:** `luxscale/gemini_manager.analyze_lighting_result()`  
> **Controlled by:** `gemini_config.json` → `ollama_priority`

---

## 1. Two Priority Modes

The waterfall order is controlled by a single flag in `gemini_config.json`:

### `ollama_priority: false` (default — Gemini first)

```
Request
  └─ Gemini account_1_free  → success? return  (source: gemini:account_1_free)
  └─ Gemini account_2_paid  → success? return  (source: gemini:account_2_paid)
  └─ Gemini account_3_backup→ success? return  (source: gemini:account_3_backup)
  └─ Ollama local           → success? return  (source: ollama:local)
  └─ Snapshot               → exists?  return  (source: snapshot)
  └─ Default                → always         (source: default)
```

**Recommended when:** paid Gemini account is configured, or highest quality responses are required.

### `ollama_priority: true` (Ollama first)

```
Request
  └─ Ollama local           → success? return  (source: ollama:local)
  └─ Gemini account_1_free  → success? return  (source: gemini:account_1_free)
  └─ Gemini account_2_paid  → success? return  (source: gemini:account_2_paid)
  └─ Gemini account_3_backup→ success? return  (source: gemini:account_3_backup)
  └─ Snapshot               → exists?  return  (source: snapshot)
  └─ Default                → always         (source: default)
```

**Recommended when:** local GPU is available, Gemini quota should be preserved.

---

## 2. Full Decision Tree

```
analyze_lighting_result(payload)
│
├─ Build prompt via ai_prompt.build_ai_prompt(payload)
│
├─ Load gemini_config.json
│
├─ ollama_priority = true?
│   ├─ YES → _try_ollama()
│   │         ├─ OLLAMA_ENABLED != "true"  → None (skip)
│   │         ├─ server unreachable        → None (skip)
│   │         ├─ HTTP error               → None (skip)
│   │         ├─ timeout (30s)            → None (skip)
│   │         ├─ validation fails         → None (skip)
│   │         └─ valid JSON + confidence ≥ min → return result
│   └─ NO → skip Ollama, go to Gemini
│
├─ _try_gemini_accounts()
│   └─ for each account in cfg["accounts"]:
│       ├─ not enabled?             → skip (log)
│       ├─ no api_key?              → skip (log)
│       ├─ used_today ≥ daily_limit → skip (log quota)
│       ├─ auto-reset if new day    → reset used_today
│       │
│       └─ _call_gemini_api(key, model, prompt, timeout)
│           ├─ HTTP 429 → _SKIP_KEY → next account
│           ├─ HTTP 400/401/403 → _SKIP_KEY → next account
│           ├─ network error → None → next account
│           ├─ parse/validation fail → None → next account
│           └─ success → increment used_today → return result
│
├─ [if ollama_priority = false] _try_ollama() as backup
│
├─ All AI sources exhausted
│   └─ _load_snapshot()
│       ├─ gemini_snapshot.json exists and has "analysis" dict → return snapshot result
│       └─ no snapshot → fall through
│
└─ Return safe default
    {
      "source": "default",
      "confidence": 0.0,
      "quality_score": 50,
      "issues": [],
      "suggestions": ["No AI analysis available yet..."],
      "summary": "AI analysis unavailable..."
    }
```

---

## 3. Skip vs None vs Fail

| Return value | Meaning | Next action |
|-------------|---------|------------|
| `_SKIP_KEY` sentinel | Rate limit or bad key | Skip this key, try next account immediately |
| `None` | Network/parse error | Log and try next account |
| `dict` with `confidence < min_confidence` | Low-quality response | Try next source |
| Valid `dict` | Success | Return immediately, stop waterfall |

---

## 4. Quota Deduction Timing

Usage is incremented **only on success** — a failed Gemini call (rate limit, parse error, low confidence) does **not** decrement the daily quota. This prevents wasting quota on bad responses.

```python
# Only after a validated successful result:
with _CONFIG_LOCK:
    cfg2 = _load_config()
    _increment_usage(cfg2, account["name"])
```

The config is reloaded (with lock) before incrementing to avoid race conditions if multiple Flask threads are running.

---

## 5. Auto-Save After Success

After every successful AI result (from any source), `_auto_save_snapshot()` is called automatically:

```python
if confidence >= 0.75 and quality_score is not None:
    save_snapshot(result, label="auto")
```

This means `gemini_snapshot.json` is kept current even without explicit user approval — the latest valid response is always available as fallback.

---

## 6. Switching Priority at Runtime

Edit `gemini_config.json` directly — the change takes effect on the **next analysis request** (no restart needed):

```json
{
  "ollama_priority": true
}
```

Or via admin API:

```http
PUT /api/ai/account
X-Admin-Token: <token>
{ "name": "account_1_free", "enabled": false }
```

---

Next: [05-prompt-engineering.md](./05-prompt-engineering.md)
