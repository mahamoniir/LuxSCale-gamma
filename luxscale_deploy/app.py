from flask import Flask, request, jsonify, send_file, send_from_directory, session
import io
from fpdf import FPDF
import json
import os
import re
import secrets
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
import tempfile
from flask_cors import CORS

from luxscale.app_logging import LOG_FILE, log_exception, log_step
from luxscale.calculation_trace import CalculationTrace

# import your existing functions
from luxscale.app_settings import (
    get_ui_config,
    load_app_settings,
    save_app_settings,
    validate_ceiling_height_m,
)
from luxscale.lighting_calc import calculate_lighting, draw_heatmap, define_places

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT_DIR, ".env"))
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "luxscale-dev-change-in-production")

from luxscale.ai_routes import register_ai_routes
register_ai_routes(app)

# Note: IES routes are defined in a separate module (ies_routes.py) for better organization.
from generate_report import build_full_report_pdf, build_solution_pdf
from flask import Response
# Example route for generating a PDF report using the functions from generate_report.py

# ── IES routes ────────────────────────────────────────────────────────────────
# ies_routes.py now exports a Blueprint called ies_bp.
# register_blueprint() is the correct way to attach it.
from luxscale.ies_routes import ies_bp
app.register_blueprint(ies_bp)
# ─────────────────────────────────────────────────────────────────────────────

_cors_raw = os.environ.get("LUXSCALE_CORS_ORIGINS", "").strip()
if _cors_raw:
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
else:
    _cors_origins = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:80",
        "http://127.0.0.1:80",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ]
CORS(
    app,
    supports_credentials=True,
    origins=_cors_origins,
    allow_headers=["Content-Type", "X-Admin-Token"],
    methods=["GET", "POST", "PUT", "OPTIONS", "DELETE"],
)

_ADMIN_TOKEN_LOCK = threading.Lock()
# In-memory bearer tokens for admin when the dashboard is on another origin (e.g. XAMPP) than Flask.
_ADMIN_TOKENS: dict[str, float] = {}
_ADMIN_TOKEN_TTL_S = int(os.environ.get("LUXSCALE_ADMIN_TOKEN_TTL_S", str(7 * 24 * 3600)))

log_step("Flask app", "initialized", app=__name__, log_file=LOG_FILE)

def _fixture_map_path() -> str:
    from luxscale.ies_dataset_config import active_fixture_map_basename

    return os.path.join(_ROOT_DIR, "assets", active_fixture_map_basename())


def _dashboard_api_base() -> str:
    return (os.environ.get("LUXSCALE_DASHBOARD_API_BASE") or "http://127.0.0.1:5000").strip()


