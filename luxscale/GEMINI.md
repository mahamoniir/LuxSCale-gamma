# LuxScale Core Module - Gemini CLI Guidelines

This directory contains the core business logic, IES integration, and AI orchestration for LuxScaleAI.

## 📂 Module Map

- **AI Orchestration:**
  - `gemini_manager.py`: Multi-account waterfall logic for Gemini API.
  - `ollama_manager.py`: Local model integration.
  - `ai_prompt.py`: Canonical prompt construction.
  - `ai_routes.py`: Flask endpoints for AI analysis.
- **IES & Photometry:**
  - `ies_analyzer.py`: Deep analysis of IES files.
  - `uniformity_calculator.py`: Grid-based uniformity calculations.
  - `fixture_map_builder.py`: Maps fixtures to IES files.
  - `sc_ies_scan.py`: Scans IES directories for metadata.
- **Lighting Calculation Engine:**
  - `lighting_calc/`: Directory containing the primary calculation algorithms.
- **Utilities:**
  - `app_settings.py`: Centralized configuration management.
  - `paths.py`: Project-wide path constants.

## 🛠️ Specialized Mandates for `luxscale/`

1.  **Waterfall Integrity:** When modifying `gemini_manager.py`, ensure that quota exhaustion or network failures in one account do not block the entire pipeline. Always maintain the `Ollama` fallback path.
2.  **IES Parsing Safety:** `ies_analyzer.py` and `uniformity_calculator.py` are performance-sensitive. Use `numpy` for grid operations. Avoid redundant file I/O.
3.  **Path Management:** Always use `luxscale/paths.py` to resolve file locations. Avoid hardcoded relative paths that might break when called from different root entry points (e.g., `app.py` vs legacy GUI).
4.  **Logging:** Use `luxscale/app_logging.py` for all internal logging to ensure consistency across the API and AI pipeline.

## 🧪 Verification
- Test changes to `ai_routes.py` using the mock payloads in `documentation/ai/`.
- Verify uniformity calculations against the reference values in `uniformity/`.
