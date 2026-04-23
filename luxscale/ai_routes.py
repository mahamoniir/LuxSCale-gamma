"""
AI Analysis Flask routes for LuxScaleAI.
Add these routes to app.py by importing and registering them,
OR copy-paste the route functions directly into app.py.

Usage in app.py:
    from luxscale.ai_routes import register_ai_routes
    register_ai_routes(app)
"""
from __future__ import annotations

import json
import os
import time
import threading
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Optional

from flask import Blueprint, request, jsonify, session, Response
from luxscale.app_logging import log_step, log_exception

ai_bp = Blueprint("ai", __name__)


_CHAT_MAX_BODY_BYTES = 32_000
_CHAT_MAX_MESSAGE_CHARS = 1_200
_CHAT_IP_MIN_INTERVAL_SECONDS = 0.25
_CHAT_RL_LOCK = threading.Lock()
_CHAT_IP_LAST: dict[str, float] = {}


def register_ai_routes(app):
    """Call this in app.py after creating the Flask app."""
    app.register_blueprint(ai_bp)


def _chat_client_ip() -> str:
    fwd = (request.headers.get("X-Forwarded-For") or "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.remote_addr or "unknown").strip() or "unknown"


def _chat_rate_limit_ok(ip: str) -> tuple[bool, float]:
    now = time.time()
    with _CHAT_RL_LOCK:
        # purge stale entries
        stale = [k for k, ts in _CHAT_IP_LAST.items() if now - ts > 3600]
        for k in stale:
            _CHAT_IP_LAST.pop(k, None)

        last = float(_CHAT_IP_LAST.get(ip, 0.0))
        delta = now - last
        if delta < _CHAT_IP_MIN_INTERVAL_SECONDS:
            return False, max(0.0, _CHAT_IP_MIN_INTERVAL_SECONDS - delta)
        _CHAT_IP_LAST[ip] = now
    return True, 0.0


def _chat_size_guard() -> tuple[bool, Optional[tuple], str]:
    ip = _chat_client_ip()
    clen = request.content_length
    if isinstance(clen, int) and clen > _CHAT_MAX_BODY_BYTES:
        return False, (
            jsonify(
                {
                    "status": "error",
                    "message": "Request too large",
                    "max_bytes": _CHAT_MAX_BODY_BYTES,
                }
            ),
            413,
        ), ip
    return True, None, ip


def _chat_request_guard() -> tuple[bool, Optional[tuple], str]:
    size_ok, size_err, ip = _chat_size_guard()
    if not size_ok:
        return size_ok, size_err, ip

    ok, retry = _chat_rate_limit_ok(ip)
    if not ok:
        return False, (
            jsonify(
                {
                    "status": "error",
                    "message": "Too many requests. Please slow down.",
                    "retry_after_seconds": round(float(retry), 2),
                }
            ),
            429,
        ), ip
    return True, None, ip


def _ai_admin_ok() -> bool:
    """
    Check admin auth for AI routes.

    Works with both:
      - Cookie session  (browser login via /api/admin/login)
      - X-Admin-Token header  (curl / cross-origin dashboard)

    Root cause of the classic blueprint auth bug:
      When Flask runs `python app.py`, the main module is registered in
      sys.modules as '__main__', NOT as 'app'. A `from app import X` inside
      a blueprint triggers a SECOND import of app.py, creating a fresh module
      with empty _ADMIN_TOKENS — so the stored token is never found.

    Fix: always look up the LIVE running module via sys.modules.
    """
    import sys

    # Get the real live app module (whichever name it was loaded under)
    app_mod = sys.modules.get("__main__") or sys.modules.get("app")

    # 1. Cookie session check
    if bool(session.get("admin")):
        return True

    # 2. Bearer token check against the LIVE _ADMIN_TOKENS dict
    tok = (request.headers.get("X-Admin-Token") or "").strip()
    if tok and app_mod is not None:
        try:
            tokens: dict = getattr(app_mod, "_ADMIN_TOKENS", {})
            lock = getattr(app_mod, "_ADMIN_TOKEN_LOCK", None)
            purge = getattr(app_mod, "_purge_expired_admin_tokens", None)
            if lock and purge:
                with lock:
                    purge()
                    exp = tokens.get(tok)
                    return exp is not None and exp > time.time()
            else:
                # No lock available — still try a plain lookup
                exp = tokens.get(tok)
                return exp is not None and exp > time.time()
        except Exception:
            pass

    # 3. Standalone / unit-test mode — app module not present, allow
    if app_mod is None:
        return True

    return False


# ---------------------------------------------------------------------------
# CHAT ROUTES
# ---------------------------------------------------------------------------

@ai_bp.route("/api/chat/menu", methods=["GET"])
def api_chat_menu():
    from luxscale.chat_service import get_menu_items

    return jsonify(
        {
            "status": "success",
            "menu_items": get_menu_items(),
        }
    )


@ai_bp.route("/api/chat/health", methods=["GET"])
def api_chat_health():
    from luxscale.chat_service import chat_health

    return jsonify({"status": "success", **chat_health()})


@ai_bp.route("/api/chat/ask", methods=["POST"])
def api_chat_ask():
    from luxscale.chat_service import handle_question

    allowed, err_resp, ip = _chat_request_guard()
    if not allowed:
        return err_resp

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    message = str(data.get("message") or "").strip()
    session_id = str(data.get("session_id") or "").strip()
    user_id = str(data.get("user_id") or "").strip()
    context_messages = data.get("context_messages")
    if not isinstance(context_messages, list):
        context_messages = []
    if not message:
        return jsonify({"status": "error", "message": "message is required"}), 400
    if len(message) > _CHAT_MAX_MESSAGE_CHARS:
        return jsonify(
            {
                "status": "error",
                "message": f"message too long (max {_CHAT_MAX_MESSAGE_CHARS} chars)",
            }
        ), 400

    log_step(
        "POST /api/chat/ask",
        "start",
        ip=ip,
        session_id=session_id or "new",
        user_id=(user_id or "anonymous"),
    )
    try:
        result = handle_question(
            message,
            session_id=session_id,
            user_id=user_id,
            context_messages=context_messages,
        )
        log_step(
            "POST /api/chat/ask",
            "done",
            ip=ip,
            source=result.get("source"),
            session_id=result.get("session_id"),
        )
        return jsonify(result)
    except Exception as e:
        log_exception("POST /api/chat/ask", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@ai_bp.route("/api/chat/feedback", methods=["POST"])
def api_chat_feedback():
    from luxscale.chat_service import handle_feedback

    allowed, err_resp, ip = _chat_size_guard()
    if not allowed:
        return err_resp

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    session_id = str(data.get("session_id") or "").strip()
    feedback = str(data.get("feedback") or "").strip()
    if not session_id:
        return jsonify({"status": "error", "message": "session_id is required"}), 400
    if not feedback:
        return jsonify({"status": "error", "message": "feedback is required"}), 400

    log_step("POST /api/chat/feedback", "start", ip=ip, session_id=session_id)
    try:
        result = handle_feedback(session_id=session_id, feedback=feedback)
        code = 200 if result.get("status") == "success" else 400
        log_step(
            "POST /api/chat/feedback",
            "done",
            ip=ip,
            session_id=result.get("session_id") or session_id,
            source=result.get("source"),
            status=result.get("status"),
        )
        return jsonify(result), code
    except Exception as e:
        log_exception("POST /api/chat/feedback", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@ai_bp.route("/api/chat/fixed-responses/regenerate", methods=["POST"])
def api_chat_fixed_responses_regenerate():
    """
    Regenerate fixed responses from standards + fixtures + IES index.
    Admin-protected to avoid public abuse.
    """
    if not _ai_admin_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from luxscale.chat_service import clear_fixed_responses_cache, chat_health
    from luxscale.fixed_responses_builder import regenerate_fixed_responses

    data = request.get_json(silent=True)
    out = None
    if isinstance(data, dict):
        out = str(data.get("output_path") or "").strip() or None

    log_step("POST /api/chat/fixed-responses/regenerate", "start", output_path=out or "default")
    try:
        doc = regenerate_fixed_responses(output_path=out)
        clear_fixed_responses_cache()
        return jsonify(
            {
                "status": "success",
                "message": "fixed_responses.json regenerated",
                "responses_count": len(doc.get("responses") or []),
                "menu_items_count": len(doc.get("menu_items") or []),
                "chat_health": chat_health(),
            }
        )
    except Exception as e:
        log_exception("POST /api/chat/fixed-responses/regenerate", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@ai_bp.route("/api/chat/image-proxy", methods=["GET"])
def api_chat_image_proxy():
    """
    Proxy remote fixture images for frontend PDF export capture.
    Restricts hosts for safety and returns image bytes directly.
    """
    raw_url = str(request.args.get("url") or "").strip()
    if not raw_url:
        return jsonify({"status": "error", "message": "url is required"}), 400

    try:
        p = urlparse(raw_url)
        host = (p.hostname or "").lower().strip()
        if p.scheme not in {"http", "https"}:
            return jsonify({"status": "error", "message": "Invalid URL scheme"}), 400

        allowed_hosts = {
            "shortcircuit.company",
            "www.shortcircuit.company",
        }
        if host not in allowed_hosts:
            return jsonify({"status": "error", "message": "Host is not allowed"}), 400

        req = Request(
            raw_url,
            headers={
                "User-Agent": "LuxScaleAI-ImageProxy/1.0",
                "Accept": "image/*,*/*;q=0.8",
            },
        )
        with urlopen(req, timeout=12) as r:
            content_type = str(r.headers.get("Content-Type") or "application/octet-stream")
            if not content_type.lower().startswith("image/"):
                return jsonify({"status": "error", "message": "URL is not an image"}), 400

            # Soft cap 8 MB
            max_bytes = 8 * 1024 * 1024
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                return jsonify({"status": "error", "message": "Image too large"}), 413

            resp = Response(data, status=200, mimetype=content_type)
            resp.headers["Cache-Control"] = "public, max-age=3600"
            return resp
    except Exception as e:
        log_exception("GET /api/chat/image-proxy", e)
        return jsonify({"status": "error", "message": "Failed to fetch image"}), 502


# ---------------------------------------------------------------------------
# POST /api/ai/analyze
# Analyze a study result with Gemini (waterfall multi-account)
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/analyze", methods=["POST"])
def api_ai_analyze():
    """
    Analyze a lighting design result with Gemini AI.

    Body: the study payload (same JSON as stored in api/data/studies/*.json)
    OR:   {"token": "<study_token>"} to analyze a saved study

    Returns:
    {
        "status": "success",
        "source": "gemini:account_1_free" | "snapshot" | "default",
        "quality_score": 0-100,
        "issues": [...],
        "suggestions": [...],
        "summary": "...",
        "confidence": 0.0-1.0
    }
    """
    from luxscale.gemini_manager import analyze_lighting_result

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    # Support token-based lookup
    token = data.get("token", "").strip()
    if token:
        payload = _load_study_payload(token)
        if payload is None:
            return jsonify({"status": "error", "message": "Study not found"}), 404
    else:
        payload = data

    if not payload.get("results"):
        return jsonify({
            "status": "error",
            "message": "Payload has no results to analyze"
        }), 400

    log_step("POST /api/ai/analyze", "start", token=token or "inline")

    try:
        result = analyze_lighting_result(payload)
        log_step("POST /api/ai/analyze", "done", source=result.get("source"))
        return jsonify({"status": "success", **result})
    except Exception as e:
        log_exception("POST /api/ai/analyze", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /api/ai/approve-fix
# User approves a fix — saves snapshot and optionally updates study
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/approve-fix", methods=["POST"])
def api_ai_approve_fix():
    """
    Called when the user approves an AI-suggested fix.
    Saves the analysis result as the new fallback snapshot.

    Body:
    {
        "analysis": { ...the analysis result from /api/ai/analyze... },
        "fix_index": 0,          // which issue was approved (optional)
        "token": "..."           // study token (optional, for audit log)
    }
    """
    from luxscale.gemini_manager import save_snapshot

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        return jsonify({"status": "error", "message": "Missing analysis object"}), 400

    fix_index = data.get("fix_index")
    token = data.get("token", "")

    log_step("POST /api/ai/approve-fix", "saving snapshot", token=token, fix_index=fix_index)

    try:
        save_snapshot(analysis, label="approved")
        from luxscale.gemini_manager import get_snapshot_history
        history = get_snapshot_history()
        latest = history[0] if history else {}
        return jsonify({
            "status": "success",
            "message": "Fix approved and snapshot saved",
            "snapshot_updated": True,
            "snapshot": {
                "filename": latest.get("filename"),
                "saved_at": latest.get("saved_at"),
                "label": latest.get("label"),
                "quality_score": latest.get("quality_score"),
                "total_snapshots": len(history),
            }
        })
    except Exception as e:
        log_exception("POST /api/ai/approve-fix", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# GET /api/ai/status
# Admin: show quota status for all Gemini accounts
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/status", methods=["GET"])
def api_ai_status():
    """
    Returns quota status for all configured Gemini accounts.
    Protected by admin session.
    """
    # Import admin check from app.py context
    if not _ai_admin_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401  # If running standalone, skip auth check

    from luxscale.gemini_manager import get_account_status, get_snapshot_history
    import os
    from luxscale.paths import project_root

    snapshot_path = os.path.join(project_root(), "gemini_snapshot.json")
    has_snapshot = os.path.isfile(snapshot_path)
    snapshot_date = None
    if has_snapshot:
        try:
            import json as _json
            with open(snapshot_path) as f:
                snap = _json.load(f)
            snapshot_date = snap.get("saved_at")
        except Exception:
            pass

    history = get_snapshot_history()

    return jsonify({
        "status": "success",
        "accounts": get_account_status(),
        "has_snapshot": has_snapshot,
        "snapshot_saved_at": snapshot_date,
        "total_snapshots": len(history),
        "latest_snapshot": history[0] if history else None,
    })


# ---------------------------------------------------------------------------
# PUT /api/ai/account
# Admin: update an account key or enable/disable at runtime
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/account", methods=["PUT"])
def api_ai_update_account():
    """
    Update a Gemini account key at runtime (no restart needed).
    Use this to switch from free to paid account.

    Body:
    {
        "name": "account_2_paid",
        "api_key": "AIza...",
        "enabled": true
    }
    """
    if not _ai_admin_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from luxscale.gemini_manager import update_account_key

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    name = data.get("name", "").strip()
    key = data.get("api_key", "").strip()
    enabled = bool(data.get("enabled", True))

    if not name:
        return jsonify({"status": "error", "message": "name required"}), 400

    success = update_account_key(name, key, enabled)
    if not success:
        return jsonify({"status": "error", "message": f"Account '{name}' not found"}), 404

    return jsonify({
        "status": "success",
        "message": f"Account '{name}' updated",
        "enabled": enabled
    })


# ---------------------------------------------------------------------------
# GET /api/ai/snapshots
# List all versioned snapshots (newest first)
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/snapshots", methods=["GET"])
def api_ai_snapshots_list():
    """
    Returns the full snapshot history index (newest first).
    Each entry has: filename, saved_at, label, source, quality_score, confidence.

    Optional query params:
      ?limit=N    — return only the N most recent entries (default: all)
      ?label=X    — filter by label ("auto", "approved")
    """
    if not _ai_admin_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from luxscale.gemini_manager import get_snapshot_history

    history = get_snapshot_history()

    # Optional label filter
    label_filter = (request.args.get("label") or "").strip()
    if label_filter:
        history = [e for e in history if e.get("label") == label_filter]

    # Optional limit
    try:
        limit = int(request.args.get("limit", 0))
        if limit > 0:
            history = history[:limit]
    except (TypeError, ValueError):
        pass

    return jsonify({
        "status": "success",
        "total": len(history),
        "snapshots": history,
    })


# ---------------------------------------------------------------------------
# GET /api/ai/snapshots/<filename>
# Load a specific versioned snapshot by filename
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/snapshots/<filename>", methods=["GET"])
def api_ai_snapshot_get(filename):
    """
    Load and return a specific versioned snapshot.
    filename must match the pattern: snap_YYYYMMDDTHHMMSSZ.json

    Returns the full snapshot including the embedded analysis dict.
    """
    if not _ai_admin_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from luxscale.gemini_manager import load_snapshot_by_filename

    snap = load_snapshot_by_filename(filename)
    if snap is None:
        return jsonify({"status": "error", "message": "Snapshot not found or invalid filename"}), 404

    return jsonify({"status": "success", "snapshot": snap})


# ---------------------------------------------------------------------------
# POST /api/ai/snapshots/restore
# Restore a specific versioned snapshot as the current fallback
# ---------------------------------------------------------------------------

@ai_bp.route("/api/ai/snapshots/restore", methods=["POST"])
def api_ai_snapshot_restore():
    """
    Restore a specific versioned snapshot as the active fallback.

    Body:
    {
        "filename": "snap_20260408T123456Z.json"
    }

    This saves the chosen snapshot as a new "restored" snapshot entry
    (preserving the original) and sets it as gemini_snapshot.json.
    """
    if not _ai_admin_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from luxscale.gemini_manager import load_snapshot_by_filename, save_snapshot

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"status": "error", "message": "filename required"}), 400

    snap = load_snapshot_by_filename(filename)
    if snap is None:
        return jsonify({"status": "error", "message": "Snapshot not found or invalid filename"}), 404

    analysis = snap.get("analysis")
    if not isinstance(analysis, dict):
        return jsonify({"status": "error", "message": "Snapshot has no analysis data"}), 400

    log_step("POST /api/ai/snapshots/restore", "restoring snapshot", filename=filename)
    save_snapshot(analysis, label="restored")

    return jsonify({
        "status": "success",
        "message": f"Snapshot '{filename}' restored as active fallback",
        "original_saved_at": snap.get("saved_at"),
        "original_source": snap.get("source"),
    })


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _load_study_payload(token: str):
    """Load study payload from disk by token."""
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        return None
    from luxscale.paths import project_root
    path = os.path.join(project_root(), "api", "data", "studies", f"{token}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
        return record.get("payload")
    except Exception:
        return None