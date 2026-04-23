# IES Render Module - Gemini CLI Guidelines

This module handles photometric IES parsing, data structuring, and thumbnail rendering.

## 🛠️ Specialized Mandates for `ies-render/`

1.  **IES Standard Compliance:** Ensure all parsing logic in `module/` adheres to the IESNA LM-63 standard.
2.  **Performance:** Photometric grids can be large. Use vectorized operations (NumPy) where possible for calculations.
3.  **Cross-Platform UI:** The viewer uses `QtPy` for compatibility across PySide and PyQt. Maintain this abstraction; do not import `PySide2` or `PyQt5` directly.
4.  **Database Integrity:** `SC-Database/` contains the canonical IES files used by the main application. Do not modify these files directly without a backup. Use `rebuild_database_from_sc_fixed.bat` if the JSON index (`ies.json`) needs updating.

## 🧪 Verification
- Run tests in `tests/` after modifying parsing logic.
- Use `run.py` to verify that rendering still works for a variety of IES types (Downlight, Highbay, Streetlight).
