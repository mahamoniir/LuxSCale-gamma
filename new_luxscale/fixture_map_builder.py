"""
Build ``assets/fixture_map.json``: API luminaire name + wattage → IES / ies_json paths + product image URLs.

Rules for image bases and extensions mirror ``result.html`` (``NAME_TO_BASE``, ``extForBase``).

Run from repository root::

    python -m luxscale.fixture_map_builder
    python -m luxscale.fixture_map_builder --out fixture_map.json --fixtures-base https://example.com/img/
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any, Dict, List, Optional

from luxscale.fixture_ies_catalog import merged_ies_relative_map, normalize_relative_ies_path
from luxscale.ies_dataset_config import active_ies_dataset
from luxscale.fixture_online_merge import (
    apply_online_to_entries,
    load_fixtures_online_document,
    online_catalog_metadata,
)
from luxscale.ies_json_builder import photometry_json_rel_from_ies_rel
from luxscale.paths import project_root

# Mirrors result.html / online-result.html NAME_TO_BASE (API name lowercased → file prefix)
API_NAME_TO_IMAGE_BASE: Dict[str, str] = {
    "sc downlight": "SC-Spot",
    "sc triproof": "SC-Triproof",
    # API name "SC backlight" = panel line (storefront SC-Backlight-* URLs)
    "sc backlight": "SC-Backlight",
    "sc flood": "SC-Flood",
    "sc flood light exterior": "SC-Flood",
    "sc highbay": "SC-HighBay",
    "sc street": "SC-Street",
    "sc solar aio street": "SC-Solar-AIO-Street",
    "eco highbay": "ECO-HighBay",
    "eco street": "ECO-Street",
    "sv flood": "SV-Flood",
}

DEFAULT_FIXTURES_BASE = "https://shortcircuit.company/assets/img/products/"


def _ext_for_image_base(base: str) -> str:
    png_keywords = ("Backlight", "Triproof", "Solar-AIO-Street", "Spot")
    for k in png_keywords:
        if k in base:
            return "png"
    return "webp"


def _fallback_image_base(api_luminaire_name: str) -> str:
    return "-".join(
        w[:1].upper() + w[1:] if w else ""
        for w in api_luminaire_name.strip().split()
    )


def _image_base_for_api_name(api_luminaire_name: str) -> str:
    key = api_luminaire_name.strip().lower()
    if key in API_NAME_TO_IMAGE_BASE:
        return API_NAME_TO_IMAGE_BASE[key]
    return _fallback_image_base(api_luminaire_name)


def _image_watt_for_url(api_luminaire_name: str, power_w: int) -> int:
    """
    CDN filenames do not always match IES metadata wattage. Override only for known assets.
    See Short Circuit product image naming (e.g. High Bay / Street storefront uses 100W sets).
    """
    key = api_luminaire_name.strip().lower()
    pw = int(power_w)
    if key == "eco highbay" and pw == 138:
        return 100
    if key == "sc highbay" and pw == 138:
        return 100
    if key == "sc street" and pw in (50, 90):
        return 100
    # Panel (SC backlight): storefront only has certain watt sets; map IES wattages to them
    if key == "sc backlight" and pw == 42:
        return 36
    if key == "sc backlight" and pw in (32, 35):
        return 36
    # Triproof: CDN has SC-Triproof-36W-transparent*.png; 30W/40W IES rows use same set
    if key == "sc triproof" and pw in (30, 40):
        return 36
    return pw


def _image_urls(
    api_luminaire_name: str, base: str, power_w: int, fixtures_base: str
) -> List[str]:
    """
    Spot / downlight: ``SC-Spot0001.png`` … ``SC-Spot0004.png`` (no watt, no ``transparent``).
    Others: ``{base}-{power}W-transparent000{n}.(webp|png)``.
    """
    base_url = fixtures_base.rstrip("/") + "/"
    ext = _ext_for_image_base(base)
    key = api_luminaire_name.strip().lower()

    if key == "sc downlight" or base == "SC-Spot":
        return [f"{base_url}{base}000{i}.{ext}" for i in range(1, 5)]

    watt = _image_watt_for_url(api_luminaire_name, power_w)
    wtag = f"{watt}W"
    return [
        f"{base_url}{base}-{wtag}-transparent000{i}.{ext}" for i in range(1, 5)
    ]


def build_fixture_map(
    *,
    fixtures_base_url: str = DEFAULT_FIXTURES_BASE,
) -> Dict[str, Any]:
    root = project_root()
    ies_render = os.path.join(root, "ies-render")

    entries: List[Dict[str, Any]] = []
    for (api_name, power_w), rel in sorted(
        merged_ies_relative_map().items(), key=lambda x: (x[0][0], x[0][1])
    ):
        rel_ies = normalize_relative_ies_path(rel)
        abs_ies = os.path.normpath(os.path.join(ies_render, rel_ies))
        img_base = _image_base_for_api_name(api_name)
        photometry_json = photometry_json_rel_from_ies_rel(rel_ies)
        entries.append(
            {
                "api_luminaire_name": api_name,
                "power_w": int(power_w),
                "relative_ies_path": rel_ies,
                "photometry_json": photometry_json,
                "ies_file_exists": os.path.isfile(abs_ies),
                "image_file_base": img_base,
                "image_extension": _ext_for_image_base(img_base),
                "image_urls": _image_urls(api_name, img_base, power_w, fixtures_base_url),
            }
        )

    online_doc = load_fixtures_online_document()
    apply_online_to_entries(entries, online_doc)

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "generated_at": now,
        "generator": "luxscale.fixture_map_builder",
        "fixtures_base_url": fixtures_base_url,
            "notes": {
            "api_field": "Matches JSON/API key Luminaire (same strings as lighting_calc output).",
            "images": (
                "SC-Spot: SC-Spot0001..4.png. Others: {image_file_base}-{power}W-transparent0001..4.{ext}; "
                "SC backlight = panel line (SC-Backlight-*). Triproof 30W/40W IES use 36W images; "
                "panel 32W/35W IES use 36W images. See _image_watt_for_url. Same as result.html."
            ),
            "photometry_json": "Relative to ies-render/ (see ies.json manifest field photometry_json).",
            "online_catalog": (
                "Rows require a published product (non-empty `images`) in fixtures_online.json and a "
                "mapping in fixture_online_merge._ONLINE_BY_API. IES paths come from "
                f"ies-render/examples/{active_ies_dataset()}/ (see luxscale.ies_dataset_config)."
            ),
            "ies_dataset": (
                f"Photometry folder: {active_ies_dataset()}. Switch in luxscale/ies_dataset_config.py."
            ),
        },
        "online_catalog_source": {
            **online_catalog_metadata(online_doc),
            "merged_at": now,
        },
        "api_name_to_image_base": dict(sorted(API_NAME_TO_IMAGE_BASE.items())),
        "entries": entries,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Write fixture_map.json for API ↔ IES ↔ images.")
    ap.add_argument(
        "--out",
        default=None,
        help="Output path (default: <repo>/assets/fixture_map.json)",
    )
    ap.add_argument(
        "--fixtures-base",
        default=DEFAULT_FIXTURES_BASE,
        help="Base URL for product rotation images (trailing slash optional).",
    )
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args(argv)

    root = project_root()
    out = args.out or os.path.join(root, "assets", "fixture_map.json")
    doc = build_fixture_map(fixtures_base_url=args.fixtures_base)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    indent = None if args.indent <= 0 else args.indent
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=indent)
    try:
        from luxscale.fixture_catalog import clear_fixture_map_cache

        clear_fixture_map_cache()
    except Exception:
        pass
    try:
        from luxscale.fixture_online_merge import clear_fixtures_online_cache

        clear_fixtures_online_cache()
    except Exception:
        pass
    print(f"Wrote {out} ({len(doc['entries'])} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
