"""
Scan ``ies-render/SC-ies`` folder names and pick one .ies per (API luminaire, power).

Folder names like ``SC FLOOD 100W`` map to API strings used by lighting_calc / fixture_map.
Folders without a trailing ``###W`` use a best-effort wattage from the first ``.ies`` file
(keyword [_INPUTWATTAGE] or similar).
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from luxscale.paths import project_root

# Normalized folder prefix (uppercase, stripped) -> API luminaire name (exact casing for API)
_FOLDER_PREFIX_TO_API: Dict[str, str] = {
    "SC FLOOD": "SC flood light exterior",
    "SV FLOOD": "SV flood",
    "SC STREET": "SC street",
    "SC HIGHBAY": "SC highbay",
    "ECO HIGHBAY": "eco highbay",
    "SC TRIPROOF": "SC triproof",
    "SC SPOT": "SC downlight",
    "SC PANEL": "SC backlight",  # power from SC PANEL 18 / 36W / 48W
}


def _sc_ies_root() -> str:
    return os.path.join(project_root(), "ies-render", "SC-ies")


def _input_wattage_from_ies_file(path: str) -> Optional[int]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read(120000)
    except OSError:
        return None
    m = re.search(
        r"\[_INPUTWATTAGE\]\s*([\d.]+)|\[INPUTWATTAGE\]\s*([\d.]+)",
        text,
        re.I,
    )
    if m:
        v = m.group(1) or m.group(2)
        try:
            return int(round(float(v)))
        except ValueError:
            return None
    return None


def _pick_ies_for_watt(files: List[str], watt: int) -> str:
    if len(files) == 1:
        return files[0]
    wtag = f"{watt}W"
    for p in sorted(files):
        if wtag in os.path.basename(p).upper():
            return p
    return sorted(files)[0]


def _parse_folder_name(dirname: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Returns (api_luminaire_name, power_w) or (None, None) if unmappable.
    """
    d = dirname.strip()
    up = d.upper()

    # SC PANEL 18 / SC PANEL 36W / SC PANEL 48W
    m = re.match(r"^SC\s+PANEL\s+(\d+)\s*W?$", d, re.I)
    if m:
        return "SC backlight", int(m.group(1))

    # ... NAME ###W
    m = re.match(r"^(.+?)\s+(\d+)\s*W$", d, re.I)
    if not m:
        return None, None
    prefix = m.group(1).strip().upper()
    watt = int(m.group(2))

    for key, api in _FOLDER_PREFIX_TO_API.items():
        if up == key or prefix == key:
            return api, watt
        if prefix.startswith(key + " ") or prefix == key:
            return api, watt
    return None, None


def scan_sc_ies() -> List[Tuple[str, int, str]]:
    """
    Returns sorted list of (api_luminaire_name, power_w, path_relative_to_ies_render).

    One row per folder after deduplication by (api, power); see scan_sc_ies_raw.
    """
    raw = scan_sc_ies_raw()
    best: Dict[Tuple[str, int], str] = {}
    for api, pw, rel in raw:
        key = (api, int(pw))
        if key not in best:
            best[key] = rel
            continue
        # Prefer path that mentions watt in filename
        cur = best[key]
        if f"{pw}W" in rel.upper() and f"{pw}W" not in cur.upper():
            best[key] = rel
    out = [(a, p, best[(a, p)]) for (a, p) in sorted(best.keys())]
    return out


