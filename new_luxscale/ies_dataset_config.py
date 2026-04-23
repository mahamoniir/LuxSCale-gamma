"""
IES photometry dataset switch (which folder under ``ies-render/examples/`` is authoritative).

**Storefront / product data** (unchanged): ``assets/fixtures_online.json``

**Fixture ↔ image ↔ online rows** (pick one file to load at runtime):
  - ``assets/fixture_map_SC_IES_Fixed_v3.json`` — **default**; IES under
    ``ies-render/examples/SC_IES_Fixed_v3/``
  - ``assets/fixture_map.json`` — legacy; IES under ``ies-render/examples/SC_FIXED/`` (commented in code)

**Merged IES index** (runtime, used when ``fixture_map`` has no row): built by scanning the
active examples folder (see ``luxscale.sc_ies_scan.scan_examples_ies_dataset``).

**Snapshot** (optional, for diff/review): ``fixture_ies_catalog*.json`` — run
``python -m luxscale.regenerate_fixture_catalog`` after changing the active dataset.

Switching datasets
------------------
1. Comment/uncomment **one** of the two ``_DEFAULT_*`` pairs below (v3 is default; SC_FIXED is optional).
2. In ``result.html``, comment/uncomment ``FIXTURE_MAP_ASSET`` the same way (product images).
3. Restart the Python app (Flask) so caches reload.

Optional env overrides (e.g. temporary use of legacy SC_FIXED)::
    set LUXSCALE_IES_DATASET=SC_FIXED
    set LUXSCALE_FIXTURE_MAP=fixture_map.json
"""
from __future__ import annotations

import os

# --- Default pair: SC_IES_Fixed_v3 + matching fixture map ---
_DEFAULT_IES_DATASET = "SC_IES_Fixed_v3"
_DEFAULT_FIXTURE_MAP_BASENAME = "fixture_map_SC_IES_Fixed_v3.json"

# --- Legacy pair: SC_FIXED (uncomment both lines below and comment the pair above) ---
# _DEFAULT_IES_DATASET = "SC_FIXED"
# _DEFAULT_FIXTURE_MAP_BASENAME = "fixture_map.json"


def active_ies_dataset() -> str:
    """Folder name under ``ies-render/examples/`` (e.g. ``SC_IES_Fixed_v3``)."""
    v = (os.environ.get("LUXSCALE_IES_DATASET") or _DEFAULT_IES_DATASET).strip()
    return v or "SC_IES_Fixed_v3"


def active_fixture_map_basename() -> str:
    """Filename under ``assets/`` (e.g. ``fixture_map_SC_IES_Fixed_v3.json``)."""
    v = (os.environ.get("LUXSCALE_FIXTURE_MAP") or _DEFAULT_FIXTURE_MAP_BASENAME).strip()
    return v or "fixture_map_SC_IES_Fixed_v3.json"
