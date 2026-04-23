# LuxScaleAI — AI Pipeline Documentation

> **Brand:** Short Circuit · **Accent:** `#eb1b26` · **Logo:** `assets/brand/`  
> **Last updated:** April 2026

---

## Document Map

| # | File | Topic |
|---|------|-------|
| 1 | [01-overview-and-architecture.md](./01-overview-and-architecture.md) | What the AI does, why it exists, component map |
| 2 | [02-gemini-multi-account.md](./02-gemini-multi-account.md) | Gemini accounts, quota tracking, `gemini_config.json` |
| 3 | [03-ollama-local-model.md](./03-ollama-local-model.md) | Ollama integration, env vars, availability check |
| 4 | [04-waterfall-logic.md](./04-waterfall-logic.md) | Priority modes, decision tree, fallback chain |
| 5 | [05-prompt-engineering.md](./05-prompt-engineering.md) | Prompt format, token optimisation, response schema |
| 6 | [06-snapshot-system.md](./06-snapshot-system.md) | Versioned snapshots, index, restore, auto-save |
| 7 | [07-api-reference.md](./07-api-reference.md) | All `/api/ai/*` endpoints with full request/response examples |
| 8 | [08-key-improvements.md](./08-key-improvements.md) | What the AI adds vs raw output — before/after comparison |
| 9 | [09-future-roadmap.md](./09-future-roadmap.md) | Fine-tuning plan, planned endpoints, long-term vision |

---

## Quick orientation

- **Entry point in code:** `luxscale/ai_routes.py` registers the Flask Blueprint
- **Main orchestrator:** `luxscale/gemini_manager.py` (waterfall, quota, snapshot)
- **Local model:** `luxscale/ollama_manager.py` (Ollama REST interface)
- **Shared prompt:** `luxscale/ai_prompt.py` (identical format for all AI sources)
- **Config file:** `gemini_config.json` at project root
- **Snapshot file:** `gemini_snapshot.json` at project root
- **Snapshot archive:** `snapshots/snap_<ISO>.json` + `snapshots/index.json`

---

## Related

- Back-end: [`../back-end/README.md`](../back-end/README.md)
- Front-end AI panel: [`../front-end/pages-inventory.md`](../front-end/pages-inventory.md)
- Parent index: [`../README.md`](../README.md)
