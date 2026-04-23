# AI Future Roadmap

> **Short Circuit · LuxScaleAI**  
> This document outlines the planned evolution of the AI pipeline — from the current state through fine-tuning to full AI-driven design assistance.

---

## Current State (April 2026)

The AI pipeline is fully operational with:

- Multi-source waterfall (Ollama → Gemini → Snapshot → Default)
- Versioned snapshot system with audit trail
- Public analysis endpoint + admin management endpoints
- Auto-save of high-confidence results
- Runtime account key management without restart

The AI **analyses completed calculations** — it does not yet influence the calculation process itself.

---

## Phase 1 — Training Data Collection (Now → Q3 2026)

### Objective

Accumulate a high-quality labelled dataset from real project usage.

### What gets collected automatically

Every time a user clicks "Approve & Save as Baseline":
- The **study payload** (room geometry, standard requirements, results)
- The **AI analysis** (issues, suggestions, quality_score)
- The **human approval signal** (label: "approved")

These pairs are stored in `snapshots/snap_<ISO>.json` and indexed in `snapshots/index.json`.

### Target

50–100 approved pairs covering:
- Various room types (office, classroom, corridor, industrial, etc.)
- Passing and failing designs
- Multiple fixture types from the SC catalog
- Different EN 12464-1 standard references

### Planned endpoint

```http
GET /api/ai/training-data
X-Admin-Token: <token>

→ Returns all "approved" snapshots as JSONL for export
```

---

## Phase 2 — Local Model Fine-Tuning (Q3–Q4 2026)

### Objective

Fine-tune the local Ollama model on LuxScaleAI-specific data so that Ollama quality approaches Gemini quality for this domain.

### Workflow

```
1. Export training pairs via GET /api/ai/training-data
2. Format as instruction-following pairs:
   { "instruction": "<prompt>", "output": "<approved_analysis_json>" }
3. Fine-tune llama3.2 or gemma3 using Ollama's fine-tuning interface
   (or LoRA adapter via llama.cpp / Unsloth)
4. Replace base model in OLLAMA_MODEL with fine-tuned variant
5. Run A/B comparison: base model vs fine-tuned on held-out test cases
6. Deploy if quality score improves by ≥ 10 points average
```

### Why this is architecturally straightforward

- All data stays local — no external training service needed
- The fine-tuned model speaks the same JSON format as the base model
- The rest of the pipeline (validation, snapshot, UI) is unchanged
- Rollback is trivial: change `OLLAMA_MODEL` back to the base model

---

## Phase 3 — Multi-Option Scoring (Q4 2026)

### Objective

Run AI analysis on **all result options** (not just the first), enabling AI-powered ranking across options.

### Current limitation

The prompt currently extracts only `results[0]`. Multi-option analysis would require:
- Iterating all result rows
- Building a comparative prompt: "Option 1 vs Option 2 vs Option 3"
- Returning a ranked list with per-option quality scores

### Planned schema extension

```json
{
  "ranking": [
    { "option_index": 2, "quality_score": 82, "summary": "Best compliance margin" },
    { "option_index": 0, "quality_score": 74, "summary": "Good balance of cost and compliance" },
    { "option_index": 1, "quality_score": 61, "summary": "Narrowly fails uniformity" }
  ],
  "overall_recommendation": "Option 3 (SC triproof 36W) achieves the best uniformity for this room footprint."
}
```

---

## Phase 4 — Pre-Calculation Input Assistance (2027)

### Objective

Use AI to suggest standards and room types **before** the user submits a calculation — reducing input errors and improving first-pass compliance rates.

### Planned features

1. **Smart room type detection** — user types "meeting room" in free text → AI maps to EN 12464-1 ref_no 5.2.1 (Conference rooms, 500 lux)
2. **Lux pre-check** — before calculating, AI warns if user-selected lux target is unusually high/low for the stated room type
3. **Geometry validation** — AI flags unusual aspect ratios or heights before submission

### Planned endpoint

```http
POST /api/ai/suggest-standard
{ "description": "large open plan office with computer workstations" }

→ Returns top 3 EN 12464-1 candidates with confidence scores
```

---

## Phase 5 — Report Narrative Generation (2027)

### Objective

Auto-generate the narrative sections of the SC-branded PDF report using AI.

### Planned content

- Executive summary paragraph (2–3 sentences, non-technical language)
- Per-solution commentary (why this fixture type suits this room)
- Compliance statement with specific margin values
- Recommended next steps

### Integration point

`generate_report.py` → new function `build_ai_narrative(payload)` → calls `/api/ai/analyze` internally and formats output as ReportLab `Paragraph` objects.

---

## Phase 6 — Continuous Learning Loop (2027+)

### Objective

Close the loop between AI suggestions and actual design decisions.

### Mechanism

```
User accepts AI suggestion (e.g. "increase to 26 fixtures")
  → System records: (original_payload, suggestion, accepted=True)
  → User re-runs calculation with 26 fixtures
  → New result is better (higher quality score)
  → (original, suggestion, improved_result) triple is a high-quality training example
  → Adds to fine-tuning dataset automatically
```

This enables the model to learn not just what issues exist, but which suggestions actually work in practice for the SC fixture catalog.

---

## Technology Dependency Map

| Phase | New dependencies | New infrastructure |
|-------|-----------------|-------------------|
| 1 (data collection) | None | Snapshot export endpoint |
| 2 (fine-tuning) | Unsloth or llama.cpp (optional) | GPU server with 24GB+ VRAM |
| 3 (multi-option) | None | Prompt refactor only |
| 4 (pre-calc assist) | None | New Flask endpoint |
| 5 (report narrative) | None | Integration in generate_report.py |
| 6 (continuous learning) | None | Training data pipeline |

---

## Guiding Principles

All future AI features will follow these constraints:

1. **Privacy first** — customer PII never leaves the server, never enters any AI prompt
2. **Graceful degradation** — every AI feature has a non-AI fallback path
3. **No forced dependency** — the calculation engine must remain fully functional with AI disabled
4. **Data sovereignty** — fine-tuned models run locally; no dependency on cloud AI for core functionality
5. **Short Circuit brand** — all AI-generated content is framed as SC-branded assistance, not generic AI output

---

*See also: [08-key-improvements.md](./08-key-improvements.md) for current value delivered.*
