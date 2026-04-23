"""
Resolve catalog ``.ies`` paths from the active fixture map JSON (see
``luxscale.ies_dataset_config.active_fixture_map_basename``).

Falls back to ``fixture_ies_catalog.merged_ies_relative_map`` when the map JSON is missing
or has no matching row.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional

from luxscale.ies_dataset_config import active_fixture_map_basename
from luxscale.paths import project_root


@lru_cache(maxsize=4)
def _load_fixture_map_document_impl(basename: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(project_root(), "assets", basename)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_fixture_map_document() -> Optional[Dict[str, Any]]:
    return _load_fixture_map_document_impl(active_fixture_map_basename())


def fixture_entry_for_api(
    luminaire_name: str, power_w: float
) -> Optional[Dict[str, Any]]:
    doc = load_fixture_map_document()
    if not doc:
        return None
    pw = int(power_w)
    name = (luminaire_name or "").strip()
    for e in doc.get("entries") or []:
        if e.get("api_luminaire_name") == name and int(e.get("power_w", -1)) == pw:
            return e
    return None


def clear_fixture_map_cache() -> None:
    _load_fixture_map_document_impl.cache_clear()
    try:
        from luxscale.fixture_online_merge import clear_fixtures_online_cache

        clear_fixtures_online_cache()
    except Exception:
        pass
