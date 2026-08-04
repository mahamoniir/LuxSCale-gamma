"""
/api/standards/*  ·  category → task/activity → full standard row flow.

Two-step "place selection" flow — mirrors the calculator UI dropdowns:

  1. GET  /api/standards/categories                    → populate select #1
  2. GET  /api/standards/categories/<category>/tasks   → populate select #2 once #1 changes
  3. Either:
     • GET  /api/standards/ref/<ref_no>                → full row when the caller
                                                         already knows the ref_no
                                                         (from the tasks response)
     • POST /api/standards/resolve-by-task             → full row + ref_no directly
                                                         from (category, task_or_activity)

  Once you have the ref_no, submit it as ``standard_ref_no`` in the
  ``/calculate`` or ``/cad_calc`` request body — the engine treats a resolved
  standard row as the source of truth for target lux (Em_r_lx) and required
  uniformity (Uo).

  (Legacy ``POST /standards/resolve`` in app.py — same output as #3-by-ref —
  is kept for backward compatibility.)

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


@standards_bp.route("/resolve-by-task", methods=["POST"])
def api_standards_resolve_by_task():
    """
    Close the two-step select in one call: give the endpoint the picked
    ``category`` and ``task_or_activity`` (exactly as they appear in the UI
    dropdowns) and get back the full row — including the ``ref_no`` you need
    to submit to ``/calculate`` or ``/cad_calc``.

    Body::

        {
          "category": "Traffic zones inside buildings",
          "task_or_activity": "Corridors and circulation areas",
          "ref_no_hint": "6.1.1"   // optional — required only when two rows in
                                   // the same category share the same task text
        }

    The endpoint also accepts the frontend picker's disambiguation form
    (``"Task text (ref_no)"``) — the ``(ref_no)`` suffix is stripped and used
    as the hint automatically.

    Response — success::

        {
          "status": "success",
          "row": { ref_no, category, category_base, task_or_activity,
                   Em_r_lx, Em_u_lx, Uo, Ra, ... },
          "category": "...",
          "task_or_activity": "..."
        }

    Response — no match (404)::

        { "status": "not_found", "row": null, "reason": "..." }

    Response — ambiguous (409)::

        {
          "status": "ambiguous",
          "row": null,
          "matches": ["6.1.1", "6.1.7"],
          "reason": "multiple rows share this task_or_activity; pass ref_no_hint ..."
        }
    """
    data = request.get_json(silent=True) or {}
    category = (data.get("category") or "").strip()
    task = (data.get("task_or_activity") or "").strip()
    hint = (data.get("ref_no_hint") or data.get("ref_no") or "").strip() or None

    if not category or not task:
        return jsonify(
            {
                "status": "error",
                "message": "category and task_or_activity are both required",
            }
        ), 400

    result = sl.resolve_by_task(category, task, ref_no_hint=hint)
    if result["status"] == "success":
        return jsonify(result)
    if result["status"] == "ambiguous":
        return jsonify(result), 409
    return jsonify(result), 404
