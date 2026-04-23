"""
Ollama local model manager for LuxScaleAI.

Provides local AI analysis as a free, unlimited alternative to Gemini.
When enabled, Ollama is tried first (if ollama_priority=true) to save API quota.

Environment variables (set in .env or system):
- OLLAMA_ENABLED=true         — Set to "true" to enable Ollama integration
- OLLAMA_URL=http://localhost:11434 — Ollama server URL
- OLLAMA_MODEL=llama3.2:3b    — Model name to use

The prompt format and expected JSON response match gemini_manager.py exactly,
so the rest of the AI pipeline (validation, snapshot, UI) works unchanged.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import socket
from typing import Optional, Dict, Any

from luxscale.app_logging import log_step, log_exception
from luxscale.ai_prompt import build_ai_prompt

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

def _get_ollama_config() -> dict:
    """Load Ollama config from environment variables."""
    return {
        "enabled": os.environ.get("OLLAMA_ENABLED", "false").lower() == "true",
        "url": os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        "model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
    }


# Cache for availability check (avoid repeated network calls)
_OLLAMA_AVAILABLE_CACHE: Optional[bool] = None


def _clear_availability_cache() -> None:
    """Clear the availability cache (call after config changes)."""
    global _OLLAMA_AVAILABLE_CACHE
    _OLLAMA_AVAILABLE_CACHE = None


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def _is_ollama_server_reachable(url: str, timeout: float = 2.0) -> bool:
    """Check if Ollama server is reachable via GET /api/tags."""
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except urllib.error.HTTPError as e:
        # 404 means server is up but endpoint missing — still reachable
        if e.code == 404:
            return True
        log_step("ollama_manager._is_ollama_server_reachable", f"HTTP {e.code}")
    except urllib.error.URLError as e:
        log_step("ollama_manager._is_ollama_server_reachable", "URL error", reason=str(e.reason))
    except socket.timeout:
        log_step("ollama_manager._is_ollama_server_reachable", "timeout")
    except Exception as e:
        log_step("ollama_manager._is_ollama_server_reachable", "error", reason=str(e))
    return False


def is_available() -> bool:
    """
    Check if Ollama is available and ready to use.

    Returns True only if:
    1. OLLAMA_ENABLED=true in environment
    2. Ollama server responds at OLLAMA_URL/api/tags
    """
    global _OLLAMA_AVAILABLE_CACHE

    # Return cached result if available (cache is process-lifetime only)
    if _OLLAMA_AVAILABLE_CACHE is not None:
        return _OLLAMA_AVAILABLE_CACHE

    cfg = _get_ollama_config()

    if not cfg["enabled"]:
        log_step("ollama_manager.is_available", "disabled via OLLAMA_ENABLED env var")
        _OLLAMA_AVAILABLE_CACHE = False
        return False

    if not cfg["url"]:
        log_step("ollama_manager.is_available", "no OLLAMA_URL configured")
        _OLLAMA_AVAILABLE_CACHE = False
        return False

    if not cfg["model"]:
        log_step("ollama_manager.is_available", "no OLLAMA_MODEL configured")
        _OLLAMA_AVAILABLE_CACHE = False
        return False

    # Check server reachability
    reachable = _is_ollama_server_reachable(cfg["url"])
    if not reachable:
        log_step("ollama_manager.is_available", "server not reachable", url=cfg["url"])
        _OLLAMA_AVAILABLE_CACHE = False
        return False

    log_step("ollama_manager.is_available", "available", url=cfg["url"], model=cfg["model"])
    _OLLAMA_AVAILABLE_CACHE = True
    return True


# ---------------------------------------------------------------------------
# Model listing (for admin dashboard / diagnostics)
# ---------------------------------------------------------------------------

def get_available_models() -> list:
    """
    Fetch list of available models from Ollama server.
    Returns empty list if server is unreachable or Ollama is disabled.
    """
    cfg = _get_ollama_config()

    if not cfg["enabled"]:
        return []

    try:
        req = urllib.request.Request(f"{cfg['url']}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            return [
                {"name": m.get("name", "unknown"), "size": m.get("size", 0)}
                for m in models
            ]
    except Exception as e:
        log_exception("ollama_manager.get_available_models", e)
        return []


# ---------------------------------------------------------------------------
# Analysis function (matches gemini_manager.py interface)
# ---------------------------------------------------------------------------

def analyze_with_ollama(prompt: str) -> Optional[str]:
    """
    Send prompt to Ollama and return raw response text.

    The prompt format is identical to gemini_manager._build_prompt(),
    so the expected JSON response shape is the same:
    {
        "confidence": 0.0-1.0,
        "quality_score": 0-100,
        "issues": [{"severity": "...", "field": "...", "description": "...", "suggested_fix": "..."}],
        "suggestions": ["tip1", "tip2"],
        "summary": "..."
    }

    Returns:
    - Raw response text on success (caller validates JSON and confidence)
    - None on failure (timeout, server error, model not found)
    """
    cfg = _get_ollama_config()

    if not cfg["enabled"]:
        log_step("ollama_manager.analyze_with_ollama", "disabled")
        return None

    if not cfg["model"]:
        log_step("ollama_manager.analyze_with_ollama", "no model configured")
        return None

    url = f"{cfg['url']}/api/generate"

    # Build request payload — minimal, JSON-only instruction
    payload = {
        "model": cfg["model"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 512
        }
    }

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        log_step("ollama_manager.analyze_with_ollama", "sending request", model=cfg["model"], url=url)
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            raw_bytes = resp.read()
            log_step("ollama_manager.analyze_with_ollama", "response received", bytes=len(raw_bytes))
            data = json.loads(raw_bytes.decode("utf-8"))
            response_text = data.get("response", "")
            if response_text:
                log_step("ollama_manager.analyze_with_ollama", "success", response_length=len(response_text))
                return response_text
            else:
                log_step("ollama_manager.analyze_with_ollama", "empty response")
                return None

    except urllib.error.HTTPError as e:
        if e.code == 404:
            log_step("ollama_manager.analyze_with_ollama", "model not found", model=cfg["model"])
        elif e.code == 503:
            log_step("ollama_manager.analyze_with_ollama", "model loading (503)")
        else:
            log_step("ollama_manager.analyze_with_ollama", f"HTTP {e.code}")
        return None
    except urllib.error.URLError as e:
        log_step("ollama_manager.analyze_with_ollama", "connection failed", reason=str(e.reason))
        return None
    except socket.timeout:
        log_step("ollama_manager.analyze_with_ollama", "timeout (30s)")
        return None
    except Exception as e:
        log_exception("ollama_manager.analyze_with_ollama", e)
        return None


# ---------------------------------------------------------------------------
# Admin: update config at runtime (optional, for future dashboard)
# ---------------------------------------------------------------------------

def update_config(key: str, value: str) -> bool:
    """
    Update Ollama config at runtime by setting environment variable.
    Note: This only affects the current process — for permanent changes,
    update .env file and restart Flask.

    Keys: "enabled", "url", "model"
    """
    key_upper = f"OLLAMA_{key.upper()}"
    if key_upper not in ("OLLAMA_ENABLED", "OLLAMA_URL", "OLLAMA_MODEL"):
        return False

    os.environ[key_upper] = str(value)
    _clear_availability_cache()
    log_step("ollama_manager.update_config", "updated", key=key_upper, value=value)
    return True


def get_config_status() -> dict:
    """Return current Ollama configuration and availability status."""
    cfg = _get_ollama_config()
    return {
        "enabled": cfg["enabled"],
        "url": cfg["url"],
        "model": cfg["model"],
        "available": is_available(),
    }


# ---------------------------------------------------------------------------
# High-level analysis (convenience wrapper for gemini_manager integration)
# ---------------------------------------------------------------------------

def analyze_study_payload(payload: dict) -> Optional[str]:
    """
    Analyze a lighting study payload using Ollama.

    This is a convenience wrapper that:
    1. Builds the prompt using the shared ai_prompt.build_ai_prompt()
    2. Sends it to Ollama via analyze_with_ollama()
    3. Returns raw response text (caller validates JSON/confidence)

    Returns:
    - Raw response text on success
    - None on failure (Ollama disabled, server unreachable, model error)
    """
    prompt = build_ai_prompt(payload)
    return analyze_with_ollama(prompt)
