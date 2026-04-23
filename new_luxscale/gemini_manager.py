"""
Gemini multi-account manager for LuxScaleAI.

Features:
- Waterfall fallback across multiple Gemini accounts
- Per-account daily quota tracking (auto-resets at midnight)
- Confidence validation before trusting any result
- Falls back to local snapshot if ALL accounts are exhausted or fail
- Account switching requires only editing gemini_config.json — no code changes

Config file: gemini_config.json  (at project root, next to app.py)
Local snapshot: gemini_snapshot.json  (written after each approved fix)
"""
from __future__ import annotations

import json
import re
import os
import datetime
import urllib.request
import urllib.error
import threading
from typing import Optional

from luxscale.paths import project_root
from luxscale.app_logging import log_step, log_exception

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = project_root()
_CONFIG_PATH = os.path.join(_ROOT, "gemini_config.json")
_SNAPSHOT_PATH = os.path.join(_ROOT, "gemini_snapshot.json")

_CONFIG_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Default config (written on first run if file is missing)
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG = {
    "accounts": [
        {
            "name": "account_1_free",
            "api_key": "",          # <-- paste your FREE account key here
            "daily_limit": 40,      # conservative — free tier = 50/day
            "used_today": 0,
            "reset_date": "",
            "enabled": True
        },
        {
            "name": "account_2_paid",
            "api_key": "",          # <-- paste your PAID account key here
            "daily_limit": 800,     # set to ~80% of your real paid limit
            "used_today": 0,
            "reset_date": "",
            "enabled": False        # set True when you upgrade
        },
        {
            "name": "account_3_backup",
            "api_key": "",          # optional third account
            "daily_limit": 40,
            "used_today": 0,
            "reset_date": "",
            "enabled": False
        }
    ],
    "model": "gemini-3.1-flash-lite-preview",
    "min_confidence": 0.6,          # below this → fallback to snapshot
    "timeout_seconds": 15
}

# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if not os.path.isfile(_CONFIG_PATH):
        _save_config(_DEFAULT_CONFIG)
        return _DEFAULT_CONFIG.copy()
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_exception("gemini_manager._load_config", e)
        return _DEFAULT_CONFIG.copy()


def _save_config(cfg: dict) -> None:
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_exception("gemini_manager._save_config", e)


# ---------------------------------------------------------------------------
# Per-account quota helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.date.today().isoformat()


def _reset_if_new_day(account: dict) -> dict:
    """Auto-reset used_today counter if we're on a new calendar day."""
    if account.get("reset_date") != _today():
        account["used_today"] = 0
        account["reset_date"] = _today()
    return account


def _account_has_quota(account: dict) -> bool:
    account = _reset_if_new_day(account)
    return (
        account.get("enabled", False)
        and bool(account.get("api_key", "").strip())
        and account.get("used_today", 0) < account.get("daily_limit", 0)
    )


def _increment_usage(cfg: dict, account_name: str) -> None:
    for acc in cfg["accounts"]:
        if acc["name"] == account_name:
            acc["used_today"] = acc.get("used_today", 0) + 1
            break
    _save_config(cfg)


# ---------------------------------------------------------------------------
# Gemini REST call (no SDK needed — pure urllib)
# ---------------------------------------------------------------------------

_SKIP_KEY = object()  # sentinel: skip this key, try next


