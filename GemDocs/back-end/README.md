# Back-End Architecture - GemDocs

The LuxScaleAI backend is a Python-based Flask application that bridges architectural lighting requirements with engineering calculations.

## 🏗️ Core Architecture

- **Web Server (`app.py`)**: Handles HTTP requests, CORS, and routing.
- **Engine (`luxscale/lighting_calc/`)**: The mathematical core that computes fixture counts and layouts.
- **Photometry (`ies-render/`)**: Specialized module for parsing IES files and calculating grid-based uniformity.
- **Data Layers**:
  - `standards/`: JSON files containing EN 12464-1 compliance targets.
  - `assets/`: Fixture catalogs and IES mapping definitions.

## 🛣️ API Endpoints

### `POST /calculate`
The primary entry point for design studies.
- **Input**: Room dimensions (`sides`, `height`) and requirement (`place` or `standard_ref_no`).
- **Output**: An array of `results`, each containing fixture counts, spacing, lux, and uniformity.

### `POST /api/ai/analyze`
Triggers the AI quality analysis pipeline for a specific calculation result.

### `POST /pdf`
Generates a professional engineering report in PDF format based on the calculation data.

## ⚙️ Calculation Workflow

1.  **Geometry Analysis**: Room area is calculated using the cyclic quadrilateral formula (Brahmagupta).
2.  **Constraint Resolution**: Target lux and uniformity are retrieved from the standards database.
3.  **Fixture Search**: The engine iterates through available luminaires, matching power and beam angle to the room's height.
4.  **Spacing Optimization**: A grid search finds the best X/Y layout that fits within spacing constraints.
5.  **Uniformity Evaluation**: If an IES file is mapped, a point-by-point grid calculation determines the actual U₀.

---
*See [Calculation Engine](./calculation-engine.md) for deeper algorithmic details.*
