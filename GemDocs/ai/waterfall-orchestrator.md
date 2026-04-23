# Waterfall Orchestrator Implementation

The `GeminiManager` class in `luxscale/gemini_manager.py` implements a robust waterfall logic to ensure the AI analysis remains functional despite API quotas or network issues.

## 🛠️ Multi-Account Management

The system uses `gemini_config.json` to load multiple API keys. It tracks:
- **Usage Counts**: Number of requests per key.
- **Cooldowns**: Temporary suspension of keys that hit rate limits.
- **Health Checks**: Periodic validation of key status.

## 💻 Local Model (Ollama) Integration

The `OllamaManager` provides a bridge to locally hosted models.
- **Endpoint**: Defaults to `http://localhost:11434`.
- **Model**: Configurable (e.g., `llama3.2`).
- **Benefit**: Zero latency (local), zero cost, and privacy-preserving.

## 📉 Failover Strategy

```python
# Simplified Waterfall Logic
def analyze(payload):
    if config.ollama_priority:
        res = ollama.try_analyze(payload)
        if res: return res
    
    for key in gemini_pool.get_available_keys():
        res = gemini.try_analyze(payload, key)
        if res: return res
        
    return snapshot_system.get_best_match(payload)
```

## 📸 Snapshot System

The snapshot system (`luxscale/gemini_manager.py`) stores successful AI responses indexed by their calculation parameters. This ensures that even in offline scenarios, the system can provide "intelligent-feeling" feedback for common room types.
