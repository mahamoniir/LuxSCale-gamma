#!/usr/bin/env python3
"""
Convenience script to regenerate assets/fixed_responses.json.

Usage:
    python generate_fixed_responses.py
    python generate_fixed_responses.py --out assets/fixed_responses.json
"""
from __future__ import annotations

import argparse

from luxscale.fixed_responses_builder import (
    DEFAULT_FIXED_RESPONSES_PATH,
    regenerate_fixed_responses,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate fixed chat responses JSON.")
    ap.add_argument(
        "--out",
        default=DEFAULT_FIXED_RESPONSES_PATH,
        help="Output JSON path (default: assets/fixed_responses.json)",
    )
    args = ap.parse_args()

    doc = regenerate_fixed_responses(output_path=args.out)
    print(
        f"Generated {args.out} with "
        f"{len(doc.get('responses') or [])} responses and "
        f"{len(doc.get('menu_items') or [])} menu items."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

