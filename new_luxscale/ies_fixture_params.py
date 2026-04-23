"""
Resolve fixture ``.ies`` paths (from ``examples/SC_FIXED`` merged catalog) and read photometrics via ies-render IES_Parser.
Loads ies_parser.py directly so module/__init__.py (Qt/scipy/thumbnail) is not imported.
"""
from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from typing import Any, Dict, Optional

from luxscale.paths import project_root

# new added after ieSControl update, to avoid circular imports between photometry_ies_adapter and this module.
from luxscale.ies_analyzer import parse_ies_file as _ies_analyze_parse, estimate_lumens as _estimate_lumens, compute_all_metrics as _compute_all_metrics
# TODO: eventually merge these into this module and remove photometry_ies_adapter.py, which is now just a thin wrapper around these functions for the catalog index / blob loading.
 
_REPO_ROOT = project_root()
IES_RENDER_ROOT = os.path.join(_REPO_ROOT, "ies-render")
_IES_PARSER_PATH = os.path.join(IES_RENDER_ROOT, "module", "ies_parser.py")

_IES_PARSER_MOD = None


def _get_ies_parser_class():
    global _IES_PARSER_MOD
    if _IES_PARSER_MOD is None:
        spec = importlib.util.spec_from_file_location(
            "ies_parser_standalone", _IES_PARSER_PATH
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        _IES_PARSER_MOD = mod
    return _IES_PARSER_MOD.IES_Parser


def get_ies_parser_module():
    """Return loaded ``ies_parser`` module (provides ``IES_Parser``, ``IESData``)."""
    _get_ies_parser_class()
    return _IES_PARSER_MOD


def clear_ies_data_cache() -> None:
    """Call after regenerating ``ies.json`` / blobs so photometry reloads."""
    _load_ies_data_cached.cache_clear()


@lru_cache(maxsize=128)
def _load_ies_data_cached(ies_path: str):
    """Prefer catalog index + JSON blob (same numerics as LM-63 parse); else parse ``.ies``."""
    npth = os.path.normpath(ies_path)
    from luxscale.photometry_ies_adapter import try_load_ies_data_via_catalog

    data = try_load_ies_data_via_catalog(npth)
    if data is not None:
        return data
    IES_Parser = _get_ies_parser_class()
    return IES_Parser(npth).ies_data


def _candela_row_for_horizontal(ies_data, h: float) -> Optional[list]:
    """Resolve candela list for horizontal angle ``h`` (exact key or nearest tabulated)."""
    try:
        cv = ies_data.candela_values
        if h in cv:
            return list(cv[h])
        hs = sorted(cv.keys())
        if not hs:
            return None
        nearest = min(hs, key=lambda x: abs(float(x) - float(h)))
        return list(cv[nearest])
    except (TypeError, KeyError, AttributeError):
        return None


def approx_beam_angle_deg_for_horizontal(
    ies_data,
    horizontal_deg: float,
    *,
    threshold: float = 0.5,
) -> Optional[float]:
    """
    Full beam angle (degrees) from one horizontal slice: 50 % peak crossing on vertical
    angles, doubled (same convention as ``ies_viewer._approx_beam_angle_deg``).
    """
    if ies_data is None:
        return None
    try:
        candela = _candela_row_for_horizontal(ies_data, horizontal_deg)
        angles = ies_data.vertical_angles
    except (TypeError, AttributeError):
        return None

    if not candela or len(candela) < 2:
        return None

    peak = max(float(c) for c in candela)
    if peak <= 0:
        return None
    cutoff = float(threshold) * peak

    half_angle = None
    for i in range(len(candela) - 1):
        c0, c1 = float(candela[i]), float(candela[i + 1])
        a0, a1 = float(angles[i]), float(angles[i + 1])
        if c0 >= cutoff >= c1:
            denom = c0 - c1
            t = (c0 - cutoff) / denom if denom != 0 else 0.0
            half_angle = a0 + t * (a1 - a0)
            break

    if half_angle is None:
        return None
    # Signed full angle from one vertical slice; caller takes abs for magnitude / display.
    return float(2.0 * half_angle)


def beam_angle_deg_min_max_from_ies(
    ies_data, *, threshold: float = 0.5
) -> tuple[Optional[float], Optional[float], Optional[float], bool]:
    """
    Across all horizontal planes: (narrowest full beam, widest full beam, first-slice full beam,
    had_negative_signed_angle).

    Asymmetric Type C files (e.g. 50°×20°) yield different angles per H; the narrowest
    slice is used as the primary ``beam_angle_deg`` for conservative layout labels.
    """
    if ies_data is None:
        return None, None, None, False
    try:
        hs = sorted(float(h) for h in (ies_data.horizontal_angles or []))
    except (TypeError, ValueError, AttributeError):
        return None, None, None, False
    if not hs:
        return None, None, None, False

    vals: list[float] = []
    first_slice: Optional[float] = None
    any_negative_signed = False
    for h in hs:
        b = approx_beam_angle_deg_for_horizontal(ies_data, h, threshold=threshold)
        if b is not None:
            bf = float(b)
            if bf < 0:
                any_negative_signed = True
            mag = abs(bf)
            vals.append(mag)
            if first_slice is None:
                first_slice = mag

    if not vals and threshold >= 0.5:
        return beam_angle_deg_min_max_from_ies(ies_data, threshold=0.1)

    if not vals:
        return None, None, None, False

    return min(vals), max(vals), first_slice, any_negative_signed


def approx_beam_angle_deg(ies_data, *, threshold: float = 0.5) -> Optional[float]:
    """
    Backward-compatible: **narrowest** full beam across H planes (was first slice only;
    that often failed or hid asymmetric beams). For range metadata use
    :func:`beam_angle_deg_min_max_from_ies`.
    """
    mn, _, _, _ = beam_angle_deg_min_max_from_ies(ies_data, threshold=threshold)
    return mn


def resolve_ies_path(luminaire_name: str, power_w: float) -> Optional[str]:
    """Resolve path from the active fixture map JSON when present; else merged IES catalog."""
    from luxscale.fixture_catalog import fixture_entry_for_api

    entry = fixture_entry_for_api(luminaire_name, power_w)
    if entry and entry.get("ies_file_exists"):
        full = os.path.normpath(
            os.path.join(IES_RENDER_ROOT, entry["relative_ies_path"])
        )
        if os.path.isfile(full):
            return full
    from luxscale.fixture_ies_catalog import merged_ies_relative_map, normalize_relative_ies_path

    key = (luminaire_name, int(power_w))
    rel = merged_ies_relative_map().get(key)
    if not rel:
        return None
    rel_norm = normalize_relative_ies_path(rel)
    full = os.path.normpath(os.path.join(IES_RENDER_ROOT, rel_norm))
    if os.path.isfile(full):
        return full
    return None


# def ies_params_for_file(ies_path: str) -> Dict[str, Any]:
    if not os.path.isfile(ies_path):
        raise FileNotFoundError(ies_path)
    d = _load_ies_data_cached(os.path.normpath(ies_path))
    lumens = float(d.lumens_per_lamp) * float(d.multiplier)
    b_min, b_max, b_first, beam_angle_ies_signed_vertical = beam_angle_deg_min_max_from_ies(
        d, threshold=0.5
    )
    asymmetric = (
        b_min is not None
        and b_max is not None
        and (float(b_max) - float(b_min)) > 3.0
    )
    def _pos_beam(x: Optional[float]) -> Optional[float]:
        if x is None:
            return None
        try:
            return abs(float(x))
        except (TypeError, ValueError):
            return None

    return {
        "ies_path": ies_path,
        "lumens_per_lamp": lumens,
        "num_lamps": int(d.num_lamps),
        "max_candela": float(d.max_value),
        "shape": d.shape,
        "opening_width_m": float(d.width),
        "opening_length_m": float(d.length),
        "opening_height_m": float(d.height),
        # Primary label: narrowest cone across H planes (conservative); not nominal 120°.
        "beam_angle_deg": _pos_beam(b_min),
        "beam_angle_deg_max": _pos_beam(b_max),
        "beam_angle_deg_first_slice": _pos_beam(b_first),
        "beam_angle_asymmetric": asymmetric,
        # True if any vertical slice produced a negative angle before taking magnitude (IES axis sign).
        "beam_angle_ies_signed_vertical": bool(beam_angle_ies_signed_vertical),
    }

def ies_params_for_file(ies_path: str) -> Dict[str, Any]:
    if not os.path.isfile(ies_path):
        raise FileNotFoundError(ies_path)

    # Parse with the accurate analyzer
    ies = _ies_analyze_parse(ies_path)
    metrics = _compute_all_metrics(ies)

    # Use integrated lumens (zonal flux method) — falls back to header if needed
    integrated_lumens = metrics.get("total_lumens", 0)
    header_lumens = float(ies.lumens_per_lamp) * float(ies.multiplier) * float(ies.num_lamps)

    # Prefer integrated lumens; use header as fallback if integration gives 0
    lumens = integrated_lumens if integrated_lumens > 0 else max(header_lumens, 0)

    # Beam angles — use global peak method (more accurate than per-slice minimum)
    beam_50 = metrics.get("beam_angle")      # 50% threshold = standard beam angle
    field_10 = metrics.get("field_angle")    # 10% threshold = field angle

    # Per-H asymmetry check
    per_h = metrics.get("per_h", {})
    h_beams = [v["beam"] for v in per_h.values() if v["beam"] is not None]
    b_min = min(h_beams) if h_beams else beam_50
    b_max = max(h_beams) if h_beams else beam_50
    asymmetric = (b_min is not None and b_max is not None and (b_max - b_min) > 3.0)

    return {
        "ies_path": ies_path,
        "lumens_per_lamp": lumens / max(ies.num_lamps, 1),
        "lumens_total": lumens,
        "lumens_integrated": integrated_lumens,     # NEW — from candela data
        "lumens_header": header_lumens,             # NEW — from IES header
        "num_lamps": int(ies.num_lamps),
        "max_candela": float(ies.max_value),
        "shape": ies.shape,
        "opening_width_m": float(ies.width),
        "opening_length_m": float(ies.length),
        "opening_height_m": float(ies.height),
        "beam_angle_deg": beam_50,                  # UPGRADED — global peak method
        "beam_angle_deg_max": b_max,
        "beam_angle_deg_first_slice": beam_50,
        "field_angle_deg": field_10,                # NEW — 10% threshold
        "beam_angle_asymmetric": asymmetric,
        "beam_angle_ies_signed_vertical": False,
        "efficacy_pct": metrics.get("efficacy_approx"),  # NEW — LOR %
    }