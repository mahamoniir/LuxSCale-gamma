"""

Build the IES catalog index and per-file photometry JSON under ``ies-render/``.



Default (split layout)::



    ies-render/ies.json              # small manifest (index)

    ies-render/ies_json/<mirror>.json  # full photometry + polar per .ies file



Run from repository root::



    python -m luxscale.ies_json_builder

    python -m luxscale.ies_json_builder --legacy-monolithic   # single huge ies.json

    python -m luxscale.ies_json_builder --meta-only           # index only, no blobs

"""

from __future__ import annotations



import argparse

import datetime as dt

import json

import os

import shutil

import sys

from typing import Any, Dict, List, Optional, Tuple



from luxscale.ies_fixture_params import _get_ies_parser_class, approx_beam_angle_deg

from luxscale.paths import project_root



SCHEMA_VERSION = 3





def _iter_ies_files(
    ies_render_root: str, only_under: Optional[str] = None
) -> List[str]:
    """
    All ``*.ies`` under ``ies_render_root``. If ``only_under`` is set (POSIX path,
    e.g. ``examples/SC_FIXED``), keep only files whose path relative to the root
    starts with that prefix.
    """
    raw: List[str] = []
    for dirpath, dirnames, filenames in os.walk(ies_render_root):

        # Do not treat generated JSON tree as IES sources

        dirnames[:] = [d for d in dirnames if d != "ies_json"]

        for name in filenames:

            if name.lower().endswith(".ies"):

                raw.append(os.path.join(dirpath, name))

    raw.sort()
    if not only_under:
        return raw
    prefix = only_under.replace("\\", "/").strip().strip("/")
    filtered: List[str] = []
    for path in raw:
        rel = _rel_from_ies_render(path, ies_render_root).replace("\\", "/")
        if rel.startswith(prefix):
            filtered.append(path)
    return filtered





def _rel_from_ies_render(abs_path: str, ies_render_root: str) -> str:

    return os.path.relpath(abs_path, ies_render_root).replace("\\", "/")





def photometry_json_rel_from_ies_rel(rel_ies: str) -> str:

    """Path under ``ies-render/`` for the blob (forward slashes)."""

    rel = rel_ies.replace("\\", "/")

    if not rel.lower().endswith(".ies"):

        rel = rel + ".ies"

    stem = rel[:-4] + ".json"

    return "ies_json/" + stem





def _serialize_candela_dict(candela_values: dict) -> Dict[str, List[float]]:

    out: Dict[str, List[float]] = {}

    for h in sorted(candela_values.keys(), key=lambda x: float(x)):

        out[str(float(h))] = [float(v) for v in candela_values[h]]

    return out





def _polar_curves_from_ies(ies_data) -> List[Dict[str, Any]]:

    va = [float(x) for x in ies_data.vertical_angles]

    curves: List[Dict[str, Any]] = []

    for h in sorted(ies_data.candela_values.keys(), key=lambda x: float(x)):

        cd = [float(x) for x in ies_data.candela_values[h]]

        curves.append(

            {

                "horizontal_deg": float(h),

                "vertical_deg": va,

                "candela": cd,

            }

        )

    return curves





def _rated_lumens_effective_per_lamp(ies_data) -> float:

    return float(ies_data.lumens_per_lamp) * float(ies_data.multiplier)





def _rated_lumens_total(ies_data) -> float:

    n = max(1, int(ies_data.num_lamps))

    return _rated_lumens_effective_per_lamp(ies_data) * float(n)


def _photometric_type_payload(ies_data) -> Dict[str, Any]:
    """LM-63 photometric metadata; defaults keep compatibility with older parsers."""
    code = int(getattr(ies_data, "photometric_type", 1) or 1)
    if code not in (1, 2, 3):
        code = 1
    name = str(getattr(ies_data, "photometric_type_name", "C") or "C")
    v_label = str(getattr(ies_data, "vertical_angle_label", "gamma") or "gamma")
    h_label = str(getattr(ies_data, "horizontal_angle_label", "C") or "C")
    return {
        "photometric_type": code,
        "photometric_type_name": name,
        "vertical_angle_label": v_label,
        "horizontal_angle_label": h_label,
    }





