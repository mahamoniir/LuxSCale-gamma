# AI Key Improvements — Before and After

> **Short Circuit · LuxScaleAI**  
> This document shows exactly what value the AI pipeline adds to lighting design results.

---

## 1. The Problem with Raw Output Alone

Without the AI pipeline, a user receives:

```
Average Lux: 487.3
U0_calculated: 0.5421
Standard margin (lux %): -2.54
Standard margin (U0 %): -9.65
Fixtures: 24
Spacing X: 2.5m
Spacing Y: 2.67m
```

**What a non-engineer sees:** A table of numbers with no guidance. "Is -2.54% bad? Should I be worried? What do I change?"

**What an engineer sees:** A narrowly failing result — needs ~2 more fixtures or higher efficacy lamps. But the engineer has to figure this out themselves.

---

## 2. After the AI Pipeline

The same result, processed through the AI:

```
Quality Score:  65 / 100   (Confidence: 90%)
Source: Gemini — account_1_free

ISSUES (2 found)
─────────────────────────────────────────────────
  ● HIGH   Average Illuminance (Em)
           Calculated lux is 2.6% below required 500 lux
           → Increase fixture count to 26 or use higher efficacy lamps

  ● MEDIUM Uniformity (U0)
           U0=0.54 is below required minimum of 0.60
           → Adjust fixture spacing or switch to wider-beam luminaire

SUGGESTIONS
  • Consider SC triproof for better uniformity in this room footprint
  • Review mounting height — 3.2m → 3.5m would improve beam overlap

SUMMARY
  Design narrowly misses both lux and uniformity targets. Minor adjustments
  to fixture count or type will achieve full compliance with minimal cost impact.

[  Approve & Save as Baseline  ]
```

---

## 3. Comparison Table

| Aspect | Without AI | With AI pipeline |
|--------|-----------|-----------------|
| Compliance signal | Pass/fail percentages only | Quality score 0–100 with colour coding |
| Issue identification | None — user must interpret margins | Explicit issues with severity (HIGH / MEDIUM / LOW) |
| Fix guidance | None | Specific actionable fix per issue |
| Engineering context | None | AI applies domain knowledge about space types and fixture types |
| Non-expert usability | Requires photometric knowledge | Self-explanatory for any user |
| Multi-option ranking | Side-by-side numbers only | Quality score enables direct ranking across options |
| Offline resilience | N/A — calculations always work | Snapshot fallback guarantees a response even with no connectivity |
| Improvement over time | Static — same output forever | Snapshot history captures approved baselines and patterns |

---

## 4. Scenarios Where AI Adds Most Value

### 4.1 Narrowly failing designs (highest value)

When lux or U₀ margins are −1% to −10%, the calculation engine shows "not compliant" but gives no guidance. The AI identifies the specific failing field, quantifies the gap in plain language, and suggests the minimum intervention to achieve compliance.

**Example:** "Increase fixture count from 24 to 26" — this is not in the calculation output. The AI infers it from the margin and room geometry.

### 4.2 Multiple simultaneous failures

When both lux AND uniformity fail, a user doesn't know which to fix first. The AI assigns `severity: "high"` to the worse failure and `severity: "medium"` to the secondary issue, giving a clear priority order.

### 4.3 Client-facing deliverables

The `quality_score` (0–100) and `summary` (one sentence) are directly quotable in client reports without translating photometric notation. A project team can communicate "Quality: 72/100 — minor adjustments recommended" without the client needing to understand lux or U₀.

### 4.4 Non-standard room types

For unusual spaces where the EN 12464-1 standard provides the minimum lux but no practical guidance, the AI applies broader lighting engineering knowledge (beam angle, mounting height, luminaire type) that isn't encoded in the calculation engine.

### 4.5 Batch historical review

Running `/api/ai/analyze` against all stored studies identifies which past projects had marginal compliance that may benefit from redesign — a capability that didn't exist before the pipeline.

---

## 5. Scenarios Where AI Adds Less Value

| Scenario | Reason |
|----------|--------|
| Clearly passing designs (quality ≥ 85) | AI confirms what the numbers already show clearly |
| Simple single-room, single-option result | Less ambiguity, less need for interpretation |
| API-only integrations (no end user) | Value is in the UX interpretation layer |

---

## 6. AI Reliability and Fallbacks

The pipeline is designed to **never fail silently**:

| Situation | User experience |
|-----------|----------------|
| Gemini available, quota remaining | Full AI analysis (source: gemini:...) |
| Gemini quota exhausted, Ollama running | Full AI analysis (source: ollama:local) |
| All AI unavailable, snapshot exists | Last approved analysis (source: snapshot) |
| All AI unavailable, no snapshot | Safe default with helpful message (source: default) |

The user always receives a structured response — never an error or empty panel.

---

## 7. Code Changes That Enabled These Improvements

| Feature added | Code location | Impact |
|--------------|--------------|--------|
| Multi-account waterfall | `gemini_manager.py` | Free tier quota never exhausted |
| Ollama local model | `ollama_manager.py` | Zero-cost unlimited analysis |
| Shared prompt module | `ai_prompt.py` | Consistent quality across all AI sources |
| Versioned snapshot system | `gemini_manager.py` → `snapshots/` | Full history, audit trail, rollback |
| Auto-save on high confidence | `_auto_save_snapshot()` | Snapshot stays current without user action |
| Runtime account management | `PUT /api/ai/account` | Key rotation without restart |
| Snapshot restore endpoint | `POST /api/ai/snapshots/restore` | Rollback to any past approved baseline |

---

Next: [09-future-roadmap.md](./09-future-roadmap.md)
