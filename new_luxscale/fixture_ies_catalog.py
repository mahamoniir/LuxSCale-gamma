"""
Merged IES catalog: scans ``ies-render/examples/<ACTIVE_DATASET>/*.ies`` (see
``luxscale.ies_dataset_config.active_ies_dataset``).

Used by ``ies_fixture_params.resolve_ies_path``, ``fixture_map_builder``, and
``catalog_luminaire_power_options`` / ``determine_luminaire``.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from luxscale.ies_dataset_config import active_ies_dataset
from luxscale.paths import project_root
from luxscale.sc_ies_scan import scan_examples_ies_dataset


def normalize_relative_ies_path(rel: str) -> str:
    """Path under ``ies-render/`` using forward slashes."""
    rel = rel.replace("\\", "/").lstrip("/")
    if rel.startswith("SC-ies/") or rel.startswith("examples/"):
        return rel
    if rel.startswith("SC-Database/"):
        return rel
    return ("SC-Database/" + rel).replace("//", "/")


def merged_ies_relative_map() -> Dict[Tuple[str, int], str]:
    """
    One row per ``(API luminaire, power W)`` from :func:`scan_examples_ies_dataset`
    for the active dataset folder, then restricted to products **published** on the
    storefront (see ``fixture_online_merge.calc_keys_allowed_by_storefront``): mapping in
    ``_ONLINE_BY_API`` and a product with non-empty ``images`` in ``fixtures_online.json``.

    If the storefront file is missing or has no published images, no filtering is applied
    (local development fallback).
    """
    from luxscale.fixture_online_merge import calc_keys_allowed_by_storefront

    m: Dict[Tuple[str, int], str] = {}
    for api, pw, rel in scan_examples_ies_dataset(active_ies_dataset()):
        m[(api, int(pw))] = rel

    allowed = calc_keys_allowed_by_storefront()
    if allowed is None:
        return m
    filtered = {k: m[k] for k in m if k in allowed}
    return filtered


def clear_fixture_ies_catalog_cache() -> None:
    """Placeholder if caching is added later."""
    pass


def _catalog_export_path() -> str:
    return os.path.join(project_root(), "assets", "fixture_ies_catalog.json")


def catalog_luminaire_power_options() -> Dict[str, List[int]]:
    """API luminaire name -> sorted distinct wattages from the merged catalog."""
    opts: Dict[str, List[int]] = {}
    for (name, pw) in merged_ies_relative_map().keys():
        opts.setdefault(name, []).append(int(pw))
    for name in opts:
        opts[name] = sorted(set(opts[name]))
    return opts


def write_fixture_ies_catalog_json(out_path: str | None = None) -> str:
    """Write merged-catalog snapshot JSON from current active IES dataset (for diff/review)."""
    if out_path is not None:
        path = out_path
    elif active_ies_dataset() == "SC_FIXED":
        path = _catalog_export_path()
    else:
        safe = active_ies_dataset().replace("/", "_").replace("\\", "_")
        path = os.path.join(project_root(), "assets", f"fixture_ies_catalog_{safe}.json")
    rows = []
    for (api, pw), rel in sorted(
        merged_ies_relative_map().items(), key=lambda x: (x[0][0], x[0][1])
    ):
        rows.append(
            {
                "api_luminaire_name": api,
                "power_w": int(pw),
                "relative_ies": rel,
            }
        )
    doc = {
        "schema_version": 1,
        "generated_note": (
            f"examples/{active_ies_dataset()} snapshot; runtime uses merged_ies_relative_map()."
        ),
        "entries": rows,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return path