def _write_dashboard_config_json() -> None:
    """Mirror ``.env`` into ``assets/dashboard_config.json`` for static (XAMPP) dashboard."""
    path = os.path.join(_ROOT_DIR, "assets", "dashboard_config.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"api_base": _dashboard_api_base()}, f, indent=2)
    except OSError:
        pass


_write_dashboard_config_json()


def _admin_credentials():
    return (
        os.environ.get("LUXSCALE_ADMIN_USER", "luxscale"),
        os.environ.get("LUXSCALE_ADMIN_PASSWORD", "LuxScaleAdmin2026"),
    )


def _purge_expired_admin_tokens() -> None:
    now = time.time()
    dead = [t for t, exp in _ADMIN_TOKENS.items() if exp < now]
    for t in dead:
        _ADMIN_TOKENS.pop(t, None)


def _admin_bearer_ok() -> bool:
    tok = (request.headers.get("X-Admin-Token") or "").strip()
    if not tok:
        return False
    with _ADMIN_TOKEN_LOCK:
        _purge_expired_admin_tokens()
        exp = _ADMIN_TOKENS.get(tok)
        return exp is not None and exp > time.time()


def _issue_admin_token() -> str:
    tok = secrets.token_urlsafe(32)
    with _ADMIN_TOKEN_LOCK:
        _purge_expired_admin_tokens()
        _ADMIN_TOKENS[tok] = time.time() + _ADMIN_TOKEN_TTL_S
    return tok


def _revoke_admin_token(tok: str) -> None:
    if not tok:
        return
    with _ADMIN_TOKEN_LOCK:
        _ADMIN_TOKENS.pop(tok, None)


def _admin_session_ok() -> bool:
    if bool(session.get("admin")):
        return True
    return _admin_bearer_ok()

_STANDARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standards")
_STANDARDS_CACHE = {}


def _standards_json_path(filename: str) -> str:
    return os.path.join(_STANDARDS_DIR, filename)


def load_standards_file(filename: str):
    """Load and cache JSON from standards/ (keywords + cleaned)."""
    if filename not in _STANDARDS_CACHE:
        path = _standards_json_path(filename)
        with open(path, encoding="utf-8") as f:
            _STANDARDS_CACHE[filename] = json.load(f)
    return _STANDARDS_CACHE[filename]


def cleaned_row_by_ref(ref_no: str):
    if not ref_no:
        return None
    ref_key = str(ref_no).strip()
    cleaned = load_standards_file("standards_cleaned.json")
    for row in cleaned:
        if str(row.get("ref_no", "")).strip() == ref_key:
            return row
    return None


def _norm_ref(ref):
    if ref is None:
        return ""
    return str(ref).strip()


def _resolve_calculate_inputs(data):
    """Returns (standard_row | None, place | None) for calculate_lighting."""
    project_info = data.get("project_info") if isinstance(data.get("project_info"), dict) else {}
    if not project_info:
        project_info = {}
    # Top-level standard_ref_no supports clients that omit nesting under project_info.
    ref = _norm_ref(project_info.get("standard_ref_no") or data.get("standard_ref_no"))
    standard_row = cleaned_row_by_ref(ref) if ref else None
    place = data.get("place")
    if isinstance(place, str) and place.strip() == "":
        place = None
    return standard_row, place


def _want_fast_calculate(data: dict) -> bool:
    """True for JSON ``fast: 1|true`` or query ``?fast=1`` (and ``true``/``yes``/``fast``)."""
    if isinstance(data, dict):
        v = data.get("fast")
        if v is True or v == 1:
            return True
        if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "fast"):
            return True
    q = (request.args.get("fast") or "").strip().lower()
    return q in ("1", "true", "yes", "fast")


@app.route("/calculate", methods=["POST"])
def api_calculate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        log_step("POST /calculate", "reject: not JSON object")
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    log_step("POST /calculate", "received", keys=list(data.keys()) if data else [])

    trace = None
    try:
        sides = data.get("sides")
        if sides is None:
            log_step("POST /calculate", "error: missing sides")
            return jsonify({"status": "error", "message": "Missing sides"}), 400
        if data.get("height") is None:
            log_step("POST /calculate", "error: missing height")
            return jsonify({"status": "error", "message": "Missing height"}), 400
        height = float(data["height"])
        ok_h, err_h = validate_ceiling_height_m(height)
        if not ok_h:
            log_step("POST /calculate", "error: ceiling height", detail=err_h)
            return jsonify({"status": "error", "message": err_h}), 400

        raw_pi = data.get("project_info") if isinstance(data.get("project_info"), dict) else {}
        project_info = dict(raw_pi)
        ref_top = _norm_ref(raw_pi.get("standard_ref_no") or data.get("standard_ref_no"))
        if ref_top:
            project_info["standard_ref_no"] = ref_top

        standard_row, place = _resolve_calculate_inputs(data)
        log_step(
            "POST /calculate: resolved inputs",
            "ok",
            place=place,
            standard_ref_no=ref_top or None,
            has_standard_row=standard_row is not None,
        )

        if not standard_row and not place:
            log_step("POST /calculate", "error: no place and no valid standard_ref_no")
            return jsonify(
                {
                    "status": "error",
                    "message": "Provide either project_info.standard_ref_no (valid ref in standards) or place",
                }
            ), 400

        calc_fast = _want_fast_calculate(data)
        trace = CalculationTrace("POST /calculate")
        trace.step(
            "api_00_ready",
            sides=sides,
            height=height,
            standard_ref_no=ref_top or None,
            has_standard_row=standard_row is not None,
            place=place,
            fast=bool(calc_fast),
        )
        if standard_row:
            results, length, width, calc_meta = calculate_lighting(
                None,
                sides,
                height,
                standard_row=standard_row,
                trace=trace,
                fast=calc_fast,
            )
        else:
            results, length, width, calc_meta = calculate_lighting(
                place, sides, height, trace=trace, fast=calc_fast
            )

        trace.step("api_01_calculate_lighting_returned", result_rows=len(results))

        log_step(
            "POST /calculate: success",
            f"{len(results)} result row(s)",
            length=length,
            width=width,
            result_rows=len(results),
        )

        trace_path = trace.save()
        log_step("POST /calculate: calculation trace file", trace_path)

        out = {
            "status": "success",
            "project_info": project_info,
            "results": results,
            "length": length,
            "width": width,
            "calculation_trace_file": trace_path,
            "calculation_meta": calc_meta,
            "ui_settings": get_ui_config(),
        }
        if standard_row:
            out["standard_row"] = standard_row
            merged_pi = dict(project_info)
            merged_pi["standard_lighting"] = standard_row
            out["project_info"] = merged_pi
        return jsonify(out)

    except Exception as e:
        if trace is not None:
            trace.step("api_ERROR", error=str(e))
            try:
                trace_path = trace.save()
                log_step("POST /calculate: calculation trace file (error)", trace_path)
            except Exception:
                trace_path = None
        else:
            trace_path = None
        log_exception("POST /calculate", e)
        err_body = {"status": "error", "message": str(e)}
        if trace_path:
            err_body["calculation_trace_file"] = trace_path
        return jsonify(err_body), 400