def _flags_for_entry(ies_data, status: str, error: Optional[str]) -> List[str]:

    flags: List[str] = []

    if status != "ok":

        flags.append("parse_failed")

        if error:

            flags.append("broken_ies")

        return flags

    rl = _rated_lumens_total(ies_data)

    if rl <= 0:

        flags.append("non_positive_rated_lumens")

    if float(ies_data.max_value) <= 0:

        flags.append("non_positive_max_candela")

    return flags





def build_entry(abs_path: str, ies_render_root: str) -> Dict[str, Any]:

    rel = _rel_from_ies_render(abs_path, ies_render_root)

    IES_Parser = _get_ies_parser_class()

    try:

        parser = IES_Parser(os.path.normpath(abs_path))

        d = parser.ies_data

    except Exception as ex:

        return {

            "relative_path": rel,

            "status": "error",

            "error": str(ex),

            "error_type": type(ex).__name__,

            "flags": _flags_for_entry(None, "error", str(ex)),

        }



    # 50 % of peak (interpolated, full angle) — same as calculator / ies_viewer FWHM label.
    beam = approx_beam_angle_deg(d, threshold=0.5)
    field_10 = approx_beam_angle_deg(d, threshold=0.1)

    rated = _rated_lumens_total(d)
    ptype = _photometric_type_payload(d)



    return {

        "relative_path": rel,

        "status": "ok",

        "header": {

            "num_lamps": int(d.num_lamps),

            "lumens_per_lamp": float(d.lumens_per_lamp),

            "multiplier": float(d.multiplier),

            "rated_lumens_per_lamp_effective_lm": _rated_lumens_effective_per_lamp(d),

            "rated_lumens_total_lm": rated,

            "opening_width_m": float(d.width),

            "opening_length_m": float(d.length),

            "opening_height_m": float(d.height),

            "shape": d.shape,

            "num_vertical_angles": len(d.vertical_angles),

            "num_horizontal_angles": len(d.horizontal_angles),
            "photometric_type": ptype["photometric_type"],
            "photometric_type_name": ptype["photometric_type_name"],
            "vertical_angle_label": ptype["vertical_angle_label"],
            "horizontal_angle_label": ptype["horizontal_angle_label"],

        },

        "photometry": {

            "vertical_angles_deg": [float(x) for x in d.vertical_angles],

            "horizontal_angles_deg": [float(x) for x in d.horizontal_angles],

            "candela_by_horizontal_deg": _serialize_candela_dict(d.candela_values),

            "max_candela": float(d.max_value),
            "photometric_type": ptype["photometric_type"],
            "photometric_type_name": ptype["photometric_type_name"],
            "vertical_angle_label": ptype["vertical_angle_label"],
            "horizontal_angle_label": ptype["horizontal_angle_label"],

        },

        "polar": {

            "description": (

                f"LM-63 Type {ptype['photometric_type_name']} photometry: "
                f"for each {ptype['horizontal_angle_label']}-plane angle in horizontal_deg, "
                f"candela vs {ptype['vertical_angle_label']} angle in vertical_deg."

            ),

            "curves": _polar_curves_from_ies(d),

        },

        "derived": {

            "beam_angle_deg_half_power_vertical_slice": beam,

            "field_angle_deg_10pct_vertical_slice": field_10,

        },

        "flags": _flags_for_entry(d, "ok", None),

        "parser": {

            "module": "ies-render/module/ies_parser.py",

            "IESData_fields": [

                "vertical_angles",

                "horizontal_angles",

                "candela_values",

                "max_value",

                "num_lamps",

                "lumens_per_lamp",

                "multiplier",

                "width",

                "length",

                "height",

                "shape",
                "photometric_type",
                "photometric_type_name",
                "vertical_angle_label",
                "horizontal_angle_label",

            ],

        },

    }





