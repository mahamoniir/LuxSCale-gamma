"""
Fixtures lookup service — the "smart" fixture endpoint.

Two source files in ``assets/`` describe fixtures for very different purposes and
don't share a naming scheme:

  - the **fixture map** (``assets/<active_fixture_map_basename()>``, e.g.
    ``fixture_map_SC_IES_Fixed_v3.json``) is what the calculation engine actually
    reads: generic entries like ``{"api_luminaire_name": "SC flood light exterior",
    "power_w": 100, "relative_ies": "..."}``. This module never re-implements that
    resolution — it reuses ``luxscale.fixture_catalog`` so both stay in sync.

  - ``assets/fixtures_online.json`` is the real product catalog (names, product
    pages, images, spec sheets) grouped by marketing category, e.g.
    ``{"type": "Flood Light", "series": "SC", "specs": {"power": "100W / 150W", ...}}``.

This module merges the two: for every calc-engine fixture entry, it finds the best
matching real product (by type keyword + series prefix + power-in-range) and returns
one combined object with both the photometric reference and the sellable product info.
"""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Dict, List, Optional

try:
    from luxscale.paths import project_root
except Exception:  # pragma: no cover
    def project_root() -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from luxscale.fixture_catalog import load_fixture_map_document, clear_fixture_map_cache


def _assets_dir() -> str:
    return os.path.join(project_root(), "assets")


