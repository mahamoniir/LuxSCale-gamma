"""
Shared prompt builder for LuxScaleAI AI analysis.

Used by both gemini_manager.py and ollama_manager.py to ensure identical
prompt format and expected JSON response structure across all AI sources.

This guarantees that the validation logic in gemini_manager._parse_and_validate()
works identically regardless of whether the response came from Gemini or Ollama.
"""
from __future__ import annotations

from typing import Dict, Any


def build_ai_prompt(payload: dict) -> str:
    """
    Build a minimal prompt for lighting design analysis.

    The prompt is optimized for:
    - Short token count (fits free tier limits)
    - Clear JSON structure expectation
    - Works with both cloud (Gemini) and local (Ollama) models

    Expected JSON response:
    {
        "confidence": 0.0-1.0,
        "quality_score": 0-100,
        "issues": [{"severity": "high|medium|low", "field": "...", "description": "...", "suggested_fix": "..."}],
        "suggestions": ["tip1", "tip2"],
        "summary": "one sentence"
    }
    """
    results = payload.get("results", [])
    standard = payload.get("standard_lighting", {}) or {}
    sides = payload.get("sides", [])
    height = payload.get("height", "?")
    place = payload.get("place", payload.get("standard_task_or_activity", "?"))

    r = results[0] if results else {}
    avg_lux = r.get("Average Lux") or r.get("E_avg_grid_lx", "?")
    u0 = r.get("U0_calculated", r.get("Uniformity", "?"))
    fixtures = r.get("Fixtures", "?")
    compliance_lux = r.get("Standard margin (lux %)", "?")
    compliance_u0 = r.get("Standard margin (U0 %)", "?")
    em_req = standard.get("Em_r_lx", standard.get("Em_u_lx", "?"))
    uo_req = standard.get("Uo", "?")

    # Keep values short
    try:
        avg_lux = round(float(avg_lux), 1)
    except (TypeError, ValueError):
        pass
    try:
        u0 = round(float(u0), 3)
    except (TypeError, ValueError):
        pass
    try:
        compliance_lux = round(float(compliance_lux), 1)
    except (TypeError, ValueError):
        pass
    try:
        compliance_u0 = round(float(compliance_u0), 1)
    except (TypeError, ValueError):
        pass

    # Determine OK/LOW status
    lux_ok = _status_ok(compliance_lux)
    u0_ok = _status_ok(compliance_u0)

    prompt = (
        "Lighting audit. Reply JSON only, no extra text.\n"
        f"Space:{place} Sides:{sides} H:{height}m\n"
        f"Required Em:{em_req}lx Uo:{uo_req}\n"
        f"Got Em:{avg_lux}lx({lux_ok}) U0:{u0}({u0_ok}) Fixtures:{fixtures}\n"
        "Return this JSON with short strings max 60 chars each:\n"
        '{"confidence":0.9,"quality_score":70,"issues":[{"severity":"high","field":"Em","description":"short reason","suggested_fix":"short fix"}],"suggestions":["tip1","tip2"],"summary":"one sentence."}'
    )
    return prompt


def _status_ok(value) -> str:
    """Return 'OK' if value is numeric and >= 0, else 'LOW'."""
    if value is None:
        return "LOW"
    s = str(value)
    try:
        num = float(s.lstrip("-"))
        return "OK" if num >= 0 else "LOW"
    except (TypeError, ValueError):
        return "LOW"


def get_expected_response_schema() -> dict:
    """
    Return the expected JSON response schema.
    Used for validation documentation and auto-filling missing fields.
    """
    return {
        "confidence": 0.8,       # 0.0-1.0, defaults to 0.8 if model responded
        "quality_score": 50,     # 0-100
        "issues": [],            # Array of issue objects
        "suggestions": [],       # Array of string tips
        "summary": ""            # One sentence summary
    }


def get_issue_schema() -> dict:
    """Return the expected schema for a single issue object."""
    return {
        "severity": "low",       # "high", "medium", or "low"
        "field": "",             # Which metric has the issue
        "description": "",       # What's wrong
        "suggested_fix": ""      # How to fix it
    }
