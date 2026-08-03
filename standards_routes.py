"""
/api/standards/*  ·  category → task/activity → full standard row flow.

Frontend flow this is built for:
  1. GET  /api/standards/categories                  → populate select #1
  2. GET  /api/standards/categories/<category>/tasks  → populate select #2 once #1 changes
  3. GET  /api/standards/ref/<ref_no>                 → full row once both selects have a value
  (existing POST /standards/resolve in app.py does the same thing as #3 — kept for
   backward compatibility with any client already using it)

  Optional helper when the room type can't be found in the text on screen:
  POST /api/standards/detect  { "text": "open plan office with workstations" }
    → ranked category guesses with matching ref_nos, so the client can pre-select
      both dropdowns instead of asking the user to search manually.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from luxscale import standards_lookup as sl

standards_bp = Blueprint("standards_api", __name__, url_prefix="/api/standards")


@standards_bp.route("/categories", methods=["GET"])
def api_standards_categories():
    return jsonify({"status": "success", "categories": sl.list_categories()})


@standards_bp.route("/categories/<path:category>/tasks", methods=["GET"])
def api_standards_tasks(category: str):
    tasks = sl.list_tasks(category)
    if not tasks:
        known = sl.known_categories()
        return jsonify(
            {
                "status": "error",
                "message": "Unknown category, or category has no rows",
                "category": category,
                "hint": "GET /api/standards/categories for valid values",
            }
        ), 404
    return jsonify({"status": "success", "category": category, "tasks": tasks})


@standards_bp.route("/detect", methods=["POST"])
def api_standards_detect():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"status": "error", "message": "text is required"}), 400
    limit = data.get("limit") or 5
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 5
    matches = sl.detect_category(text, limit=limit)
    return jsonify({"status": "success", "query": text, "matches": matches})


@standards_bp.route("/ref/<path:ref_no>", methods=["GET"])
def api_standards_ref(ref_no: str):
    row = sl.resolve_ref(ref_no)
    if not row:
        return jsonify({"status": "error", "message": "Unknown ref_no", "ref_no": ref_no}), 404
    return jsonify({"status": "success", "row": row})
