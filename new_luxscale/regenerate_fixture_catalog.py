"""
Regenerate ``assets/fixture_ies_catalog.json`` (snapshot) and the active ``fixture_map*.json``.

Also clears fixture / online JSON caches. Run from repo root::

    python -m luxscale.regenerate_fixture_catalog

Build **only** the v3 map file (without changing ``luxscale/ies_dataset_config.py`` defaults)::

    set LUXSCALE_IES_DATASET=SC_IES_Fixed_v3
    py -m luxscale.fixture_map_builder --out assets/fixture_map_SC_IES_Fixed_v3.json

Photometry JSON index: use ``--only-under`` matching the dataset folder, e.g.::

    py -m luxscale.ies_json_builder --clean-blobs --only-under examples/SC_IES_Fixed_v3
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from luxscale.fixture_catalog import clear_fixture_map_cache
from luxscale.fixture_ies_catalog import write_fixture_ies_catalog_json
from luxscale.fixture_map_builder import DEFAULT_FIXTURES_BASE, build_fixture_map
from luxscale.fixture_online_merge import clear_fixtures_online_cache


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write fixture_ies_catalog.json snapshot and fixture_map JSON from merged IES catalog."
    )
    ap.add_argument(
        "--fixtures-base",
        default=None,
        help="fixtures_base_url for fixture_map (default: fixture_map_builder default)",
    )
    ap.add_argument(
        "--skip-json-snapshot",
        action="store_true",
        help="Only rebuild fixture_map (skip writing fixture_ies_catalog.json).",
    )
    ap.add_argument(
        "--ies-dataset",
        default=None,
        help="Set LUXSCALE_IES_DATASET for this run (e.g. SC_IES_Fixed_v3).",
    )
    ap.add_argument(
        "--out-map",
        default=None,
        help="Output fixture map path (default: assets/fixture_map.json).",
    )
    ap.add_argument(
        "--out-catalog",
        default=None,
        help=(
            "Optional path for fixture_ies_catalog-style snapshot "
            "(default: assets/fixture_ies_catalog.json when not using --ies-dataset; "
            "use e.g. assets/fixture_ies_catalog_SC_IES_Fixed_v3.json for v3-only export)."
        ),
    )
    args = ap.parse_args(argv)

    if args.ies_dataset:
        os.environ["LUXSCALE_IES_DATASET"] = args.ies_dataset

    if not args.skip_json_snapshot:
        path = write_fixture_ies_catalog_json(args.out_catalog)
        print(f"Wrote catalog snapshot {path}", file=sys.stderr)

    fb = args.fixtures_base or DEFAULT_FIXTURES_BASE
    doc = build_fixture_map(fixtures_base_url=fb)

    from luxscale.paths import project_root

    out = args.out_map or os.path.join(project_root(), "assets", "fixture_map.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    clear_fixture_map_cache()
    clear_fixtures_online_cache()
    print(f"Wrote {out} ({len(doc['entries'])} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