def _call_gemini_api(api_key: str, model: str, prompt: str, timeout: int):
    """
    Call Gemini generateContent endpoint.
    Returns text string on success.
    Returns _SKIP_KEY sentinel when key should be skipped (429, 400, 401, 403).
    Returns None on generic network/parse errors.
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 512
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Read in chunks to ensure we get the full response body
            chunks = []
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            raw_bytes = b"".join(chunks)
            log_step("gemini_manager._call_gemini_api", "full response received", bytes=len(raw_bytes))
            data = json.loads(raw_bytes.decode("utf-8"))
            # Log the full API response structure
            log_step("gemini_manager._call_gemini_api", "api response keys", keys=list(data.keys()))
            candidate = data.get("candidates", [{}])[0]
            log_step("gemini_manager._call_gemini_api", "candidate info",
                     finishReason=candidate.get("finishReason"),
                     content_keys=list(candidate.get("content", {}).keys()) if candidate.get("content") else None)
            text = candidate["content"]["parts"][0]["text"]
            log_step("gemini_manager._call_gemini_api", "extracted text", length=len(text), text=text[:300])
            return text
    except urllib.error.HTTPError as e:
        if e.code == 429:
            log_step("gemini_manager._call_gemini_api", "429 rate limited — skip to next key", model=model)
            return _SKIP_KEY
        if e.code in (400, 401, 403):
            log_step("gemini_manager._call_gemini_api", f"HTTP {e.code} bad/revoked key — skip to next key", model=model)
            return _SKIP_KEY
        log_step("gemini_manager._call_gemini_api", f"HTTP {e.code}", model=model)
        return None
    except Exception as e:
        log_exception("gemini_manager._call_gemini_api", e)
        return None


# ---------------------------------------------------------------------------
# Result validation
# ---------------------------------------------------------------------------

def _parse_and_validate(raw_text: str, min_confidence: float) -> Optional[dict]:
    """
    Expect the model to return JSON. Validate structure and confidence score.
    Returns parsed dict or None if invalid/low-confidence.
    """
    import re as _re

    if not raw_text:
        return None

    # Always log the raw response so we can see what Gemini actually sent
    log_step("gemini_manager._parse_and_validate", "raw response",
             length=len(raw_text), raw=raw_text[:800])

    text = raw_text.strip()

    # Attempt 1: strip ```json ... ``` or ``` ... ``` fences
    text = _re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = _re.sub(r"\s*```$", "", text).strip()

    # Attempt 2: if still no leading {, extract first { ... } block
    if not text.startswith("{"):
        match = _re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)
        else:
            log_step("gemini_manager._parse_and_validate", "no JSON object found in response")
            return None

    # Attempt 3: parse
    result = None
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Last resort: find outermost { }
        try:
            start = text.index("{")
            end = text.rindex("}") + 1 if "}" in text else len(text)
            result = json.loads(text[start:end])
        except Exception as e:
            log_step("gemini_manager._parse_and_validate", "JSON parse failed after all attempts", error=str(e))
            return None

    if not isinstance(result, dict):
        return None

    # Auto-add missing fields with safe defaults so we never fail on structure
    if "issues" not in result:
        result["issues"] = []
    if "suggestions" not in result:
        result["suggestions"] = []
    if "summary" not in result:
        result["summary"] = ""
    if "quality_score" not in result:
        result["quality_score"] = 50

    # Confidence check — default to 0.8 if missing (model responded, trust it)
    confidence = result.get("confidence", 0.8)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.8
    result["confidence"] = confidence

    if confidence < min_confidence:
        log_step(
            "gemini_manager._parse_and_validate",
            "low confidence — fallback",
            confidence=confidence,
            min_confidence=min_confidence
        )
        return None

    return result


# ---------------------------------------------------------------------------
# Versioned snapshot system — never deletes old snapshots
# ---------------------------------------------------------------------------
# Layout on disk:
#   gemini_snapshot.json          — latest (symlink-equivalent, written every save)
#   snapshots/snap_<ISO>.json     — versioned archive, one per save
#   snapshots/index.json          — ordered list of all saved snapshots (newest first)
# ---------------------------------------------------------------------------

_SNAPSHOTS_DIR = os.path.join(_ROOT, "snapshots")


def _ensure_snapshots_dir() -> None:
    os.makedirs(_SNAPSHOTS_DIR, exist_ok=True)


def _snapshots_index_path() -> str:
    return os.path.join(_SNAPSHOTS_DIR, "index.json")


def _load_snapshots_index() -> list:
    """Return list of snapshot metadata dicts, newest first."""
    path = _snapshots_index_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        log_exception("gemini_manager._load_snapshots_index", e)
        return []


def _save_snapshots_index(entries: list) -> None:
    try:
        with open(_snapshots_index_path(), "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_exception("gemini_manager._save_snapshots_index", e)


def _load_snapshot() -> Optional[dict]:
    """Load the most recent snapshot (gemini_snapshot.json)."""
    if not os.path.isfile(_SNAPSHOT_PATH):
        return None
    try:
        with open(_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_exception("gemini_manager._load_snapshot", e)
        return None


def save_snapshot(analysis_result: dict, label: str = "approved") -> None:
    """
    Save a versioned snapshot.

    - Always writes a new file in snapshots/snap_<timestamp>.json
    - Updates snapshots/index.json with the new entry (newest first)
    - Overwrites gemini_snapshot.json with the latest (used as fallback)

    Old snapshots are NEVER deleted.

    Args:
        analysis_result: The analysis dict from analyze_lighting_result()
        label: Human-readable label ("approved", "auto", etc.)
    """
    _ensure_snapshots_dir()

    now_iso = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_iso = now_iso  # already filename-safe
    versioned_filename = f"snap_{safe_iso}.json"
    versioned_path = os.path.join(_SNAPSHOTS_DIR, versioned_filename)

    snapshot = {
        "saved_at": datetime.datetime.utcnow().isoformat() + "Z",
        "label": label,
        "source": analysis_result.get("source", "unknown"),
        "quality_score": analysis_result.get("quality_score"),
        "confidence": analysis_result.get("confidence"),
        "analysis": analysis_result,
    }

    # 1. Write versioned file
    try:
        with open(versioned_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        log_step("gemini_manager.save_snapshot", "versioned snapshot saved",
                 file=versioned_filename, label=label)
    except Exception as e:
        log_exception("gemini_manager.save_snapshot (versioned)", e)

    # 2. Update index (newest first, keep up to 200 entries)
    index = _load_snapshots_index()
    index.insert(0, {
        "filename": versioned_filename,
        "saved_at": snapshot["saved_at"],
        "label": label,
        "source": snapshot["source"],
        "quality_score": snapshot["quality_score"],
        "confidence": snapshot["confidence"],
    })
    index = index[:200]  # cap history
    _save_snapshots_index(index)

    # 3. Overwrite gemini_snapshot.json (latest = current fallback)
    try:
        with open(_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        log_step("gemini_manager.save_snapshot", "latest snapshot updated",
                 path=_SNAPSHOT_PATH, total_snapshots=len(index))
    except Exception as e:
        log_exception("gemini_manager.save_snapshot (latest)", e)


def load_snapshot_by_filename(filename: str) -> Optional[dict]:
    """Load a specific versioned snapshot by filename (from index)."""
    # Sanitize: only allow safe filenames
    if not re.fullmatch(r"snap_\d{8}T\d{6}Z\.json", filename):
        log_step("gemini_manager.load_snapshot_by_filename",
                 "rejected unsafe filename", filename=filename)
        return None
    path = os.path.join(_SNAPSHOTS_DIR, filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_exception("gemini_manager.load_snapshot_by_filename", e)
        return None


def get_snapshot_history() -> list:
    """Return the snapshot index (list of metadata dicts, newest first)."""
    return _load_snapshots_index()


def _auto_save_snapshot(result: dict) -> None:
    """
    Automatically save a high-confidence result as a snapshot.
    Called internally after each successful AI analysis.
    Only saves if confidence >= 0.75 and quality_score is present.
    """
    try:
        confidence = float(result.get("confidence", 0))
        quality_score = result.get("quality_score")
        if confidence >= 0.75 and quality_score is not None:
            save_snapshot(result, label="auto")
            log_step("gemini_manager._auto_save_snapshot", "auto-saved",
                     confidence=confidence, quality_score=quality_score)
        else:
            log_step("gemini_manager._auto_save_snapshot", "skipped (low confidence or missing score)",
                     confidence=confidence)
    except Exception as e:
        log_exception("gemini_manager._auto_save_snapshot", e)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def analyze_lighting_result(study_payload: dict) -> dict:
    """
    Main entry point. Waterfall order is controlled by gemini_config.json:

    ollama_priority: true  → Ollama first (saves Gemini tokens), Gemini as backup
    ollama_priority: false → Gemini first (better quality), Ollama as backup

    Returns a dict with shape:
    {
        "source": "ollama:local" | "gemini:account_1_free" | "snapshot" | "default",
        "confidence": 0.0-1.0,
        "issues": [...],
        "suggestions": [...],
        "quality_score": 0-100,
        "summary": "..."
    }
    """
    prompt = _build_prompt(study_payload)

    with _CONFIG_LOCK:
        cfg = _load_config()

    model = cfg.get("model", "gemini-3.1-flash-lite-preview")
    min_confidence = cfg.get("min_confidence", 0.6)
    timeout = cfg.get("timeout_seconds", 15)
    ollama_priority = cfg.get("ollama_priority", False)

    def _try_ollama():
        """Try Ollama local model. Returns validated dict or None."""
        try:
            from luxscale.ollama_manager import is_available, analyze_with_ollama
            if not is_available():
                log_step("gemini_manager.analyze", "Ollama not available (not running or disabled)")
                return None
            log_step("gemini_manager.analyze", "trying Ollama local")
            raw = analyze_with_ollama(prompt)
            if not raw:
                return None
            validated = _parse_and_validate(raw, min_confidence)
            if validated:
                validated["source"] = "ollama:local"
                log_step("gemini_manager.analyze", "Ollama success")
                _auto_save_snapshot(validated)
                return validated
            log_step("gemini_manager.analyze", "Ollama failed validation")
            return None
        except ImportError:
            return None

    def _try_gemini_accounts():
        """Try all Gemini accounts in order. Returns validated dict or None."""
        for account in cfg["accounts"]:
            _reset_if_new_day(account)
            if not _account_has_quota(account):
                log_step(
                    "gemini_manager.analyze",
                    f"skipping {account['name']} — no quota or disabled",
                    used=account.get("used_today"),
                    limit=account.get("daily_limit"),
                    enabled=account.get("enabled")
                )
                continue

            log_step("gemini_manager.analyze", f"trying {account['name']}")
            raw = _call_gemini_api(account["api_key"], model, prompt, timeout)

            if raw is _SKIP_KEY or raw is None:
                reason = "rate limited / bad key" if raw is _SKIP_KEY else "connection error"
                log_step("gemini_manager.analyze", f"{account['name']} skipped ({reason}) — trying next")
                continue

            validated = _parse_and_validate(raw, min_confidence)
            if validated is None:
                log_step("gemini_manager.analyze", f"{account['name']} failed validation — trying next")
                continue

            # Success — increment usage and return
            with _CONFIG_LOCK:
                cfg2 = _load_config()
                _increment_usage(cfg2, account["name"])

            validated["source"] = f"gemini:{account['name']}"
            log_step("gemini_manager.analyze", "Gemini success", source=validated["source"])
            _auto_save_snapshot(validated)
            return validated

        return None

    # --- Waterfall based on priority setting ---
    if ollama_priority:
        log_step("gemini_manager.analyze", "mode: Ollama first (ollama_priority=true)")
        result = _try_ollama() or _try_gemini_accounts()
    else:
        log_step("gemini_manager.analyze", "mode: Gemini first (ollama_priority=false)")
        result = _try_gemini_accounts() or _try_ollama()

    if result:
        return result

    # All failed — try snapshot
    log_step("gemini_manager.analyze", "all sources failed — loading snapshot")
    snapshot = _load_snapshot()
    if snapshot and isinstance(snapshot.get("analysis"), dict):
        snap_result = dict(snapshot["analysis"])
        snap_result["source"] = "snapshot"
        snap_result["snapshot_saved_at"] = snapshot.get("saved_at", "unknown")
        log_step("gemini_manager.analyze", "returning snapshot", saved_at=snapshot.get("saved_at"))
        return snap_result

    # No snapshot — return safe default
    log_step("gemini_manager.analyze", "no snapshot — returning default")
    return {
        "source": "default",
        "confidence": 0.0,
        "issues": [],
        "suggestions": ["No AI analysis available yet. Run more calculations to build a snapshot."],
        "quality_score": 50,
        "summary": "AI analysis unavailable. All accounts at quota limit or unconfigured."
    }


def get_account_status() -> list:
    """Return quota status for all accounts (for admin dashboard)."""
    with _CONFIG_LOCK:
        cfg = _load_config()
    status = []
    for acc in cfg["accounts"]:
        _reset_if_new_day(acc)
        status.append({
            "name": acc["name"],
            "enabled": acc.get("enabled", False),
            "has_key": bool(acc.get("api_key", "").strip()),
            "used_today": acc.get("used_today", 0),
            "daily_limit": acc.get("daily_limit", 0),
            "remaining": max(0, acc.get("daily_limit", 0) - acc.get("used_today", 0)),
            "reset_date": acc.get("reset_date", "")
        })
    return status


def update_account_key(account_name: str, new_api_key: str, enabled: bool = True) -> bool:
    """Update an account's API key at runtime — no restart needed."""
    with _CONFIG_LOCK:
        cfg = _load_config()
        for acc in cfg["accounts"]:
            if acc["name"] == account_name:
                acc["api_key"] = new_api_key.strip()
                acc["enabled"] = enabled
                acc["used_today"] = 0
                acc["reset_date"] = _today()
                _save_config(cfg)
                log_step("gemini_manager.update_account_key", "updated", account=account_name)
                return True
    return False


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(payload: dict) -> str:
    """Build a minimal prompt that fits within free tier output token limits.

    Delegates to luxscale.ai_prompt.build_ai_prompt() for consistent format
    across Gemini and Ollama sources.
    """
    from luxscale.ai_prompt import build_ai_prompt
    return build_ai_prompt(payload)