def _parse_sc_fixed_basename(name: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Map flat filenames in ``ies-render/examples/SC_FIXED/*.ies`` to API luminaire + wattage.

    Examples: ``SC_PANEL_35W_...``, ``SC_SPOT_10W_...``, ``GL-FL-..._150W_4000K...``
    """
    base = name.rsplit(".", 1)[0]
    m = re.match(r"^SC_PANEL_(\d+)W", base, re.I)
    if m:
        return "SC backlight", int(m.group(1))
    m = re.match(r"^SC_SPOT_(\d+)W", base, re.I)
    if m:
        return "SC downlight", int(m.group(1))
    m = re.match(r"^SC_TRIPROOF_(\d+)W", base, re.I)
    if m:
        return "SC triproof", int(m.group(1))
    m = re.match(r"^SC_SV_FLOOD_(\d+)W", base, re.I)
    if m:
        return "SV flood", int(m.group(1))
    m = re.match(r"^SC_STREETLIGHT_(\d+)W", base, re.I)
    if m:
        return "SC street", int(m.group(1))
    m = re.match(r"^SC_ECO_HIGHBAY_(\d+)W", base, re.I)
    if m:
        return "SC highbay", int(m.group(1))
    m = re.search(r"_(\d+)W_4000K", base, re.I) or re.search(r"_(\d+)W_5000K", base, re.I)
    if m and base.upper().startswith("GL-FL"):
        return "SC flood light exterior", int(m.group(1))
    return None, None


def scan_examples_sc_fixed() -> List[Tuple[str, int, str]]:
    """
    Flat ``.ies`` files under ``ies-render/examples/SC_FIXED`` (not ``results/``).

    This is the **sole** source for :func:`luxscale.fixture_ies_catalog.merged_ies_relative_map`.
    Duplicate ``(api, power)`` from 4000K vs 5000K files: last filename in sorted order wins.
    """
    fixed = os.path.join(project_root(), "ies-render", "examples", "SC_FIXED")
    ies_render = os.path.join(project_root(), "ies-render")
    if not os.path.isdir(fixed):
        return []
    out: List[Tuple[str, int, str]] = []
    for name in sorted(os.listdir(fixed)):
        if not name.lower().endswith(".ies"):
            continue
        path = os.path.join(fixed, name)
        if not os.path.isfile(path):
            continue
        api, pw = _parse_sc_fixed_basename(name)
        if api is None or pw is None:
            continue
        rel = os.path.relpath(path, ies_render).replace("\\", "/")
        out.append((api, int(pw), rel))
    # Storefront/API mismatch: SC Spot is sold as ~10W but lighting_calc often uses 9W.
    # Reuse the SC_FIXED SPOT photometry for 9W so beam angle matches the validated file (~39° FWHM).
    for api, pw, rel in list(out):
        if (
            api == "SC downlight"
            and pw == 10
            and "SC_FIXED" in rel.replace("\\", "/")
            and "SC_SPOT" in rel.upper()
        ):
            out.append(("SC downlight", 9, rel))
            break
    return out


def _parse_sc_v3_flat_basename(name: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Map flat ``SC_IES_Fixed_v3/*.ies`` names to API luminaire + wattage.

    Filenames use underscores and optional ``.ies`` / ``.IES``.
    """
    base = name.rsplit(".", 1)[0]
    m = re.match(r"^SC_PANEL_(\d+)W$", base, re.I)
    if m:
        return "SC backlight", int(m.group(1))
    m = re.match(r"^SC_SPOT_(\d+)W$", base, re.I)
    if m:
        return "SC downlight", int(m.group(1))
    m = re.match(r"^SC_TRIPROOF_(\d+)W$", base, re.I)
    if m:
        return "SC triproof", int(m.group(1))
    m = re.match(r"^SC_SV_FLOOD_(\d+)W$", base, re.I)
    if m:
        return "SV flood", int(m.group(1))
    m = re.match(r"^SV_FLOOD_(\d+)W$", base, re.I)
    if m:
        return "SV flood", int(m.group(1))
    m = re.match(r"^SC_STREETLIGHT_(\d+)W$", base, re.I)
    if m:
        return "SC street", int(m.group(1))
    m = re.match(r"^SC_HIGHBAY_(\d+)W$", base, re.I)
    if m:
        return "SC highbay", int(m.group(1))
    m = re.match(r"^SC_ECO_HIGHBAY_(\d+)W$", base, re.I)
    if m:
        return "SC highbay", int(m.group(1))
    m = re.match(r"^ECO_HIGHBAY_(\d+)W$", base, re.I)
    if m:
        return "eco highbay", int(m.group(1))
    m = re.match(r"^SC_FLOOD_(\d+)W$", base, re.I)
    if m:
        return "SC flood light exterior", int(m.group(1))
    m = re.match(r"^GL-FL.*_(\d+)W_", base, re.I)
    if m:
        return "SC flood light exterior", int(m.group(1))
    return None, None


def scan_examples_sc_ies_v3() -> List[Tuple[str, int, str]]:
    """
    Flat and nested ``.ies`` under ``ies-render/examples/SC_IES_Fixed_v3``.

    Adds the same API wattage keys as the storefront / ``SC_FIXED`` catalog where filenames
    differ (e.g. panel 32W/35W → ``SC_PANEL_36W.ies``; triproof 30W/40W → ``SC_TRIPROOF_36W.ies``).
    """
    root = os.path.join(project_root(), "ies-render", "examples", "SC_IES_Fixed_v3")
    ies_render = os.path.join(project_root(), "ies-render")
    if not os.path.isdir(root):
        return []

    rel_base = "examples/SC_IES_Fixed_v3"
    out: List[Tuple[str, int, str]] = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isfile(path) and name.lower().endswith(".ies"):
            api, pw = _parse_sc_v3_flat_basename(name)
            if api is None or pw is None:
                continue
            rel = os.path.relpath(path, ies_render).replace("\\", "/")
            out.append((api, int(pw), rel))
        elif os.path.isdir(path):
            dm = re.match(r"^SC_STREET_(\d+)W$", name, re.I)
            if not dm:
                continue
            wfolder = int(dm.group(1))
            for fn in sorted(os.listdir(path)):
                if not fn.lower().endswith(".ies"):
                    continue
                fp = os.path.join(path, fn)
                if not os.path.isfile(fp):
                    continue
                rel = os.path.relpath(fp, ies_render).replace("\\", "/")
                mfile = re.search(r"_(\d+)W\.(?:IES|ies)$", fn, re.I)
                wuse = int(mfile.group(1)) if mfile else wfolder
                out.append(("SC street", wuse, rel))

    best: Dict[Tuple[str, int], str] = {}
    for api, pw, rel in out:
        key = (api, int(pw))
        if key not in best:
            best[key] = rel
            continue
        cur = best[key]
        if f"{pw}W" in rel.upper() and f"{pw}W" not in cur.upper():
            best[key] = rel

    merged = [(a, p, best[(a, p)]) for (a, p) in sorted(best.keys())]

    # Align storefront API keys (same as fixture_online_merge._ONLINE_BY_API) to v3 files.
    overrides: List[Tuple[str, int, str]] = [
        ("SC backlight", 32, f"{rel_base}/SC_PANEL_36W.ies"),
        ("SC backlight", 35, f"{rel_base}/SC_PANEL_36W.ies"),
        ("SC downlight", 9, f"{rel_base}/SC_SPOT_10W.ies"),
        ("SC triproof", 30, f"{rel_base}/SC_TRIPROOF_36W.ies"),
        ("SC triproof", 40, f"{rel_base}/SC_TRIPROOF_36W.ies"),
        (
            "SC street",
            30,
            f"{rel_base}/SC_STREET_50W/SL250SI5KN01_75x150deg_50W.IES",
        ),
        (
            "SC street",
            60,
            f"{rel_base}/SC_STREET_90W/SL290SI5KN01_75x150deg_90W.IES",
        ),
    ]
    ob: Dict[Tuple[str, int], str] = {(a, b): c for a, b, c in merged}
    for api, pw, rel in overrides:
        fp = os.path.join(project_root(), "ies-render", rel.replace("/", os.sep))
        if os.path.isfile(fp):
            ob[(api, int(pw))] = rel

    out_list = [(a, p, ob[(a, p)]) for (a, p) in sorted(ob.keys())]

    # Reuse 10W spot file for 9W API (same as SC_FIXED behaviour).
    for api, pw, rel in list(out_list):
        if (
            api == "SC downlight"
            and pw == 10
            and "SC_IES_Fixed_v3" in rel.replace("\\", "/")
            and "SC_SPOT" in rel.upper()
        ):
            out_list.append(("SC downlight", 9, rel))
            break
    return out_list


def scan_examples_ies_dataset(examples_subdir: str) -> List[Tuple[str, int, str]]:
    """
    Dispatch to the flat-folder scanner for the given ``examples`` folder name.

    ``examples_subdir`` is the directory name only (e.g. ``SC_FIXED`` or ``SC_IES_Fixed_v3``),
    resolved under ``ies-render/examples/``.
    """
    name = (examples_subdir or "").strip().replace("\\", "/").rstrip("/")
    if name.endswith("/examples"):
        name = os.path.basename(name)
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if name == "SC_FIXED":
        return scan_examples_sc_fixed()
    if name == "SC_IES_Fixed_v3":
        return scan_examples_sc_ies_v3()
    raise ValueError(
        f"Unknown IES examples dataset {examples_subdir!r}; "
        f"expected 'SC_FIXED' or 'SC_IES_Fixed_v3'"
    )


def scan_sc_ies_raw() -> List[Tuple[str, int, str]]:
    """One entry per resolved folder; may duplicate (api, power) before merge."""
    root = _sc_ies_root()
    if not os.path.isdir(root):
        return []

    ies_render = os.path.join(project_root(), "ies-render")
    out: List[Tuple[str, int, str]] = []

    for name in sorted(os.listdir(root)):
        sub = os.path.join(root, name)
        if not os.path.isdir(sub):
            continue
        ies_files = [
            os.path.join(sub, f)
            for f in sorted(os.listdir(sub))
            if f.lower().endswith(".ies")
        ]
        if not ies_files:
            continue

        api, watt = _parse_folder_name(name)
        if api is not None and watt is not None:
            pick = _pick_ies_for_watt(ies_files, watt)
            rel = os.path.relpath(pick, ies_render).replace("\\", "/")
            out.append((api, watt, rel))
            continue

        # Folders without ###W: ECO HIGHBAY, SC HIGHBAY, SC TRIPROOF, SC SPOT, ...
        uname = name.strip().upper()
        if uname == "SC TRIPROOF":
            pick = sorted(ies_files)[0]
            rel = os.path.relpath(pick, ies_render).replace("\\", "/")
            out.append(("SC triproof", 36, rel))
            continue
        if uname == "SC SPOT":
            pick = sorted(ies_files)[0]
            rel = os.path.relpath(pick, ies_render).replace("\\", "/")
            out.append(("SC downlight", 9, rel))
            continue

        api = _FOLDER_PREFIX_TO_API.get(uname)
        if api is None:
            continue
        pick = ies_files[0]
        watt = _input_wattage_from_ies_file(pick)
        if watt is None or watt <= 0:
            watt = 100
        rel = os.path.relpath(pick, ies_render).replace("\\", "/")
        out.append((api, watt, rel))

    return out
