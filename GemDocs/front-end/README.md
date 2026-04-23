# Front-End Architecture - GemDocs

LuxScaleAI's front-end is designed to be a high-performance, visual design tool for architects and engineers.

## 🎨 Design Philosophy

The user interface emphasizes **Visual Feedback**. Every room dimension or fixture choice is reflected in real-time, with interactive cards for calculation results.

## 📂 Component Map

- **Modern Pages**:
  - `index2.html`: Primary calculation interface.
  - `result.html`: Post-calculation study viewer.
- **AI Integration**:
  - `ai_panel_for_result_html.html`: Modular panel for the AI quality score and improvement suggestions.
- **Assets**:
  - `assets/standards-picker.js`: A specialized JS module for searching the EN 12464-1 standards database.
  - `assets/standard-display.js`: Handles the UI rendering of target requirements.

## 🔄 State & Data Flow

1.  **Input Phase**: User enters dimensions and room function.
2.  **API Call**: Data is sent to the Flask `/calculate` endpoint via standard `fetch`.
3.  **Normalization**: Result keys from the Python backend are mapped to readable labels (e.g., `Fixtures` -> `Count`).
4.  **Persistence**: Studies are saved to the PHP API (`api/submit.php`) to generate a unique sharing token.

## 🛠️ Key Visual Modules

- **Heatmap View**: Visual representation of the uniformity grid.
- **Fixture Cards**: Dynamic cards showing power, lux, and spacing for each option.
- **AI Score Gauge**: Interactive visual feedback for the quality analysis.

---
*See [Pages Inventory](./pages-inventory.md) for a detailed breakdown of all web routes.*
