"""
Load the small ``ies-render/ies.json`` index and optional per-file photometry blobs
under ``ies-render/ies_json/``.

Paths are relative to the repository root (``luxscale.paths.project_root``).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from luxscale.paths import project_root


def ies_render_dir() -> str:
    return os.path.join(project_root(), "ies-render")


def ies_index_path() -> str:
    return os.path.join(ies_render_dir(), "ies.json")


def _blob_abs_path(photometry_json: str) -> str:
    """``photometry_json`` is relative to ``ies-render/`` (e.g. ``ies_json/...``)."""
    return os.path.normpath(os.path.join(ies_render_dir(), photometry_json))


@lru_cache(maxsize=1)
def load_ies_index() -> Dict[str, Any]:
    path = ies_index_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def index_entries() -> List[Dict[str, Any]]:
    return list(load_ies_index().get("entries") or [])


def index_entry_by_relative_path(relative_ies_path: str) -> Optional[Dict[str, Any]]:
    """``relative_ies_path`` uses forward slashes, relative to ``ies-render/``."""
    key = relative_ies_path.replace("\\", "/")
    for e in index_entries():
        if (e.get("relative_path") or "").replace("\\", "/") == key:
            return e
    return None


def load_photometry_blob(relative_ies_path: str) -> Optional[Dict[str, Any]]:
    """
    Load full photometry + polar for one catalog file.

    Returns ``None`` if the index has no ``photometry_json`` or the blob is missing.
    """
    entry = index_entry_by_relative_path(relative_ies_path)
    if not entry:
        return None
    ref = entry.get("photometry_json")
    if not ref:
        return None
    path = _blob_abs_path(str(ref))
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clear_index_cache() -> None:
    """After regenerating ``ies.json``, call this in tests or long-running tools."""
    load_ies_index.cache_clear()