@app.route("/pdf", methods=["POST"])
def api_pdf():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected JSON body"}), 400

    sides = data.get("sides")
    if sides is None:
        return jsonify({"status": "error", "message": "Missing sides"}), 400
    if data.get("height") is None:
        return jsonify({"status": "error", "message": "Missing height"}), 400
    height = float(data["height"])
    raw_pi = data.get("project_info") if isinstance(data.get("project_info"), dict) else {}
    project_info = dict(raw_pi)
    ref_top = _norm_ref(raw_pi.get("standard_ref_no") or data.get("standard_ref_no"))
    if ref_top:
        project_info["standard_ref_no"] = ref_top

    standard_row, place = _resolve_calculate_inputs(data)
    if not standard_row and not place:
        return jsonify(
            {"status": "error", "message": "Provide either standard_ref_no or place"}
        ), 400
    calc_fast = _want_fast_calculate(data)
    if standard_row:
        results, length, width, _meta = calculate_lighting(
            None, sides, height, standard_row=standard_row, fast=calc_fast
        )
    else:
        results, length, width, _meta = calculate_lighting(
            place, sides, height, fast=calc_fast
        )

    pdf = FPDF(format='A4')
    pdf.add_page()
    pdf.set_font("Arial", size=16)
    pdf.cell(200, 10, "Lighting Design Report", ln=True)
    for k, v in project_info.items():
        pdf.cell(200, 10, f"{k}: {v}", ln=True)

    for res in results:
        pdf.add_page()
        for key, val in res.items():
            pdf.cell(0, 10, f"{key}: {val}", ln=True)

    pdf_bytes = io.BytesIO(pdf.output(dest='S').encode('latin1'))
    pdf_bytes.seek(0)
    return send_file(pdf_bytes, download_name="report.pdf", as_attachment=True)

@app.route("/", methods=["GET"])
def api_index():
    return jsonify({"status": "success", "message": "Welcome to the API"})


@app.route("/places", methods=["GET"])
def api_places():
    """
    Calculator room types + standard categories from standards_keywords_upgraded.json,
    merged with categories present in standards_cleaned.json. Used with category → task → ref_no → lux.
    """
    calculator_places = []
    for key, meta in define_places.items():
        calculator_places.append(
            {
                "key": key,
                "lux": meta["lux"],
                "uniformity": meta["uniformity"],
            }
        )

    keywords = load_standards_file("standards_keywords_upgraded.json")
    cleaned = load_standards_file("standards_cleaned.json")

    cat_from_keywords = set((keywords.get("category_keywords") or {}).keys())
    cat_from_cleaned = {row["category"] for row in cleaned if row.get("category")}
    standard_categories = sorted(cat_from_keywords | cat_from_cleaned)

    return jsonify(
        {
            "calculator_places": calculator_places,
            "places": calculator_places,
            "standard_categories": standard_categories,
            "category_keywords": keywords.get("category_keywords") or {},
            "metadata": keywords.get("metadata") or {},
        }
    )


@app.route("/api/ui-settings", methods=["GET"])
def api_ui_settings_public():
    """Public: pagination defaults for result UI (matches ``calculate`` response)."""
    return jsonify(get_ui_config())


@app.route("/api/public-config", methods=["GET"])
def api_public_config():
    """Public: dashboard API base URL from ``.env`` (``LUXSCALE_DASHBOARD_API_BASE``)."""
    return jsonify({"api_base": _dashboard_api_base()})


