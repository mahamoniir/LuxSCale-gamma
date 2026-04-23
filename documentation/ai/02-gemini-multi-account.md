# Gemini Multi-Account Manager

> **Module:** `luxscale/gemini_manager.py`  
> **Config:** `gemini_config.json` (project root, gitignored)

---

## 1. Design Goal

The Gemini integration supports **multiple accounts** with automatic daily quota tracking. This allows the system to:

- Run on **free-tier Gemini accounts** without hitting daily limits
- Seamlessly switch to a **paid account** in production without code changes
- Degrade gracefully when all accounts are exhausted — falling back to Ollama or snapshot

All configuration is in `gemini_config.json`. No code changes are needed to add accounts, change the model, or switch priority.

---

## 2. `gemini_config.json` Reference

```json
{
  "accounts": [
    {
      "name": "account_1_free",
      "api_key": "AIzaSy...",
      "daily_limit": 40,
      "used_today": 3,
      "reset_date": "2026-04-15",
      "enabled": true
    },
    {
      "name": "account_2_paid",
      "api_key": "",
      "daily_limit": 800,
      "used_today": 0,
      "reset_date": "",
      "enabled": false
    },
    {
      "name": "account_3_backup",
      "api_key": "",
      "daily_limit": 40,
      "used_today": 0,
      "reset_date": "",
      "enabled": false
    }
  ],
  "model": "gemini-3.1-flash-lite-preview",
  "ollama_priority": false,
  "min_confidence": 0.6,
  "timeout_seconds": 15
}
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable account identifier |
| `api_key` | string | Google AI Studio API key (starts with `AIzaSy`) |
| `daily_limit` | int | Max requests per calendar day — set conservatively |
| `used_today` | int | **Auto-managed** — incremented after each successful call |
| `reset_date` | string | **Auto-managed** — YYYY-MM-DD, resets `used_today` to 0 on new day |
| `enabled` | bool | `false` = skip this account entirely |
| `model` | string | Gemini model name — applies to all accounts |
| `ollama_priority` | bool | `true` = try Ollama before Gemini |
| `min_confidence` | float | Reject results below this confidence (0.0–1.0) |
| `timeout_seconds` | int | HTTP timeout for Gemini API calls |

> **Never manually edit `used_today` or `reset_date`** — these are managed automatically.

---

## 3. Quota Tracking

### Auto-reset logic

On every request, `_reset_if_new_day(account)` checks:

```python
if account["reset_date"] != today_iso:
    account["used_today"] = 0
    account["reset_date"] = today_iso
```

This means the counter resets at **midnight local server time** (or UTC, depending on server timezone).

### Account eligibility check

An account is used only when:
1. `enabled: true`
2. `api_key` is non-empty
3. `used_today < daily_limit`

### Conservative limits

| Account type | Actual API limit | Recommended `daily_limit` |
|-------------|-----------------|--------------------------|
| Free tier | 50 req/day | 40 (20% buffer) |
| Paid (standard) | 1000 req/day | 800 (20% buffer) |

---

## 4. Gemini API Call

The implementation uses **pure `urllib`** — no Gemini SDK required. This means zero extra dependencies and works in any Python 3.x environment.

```python
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
body = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "temperature": 0.1,
        "maxOutputTokens": 512
    }
}
```

### HTTP error handling

| HTTP code | Action |
|-----------|--------|
| 200 | Parse response, validate JSON |
| 429 | Rate limited — skip to next account (`_SKIP_KEY` sentinel) |
| 400 | Bad request / invalid key — skip to next account |
| 401/403 | Auth failure / revoked key — skip to next account |
| Other | Log and skip (network error) |

---

## 5. Supported Models

| Model | RPD (free) | Output quality | Recommended for |
|-------|-----------|---------------|----------------|
| `gemini-3.1-flash-lite-preview` | 500 | High | Default — full JSON response |
| `gemini-2.5-flash` | 20 | High | Premium quality — limited free quota |
| `gemini-2.0-flash` | 500 | Good | Alternative to 3.1-flash-lite |

> **Current default:** `gemini-3.1-flash-lite-preview` — best balance of quality and free quota.

---

## 6. Runtime Account Management

Admin can update an account key **without restarting Flask**:

```http
PUT /api/ai/account
X-Admin-Token: <admin_token>

{
  "name": "account_2_paid",
  "api_key": "AIzaSy_your_new_key",
  "enabled": true
}
```

This is handled by `gemini_manager.update_account_key()` which writes the new key to `gemini_config.json` and resets the usage counter.

---

Next: [03-ollama-local-model.md](./03-ollama-local-model.md)
