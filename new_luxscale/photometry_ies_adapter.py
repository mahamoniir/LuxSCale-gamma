"""
Build ``IESData`` (LM-63 photometric web) from the catalog index + JSON blobs.

When ``ies-render/ies.json`` lists ``photometry_json`` and the blob exists, we use the
same numeric arrays the builder extracted from ``IES_Parser`` — so illuminance and
uniformity math matches parsing the ``.ies`` file directly, without LM-63 text round-trip.

Fallback: parse ``.ies`` with ``IES_Parser`` (``luxscale.ies_fixture_params``).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from luxscale.ies_json_loader import index_entry_by_relative_path, load_photometry_blob
from luxscale.paths import project_root


def ies_render_root() -> str:
    return os.path.join(project_root(), "ies-render")


def absolute_ies_path_to_relative(abs_path: str) -> Optional[str]:
    """Path under ``ies-render/``, forward slashes, or ``None`` if outside tree."""
    irr = os.path.normpath(ies_render_root())
    np = os.path.normpath(abs_path)
    if not np.lower().endswith(".ies"):
        return None
    try:
        rel = os.path.relpath(np, irr)
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    return rel.replace("\\", "/")


def ies_data_from_index_and_blob(index_entry: Dict[str, Any], blob: Dict[str, Any]) -> Any:
    """
    Construct parser ``IESData`` from manifest row + photometry blob.

    Candela rows are keyed by horizontal angle (float) exactly as ``IES_Parser`` uses.
    """
    from luxscale.ies_fixture_params import get_ies_parser_module

    mod = get_ies_parser_module()
    IESData = mod.IESData

    header = index_entry["header"]
    p = blob["photometry"]
    ha = [float(x) for x in p["horizontal_angles_deg"]]
    va = [float(x) for x in p["vertical_angles_deg"]]
    raw_cd: Dict[str, Any] = p["candela_by_horizontal_deg"]

    candela_values: Dict[float, list] = {}
    for angle in ha:
        key = str(float(angle))
        row = raw_cd.get(key)
        if row is None:
            row = raw_cd.get(str(angle))
        if row is None:
            raise KeyError(f"missing candela row for horizontal angle {angle}")
        candela_values[float(angle)] = [float(v) for v in row]

    max_cd = float(p.get("max_candela") or 0.0)
    if max_cd <= 0 and candela_values:
        max_cd = max(max(row) for row in candela_values.values())

    # Preserve LM-63 type metadata when loading via catalog JSON.
    ptype = int(
        p.get(
            "photometric_type",
            header.get("photometric_type", 1),
        )
        or 1
    )
    if ptype not in (1, 2, 3):
        ptype = 1
    ptype_name = str(
        p.get(
            "photometric_type_name",
            header.get("photometric_type_name", "C"),
        )
        or "C"
    )
    v_label = str(
        p.get(
            "vertical_angle_label",
            header.get("vertical_angle_label", "gamma"),
        )
        or "gamma"
    )
    h_label = str(
        p.get(
            "horizontal_angle_label",
            header.get("horizontal_angle_label", "C"),
        )
        or "C"
    )

    return IESData(
        va,
        ha,
        candela_values,
        max_cd,
        int(header["num_lamps"]),
        float(header["lumens_per_lamp"]),
        float(header["multiplier"]),
        float(header["opening_width_m"]),
        float(header["opening_length_m"]),
        float(header["opening_height_m"]),
        str(header["shape"]),
        ptype,
        ptype_name,
        v_label,
        h_label,
    )


def try_load_ies_data_via_catalog(abs_ies_path: str) -> Optional[Any]:
    """
    Return ``IESData`` from catalog JSON if available; else ``None`` (caller parses ``.ies``).
    """
    rel = absolute_ies_path_to_relative(abs_ies_path)
    if not rel:
        return None
    entry = index_entry_by_relative_path(rel)
    if not entry or entry.get("status") != "ok":
        return None
    blob = load_photometry_blob(rel)
    if not blob:
        return None
    try:
        return ies_data_from_index_and_blob(entry, blob)
    except (KeyError, TypeError, ValueError):
        return None
