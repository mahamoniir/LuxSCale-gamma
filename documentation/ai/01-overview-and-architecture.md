# AI Pipeline — Overview and Architecture

> **Short Circuit · LuxScaleAI**  
> Brand colours: `#eb1b26` (red accent) · `#111` (dark BG) · `#fff` (text)  
> Logo: `assets/brand/logo-bg-dark.png` (on dark) / `assets/brand/logo-bg-light.png` (on light)

---

## 1. Purpose

The AI pipeline is a **post-calculation analysis layer**. After the core photometric engine produces fixture options, the AI:

1. **Scores** the quality of each lighting design (0–100)
2. **Identifies issues** with severity levels (HIGH / MEDIUM / LOW)
3. **Suggests fixes** — specific, actionable, tied to the failing field
4. **Summarises** the result in plain language for non-engineer users

The AI does **not** replace the calculation engine. It adds an interpretation and guidance layer on top of the raw photometric numbers.

---

## 2. Position in the System

```
User submits room geometry
         │
         ▼
POST /calculate
  → calculate_lighting()          ← lumen method + IES uniformity
  → returns results[]             ← raw numbers (lux, U₀, fixtures, spacing)
         │
         ▼
POST /api/submit
  → stores study as JSON          ← api/data/studies/<token>.json
         │
         ▼
result.html loads study via GET /api/get?token=...
         │
         ▼
POST /api/ai/analyze  ← AI pipeline starts here
  → gemini_manager.analyze_lighting_result(payload)
  → waterfall: Ollama → Gemini → Snapshot → Default
  → returns quality_score, issues, suggestions, summary
         │
         ▼
result.html renders AI panel
  → score badge, severity cards, suggestion list, approve button
```

---

## 3. Component Map

```
luxscale/
├── ai_routes.py          Flask Blueprint — /api/ai/* endpoints
├── gemini_manager.py     Main orchestrator: waterfall, quota, config, snapshot
├── ollama_manager.py     Local Ollama model interface (free, unlimited)
└── ai_prompt.py          Shared prompt builder (same format for all AI sources)

project root/
├── gemini_config.json    Live config: accounts, API keys, model, priority, quota
├── gemini_snapshot.json  Latest approved analysis (fallback when all AI fails)
└── snapshots/
    ├── index.json        Ordered snapshot history (newest first, max 200)
    └── snap_<ISO>.json   Individual versioned snapshot files (never deleted)
```

---

## 4. What the AI Receives

The AI receives a **study payload** — the same JSON stored in `api/data/studies/<token>.json`. Crucially:

- Room dimensions (`sides`, `height`)
- Standard requirements (`Em_r_lx`, `Uo`) from `standard_lighting`
- Calculated results (`results[]`) — first row used for the prompt
- Space type (`place` or `standard_task_or_activity`)

**What is explicitly excluded from the prompt:**
- Customer name, phone, email, company — privacy is protected by design
- Full grid uniformity data — too large for free-tier token budgets
- All result rows beyond the first — prompt stays small

---

## 5. What the AI Returns

```json
{
  "source": "gemini:account_1_free",
  "confidence": 0.9,
  "quality_score": 65,
  "issues": [
    {
      "severity": "high",
      "field": "Average Illuminance (Em)",
      "description": "Calculated lux is 2.6% below required 500 lux",
      "suggested_fix": "Increase fixture count to 26 or use higher efficacy"
    },
    {
      "severity": "medium",
      "field": "Uniformity (U0)",
      "description": "U0=0.54 is below required 0.6",
      "suggested_fix": "Adjust spacing or use wider beam angle fixtures"
    }
  ],
  "suggestions": [
    "Consider SC triproof for better uniformity in this room size",
    "Increase mounting height if ceiling allows"
  ],
  "summary": "Design narrowly misses both lux and uniformity targets. Minor adjustments will achieve compliance."
}
```

---

## 6. Source Labels

| `source` value | Meaning |
|---------------|---------|
| `ollama:local` | Answered by local Ollama model |
| `gemini:account_1_free` | Answered by Gemini, first free account |
| `gemini:account_2_paid` | Answered by Gemini, paid account |
| `snapshot` | All AI sources failed — returning last approved analysis |
| `default` | No AI and no snapshot — safe empty default |

---

## 7. Security Design

- API keys live only in `gemini_config.json` — gitignored, never in code
- Customer PII (name, phone, email) is never included in AI prompts
- `/api/ai/status` and `/api/ai/account` require admin auth (`_ai_admin_ok()`)
- `/api/ai/analyze` is public — it returns analysis only, never exposes keys
- Study tokens are validated against `[a-f0-9]{32}` before any file access
- Snapshot files use timestamp-only filenames — no project data in filename

---

Next: [02-gemini-multi-account.md](./02-gemini-multi-account.md)
