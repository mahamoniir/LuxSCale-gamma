# Ollama Local Model Integration

> **Module:** `luxscale/ollama_manager.py`  
> **Config:** Environment variables (`.env` or system)  
> **Brand:** Short Circuit · `#eb1b26` accent

---

## 1. Why Ollama?

Ollama provides a **free, unlimited, local** AI analysis option. When running on a machine with a capable GPU (or even CPU for smaller models), Ollama eliminates Gemini API quota concerns entirely during development and can serve as the primary AI source in production setups where data privacy is critical.

Key advantages:
- Zero API cost — no usage limits
- All data stays on your server — no PII ever leaves
- Works offline / air-gapped deployments
- Same prompt format as Gemini — zero code changes needed

---

## 2. Environment Variables

Set these in `.env` or as system environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_ENABLED` | `false` | Set to `true` to activate Ollama integration |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server base URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model name (must be pulled first) |

### Example `.env` entries

```dotenv
OLLAMA_ENABLED=true
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:27b
```

---

## 3. Availability Check

Before every analysis request, `ollama_manager.is_available()` verifies:

1. `OLLAMA_ENABLED=true` in environment
2. Server responds at `OLLAMA_URL/api/tags` (GET, 2s timeout)

The result is **cached for the lifetime of the process** — no repeated network calls on every request. Cache clears automatically when `update_config()` is called.

```python
# Internal flow
if not cfg["enabled"]:      → False (log: disabled)
if not cfg["url"]:          → False (log: no URL)
if not cfg["model"]:        → False (log: no model)
if not server_reachable():  → False (log: unreachable)
→ True, cache result
```

---

## 4. API Call Format

Ollama's `/api/generate` endpoint is called with `stream: false` to get a single complete response:

```json
{
  "model": "gemma3:27b",
  "prompt": "<lighting audit prompt>",
  "stream": false,
  "options": {
    "temperature": 0.1,
    "num_predict": 512
  }
}
```

- `temperature: 0.1` — keeps responses deterministic and structured
- `num_predict: 512` — matches Gemini's `maxOutputTokens: 512`
- `stream: false` — entire response arrives in one HTTP response body
- **Timeout: 30 seconds** — longer than Gemini (15s) because local GPU inference is slower

---

## 5. Recommended Models

| Model | Size | Quality | Speed (GPU) | Recommended use |
|-------|------|---------|-------------|----------------|
| `llama3.2:3b` | 2 GB | Medium | ~3s | Fast dev/test machine |
| `llama3.2:8b` | 5 GB | Good | ~6s | Balanced production |
| `gemma3:27b` | 17 GB | High | ~12s | Best local quality |
| `mistral:7b` | 4 GB | Good | ~5s | Alternative to llama 8b |

### Pulling a model

```bash
ollama pull gemma3:27b
```

Then set `OLLAMA_MODEL=gemma3:27b` in `.env`.

---

## 6. Response Validation

Ollama's raw response is passed through the **same validation pipeline** as Gemini responses — `gemini_manager._parse_and_validate()`:

1. Strip markdown code fences (` ```json `)
2. Extract first `{...}` block if response has prose prefix
3. JSON parse with three fallback attempts
4. Check `confidence >= min_confidence` (default 0.6)
5. Auto-fill missing fields with safe defaults

If validation fails, the waterfall moves to the next source. This ensures Ollama failures are handled identically to Gemini failures.

---

## 7. Setting Ollama as Primary

In `gemini_config.json`:

```json
{
  "ollama_priority": true
}
```

With this setting, every analysis request tries Ollama **before** Gemini accounts. This is recommended when:
- You have a local GPU and `gemma3:27b` or similar installed
- You want to preserve Gemini free-tier quota
- You are in a privacy-sensitive deployment

---

## 8. Admin Diagnostics

Query Ollama status from the admin dashboard via `GET /api/ai/status`:

```json
{
  "accounts": [...],
  "ollama": {
    "enabled": true,
    "url": "http://localhost:11434",
    "model": "gemma3:27b",
    "available": true
  }
}
```

`get_available_models()` fetches the full list of pulled models from `/api/tags` — useful for confirming the desired model is installed.

---

Next: [04-waterfall-logic.md](./04-waterfall-logic.md)