_STUDIES_DIR = os.path.join(_ROOT_DIR, "api", "data", "studies")


def _study_payload_to_api_response(payload: dict) -> dict:
    """Same JSON shape as ``api/get.php`` for result.html."""
    sides = payload["sides"]
    w = max(float(sides[0]), float(sides[2]))
    l = max(float(sides[1]), float(sides[3]))
    p = payload
    req = {
        "project_name": p.get("project_name", ""),
        "sides": p["sides"],
        "height": p["height"],
    }
    if "place" in p:
        req["place"] = p["place"]
    if p.get("standard_ref_no") is not None:
        req["standard_ref_no"] = p["standard_ref_no"]
    if p.get("standard_category"):
        req["standard_category"] = p["standard_category"]
    if p.get("standard_task_or_activity"):
        req["standard_task_or_activity"] = p["standard_task_or_activity"]
    if p.get("standard_lighting") is not None:
        req["standard_lighting"] = p["standard_lighting"]

    meta = p.get("calculation_meta")
    if not isinstance(meta, dict):
        meta = {}

    out = {
        "status": "success",
        "results": p["results"],
        "calculation_meta": meta,
        "project_info": {
            "Project Name": p.get("project_name", ""),
            "Client Name": p.get("name", ""),
            "Client Number": p.get("phone", ""),
            "Company Name": p.get("company", ""),
        },
        "request": req,
        "customer": {
            "name": p.get("name", ""),
            "phone": p.get("phone", ""),
            "company": p.get("company", ""),
            "email": p.get("email", ""),
        },
        "width": w,
        "length": l,
    }
    if p.get("standard_lighting") is not None:
        out["standard_lighting"] = p["standard_lighting"]
    return out


