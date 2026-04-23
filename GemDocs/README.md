# GemDocs - LuxScaleAI Documentation (Gemini Edition)

Welcome to the Gemini-generated documentation for LuxScaleAI. This documentation provides a comprehensive overview of the project's architecture, AI pipeline, calculation engine, and frontend integration, synthesized through deep codebase analysis.

## 📂 Documentation Structure

- **[AI Pipeline](./ai/README.md)**: Deep dive into the Gemini/Ollama waterfall orchestrator, prompt engineering, and analysis logic.
- **[Back-End Architecture](./back-end/README.md)**: Flask API routes, calculation engine, IES parsing, and PDF generation.
- **[Front-End Integration](./front-end/README.md)**: Modern UI components, legacy Tkinter paths, and state management.
- **[Lighting Engineering](./lighting/README.md)**: Core lighting principles, lumen method, and spacing heuristics used in the engine.
- **[Mathematical Foundation](./math/README.md)**: The equations and algorithms behind the lux and uniformity calculations.

## 🚀 Quick Start for Developers

1.  **Environment Setup**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```
2.  **Run the API**:
    ```bash
    python app.py
    ```
3.  **Core API Endpoint**: `POST /calculate` - Accepts room dimensions and target requirements.

---
*This documentation is maintained by Gemini CLI to provide an up-to-date and technically rigorous reference for the LuxScaleAI ecosystem.*
