# Prompt Engineering

> **Module:** `luxscale/ai_prompt.py`  
> **Used by:** `gemini_manager.py` and `ollama_manager.py` (identical format)

---

## 1. Design Constraints

The prompt must satisfy competing constraints across all AI sources:

| Constraint | Reason |
|-----------|--------|
| Short input tokens | Free-tier Gemini has low RPM; smaller prompts = faster calls |
| Short output tokens | Free-tier Gemini `gemini-3.1-flash-lite-preview` caps at 512 tokens |
| JSON-only response | Eliminates prose parsing, enables structured validation |
| Works with local models | Ollama models (llama, gemma) need explicit JSON instructions |
| Deterministic | `temperature: 0.1` reduces hallucination in numeric fields |

---

## 2. Prompt Format

The prompt is built by `build_ai_prompt(payload)` in `luxscale/ai_prompt.py`:

```
Lighting audit. Reply JSON only, no extra text.
Space:{place} Sides:{sides} H:{height}m
Required Em:{Em_r_lx}lx Uo:{Uo}
Got Em:{avg_lux}lx({OK|LOW}) U0:{u0}({OK|LOW}) Fixtures:{count}
Return this JSON with short strings max 60 chars each:
{"confidence":0.9,"quality_score":70,"issues":[{"severity":"high","field":"Em","description":"short reason","suggested_fix":"short fix"}],"suggestions":["tip1","tip2"],"summary":"one sentence."}
```

### Example filled prompt

```
Lighting audit. Reply JSON only, no extra text.
Space:Office Sides:[10, 8, 10, 8] H:3.2m
Required Em:500lx Uo:0.6
Got Em:487.3lx(LOW) U0:0.542(LOW) Fixtures:24
Return this JSON with short strings max 60 chars each:
{"confidence":0.9,"quality_score":70,"issues":[{"severity":"high","field":"Em","description":"short reason","suggested_fix":"short fix"}],"suggestions":["tip1","tip2"],"summary":"one sentence."}
```

---

## 3. Field Extraction from Payload

The prompt extracts from `payload["results"][0]` (first result row):

| Prompt field | Source key (priority order) |
|-------------|---------------------------|
| `avg_lux` | `Average Lux` → `E_avg_grid_lx` |
| `u0` | `U0_calculated` → `Uniformity` |
| `fixtures` | `Fixtures` |
| `compliance_lux` | `Standard margin (lux %)` |
| `compliance_u0` | `Standard margin (U0 %)` |
| `Em_r_lx` | `standard_lighting.Em_r_lx` → `Em_u_lx` |
| `Uo` | `standard_lighting.Uo` |
| `place` | `payload.place` → `standard_task_or_activity` |

### OK/LOW status logic

```python
def _status_ok(value) -> str:
    # "OK" if numeric and >= 0 (margin is positive = passing)
    # "LOW" if negative or non-numeric (failing compliance)
```

This converts the raw margin percentage into a simple signal the AI can interpret without arithmetic.

---

## 4. Expected Response Schema

```json
{
  "confidence": 0.9,
  "quality_score": 70,
  "issues": [
    {
      "severity": "high | medium | low",
      "field": "field name (max 60 chars)",
      "description": "what is wrong (max 60 chars)",
      "suggested_fix": "how to fix it (max 60 chars)"
    }
  ],
  "suggestions": ["tip1 (max 60 chars)", "tip2"],
  "summary": "one complete sentence"
}
```

### Field constraints

| Field | Type | Range | Notes |
|-------|------|-------|-------|
| `confidence` | float | 0.0–1.0 | Reject if < `min_confidence` (default 0.6) |
| `quality_score` | int | 0–100 | 0 = completely failing, 100 = perfect |
| `issues[].severity` | string | `high`, `medium`, `low` | Used for colour coding in UI |
| All string fields | string | max 60 chars | Enforced by prompt instruction |

---

## 5. Response Parsing — Three-Attempt Strategy

`gemini_manager._parse_and_validate()` handles imperfect model output:

```
Attempt 1: Strip ``` json fences, strip trailing ```
Attempt 2: If no leading {, regex-extract first {...} block
Attempt 3: Find outermost { and } by index, parse that slice
```

After successful parse:
- Missing `issues` → default `[]`
- Missing `suggestions` → default `[]`
- Missing `summary` → default `""`
- Missing `quality_score` → default `50`
- Missing `confidence` → default `0.8` (model responded, assume trustworthy)

---

## 6. Why a Shared Prompt Module?

Before `ai_prompt.py` was extracted, `gemini_manager.py` had its own `_build_prompt()`. When `ollama_manager.py` was added, it needed the same prompt. The shared module guarantees:

- **Identical prompt format** for both AI sources
- **Identical response schema** — `_parse_and_validate()` works on both
- **Single place to improve** — any prompt improvement benefits all sources
- **Testable in isolation** — `build_ai_prompt()` has no Flask dependencies

---

## 7. Prompt Improvement Guidelines

When iterating on the prompt:

1. Keep total prompt under ~150 tokens (current ~120 tokens)
2. Always include the JSON example in the prompt — models copy the structure
3. The `max 60 chars each` instruction prevents token runaway in strings
4. `Reply JSON only, no extra text` prevents prose preambles from breaking parsing
5. Test with both Gemini and Ollama models before merging changes
6. Run against a real study payload with both LOW and OK fields to test issue detection

---

Next: [06-snapshot-system.md](./06-snapshot-system.md)
