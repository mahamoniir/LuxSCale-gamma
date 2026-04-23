"""
Storefront data from ``assets/fixtures_online.json``.

- **Database filter:** only luminaire + wattage rows whose mapped ``product_id`` exists on
  the site and has a non-empty ``images`` list are included in
  ``fixture_ies_catalog.merged_ies_relative_map`` (see ``calc_keys_allowed_by_storefront``).
- **fixture_map:** ``apply_online_to_entries`` attaches ``online`` (URL, title, …) to each row.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

from luxscale.paths import project_root

# (api_luminaire_name exact case as in API, power_w, fixtures_online product id, match_note or None)
# Aligned with ``examples/SC_FIXED`` merged catalog only.
_ONLINE_BY_API: List[Tuple[str, int, str, Optional[str]]] = [
    (
        "SC backlight",
        32,
        "sc-panel-36",
        "SC_FIXED 32W panel; storefront uses 36W panel imagery.",
    ),
    (
        "SC backlight",
        35,
        "sc-panel-36",
        "SC_FIXED 35W panel; storefront 36W family page.",
    ),
    (
        "SC downlight",
        9,
        "sc-spot",
        "API 9W uses SC_SPOT 10W IES in SC_FIXED.",
    ),
    ("SC downlight", 10, "sc-spot", None),
    ("SC flood light exterior", 100, "sc-flood-100", None),
    (
        "SC flood light exterior",
        150,
        "sc-flood-100",
        "150W GL-FL SC_FIXED; grouped with 100W/150W storefront line.",
    ),
    ("SC flood light exterior", 200, "sc-flood-200", None),
    ("SC highbay", 100, "sc-high-bay", None),
    ("SC highbay", 150, "sc-high-bay", None),
    ("SC highbay", 200, "sc-high-bay", None),
    ("SC street", 30, "sc-street-100", "SC_FIXED 30W street IES."),
    ("SC street", 60, "sc-street-100", "SC_FIXED 60W street IES."),
    ("SC triproof", 30, "sc-triproof", None),
    ("SC triproof", 40, "sc-triproof", None),
    ("SV flood", 100, "sv-flood-100", None),
    ("SV flood", 150, "sv-flood-100", "150W SV flood SC_FIXED."),
    ("SV flood", 200, "sv-flood-200", None),
    ("SV flood", 300, "sv-flood-300", None),
]


def load_fixtures_online_path() -> str:
    return os.path.join(project_root(), "assets", "fixtures_online.json")


@lru_cache(maxsize=1)
def load_fixtures_online_document() -> Optional[Dict[str, Any]]:
    path = load_fixtures_online_path()
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clear_fixtures_online_cache() -> None:
    load_fixtures_online_document.cache_clear()


def published_product_ids_with_images(online_doc: Optional[Dict[str, Any]]) -> set[str]:
    """Product ``id`` values that have at least one image URL (published on site)."""
    if not online_doc:
        return set()
    out: set[str] = set()
    for cat in online_doc.get("categories") or []:
        for p in cat.get("products") or []:
            pid = p.get("id")
            if not pid:
                continue
            imgs = p.get("images")
            if isinstance(imgs, list) and len(imgs) > 0:
                out.add(str(pid))
    return out


def find_online_product(
    online_doc: Dict[str, Any], product_id: str
) -> Optional[Dict[str, Any]]:
    for cat in online_doc.get("categories") or []:
        for p in cat.get("products") or []:
            if p.get("id") == product_id:
                out = dict(p)
                out["_category_id"] = cat.get("id")
                return out
    return None


def _link_for_api_power(api_name: str, power_w: int) -> Optional[Tuple[str, Optional[str]]]:
    for an, pw, pid, note in _ONLINE_BY_API:
        if an == api_name and int(pw) == int(power_w):
            return pid, note
    return None


def calc_keys_allowed_by_storefront(
    online_doc: Optional[Dict[str, Any]] = None,
) -> Optional[Set[Tuple[str, int]]]:
    """
    ``(api_luminaire_name, power_w)`` keys that may appear in the IES database.

    Requires a mapping in ``_ONLINE_BY_API`` and a **published** product (``images`` non-empty)
    in ``fixtures_online.json`` for that product id.

    Returns ``None`` if the storefront file is missing or has no published products — caller
    should treat that as “no filtering” (development fallback).
    """
    doc = online_doc if online_doc is not None else load_fixtures_online_document()
    if not doc:
        return None
    published = published_product_ids_with_images(doc)
    if not published:
        return None
    allowed: Set[Tuple[str, int]] = set()
    for api, pw, pid, _note in _ONLINE_BY_API:
        if pid not in published:
            continue
        prod = find_online_product(doc, pid)
        if not prod:
            continue
        imgs = prod.get("images")
        if not isinstance(imgs, list) or len(imgs) == 0:
            continue
        allowed.add((api.strip(), int(pw)))
    return allowed


def apply_online_to_entries(
    entries: List[Dict[str, Any]],
    online_doc: Optional[Dict[str, Any]] = None,
) -> None:
    """Mutates each entry: sets `online` when a mapping exists and product is found."""
    doc = (
        online_doc
        if online_doc is not None
        else load_fixtures_online_document()
    )
    if not doc:
        return
    for e in entries:
        api = (e.get("api_luminaire_name") or "").strip()
        pw = int(e.get("power_w", -1))
        hit = _link_for_api_power(api, pw)
        if not hit:
            continue
        product_id, match_note = hit
        prod = find_online_product(doc, product_id)
        if not prod:
            continue
        e["online"] = {
            "product_id": product_id,
            "product_url": prod.get("url"),
            "product_title": prod.get("title") or prod.get("name"),
            "category_id": prod.get("_category_id"),
            "match_note": match_note,
        }


def online_catalog_metadata(online_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    doc = online_doc if online_doc is not None else load_fixtures_online_document()
    if not doc:
        return {
            "file": "fixtures_online.json",
            "merged_at": None,
            "note": "fixtures_online.json not found; online block skipped.",
        }
    return {
        "file": "fixtures_online.json",
        "company": doc.get("company"),
        "website": doc.get("website"),
        "base_image_url": doc.get("base_image_url"),
        "generated_at": doc.get("generated_at"),
    }