@app.route("/api/submit", methods=["POST"])
def api_study_submit():
    """
    Store study JSON (same contract as ``api/submit.php``). Allows ``results: []``.
    Use when XAMPP/PHP submit is missing or another host returns misleading 200+error bodies.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400
    sides = data.get("sides")
    if not isinstance(sides, list) or len(sides) != 4:
        return jsonify(
            {"error": "Missing required fields: sides (array of 4 numbers)"}
        ), 400
    for s in sides:
        try:
            if float(s) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(
                {"error": "Missing required fields: sides must be positive numbers"}
            ), 400
    try:
        ht = float(data["height"])
        if ht <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Missing required fields: height"}), 400
    ok_h, err_h = validate_ceiling_height_m(ht)
    if not ok_h:
        return jsonify({"error": err_h}), 400
    if "results" not in data or not isinstance(data["results"], list):
        return jsonify(
            {"error": "Missing required fields: results (array, may be empty)"}
        ), 400

    token = secrets.token_hex(16)
    os.makedirs(_STUDIES_DIR, exist_ok=True)
    path = os.path.join(_STUDIES_DIR, f"{token}.json")
    record = {
        "token": token,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "payload": data,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
    except OSError as e:
        log_exception("api_study_submit", e)
        return jsonify({"error": "Could not save study"}), 500

    log_step("api_study_submit", "saved", token_prefix=token[:8])
    return jsonify({"status": "success", "token": token})


@app.route("/api/upload-drawing", methods=["POST"])
def upload_drawing():
    token = request.form.get("token")
    file = request.files.get("file")
    if not token or not file:
        return jsonify({"status": "error", "message": "Missing token or file"}), 400

    upload_dir = os.path.join("luxscale", "uploads")
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    filename = f"{token}_drawing.png"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    return jsonify({"status": "success", "message": "Drawing uploaded", "path": filepath})


@app.route("/api/get", methods=["GET"])
def api_study_get():
    """Load study by token (same contract as ``api/get.php``)."""
    token = (request.args.get("token") or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        return jsonify({"status": "error", "message": "Invalid token"}), 400
    path = os.path.join(_STUDIES_DIR, f"{token}.json")
    if not os.path.isfile(path):
        return jsonify({"status": "error", "message": "Study not found"}), 404
    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log_exception("api_study_get", e)
        return jsonify({"status": "error", "message": "Corrupt study record"}), 500
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        return jsonify({"status": "error", "message": "Corrupt study record"}), 500
    return jsonify(_study_payload_to_api_response(record["payload"]))


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(silent=True) or {}
    u, p = _admin_credentials()
    if data.get("username") == u and data.get("password") == p:
        session["admin"] = True
        token = _issue_admin_token()
        return jsonify({"status": "success", "token": token})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    tok = (request.headers.get("X-Admin-Token") or "").strip()
    _revoke_admin_token(tok)
    session.pop("admin", None)
    return jsonify({"status": "success"})


@app.route("/api/admin/settings", methods=["GET", "PUT"])
def api_admin_settings():
    if not _admin_session_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if request.method == "GET":
        return jsonify(load_app_settings())
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"status": "error", "message": "Expected JSON object"}), 400
    save_app_settings(body)
    return jsonify({"status": "success", "settings": load_app_settings()})


@app.route("/api/admin/fixture-map", methods=["GET", "PUT"])
def api_admin_fixture_map():
    if not _admin_session_ok():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if request.method == "GET":
        with open(_fixture_map_path(), encoding="utf-8") as f:
            return jsonify(json.load(f))
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"status": "error", "message": "Expected JSON object"}), 400
    with open(_fixture_map_path(), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    try:
        from luxscale.fixture_catalog import clear_fixture_map_cache

        clear_fixture_map_cache()
    except Exception:
        pass
    return jsonify({"status": "success"})


@app.route("/assets/<path:path>")
def serve_project_assets(path: str):
    """Serve ``assets/`` (logo, favicon, video, etc.) when the admin UI is opened from Flask."""
    return send_from_directory(os.path.join(_ROOT_DIR, "assets"), path)


@app.route("/admin/dashboard.html")
def admin_dashboard_static():
    path = os.path.join(_ROOT_DIR, "admin", "dashboard.html")
    if not os.path.isfile(path):
        return jsonify({"error": "dashboard not found"}), 404
    return send_file(path)


@app.route("/standards/resolve", methods=["POST"])
def api_standards_resolve():
    """Return one row from standards_cleaned.json by ref_no (validates client selection)."""
    data = request.get_json(silent=True) or {}
    ref = (data.get("ref_no") or "").strip()
    if not ref:
        return jsonify({"status": "error", "message": "ref_no required"}), 400
    row = cleaned_row_by_ref(ref)
    if not row:
        return jsonify({"status": "error", "message": "Unknown ref_no"}), 404
    return jsonify({"status": "success", "row": row})

# generate report routes are in generate_report.py, which imports this app.py. To avoid circular imports, we import the report functions here and define the API route here, while the main report-building logic is in generate_report.py.
"""
Add these two routes to your app.py.
Place them anywhere after your existing routes are defined
and after `from generate_report import build_full_report_pdf, build_solution_pdf`
is at the top of app.py.
"""

import json, os
from flask import Response, abort, jsonify

# ── where your study JSON files live ──────────────────────────────
STUDIES_DIR = os.path.join(os.path.dirname(__file__), "api", "data", "studies")


def _load_payload(token: str) -> dict:
    """Load and return the 'payload' dict for a given token."""
    # Basic safety: only allow hex tokens (no path traversal)
    if not token or not all(c in "0123456789abcdefABCDEF" for c in token):
        abort(400, description="Invalid token format")
    path = os.path.join(STUDIES_DIR, f"{token}.json")
    if not os.path.isfile(path):
        abort(404, description=f"Study not found: {token}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("payload", data)


@app.route("/api/report/<token>/full", methods=["GET"])
def api_report_full(token):
    """Generate and stream the full report PDF (all solutions)."""
    try:
        payload   = _load_payload(token)
        pdf_bytes = build_full_report_pdf(payload)
        filename  = f"SC_LuxScale_Report_{token[:8]}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        app.logger.error("Full PDF error for token %s: %s", token, e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/report/<token>/solution/<int:sol_index>", methods=["GET"])
def api_report_solution(token, sol_index):
    """Generate and stream a single-solution PDF."""
    try:
        payload   = _load_payload(token)
        results   = payload.get("results", [])
        if sol_index < 0 or sol_index >= len(results):
            return jsonify({"error": f"Solution index {sol_index} out of range (have {len(results)})"}), 404
        pdf_bytes = build_solution_pdf(payload, sol_index)
        filename  = f"SC_LuxScale_Solution_{sol_index + 1}_{token[:8]}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        app.logger.error("Solution PDF error for token %s idx %d: %s", token, sol_index, e, exc_info=True)
        return jsonify({"error": str(e)}), 500
    
# ───────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # use Railway's port
    app.run(host="0.0.0.0", port=port, debug=False)