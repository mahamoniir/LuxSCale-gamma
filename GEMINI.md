# Gemini CLI Guidelines - LuxScaleAI

This document provides foundational mandates and expert guidance for Gemini CLI (and other AI agents) when working in the LuxScaleAI repository.

## 🏗️ Technical Architecture & Stack

LuxScaleAI is a hybrid lighting design platform combining traditional engineering heuristics with IES-backed photometric analysis and an AI-driven quality pipeline.

- **Backend:** Flask (Python 3.12+) serving calculation results and AI analysis.
- **Frontend:** Modern HTML/CSS/JS (`index2.html`, `result.html`) with legacy Tkinter GUI paths.
- **Calculation Engine:** 
  - `luxscale/lighting_calc/`: Core logic (geometry, spacing, lumen method).
  - `ies-render/`: Photometric IES parsing and grid-based uniformity (U₀) calculation.
- **AI Pipeline:** Waterfall orchestrator (`luxscale/gemini_manager.py`) using Gemini API and/or local Ollama.
- **Persistence:** PHP-based token system (`api/submit.php`) for study storage/retrieval.

## ⚖️ Core Mandates

1.  **Surgical Consistency:** Adhere strictly to existing patterns. Use `CLAUDE.md` and `PYTHON_TECHNICAL_DESCRIPTION.md` as primary architectural references.
2.  **No Hacks:** Maintain structural integrity. Avoid `any` types in Python, reflection hacks, or prototype manipulation in JS. Use explicit composition and delegation.
3.  **Credential Safety:** NEVER log or commit API keys. Protect `.env`, `gemini_config.json`, and `gemini_key_tester.py`.
4.  **Validation First:** Every bug fix MUST be preceded by an empirical reproduction script. Every feature MUST include automated tests (Unit/Integration).

## 🤖 AI Pipeline & Waterfall Logic

When working on the AI analysis features (`luxscale/ai_*.py`, `luxscale/gemini_manager.py`):
- **Waterfall Priority:** Ollama (if enabled) → Gemini Account Pool → Snapshot Fallback → Default JSON.
- **Multi-Account:** Handle quota management and rate limiting across multiple Gemini keys gracefully.
- **Prompting:** Use `luxscale/ai_prompt.py` for all LLM sources to ensure format consistency.

## 🛠️ Coding Standards & Workflows

### Python
- **Explicit over Implicit:** Prefer clear, typed functions over broad dictionaries where possible.
- **Error Handling:** Avoid generic `except Exception`. Use specific error types and provide actionable feedback in API responses.
- **Constants:** Externalize hardcoded values (lux targets, efficacy) to JSON files in `standards/` or `assets/`.
- **Maintenance Risk:** Be aware of `maha/` directory; it contains duplicate logic. Prioritize fixes in root/`luxscale/` and sync if required.

### IES & Photometry
- Use the `ies-render` module for all photometric grid calculations.
- Maintain compatibility with `IESData` namedtuple and `IES_Thumbnail_Generator`.

### Testing & Verification
- Use `pytest` for Python logic (add tests to `luxscale/tests/` if missing).
- Validate calculations against known IES files (`ies-render/SC-Database/`).
- Use `curl` or `Postman` to smoke test `/calculate` and `/api/ai/analyze` after changes.

## 📂 Key Documentation

- `CLAUDE.md`: High-level architecture and quick-start.
- `PYTHON_TECHNICAL_DESCRIPTION.md`: Detailed algorithm and refactor roadmap.
- `documentation/ai/`: AI pipeline deep-dive.
- `uniformity/`: Explanations for lux and uniformity calculations.

---
*Follow these instructions to maintain the technical integrity and long-term maintainability of LuxScaleAI.*
