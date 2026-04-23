"""
ies_routes.py  ·  LuxScale IES integration
==========================================
Drop this file into your luxscale/ folder (next to app.py / main.py).
Register with:
    from ies_routes import ies_bp
    app.register_blueprint(ies_bp)

Depends on ies_analyzer.py being in the same folder.
Requires: Flask, numpy, matplotlib, scipy, Pillow
"""

import io
import base64
import uuid
import math as _math
import os
from pathlib import Path
from flask import Blueprint, request, jsonify, abort

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as _np
from PIL import Image as _PILImage

try:
    # When imported as part of the luxscale package (e.g. from luxscale.ies_routes)
    from .ies_analyzer import (
        parse_ies, parse_ies_file, compute_all_metrics,
        compute_beam_angle, plot_polar, plot_3d_surface,
        DARK_BG, DEMO_IES,
    )
except ImportError:
    # When run directly or ies_analyzer.py is on sys.path
    from ies_analyzer import (
        parse_ies, parse_ies_file, compute_all_metrics,
        compute_beam_angle, plot_polar, plot_3d_surface,
        DARK_BG, DEMO_IES,
    )

ies_bp = Blueprint("ies", __name__, url_prefix="/ies")

# ── In-memory session store keyed by session_id ───────────────────────────────
_sessions: dict = {}

# ── Render result cache (keyed by render params hash) ────────────────────────
import hashlib as _hashlib
_render_cache: dict = {}
_RENDER_CACHE_MAX = 64   # keep last 64 renders in memory

def _cache_key(*args) -> str:
    """MD5 of all render params joined — used to skip redundant renders."""
    return _hashlib.md5("|".join(str(a) for a in args).encode()).hexdigest()

def _cache_get(key):
    return _render_cache.get(key)

def _cache_set(key, value):
    if len(_render_cache) >= _RENDER_CACHE_MAX:
        # evict oldest entry
        _render_cache.pop(next(iter(_render_cache)))
    _render_cache[key] = value

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fig_to_b64(fig, dpi=90) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=DARK_BG, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()


def _sess(sid: str) -> dict:
    if sid not in _sessions:
        abort(404, description="IES session not found. Please upload a file first.")
    return _sessions[sid]


def _customer_summary(ies, metrics: dict) -> dict:
    """
    Returns ONLY the values a customer / installer needs.
    No internal photometry jargon — plain labels, rounded values.
    """
    beam  = metrics.get("beam_angle")
    field = metrics.get("field_angle")
    lm    = metrics.get("total_lumens")

    # Declared output from IES header
    declared_lm = None
    if ies.lumens_per_lamp > 0 and ies.num_lamps > 0:
        declared_lm = ies.lumens_per_lamp * ies.num_lamps * ies.multiplier

    # Pick the "best" lumen value to show the customer:
    # prefer the integrated (measured) value; fall back to declared.
    display_lm = lm if (lm and lm > 0) else declared_lm

    return {
        # ── What customers care about ─────────────────────────────────
        "total_lumens":   round(display_lm)  if display_lm  else None,
        "beam_angle_deg": round(beam, 1)      if beam        else None,
        "field_angle_deg":round(field, 1)     if field       else None,
        "peak_candela":   round(ies.max_value) if ies.max_value else None,

        # ── Extra context (shown in collapsed "Tech" section) ─────────
        "declared_lumens": round(declared_lm) if declared_lm else None,
        "lor_pct": round(
            min(lm / max(declared_lm, 1) * 100, 999), 1
        ) if (lm and declared_lm and declared_lm > 0) else None,
        "symmetry":  ies.symmetry_label(),
        "shape":     ies.shape,

        # ── Passed back so JS can pre-fill the panorama sliders ───────
        "fixture_width_m":  round(ies.width,  4),
        "fixture_length_m": round(ies.length, 4),
        "fixture_height_m": round(ies.height, 4),

        # ── Raw for the polar / 3-D tab ───────────────────────────────
        "horizontal_angles": ies.horizontal_angles,
        "num_vertical":  ies.num_vertical,
        "num_horizontal": ies.num_horizontal,
    }


def _flux_scale_for_session(sess: dict) -> float:
    """
    Return the candela→lux scaling factor so the panorama/floorplan renders
    match the calculation engine's absolute illuminance values.

    The calculation engine scales:  I_rendered = I_ies * (design_lm / ies_lm)
    where design_lm = lumens_per_fixture from the study (power × efficacy).

    If design_lumens was NOT passed at upload time we return 1.0 (raw IES values).
    The caller can then multiply by the intensity slider as usual.
    """
    design_lm = sess.get("design_lumens")
    if not design_lm or design_lm <= 0:
        return 1.0
    ies  = sess["ies"]
    mets = sess["metrics"]
    ies_lm = mets.get("total_lumens") or 0
    # Fall back to IES header lumens if zonal flux not computed
    if not ies_lm or ies_lm <= 0:
        ies_lm = float(ies.lumens_per_lamp) * max(1, int(ies.num_lamps)) * float(ies.multiplier)
    if ies_lm <= 0:
        return 1.0
    # Mirror the clamp used by uniformity_calculator.py
    from luxscale.lighting_calc.constants import (
        ies_lumen_to_design_ratio_max, ies_lumen_to_design_ratio_min,
    )
    ratio_raw = float(design_lm) / float(ies_lm)
    ratio_eff = min(max(ratio_raw, ies_lumen_to_design_ratio_min),
                    ies_lumen_to_design_ratio_max)
    return ratio_eff


# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────

def _load_fixture_map() -> list:
    """
    Load the active fixture_map JSON (e.g. fixture_map_SC_IES_Fixed_v3.json).
    Returns the list of entries, or [] on any failure.
    """
    import json as _json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Try active dataset map first, then fall back to fixture_map.json
    candidates = []
    try:
        from .ies_dataset_config import active_fixture_map_basename
        candidates.append(os.path.join(root, "assets", active_fixture_map_basename()))
    except Exception:
        pass
    candidates += [
        os.path.join(root, "assets", "fixture_map_SC_IES_Fixed_v3.json"),
        os.path.join(root, "assets", "fixture_map.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    doc = _json.load(fh)
                return doc.get("entries", [])
            except Exception:
                pass
    return []


def _find_ies_by_luminaire(luminaire_name: str, power_w: float, ies_filename: str = "") -> "str | None":
    """
    Locate an IES file on disk given a luminaire name + wattage.

    Search order:
      1. fixture_map.json — exact match on api_luminaire_name + power_w
         → resolves relative_ies_path under  <root>/ies-render/
      2. Explicit ies_filename searched across all known IES directories.
      3. Fuzzy filename match across all known IES directories.

    Returns the absolute path or None.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # All directories that may contain .ies files
    ies_render_base = os.path.join(root, "ies-render")
    search_dirs = [
        os.path.join(ies_render_base, "examples", "SC_IES_Fixed_v3"),
        os.path.join(ies_render_base, "examples", "SC_FIXED"),
        os.path.join(ies_render_base, "examples"),
        ies_render_base,
        os.path.join(root, "assets", "ies"),
        os.path.join(root, "assets", "IES"),
        os.path.join(root, "ies"),
        UPLOAD_DIR,
    ]

    # ── 1. Fixture-map exact lookup ───────────────────────────────────────────
    power_int = int(round(power_w)) if power_w else 0
    name_norm = luminaire_name.strip().lower()
    entries   = _load_fixture_map()
    for entry in entries:
        entry_name  = (entry.get("api_luminaire_name") or "").strip().lower()
        entry_power = int(round(float(entry.get("power_w") or 0)))
        if entry_name == name_norm and entry_power == power_int:
            rel = entry.get("relative_ies_path", "")
            if rel:
                # relative_ies_path is relative to ies-render/
                full = os.path.join(ies_render_base, rel.replace("/", os.sep))
                if os.path.isfile(full):
                    return full
                # Also try it relative to project root
                full2 = os.path.join(root, rel.replace("/", os.sep))
                if os.path.isfile(full2):
                    return full2

    # ── 2. Explicit ies_filename hint ────────────────────────────────────────
    if ies_filename:
        bare = os.path.basename(ies_filename)
        for d in search_dirs:
            # exact filename in directory
            p = os.path.join(d, bare)
            if os.path.isfile(p):
                return p
        # absolute / relative path as given
        if os.path.isfile(ies_filename):
            return ies_filename

    # ── 3. Fuzzy match by luminaire name + wattage across all dirs ────────────
    name_slug  = name_norm.replace(" ", "_").replace("-", "_")
    candidates = [
        f"{name_slug}_{power_int}w",
        f"{name_slug}_{power_int}W",
        name_slug,
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not fname.lower().endswith(".ies"):
                continue
            fl = fname.lower()
            for cand in candidates:
                if cand in fl:
                    return os.path.join(d, fname)

    # ── 4. Recursive search under ies-render/ (last resort) ──────────────────
    if ies_filename:
        bare = os.path.basename(ies_filename).lower()
        for dirpath, _dirs, files in os.walk(ies_render_base):
            for fname in files:
                if fname.lower() == bare:
                    return os.path.join(dirpath, fname)

    return None


@ies_bp.route("/upload", methods=["POST"])
def upload():
    """
    POST multipart/form-data — three modes:

    Mode A — actual .ies file upload:
        field "file" = <.ies file>

    Mode B — lookup by luminaire name (from result card button):
        fields: luminaire_name, power_w, [ies_filename]
        Server locates the IES file in assets/ies/ and loads it.

    Mode C — built-in demo:
        field "demo" = 1

    Returns JSON:
        { session_id, filename, customer: {...}, ies_data: {...} }
    """
    # ── Mode C: demo ─────────────────────────────────────────────────────────
    if "demo" in request.form:
        sid  = str(uuid.uuid4())[:8]
        path = os.path.join(UPLOAD_DIR, f"{sid}_demo.ies")
        with open(path, "w") as f:
            f.write(DEMO_IES)
        ies     = parse_ies(DEMO_IES)
        metrics = compute_all_metrics(ies)
        _sessions[sid] = {"ies": ies, "metrics": metrics,
                          "path": path, "filename": "demo.ies"}
        return jsonify(_response(sid, "demo.ies", ies, metrics))

    # ── Mode B: lookup by luminaire name ─────────────────────────────────────
    if "luminaire_name" in request.form and "file" not in request.files:
        luminaire_name  = request.form.get("luminaire_name", "").strip()
        power_w         = float(request.form.get("power_w", 0) or 0)
        ies_filename    = request.form.get("ies_filename", "").strip()
        # design_lumens: passed from result.html so panorama/floorplan can
        # match the calculation engine's flux scaling exactly.
        # Falls back to power_w * efficacy if not supplied.
        _dl_raw = request.form.get("design_lumens", "") or request.form.get("lumens_per_fixture", "")
        design_lumens   = float(_dl_raw) if _dl_raw else None

        ies_path = _find_ies_by_luminaire(luminaire_name, power_w, ies_filename)
        if not ies_path:
            return jsonify({
                "error": (
                    f"IES file not found for '{luminaire_name}' {power_w}W. "
                    f"Place .ies files in assets/ies/ or upload directly."
                )
            }), 404

        try:
            ies = parse_ies_file(ies_path)
        except Exception as e:
            return jsonify({"error": f"Failed to parse IES file: {e}"}), 422

        sid     = str(uuid.uuid4())[:8]
        metrics = compute_all_metrics(ies)
        fname   = os.path.basename(ies_path)
        _sessions[sid] = {"ies": ies, "metrics": metrics,
                          "path": ies_path, "filename": fname,
                          "design_lumens": design_lumens}
        return jsonify(_response(sid, fname, ies, metrics))

    # ── Mode A: file upload ───────────────────────────────────────────────────
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".ies"):
        return jsonify({"error": "Only .ies files are accepted"}), 400

    sid       = str(uuid.uuid4())[:8]
    safe_name = f"{sid}_{Path(f.filename).name}"
    path      = os.path.join(UPLOAD_DIR, safe_name)
    f.save(path)

    try:
        ies = parse_ies_file(path)
    except Exception as e:
        os.remove(path)
        return jsonify({"error": str(e)}), 422

    metrics = compute_all_metrics(ies)
    _sessions[sid] = {"ies": ies, "metrics": metrics,
                      "path": path, "filename": f.filename}
    return jsonify(_response(sid, f.filename, ies, metrics))


def _response(sid, filename, ies, metrics):
    return {
        "session_id": sid,
        "filename":   filename,
        "customer":   _customer_summary(ies, metrics),
        "ies_data": {
            "vertical_angles":   ies.vertical_angles,
            "horizontal_angles": ies.horizontal_angles,
            "candela_matrix":    [ies.candela_values[h] for h in ies.horizontal_angles],
            "max_value":         ies.max_value,
            "symmetry":          ies.symmetry_label(),
            "beam_angle":        metrics.get("beam_angle"),
            "field_angle":       metrics.get("field_angle"),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Specs  — used by openies.html standalone page to retrieve session data
# ─────────────────────────────────────────────────────────────────────────────

@ies_bp.route("/specs")
def specs():
    """
    GET /ies/specs?sid=<id>[&design_lumens=<lm>]
    Returns customer summary + filename for the standalone openies.html page.
    If design_lumens is supplied, it is stored in the session so subsequent
    panorama / floorplan renders apply the correct flux scaling.
    """
    sid  = request.args.get("sid", "")
    sess = _sess(sid)

    # Retroactively store design_lumens if openies.html sends it
    dl = request.args.get("design_lumens", "")
    if dl:
        try:
            dl_val = float(dl)
            if dl_val > 0 and not sess.get("design_lumens"):
                sess["design_lumens"] = dl_val
        except (ValueError, TypeError):
            pass

    return jsonify({
        "session_id": sid,
        "filename":   sess.get("filename", ""),
        "customer":   _customer_summary(sess["ies"], sess["metrics"]),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Polar plot  (used for the "Polar Curve" button in the product modal)
# ─────────────────────────────────────────────────────────────────────────────

@ies_bp.route("/plot/polar")
def plot_polar_endpoint():
    """
    GET /ies/plot/polar?sid=<id>&h_idx=0&scale=linear&show_beam=true
    Returns { image: "<base64 PNG>" }
    """
    sid      = request.args.get("sid", "")
    sess     = _sess(sid)
    h_idx    = int(request.args.get("h_idx", 0))
    scale    = request.args.get("scale", "linear")
    show_beam = request.args.get("show_beam", "true") == "true"

    fig = plot_polar(sess["ies"], sess["metrics"],
                     h_idx=h_idx, scale=scale, show_beam=show_beam)
    return jsonify({"image": _fig_to_b64(fig)})


# ─────────────────────────────────────────────────────────────────────────────
# 3-D candela surface  (Three.js raw data endpoint)
# ─────────────────────────────────────────────────────────────────────────────

@ies_bp.route("/ies_data")
def ies_data():
    """
    GET /ies/ies_data?sid=<id>
    Returns full candela matrix for the Three.js 3-D viewer.
    """
    sid     = request.args.get("sid", "")
    sess    = _sess(sid)
    ies     = sess["ies"]
    metrics = sess["metrics"]
    return jsonify({
        "vertical_angles":   ies.vertical_angles,
        "horizontal_angles": ies.horizontal_angles,
        "candela_matrix":    [ies.candela_values[h] for h in ies.horizontal_angles],
        "max_value":         ies.max_value,
        "beam_angle":        metrics.get("beam_angle"),
        "field_angle":       metrics.get("field_angle"),
        "peak_candela":      ies.max_value,
        "symmetry":          ies.symmetry_label(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Panorama  (360° light simulation — uses place dimensions from POST body)
# ─────────────────────────────────────────────────────────────────────────────

@ies_bp.route("/panorama", methods=["GET", "POST"])
def panorama():
    """
    GET  /ies/panorama?sid=<id>&room_w=<m>&room_l=<m>&room_h=<m>&...
    POST /ies/panorama  { sid, room_w, room_l, room_h, ... }

    room_w, room_l, room_h  -> come from the place/project data in LuxScale
    fixture_h               -> mounting height of the luminaire
    intensity               -> 0.0-2.0  (default 1.0)
    ct                      -> warm | neutral | cool
    w, h                    -> panorama resolution (default 1024x512)

    fixture_positions       -> JSON array of [x, z] pairs (metres, room-centred)
                               e.g. [[-2,0],[2,0]]
                               If omitted, a single fixture at [0,0] is assumed.
    layout_nx, layout_ny    -> grid dimensions (alternative to fixture_positions)
    spacing_x, spacing_y    -> grid spacing in metres

    Returns { image: "<base64 PNG>", width, height }
    """
    import json as _json_mod
    if request.method == "POST":
        args = request.get_json(force=True) or {}
        g = args.get
    else:
        g = request.args.get

    sid       = g("sid", "")
    sess      = _sess(sid)
    ies       = sess["ies"]

    # ── Room / space dimensions from LuxScale place data ─────────────────────
    room_w    = float(g("room_w",    g("room_sz", 6.0)))
    room_l    = float(g("room_l",    g("room_sz", 6.0)))
    room_h    = float(g("room_h",    3.0))

    # ── Luminaire mounting height (defaults to 80 % of ceiling height) ────────
    fixture_h = float(g("fixture_h", room_h * 0.80))
    fixture_h = min(fixture_h, room_h - 0.05)   # never above ceiling

    intensity    = float(g("intensity", 1.0))
    ct           = g("ct", "warm")
    # Apply the same flux scaling as the calculation engine so absolute lux matches
    intensity   *= _flux_scale_for_session(sess)

    # ── Fixture positions ─────────────────────────────────────────────────────
    # Accept either:
    #   fixture_positions = [[x1,z1],[x2,z2],...]   (room-centred metres)
    # or derive from grid:
    #   layout_nx, layout_ny, spacing_x, spacing_y
    fixture_positions = None
    raw_fp = g("fixture_positions", None)
    if raw_fp:
        try:
            if isinstance(raw_fp, str):
                raw_fp = _json_mod.loads(raw_fp)
            fixture_positions = [(float(p[0]), float(p[1])) for p in raw_fp]
        except Exception:
            fixture_positions = None

    if not fixture_positions:
        nx = int(float(g("layout_nx", 1) or 1))
        ny = int(float(g("layout_ny", 1) or 1))
        sx = float(g("spacing_x", room_w / max(nx, 1)))
        sy = float(g("spacing_y", room_l / max(ny, 1)))
        if nx > 1 or ny > 1:
            xs = [-(nx - 1) * sx / 2 + c * sx for c in range(nx)]
            zs = [-(ny - 1) * sy / 2 + r * sy for r in range(ny)]
            fixture_positions = [(x, z) for z in zs for x in xs]
        else:
            fixture_positions = [(0.0, 0.0)]

    # ── Performance cap ───────────────────────────────────────────────────────
    # Rendering >400 fixtures per-pixel is slow. Sub-sample a centred patch of
    # the grid and scale intensity to preserve total luminous flux.
    MAX_FIXTURES = 400
    total_fixture_count = len(fixture_positions)
    if total_fixture_count > MAX_FIXTURES:
        ratio    = _math.sqrt(MAX_FIXTURES / total_fixture_count)
        keep_nx  = max(1, round(nx * ratio))
        keep_ny  = max(1, round(ny * ratio))
        xs_k = [-(keep_nx - 1) * sx / 2 + c * sx for c in range(keep_nx)]
        zs_k = [-(keep_ny - 1) * sy / 2 + r * sy for r in range(keep_ny)]
        fixture_positions    = [(x, z) for z in zs_k for x in xs_k]
        sampled_count        = len(fixture_positions)
        # Scale up so brightness matches all fixtures
        intensity *= total_fixture_count / max(sampled_count, 1)

    W         = min(int(g("w",  768)), 1024)   # hard-cap: 1024 max
    PH        = min(int(g("h",  384)), 512)    # hard-cap: 512 max

    # ── Render cache check ────────────────────────────────────────────────────
    _ck = _cache_key(sid, room_w, room_l, room_h, fixture_h, intensity, ct,
                     W, PH, str(sorted(fixture_positions)))
    _cached = _cache_get(_ck)
    if _cached:
        return jsonify(_cached)

    # ── Build candela lookup arrays ───────────────────────────────────────────
    va  = _np.array(ies.vertical_angles,   dtype=_np.float64)
    ha  = _np.array(ies.horizontal_angles, dtype=_np.float64)
    mat = _np.array([ies.candela_values[h] for h in ies.horizontal_angles],
                    dtype=_np.float64)   # (nH, nV)
    nH, nV = mat.shape
    max_ha = float(ha[-1])

    def lookup(v_flat, h_flat):
        v = _np.clip(v_flat.ravel(), va[0], va[-1])
        h = (_np.fmod(_np.fmod(h_flat.ravel(), 360.0) + 360.0, 360.0))
        if max_ha <= 90.5:
            h = _np.where(h > 270.0, 360.0 - h, h)
            h = _np.where(h > 180.0, h - 180.0,  h)
            h = _np.where(h >  90.0, 180.0 - h,  h)
        elif max_ha <= 180.5:
            h = _np.where(h > 180.0, 360.0 - h, h)
        h = _np.zeros_like(h) if nH == 1 else _np.clip(h, ha[0], ha[-1])
        with _np.errstate(divide="ignore", invalid="ignore"):
            hi  = _np.clip(_np.searchsorted(ha, h, "right") - 1, 0, nH - 2)
            dha = _np.where(ha[hi+1] > ha[hi], ha[hi+1] - ha[hi], 1.0)
            ht  = _np.clip((h - ha[hi]) / dha, 0.0, 1.0)
            vi  = _np.clip(_np.searchsorted(va, v, "right") - 1, 0, nV - 2)
            dva = _np.where(va[vi+1] > va[vi], va[vi+1] - va[vi], 1.0)
            vt  = _np.clip((v - va[vi]) / dva, 0.0, 1.0)
        hi1 = _np.minimum(hi + 1, nH - 1)
        vi1 = _np.minimum(vi + 1, nV - 1)
        c   = (  mat[hi,  vi ] * (1-vt) + mat[hi,  vi1] * vt) * (1-ht) \
            + (  mat[hi1, vi ] * (1-vt) + mat[hi1, vi1] * vt) * ht
        return c * intensity

    # ── Ray grid  (equirectangular) ───────────────────────────────────────────
    cam_y  = 1.2                    # eye level (m)
    ceil_y = room_h
    sx     = room_w / 2.0           # half-width  (X axis)
    sz     = room_l / 2.0           # half-length (Z axis)

    # ── Camera XZ: snap to fixture nearest the room centre ───────────────────
    # For large rooms (e.g. 200x150 m) standing at 0,0 makes all fixtures look
    # dim (inverse-square law).  Placing the camera directly under the closest
    # fixture gives a representative view of real lighting quality.
    if fixture_positions:
        cam_fx, cam_fz = min(fixture_positions, key=lambda p: p[0]**2 + p[1]**2)
    else:
        cam_fx, cam_fz = 0.0, 0.0
    INF    = 1e30

    lon = (_np.arange(W,  dtype=_np.float64) / W  - 0.5) * 2.0 * _math.pi
    lat = (0.5 - _np.arange(PH, dtype=_np.float64) / PH) * _math.pi
    LON, LAT = _np.meshgrid(lon, lat)
    RX = _np.cos(LAT) * _np.sin(LON)
    RY = _np.sin(LAT)
    RZ = _np.cos(LAT) * _np.cos(LON)

    # ── Ray → box intersection ────────────────────────────────────────────────
    t_hit = _np.full((PH, W), INF, dtype=_np.float64)
    NX    = _np.zeros((PH, W), dtype=_np.float64)
    NY    = _np.zeros((PH, W), dtype=_np.float64)
    NZ    = _np.zeros((PH, W), dtype=_np.float64)

    def hit_plane(Rcomp, O_val, p_val, nx, ny, nz, bounds_fn):
        with _np.errstate(divide="ignore", invalid="ignore"):
            t = _np.where(_np.abs(Rcomp) > 1e-9, (p_val - O_val) / Rcomp, INF)
        t = _np.where(t > 1e-4, t, INF)
        hx = cam_fx + RX * t
        hy = cam_y  + RY * t
        hz = cam_fz + RZ * t
        t  = _np.where(bounds_fn(hx, hy, hz), t, INF)
        upd = t < t_hit
        _np.copyto(t_hit, t,  where=upd)
        _np.copyto(NX,    nx, where=upd)
        _np.copyto(NY,    ny, where=upd)
        _np.copyto(NZ,    nz, where=upd)

    hit_plane(RY, cam_y, 0.0,   0,  1, 0,
              lambda hx,hy,hz: (_np.abs(hx)<=sx) & (_np.abs(hz)<=sz))   # floor
    hit_plane(RY, cam_y, ceil_y, 0, -1, 0,
              lambda hx,hy,hz: (_np.abs(hx)<=sx) & (_np.abs(hz)<=sz))   # ceiling
    hit_plane(RX, cam_fx, -sx,  1, 0, 0,
              lambda hx,hy,hz: (hy>=0)&(hy<=ceil_y)&(_np.abs(hz)<=sz))  # wall -X
    hit_plane(RX, cam_fx,  sx, -1, 0, 0,
              lambda hx,hy,hz: (hy>=0)&(hy<=ceil_y)&(_np.abs(hz)<=sz))  # wall +X
    hit_plane(RZ, cam_fz, -sz,  0, 0,  1,
              lambda hx,hy,hz: (hy>=0)&(hy<=ceil_y)&(_np.abs(hx)<=sx))  # wall -Z
    hit_plane(RZ, cam_fz,  sz,  0, 0, -1,
              lambda hx,hy,hz: (hy>=0)&(hy<=ceil_y)&(_np.abs(hx)<=sx))  # wall +Z

    # ── Illuminance — sum contributions from ALL fixtures ─────────────────────
    missed = t_hit >= INF * 0.5
    t_safe = _np.where(missed, 1.0, t_hit)
    HX  = cam_fx + RX * t_safe   # hit-point X (room-centred)
    HY  = cam_y  + RY * t_safe   # hit-point Y
    HZ  = cam_fz + RZ * t_safe   # hit-point Z

    REFL = _np.where(NY > 0.5, 0.40,
           _np.where(NY < -0.5, 0.85, 0.72))

    RAD = _np.zeros((PH, W), dtype=_np.float64)
    # Batch all fixtures together using numpy broadcasting for speed
    _fp_arr = _np.array(fixture_positions, dtype=_np.float64)  # (F, 2)
    _FX = _fp_arr[:, 0][:, None, None]  # (F,1,1)
    _FZ = _fp_arr[:, 1][:, None, None]  # (F,1,1)
    _DX  = HX[None] - _FX              # (F,PH,W)
    _DY  = _np.full_like(_DX, HY[None] - fixture_h) if True else None
    _DY  = (HY - fixture_h)[None] * _np.ones_like(_DX)
    _DZ  = HZ[None] - _FZ
    _D2  = _DX*_DX + _DY*_DY + _DZ*_DZ
    _D   = _np.sqrt(_D2) + 1e-6
    _V_ANG = _np.degrees(_np.arccos(_np.clip(-_DY / _D, -1.0, 1.0)))
    _H_ANG = (_np.degrees(_np.arctan2(_DZ, _DX)) + 360.0) % 360.0
    # Process each fixture lookup (lookup is not batched over F dim, call in loop but avoid py overhead)
    for _fi in range(len(fixture_positions)):
        _CD  = lookup(_V_ANG[_fi], _H_ANG[_fi]).reshape(PH, W)
        _COS = _np.maximum(0.0, -(_DX[_fi]*NX + _DY[_fi]*NY + _DZ[_fi]*NZ) / _D[_fi])
        RAD += _CD * _COS / (_D2[_fi] + 1e-9) * REFL

    RAD = _np.where(missed, 0.0, RAD)

    # ── Tone mapping ──────────────────────────────────────────────────────────
    valid = RAD[~missed]
    p99   = float(_np.percentile(valid, 99)) if valid.size > 0 else 1.0
    p99   = max(p99, 1e-4)
    T     = _np.log1p(RAD / p99 * 10.0) / _math.log1p(10.0)
    T     = _np.clip(T ** 0.68, 0.0, 1.0)

    CT = {"warm":    (1.00, 0.84, 0.54),
          "neutral": (1.00, 0.96, 0.82),
          "cool":    (0.82, 0.92, 1.00)}
    r, g, b = CT.get(ct, CT["warm"])

    img8 = (_np.stack([
        _np.clip(T * r + 0.012, 0, 1),
        _np.clip(T * g + 0.012, 0, 1),
        _np.clip(T * b + 0.012, 0, 1),
    ], axis=-1) * 255).astype(_np.uint8)

    pil = _PILImage.fromarray(img8, "RGB")
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=82, optimize=False, progressive=False)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()

    # ── Cache this render ─────────────────────────────────────────────────────
    _cache_set(_ck, {"image": img_b64, "width": W, "height": PH})

    return jsonify({"image": img_b64, "width": W, "height": PH})

@ies_bp.route("/floorplan", methods=["GET", "POST"])
def floorplan():
    """
    Render a top-down false-colour illuminance heatmap for the full room.
    All fixture positions contribute at work-plane height (0.85 m default).

    Accepts same params as /panorama:
      sid, room_w, room_l, fixture_h, intensity, ct,
      fixture_positions (JSON array), layout_nx/ny + spacing_x/y,
      w, h  -> output image size (default 800x600)
    """
    import json as _json_mod
    if request.method == "POST":
        args = request.get_json(force=True) or {}
        g = args.get
    else:
        g = request.args.get

    sid   = g("sid", "")
    sess  = _sess(sid)
    ies   = sess["ies"]

    room_w    = float(g("room_w",    g("room_sz", 6.0)))
    room_l    = float(g("room_l",    g("room_sz", 6.0)))
    room_h    = float(g("room_h",    3.0))
    fixture_h = float(g("fixture_h", room_h * 0.80))
    fixture_h = min(fixture_h, room_h - 0.05)
    intensity    = float(g("intensity", 1.0))
    ct           = g("ct", "warm")
    # Apply the same flux scaling as the calculation engine so absolute lux matches
    intensity   *= _flux_scale_for_session(sess)
    W         = min(int(g("w", 600)), 1024)   # hard-cap
    H         = min(int(g("h", 450)), 768)    # hard-cap
    work_h    = float(g("work_h", 0.85))   # work-plane height (m)

    # ── Fixture positions (same logic as panorama) ────────────────────────────
    fixture_positions = None
    raw_fp = g("fixture_positions", None)
    if raw_fp:
        try:
            if isinstance(raw_fp, str):
                raw_fp = _json_mod.loads(raw_fp)
            fixture_positions = [(float(p[0]), float(p[1])) for p in raw_fp]
        except Exception:
            fixture_positions = None

    if not fixture_positions:
        nx = int(float(g("layout_nx", 1) or 1))
        ny = int(float(g("layout_ny", 1) or 1))
        sx = float(g("spacing_x", room_w / max(nx, 1)))
        sy = float(g("spacing_y", room_l / max(ny, 1)))
        if nx > 1 or ny > 1:
            xs = [-(nx - 1) * sx / 2 + c * sx for c in range(nx)]
            zs = [-(ny - 1) * sy / 2 + r * sy for r in range(ny)]
            fixture_positions = [(x, z) for z in zs for x in xs]
        else:
            fixture_positions = [(0.0, 0.0)]

    # ── Render cache check ────────────────────────────────────────────────────
    _fck = _cache_key(sid, room_w, room_l, room_h, fixture_h, intensity, ct,
                      W, H, str(sorted(fixture_positions)))
    _fcached = _cache_get(_fck)
    if _fcached:
        return jsonify(_fcached)

    # ── IES candela lookup ────────────────────────────────────────────────────
    va  = _np.array(ies.vertical_angles,   dtype=_np.float64)
    ha  = _np.array(ies.horizontal_angles, dtype=_np.float64)
    mat = _np.array([ies.candela_values[h] for h in ies.horizontal_angles],
                    dtype=_np.float64)
    nH, nV = mat.shape
    max_ha  = float(ha[-1])

    def lookup(v_flat, h_flat):
        v = _np.clip(v_flat.ravel(), va[0], va[-1])
        h = (_np.fmod(_np.fmod(h_flat.ravel(), 360.0) + 360.0, 360.0))
        if max_ha <= 90.5:
            h = _np.where(h > 270.0, 360.0 - h, h)
            h = _np.where(h > 180.0, h - 180.0,  h)
            h = _np.where(h >  90.0, 180.0 - h,  h)
        elif max_ha <= 180.5:
            h = _np.where(h > 180.0, 360.0 - h, h)
        h = _np.zeros_like(h) if nH == 1 else _np.clip(h, ha[0], ha[-1])
        with _np.errstate(divide="ignore", invalid="ignore"):
            hi  = _np.clip(_np.searchsorted(ha, h, "right") - 1, 0, nH - 2)
            dha = _np.where(ha[hi+1] > ha[hi], ha[hi+1] - ha[hi], 1.0)
            ht  = _np.clip((h - ha[hi]) / dha, 0.0, 1.0)
            vi  = _np.clip(_np.searchsorted(va, v, "right") - 1, 0, nV - 2)
            dva = _np.where(va[vi+1] > va[vi], va[vi+1] - va[vi], 1.0)
            vt  = _np.clip((v - va[vi]) / dva, 0.0, 1.0)
        hi1 = _np.minimum(hi + 1, nH - 1)
        vi1 = _np.minimum(vi + 1, nV - 1)
        c   = (  mat[hi,  vi ] * (1-vt) + mat[hi,  vi1] * vt) * (1-ht) \
            + (  mat[hi1, vi ] * (1-vt) + mat[hi1, vi1] * vt) * ht
        return c * intensity

    # ── Build work-plane grid ─────────────────────────────────────────────────
    # Grid covers the full room floor at work-plane height
    xs_grid = _np.linspace(-room_w/2, room_w/2, W)
    zs_grid = _np.linspace(-room_l/2, room_l/2, H)
    GX, GZ  = _np.meshgrid(xs_grid, zs_grid)   # (H, W)

    DY_fix  = work_h - fixture_h                # always negative (fixture above work-plane)
    LUX_MAP = _np.zeros((H, W), dtype=_np.float64)

    for (fx, fz) in fixture_positions:
        DX  = GX - fx
        DZ  = GZ - fz
        DY  = _np.full_like(DX, DY_fix)
        D2  = DX*DX + DY*DY + DZ*DZ
        D   = _np.sqrt(D2) + 1e-6
        # Vertical angle from fixture downward
        V_ANG = _np.degrees(_np.arccos(_np.clip(-DY / D, -1.0, 1.0)))
        H_ANG = (_np.degrees(_np.arctan2(DZ, DX)) + 360.0) % 360.0
        CD    = lookup(V_ANG, H_ANG).reshape(H, W)
        # cos(incidence) on horizontal work-plane = -DY/D (upward normal)
        COS   = _np.maximum(0.0, -DY / D)
        LUX_MAP += CD * COS / (D2 + 1e-9)

    # ── Colour map: infrared false-colour (black→purple→red→orange→yellow→white)
    # Normalise to p99 so hotspots don't crush the scale
    p99   = float(_np.percentile(LUX_MAP, 99))
    p01   = float(_np.percentile(LUX_MAP,  1))
    p99   = max(p99, 1e-4)
    T     = _np.clip(LUX_MAP / p99, 0.0, 1.2)

    # False-colour: black(0) → deep-blue(0.1) → blue(0.2) → cyan(0.35)
    #               → green(0.5) → yellow(0.7) → red(0.85) → white(1.0+)
    def fc(t):
        t = _np.clip(t, 0.0, 1.2)
        r = _np.clip( 4*(t - 0.5),  0, 1) * _np.clip(4*(1.0 - t) + 1, 0, 1) + _np.clip(t - 0.9, 0, 1) * 5
        g = _np.clip( 4*(t - 0.25), 0, 1) * _np.clip(4*(0.75- t) + 1, 0, 1)
        b = _np.clip( 4*(0.5 - t),  0, 1) + _np.clip(4*(t - 0.85), 0, 1)
        return _np.clip(r,0,1), _np.clip(g,0,1), _np.clip(b,0,1)

    R, G, B = fc(T)

    # ── Draw fixture positions as small white dots ────────────────────────────
    for (fx, fz) in fixture_positions:
        px = int((fx + room_w/2) / room_w * (W-1))
        pz = int((fz + room_l/2) / room_l * (H-1))
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx*dx + dy*dy <= 4:
                    ix, iz = _np.clip(px+dx, 0, W-1), _np.clip(pz+dy, 0, H-1)
                    R[iz, ix] = 1.0; G[iz, ix] = 1.0; B[iz, ix] = 1.0

    img8 = (_np.stack([R, G, B], axis=-1) * 255).astype(_np.uint8)

    # ── Compute stats for overlay ─────────────────────────────────────────────
    e_avg = float(_np.mean(LUX_MAP))
    e_min = float(_np.min(LUX_MAP))
    e_max = float(_np.max(LUX_MAP))

    pil = _PILImage.fromarray(img8, "RGB")
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=82, optimize=False, progressive=False)
    buf.seek(0)
    _fimg_b64 = base64.b64encode(buf.read()).decode()
    _fresult = {
        "image":   _fimg_b64,
        "width":   W,
        "height":  H,
        "e_avg":   round(e_avg, 1),
        "e_min":   round(e_min, 1),
        "e_max":   round(e_max, 1),
        "fixtures": len(fixture_positions),
    }
    _cache_set(_fck, _fresult)
    return jsonify(_fresult)