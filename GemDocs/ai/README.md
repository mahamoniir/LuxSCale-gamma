# AI Pipeline - GemDocs

The LuxScaleAI AI pipeline provides post-calculation analysis to score lighting designs and suggest optimizations. It is designed for high availability and cost-efficiency through a multi-tiered waterfall system.

## 📁 Key Components

- **`luxscale/gemini_manager.py`**: The core orchestrator managing multiple Gemini API accounts and failover logic.
- **`luxscale/ollama_manager.py`**: Local LLM integration (e.g., Llama 3) for free, unlimited analysis.
- **`luxscale/ai_prompt.py`**: Standardizes inputs into a consistent prompt format for all models.
- **`luxscale/ai_routes.py`**: Exposes endpoints like `/api/ai/analyze` and `/api/ai/approve-fix`.

## 🔄 The Waterfall Workflow

1.  **Request**: Frontend sends a token or calculation payload to `/api/ai/analyze`.
2.  **Ollama (Primary/Secondary)**: If enabled and prioritized, Ollama attempts the analysis first.
3.  **Gemini Pool**: If Ollama fails or is de-prioritized, the system iterates through a pool of Gemini API keys.
4.  **Snapshot Fallback**: If all AI sources fail, the system returns a pre-computed "snapshot" for similar results if available.
5.  **Heuristic Default**: As a last resort, a rule-based heuristic analysis is returned.

---
*See [Waterfall Orchestrator](./waterfall-orchestrator.md) for technical implementation details.*