def build_entry_meta_only(abs_path: str, ies_render_root: str) -> Dict[str, Any]:

    full = build_entry(abs_path, ies_render_root)

    if full.get("status") != "ok":

        return full

    full["photometry"].pop("candela_by_horizontal_deg", None)

    pol = full.get("polar") or {}

    pol.pop("curves", None)

    pol["curves_omitted"] = True

    return full





def _split_entry_for_manifest(

    entry: Dict[str, Any], *, include_blob: bool

) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:

    """

    Returns (manifest_row, blob_document_or_none).

    """

    if entry.get("status") != "ok":

        return entry, None

    rel = entry["relative_path"]

    photometry_json = photometry_json_rel_from_ies_rel(rel)

    manifest = {k: v for k, v in entry.items() if k not in ("photometry", "polar")}

    manifest["photometry_json"] = photometry_json

    if not include_blob:

        manifest.pop("photometry_json", None)

        return manifest, None

    blob = {

        "schema_version": SCHEMA_VERSION,

        "relative_path": rel,

        "photometry": entry["photometry"],

        "polar": entry["polar"],

    }

    return manifest, blob





def _manifest_document(

    *,

    irr: str,

    entries_manifest: List[Dict[str, Any]],

    layout: str,

    flag_counts: Dict[str, int],

    files_total: int,

    ok: int,

    err: int,

) -> Dict[str, Any]:

    root = project_root()

    return {

        "schema_version": SCHEMA_VERSION,

        "layout": layout,

        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),

        "generator": "luxscale.ies_json_builder",

        "ies_render_root": os.path.relpath(irr, root).replace("\\", "/"),

        "photometry_blobs_dir": "ies_json",

        "notes": {

            "ies_polar": (

                "ies-render/module/ies_polar.py is image pixel geometry only, "

                "not IES photometry; polar plots use photometry blobs."

            ),

            "tilt": "Parser supports only TILT=NONE; other TILT values raise parse errors.",

            "loader": "luxscale.ies_json_loader.load_photometry_blob(relative_path)",

        },

        "summary": {

            "files_total": files_total,

            "parsed_ok": ok,

            "parse_failed": err,

            "flags_count": dict(sorted(flag_counts.items())),

        },

        "entries": entries_manifest,

    }





def build_database(

    *,

    ies_render_root: Optional[str] = None,

    meta_only: bool = False,

    legacy_monolithic: bool = False,

    only_under: Optional[str] = None,

) -> Dict[str, Any]:

    """``legacy_monolithic``: one document with full photometry inline (large ``ies.json``)."""

    root = project_root()

    irr = ies_render_root or os.path.join(root, "ies-render")

    if not os.path.isdir(irr):

        raise FileNotFoundError(f"ies-render not found: {irr}")



    files = _iter_ies_files(irr, only_under=only_under)

    builder = build_entry_meta_only if meta_only else build_entry



    entries: List[Dict[str, Any]] = []

    flag_counts: Dict[str, int] = {}

    ok = err = 0



    for path in files:

        e = builder(path, irr)

        entries.append(e)

        if e.get("status") == "ok":

            ok += 1

        else:

            err += 1

        for f in e.get("flags") or []:

            flag_counts[f] = flag_counts.get(f, 0) + 1



    if legacy_monolithic:

        return _manifest_document(

            irr=irr,

            entries_manifest=entries,

            layout="monolithic",

            flag_counts=flag_counts,

            files_total=len(files),

            ok=ok,

            err=err,

        )



    manifest_rows: List[Dict[str, Any]] = []

    blobs: List[Tuple[str, Dict[str, Any]]] = []

    for e in entries:

        if meta_only:

            m, _ = _split_entry_for_manifest(e, include_blob=False)

            if e.get("status") == "ok":

                m["photometry_json"] = photometry_json_rel_from_ies_rel(e["relative_path"])

                m["photometry_note"] = "omitted_meta_only_build"

            manifest_rows.append(m)

            continue

        m, blob = _split_entry_for_manifest(e, include_blob=True)

        manifest_rows.append(m)

        if blob:

            blobs.append((m["photometry_json"], blob))



    doc = _manifest_document(

        irr=irr,

        entries_manifest=manifest_rows,

        layout="split_index_and_blobs",

        flag_counts=flag_counts,

        files_total=len(files),

        ok=ok,

        err=err,

    )

    doc["_write_blobs"] = blobs  # internal; stripped before json.dump

    return doc