@lru_cache(maxsize=1)
def _load_products_doc() -> Dict[str, Any]:
    path = os.path.join(_assets_dir(), "fixtures_online.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clear_fixtures_lookup_cache() -> None:
    _load_products_doc.cache_clear()
    clear_fixture_map_cache()


def _all_products() -> List[Dict[str, Any]]:
    doc = _load_products_doc()
    out = []
    for cat in doc.get("categories") or []:
        for p in cat.get("products") or []:
            p = dict(p)
            p["category_id"] = cat.get("id")
            p["category_name"] = cat.get("name")
            out.append(p)
    return out


# ── name/type/power matching heuristics ──────────────────────────────────────

_TYPE_KEYWORDS = [
    ("backlight", "Panel"),
    ("downlight", "Spot"),
    ("spot", "Spot"),
    ("triproof", "Triproof"),
    ("highbay", "High Bay"),
    ("high bay", "High Bay"),
    ("street", "Street Light"),
    ("flood", "Flood Light"),
    ("panel", "Panel"),
    ("solar", "Solar Street Light"),
]


def _guess_product_type(api_luminaire_name: str) -> Optional[str]:
    name = (api_luminaire_name or "").lower()
    for needle, product_type in _TYPE_KEYWORDS:
        if needle in name:
            return product_type
    return None


def _guess_series(api_luminaire_name: str) -> Optional[str]:
    name = (api_luminaire_name or "").strip().lower()
    for prefix in ("sc", "sv", "eco"):
        if name.startswith(prefix + " ") or name == prefix:
            return prefix.upper()
    return None


def _power_values_in_spec(power_spec: str) -> List[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", power_spec or "")]


def _power_matches(power_w: float, power_spec: str, tolerance: float = 0.15) -> bool:
    values = _power_values_in_spec(power_spec)
    if not values:
        return False
    for v in values:
        if v == 0:
            continue
        if abs(v - power_w) / v <= tolerance:
            return True
    return False


def _best_product_match(api_luminaire_name: str, power_w: float) -> Optional[Dict[str, Any]]:
    product_type = _guess_product_type(api_luminaire_name)
    series = _guess_series(api_luminaire_name)
    candidates = _all_products()

    def _filtered(require_type: bool, require_series: bool, require_power: bool) -> List[Dict[str, Any]]:
        out = []
        for p in candidates:
            if require_type and product_type and p.get("type") != product_type:
                continue
            if require_series and series and (p.get("series") or "").upper() != series:
                continue
            if require_power and not _power_matches(power_w, (p.get("specs") or {}).get("power", "")):
                continue
            out.append(p)
        return out

    # Progressively relax constraints until something matches.
    for require_type, require_series, require_power in (
        (True, True, True),
        (True, False, True),
        (True, True, False),
        (True, False, False),
    ):
        found = _filtered(require_type, require_series, require_power)
        if found:
            return found[0]

    # Last resort: fuzzy name similarity against product name/title.
    best, best_score = None, 0.0
    name_norm = (api_luminaire_name or "").lower()
    for p in candidates:
        for field in ("name", "title", "id"):
            score = SequenceMatcher(None, name_norm, str(p.get(field, "")).lower()).ratio()
            if score > best_score:
                best, best_score = p, score
    return best if best_score >= 0.45 else None


def _product_summary(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not p:
        return None
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "title": p.get("title"),
        "url": p.get("url"),
        "type": p.get("type"),
        "series": p.get("series"),
        "category": p.get("category_name"),
        "images": p.get("images") or [],
        "specs": p.get("specs") or {},
    }


# ── public API ────────────────────────────────────────────────────────────────

def list_fixture_types() -> List[str]:
    doc = load_fixture_map_document() or {}
    names = {e.get("api_luminaire_name") for e in doc.get("entries") or [] if e.get("api_luminaire_name")}
    return sorted(names)


def list_fixtures(
    type_filter: Optional[str] = None,
    q: Optional[str] = None,
    min_power: Optional[float] = None,
    max_power: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    The smart merged catalog: every calc-engine fixture entry enriched with the
    best-matching real product (name, images, spec sheet) when one can be found.
    """
    doc = load_fixture_map_document() or {}
    q_norm = (q or "").strip().lower()
    out = []
    for e in doc.get("entries") or []:
        name = e.get("api_luminaire_name") or ""
        power_w = e.get("power_w")
        if type_filter and type_filter.strip().lower() not in name.lower():
            continue
        if min_power is not None and (power_w is None or power_w < min_power):
            continue
        if max_power is not None and (power_w is None or power_w > max_power):
            continue
        product = _best_product_match(name, power_w or 0)
        if q_norm:
            haystack = " ".join(
                [name, str(product.get("name", "")) if product else "", str(product.get("title", "")) if product else ""]
            ).lower()
            if q_norm not in haystack:
                continue
        out.append(
            {
                "api_luminaire_name": name,
                "power_w": power_w,
                "relative_ies": e.get("relative_ies"),
                "ies_available": bool(e.get("relative_ies")),
                "product": _product_summary(product),
            }
        )
    out.sort(key=lambda r: (r["api_luminaire_name"] or "", r["power_w"] or 0))
    return out


def get_fixture(api_luminaire_name: str, power_w: float) -> Optional[Dict[str, Any]]:
    """Exact match on name + power (same contract as fixture_catalog.fixture_entry_for_api), enriched."""
    from luxscale.fixture_catalog import fixture_entry_for_api

    entry = fixture_entry_for_api(api_luminaire_name, power_w)
    if not entry:
        return None
    product = _best_product_match(api_luminaire_name, power_w)
    return {
        "api_luminaire_name": entry.get("api_luminaire_name"),
        "power_w": entry.get("power_w"),
        "relative_ies": entry.get("relative_ies"),
        "ies_available": bool(entry.get("relative_ies")),
        "product": _product_summary(product),
    }


def list_products(category_id: Optional[str] = None) -> List[Dict[str, Any]]:
    products = _all_products()
    if category_id:
        products = [p for p in products if p.get("category_id") == category_id]
    return [_product_summary(p) for p in products]


def list_product_categories() -> List[Dict[str, Any]]:
    doc = _load_products_doc()
    return [
        {"id": c.get("id"), "name": c.get("name"), "url": c.get("url"), "product_count": len(c.get("products") or [])}
        for c in doc.get("categories") or []
    ]
