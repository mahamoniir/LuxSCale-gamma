"""
Runtime UI/calc settings merged from ``assets/app_settings.json`` (optional) and defaults.
Edited via admin dashboard or by hand; used by lighting_calc and Flask API.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from luxscale.paths import project_root

DEFAULT_SETTINGS: Dict[str, Any] = {
    "schema_version": 1,
    "ui": {
        "results_initial_count": 3,
        "results_batch_size": 3,
        "show_compliance_margin_fields": True,
    },
    "calc": {
        "max_solutions_total": 80,
        "interior_height_min_m": 2.0,
        "interior_height_max_m": 5.0,
        "exterior_height_min_m": 5.0,
        "exterior_height_max_m": 20.0,
        # Maintained illuminance design: output multiplier (lumen depreciation, dirt); typical 0.8–0.9.
        "maintenance_factor": 0.8,
        # Approximate inter-reflected light on the work plane (not full radiosity). Scales grid lx.
        "room_reflectance_preset": "medium",
    },
}

# Preset ids for ``calc.room_reflectance_preset``. ``indirect_fraction`` scales direct grid E (U0/U1 unchanged).
ROOM_REFLECTANCE_PRESETS: Dict[str, Dict[str, Any]] = {
    "direct_only": {
        "label": "Direct only (no inter-reflection estimate)",
        "indirect_fraction": 0.0,
    },
    "dark": {
        "label": "Dark room (ρ ceiling/wall/floor ≈ 0.5 / 0.3 / 0.2)",
        "indirect_fraction": 0.05,
    },
    "medium": {
        "label": "Medium (ρ ≈ 0.7 / 0.5 / 0.2)",
        "indirect_fraction": 0.12,
    },
    "light": {
        "label": "Light room (ρ ≈ 0.8 / 0.7 / 0.3)",
        "indirect_fraction": 0.18,
    },
}


def _settings_path() -> str:
    return os.path.join(project_root(), "assets", "app_settings.json")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=1)
def load_app_settings() -> Dict[str, Any]:
    path = _settings_path()
    if not os.path.isfile(path):
        return deepcopy(DEFAULT_SETTINGS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return deepcopy(DEFAULT_SETTINGS)
        return _deep_merge(DEFAULT_SETTINGS, data)
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_SETTINGS)


def save_app_settings(doc: Dict[str, Any]) -> None:
    path = _settings_path()
    merged = _deep_merge(DEFAULT_SETTINGS, doc)
    merged["schema_version"] = merged.get("schema_version") or 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    clear_app_settings_cache()


def clear_app_settings_cache() -> None:
    load_app_settings.cache_clear()


def get_interior_height_min_m() -> float:
    try:
        return float(load_app_settings()["calc"]["interior_height_min_m"])
    except (TypeError, ValueError, KeyError):
        return float(DEFAULT_SETTINGS["calc"]["interior_height_min_m"])


def get_interior_height_max_m() -> float:
    return float(load_app_settings()["calc"]["interior_height_max_m"])


def get_exterior_height_max_m() -> float:
    try:
        return float(load_app_settings()["calc"]["exterior_height_max_m"])
    except (TypeError, ValueError, KeyError):
        return float(DEFAULT_SETTINGS["calc"]["exterior_height_max_m"])


def validate_ceiling_height_m(height: float) -> Tuple[bool, Optional[str]]:
    """
    Interior zone: height < interior_height_max_m → allowed [interior_height_min_m, interior_height_max_m).
    Exterior zone: height ≥ interior_height_max_m → allowed [interior_height_max_m, exterior_height_max_m].
    """
    try:
        h = float(height)
    except (TypeError, ValueError):
        return False, "Not logical dimensions: invalid ceiling height."

    th = get_interior_height_max_m()
    h_min = get_interior_height_min_m()
    h_ext_max = get_exterior_height_max_m()

    if h < th:
        if h < h_min:
            return (
                False,
                f"Not logical dimensions: interior ceiling height must be between {h_min:g} m and {th:g} m "
                f"(below {th:g} m for indoor catalog).",
            )
        return True, None

    if h > h_ext_max:
        return (
            False,
            f"Not logical dimensions: exterior ceiling height must be between {th:g} m and {h_ext_max:g} m.",
        )
    return True, None


def get_maintenance_factor() -> float:
    """Design maintenance factor applied to emitted flux (typical 0.8–0.9 for LED interiors)."""
    try:
        v = float(load_app_settings()["calc"]["maintenance_factor"])
    except (TypeError, ValueError, KeyError):
        v = float(DEFAULT_SETTINGS["calc"]["maintenance_factor"])
    return max(0.35, min(1.0, v))


def get_room_reflectance_preset_id() -> str:
    try:
        v = str(load_app_settings()["calc"].get("room_reflectance_preset") or "").strip()
    except (AttributeError, KeyError, TypeError):
        v = ""
    if v and v in ROOM_REFLECTANCE_PRESETS:
        return v
    return "medium"


def get_inter_reflection_fraction() -> float:
    """Estimated indirect fraction applied to direct horizontal illuminance (not full cavity/radiosity)."""
    pid = get_room_reflectance_preset_id()
    p = ROOM_REFLECTANCE_PRESETS.get(pid) or ROOM_REFLECTANCE_PRESETS["medium"]
    try:
        return max(0.0, min(0.5, float(p.get("indirect_fraction", 0.0))))
    except (TypeError, ValueError):
        return 0.12


def get_room_reflectance_preset_label() -> str:
    pid = get_room_reflectance_preset_id()
    p = ROOM_REFLECTANCE_PRESETS.get(pid) or ROOM_REFLECTANCE_PRESETS["medium"]
    return str(p.get("label") or pid)


def get_max_solutions_total() -> int:
    """Maximum number of **compliant** (lux + Uo) options to return; search stops once this many are found."""
    try:
        n = int(load_app_settings()["calc"]["max_solutions_total"])
    except (TypeError, ValueError, KeyError):
        n = int(DEFAULT_SETTINGS["calc"]["max_solutions_total"])
    return max(1, min(n, 1000))


def get_ui_config() -> Dict[str, Any]:
    s = load_app_settings()
    return {
        "results_initial_count": int(s["ui"]["results_initial_count"]),
        "results_batch_size": int(s["ui"]["results_batch_size"]),
        "show_compliance_margin_fields": bool(s["ui"].get("show_compliance_margin_fields", True)),
        "ceiling_height_bounds": {
            "interior_min_m": get_interior_height_min_m(),
            "interior_max_m": get_interior_height_max_m(),
            "exterior_max_m": get_exterior_height_max_m(),
        },
        "maintenance_factor": get_maintenance_factor(),
        "room_reflectance_preset": get_room_reflectance_preset_id(),
        "room_reflectance_presets": [
            {"id": k, "label": str(v.get("label", k))}
            for k, v in ROOM_REFLECTANCE_PRESETS.items()
        ],
    }