def _write_split(
    irr: str,
    doc: Dict[str, Any],
    out_index: str,
    indent: Optional[int],
) -> int:
    blobs = doc.pop("_write_blobs", None) or []
    os.makedirs(os.path.dirname(os.path.abspath(out_index)), exist_ok=True)
    with open(out_index, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=indent)

    for rel_under_ir, blob in blobs:
        abs_blob = os.path.normpath(os.path.join(irr, rel_under_ir.replace("/", os.sep)))
        os.makedirs(os.path.dirname(abs_blob), exist_ok=True)
        with open(abs_blob, "w", encoding="utf-8") as bf:
            json.dump(blob, bf, ensure_ascii=False, indent=indent)
    return len(blobs)





def main(argv: Optional[List[str]] = None) -> int:

    ap = argparse.ArgumentParser(

        description="Build ies.json index and ies_json/*.json photometry blobs."

    )

    ap.add_argument(

        "--out",

        default=None,

        help="Index JSON path (default: <repo>/ies-render/ies.json)",

    )

    ap.add_argument(

        "--ies-render",

        default=None,

        help="Override ies-render directory (default: <repo>/ies-render)",

    )

    ap.add_argument(

        "--meta-only",

        action="store_true",

        help="Index only (headers/flags); no photometry blobs written.",

    )

    ap.add_argument(

        "--legacy-monolithic",

        action="store_true",

        help="Write a single large ies.json with full photometry (old behavior).",

    )

    ap.add_argument(

        "--clean-blobs",

        action="store_true",

        help="Delete ies-render/ies_json/ before writing (removes stale blob files).",

    )

    ap.add_argument(

        "--only-under",

        default=None,

        metavar="REL_PATH",

        help="Only index .ies files whose path under ies-render starts with this prefix "

        "(e.g. examples/SC_FIXED). Default: entire tree.",

    )

    ap.add_argument(

        "--indent",

        type=int,

        default=2,

        help="JSON indent (default 2; use 0 for minified).",

    )

    args = ap.parse_args(argv)



    root = project_root()

    out_path = args.out or os.path.join(root, "ies-render", "ies.json")

    irr = args.ies_render or os.path.join(root, "ies-render")



    if args.clean_blobs and not args.legacy_monolithic:

        blob_root = os.path.join(irr, "ies_json")

        if os.path.isdir(blob_root):

            shutil.rmtree(blob_root)



    db = build_database(

        ies_render_root=irr,

        meta_only=args.meta_only,

        legacy_monolithic=args.legacy_monolithic,

        only_under=args.only_under,

    )



    indent = None if args.indent <= 0 else args.indent

    blob_count = 0
    if args.legacy_monolithic:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=indent)
    else:
        blob_count = _write_split(irr, db, out_path, indent)

    s = db["summary"]
    print(
        f"Wrote index {out_path} | total={s['files_total']} ok={s['parsed_ok']} failed={s['parse_failed']} layout={db.get('layout')}",
        file=sys.stderr,
    )
    if not args.legacy_monolithic and not args.meta_only:
        print(
            f"Photometry blobs: {blob_count} files under {os.path.join(irr, 'ies_json')}",
            file=sys.stderr,
        )

    if s.get("flags_count"):
        print(f"Flags: {s['flags_count']}", file=sys.stderr)

    try:
        from luxscale.ies_fixture_params import clear_ies_data_cache
        from luxscale.ies_json_loader import clear_index_cache

        clear_index_cache()
        clear_ies_data_cache()
    except Exception:
        pass

    return 0





if __name__ == "__main__":

    raise SystemExit(main())


