# Pages Inventory & UI Flow

This inventory lists all critical web interfaces in LuxScaleAI and their primary responsibilities.

## 📊 Core Calculation Workflow

### `index2.html` (The "Calculator")
- **Purpose**: Main workspace for designers.
- **Features**: Integrated standards search, real-time geometry input, and result card generation.
- **Client Logic**: Handles complex JSON transformations to ensure cross-platform compatibility.

### `result.html` (The "Study Viewer")
- **Purpose**: A public-facing view for sharing study results via token.
- **Features**: PDF export, AI analysis trigger, and detailed engineering metrics.

### `online-result.html` (Legacy Viewer)
- **Status**: Maintaining for backward compatibility with older studies.

## 🔧 Modular Panels

### `ai_panel_for_result_html.html`
- A modular UI component that can be injected into any result page.
- Handles the state management for the AI "waterfall" status (Ollama vs Gemini).

## 🚀 Future Roadmap: React Migration

Plans are underway to migrate the current HTML/JS stack to a unified React architecture.
- **Goal**: Improved state management and a more componentized design system.
- **Status**: Researching [Maha] integration for advanced 3D room visualization.

---
*See [API Client](./api-client-and-state.md) for details on how the front-end communicates with the calculation engine.*
