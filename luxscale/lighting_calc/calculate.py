"""Core lumen-method calculator and IES-backed uniformity side-calculations."""

from __future__ import annotations

import datetime
import os
import time
from typing import Optional

from luxscale.app_logging import log_step
from luxscale.calculation_trace import CalculationTrace
from luxscale.ies_fixture_params import ies_params_for_file, resolve_ies_path
from luxscale.uniformity_calculator import (
    compute_uniformity_metrics,
    format_uniformity_report_txt,
    polygon_layout_interior_count,
    uniformity_grid_n_for_polygon,
    uniformity_grid_n_for_room,
    write_uniformity_session_txt,
)

from .constants import (
    beam_angle,
    define_places,
    fixture_density_warn_per_m2,
    led_efficacy,
)
from .geometry import (
    calculate_spacing,
    cyclic_quadrilateral_area,
    determine_luminaire,
    determine_zone,
    spacing_factor_pairs,
)


def _rank_factor_pairs_for_polygon(
    pairs: list,
    polygon,
    length: float,
    width: float,
    orientation_rad: float,
) -> list:
    """
    Prefer layouts whose rectangular centres land inside the polygon most often
    (coverage score), then keep the original most-square ordering as a tie-break.
    """
    if polygon is None or not pairs:
        return pairs
    scored = []
    for i, (bx, by) in enumerate(pairs):
        interior = polygon_layout_interior_count(
            polygon, length, width, int(bx), int(by), float(orientation_rad)
        )
        total = max(1, int(bx) * int(by))
        scored.append((-interior / total, i, (bx, by)))
    scored.sort()
    return [t[2] for t in scored]


def _non_negative_beam_angle_deg(v) -> Optional[float]:
    """
    Half-power beam estimates from some IES vertical grids can be negative (axis sign).
    Use magnitude for display, CSV, and threshold checks so values match physical cone width.
    """
    if v is None:
        return None
    try:
        return abs(float(v))
    except (TypeError, ValueError):
        return None


_BEAM_ANGLE_ROW_KEYS = (
    "beam_angle_deg",
    "Beam Angle (deg)",
    "Beam angle (deg)",
    "Beam Angle (°)",
    "Beam Angle (Â°)",
)

_BEAM_ANGLE_NOTE_TEXT = (
    "IES vertical angles follow a signed convention; the beam angle shown is the magnitude "
    "(absolute value). If the value still looks wrong, check the source IES file."
)


def _ies_meta_for_result_row(row: dict) -> Optional[dict]:
    """Re-resolve IES photometry for a result row (luminaire + power). Used when ``ies_meta`` is out of scope (e.g. fallback pool)."""
    try:
        lum = row.get("Luminaire")
        pw = row.get("Power (W)")
        if not lum or pw is None:
            return None
        pth = resolve_ies_path(str(lum), float(pw))
        if not pth or not os.path.isfile(pth):
            return None
        return ies_params_for_file(pth)
    except Exception:
        return None


def _sync_beam_angle_output_keys(row: dict, ies_meta: Optional[dict]) -> None:
    """
    Set every beam key the UI / JSON layers may read, from IES metadata when available.

    ``result.html`` uses ``beam_angle_deg`` and ``Beam Angle (deg)``; some pipelines strip
    Unicode in ``Beam Angle (°)``, so we always duplicate ASCII-only fields here.
    Negative angles from odd IES axis conventions are shown as positive magnitudes.
    """
    for k in _BEAM_ANGLE_ROW_KEYS:
        if k in row and row[k] is not None:
            nn = _non_negative_beam_angle_deg(row[k])
            if nn is not None:
                row[k] = round(nn, 1)

    bd: Optional[float] = None
    if ies_meta is not None:
        nn = _non_negative_beam_angle_deg(ies_meta.get("beam_angle_deg"))
        if nn is not None:
            bd = round(nn, 1)
    if bd is None:
        for k in _BEAM_ANGLE_ROW_KEYS:
            if k in row and row[k] is not None:
                nn = _non_negative_beam_angle_deg(row[k])
                if nn is not None:
                    bd = round(nn, 1)
                    break

    if bd is None:
        if ies_meta is not None and ies_meta.get("beam_angle_ies_signed_vertical"):
            row["Beam angle note"] = _BEAM_ANGLE_NOTE_TEXT
        return

    row["beam_angle_deg"] = bd
    row["Beam Angle (°)"] = bd
    row["Beam Angle (deg)"] = bd
    row["Beam angle (deg)"] = bd

    if ies_meta and ies_meta.get("beam_angle_asymmetric"):
        bm = ies_meta.get("beam_angle_deg_max")
        bmxv = _non_negative_beam_angle_deg(bm)
        if bmxv is not None:
            bmx = round(bmxv, 1)
            row["Beam angle max (°)"] = bmx
            row["beam_angle_max_deg"] = bmx
            row["Beam angle max (deg)"] = bmx

    if ies_meta is not None and ies_meta.get("beam_angle_ies_signed_vertical"):
        row["Beam angle note"] = _BEAM_ANGLE_NOTE_TEXT


def _apply_ies_file_and_lumens_row(
    row: dict,
    ies_meta: Optional[dict],
    power: float,
    efficacy_display: float,
) -> None:
    """Attach IES filename and lumens for display; if header lumens ≤ 0, show rated flux."""
    if not ies_meta:
        return
    row["IES file"] = os.path.basename(ies_meta["ies_path"])
    try:
        lm_raw = float(ies_meta["lumens_per_lamp"])
    except (TypeError, ValueError):
        lm_raw = 0.0
    if lm_raw > 0:
        row["IES lumens (lm)"] = round(lm_raw, 2)
    else:
        row["IES lumens (lm)"] = round(float(power) * float(efficacy_display), 2)
        row["IES lumens note"] = (
            "IES header lumens ≤ 0; shown value is rated (W × lm/W)."
        )


def _annotate_fixture_density(row: dict, area: float) -> None:
    """Flag unusually dense layouts (weak luminaires can force many fixtures)."""
    if area <= 1e-12:
        return
    try:
        nf = int(row.get("Fixtures") or 0)
    except (TypeError, ValueError):
        return
    if nf < 1:
        return
    d = nf / float(area)
    row["Fixtures per m²"] = round(d, 4)
    if d > fixture_density_warn_per_m2:
        row["Fixture density warning"] = (
            f"{d:.2f} fixtures/m² exceeds typical guidance (~{fixture_density_warn_per_m2:.2f}/m²); "
            "verify spacing, mounting, and whether a higher-output luminaire is more appropriate."
        )


def _uniformity_chunk_placeholder(
    option_index: int,
    lum_name: str,
    power_w: float,
    reason: str,
) -> str:
    return (
        "=" * 72
        + "\n"
        + f"Option {option_index + 1} — Uniformity (point-by-point, IES candela)\n"
        + "=" * 72
        + f"\nLuminaire: {lum_name}\nPower (W): {power_w}\n"
        + f"Report skipped: {reason}\n"
    )


def _sync_uniformity_report_chunks(
    results: list,
    uniformity_report_chunks: list,
    length: float,
    width: float,
    height: float,
    u_grid_n: int,
    required_uniformity: float,
    polygon=None,
    polygon_orientation_rad: float = 0.0,
) -> None:
    """
    Build one txt section per result row so the report matches the result page order
    and count.

    Rows that became compliant inside the search loop already append chunks there; if
    that list matches ``len(results)``, we keep it (avoids duplicate IES grid work).
    Otherwise we rebuild (e.g. closest-non-compliant fallback left chunks empty, or
    chunk count drifted from result count).
    """
    if not results:
        uniformity_report_chunks.clear()
        return
    if len(uniformity_report_chunks) == len(results):
        return
    uniformity_report_chunks.clear()
    from luxscale.app_settings import (
        get_inter_reflection_fraction,
        get_maintenance_factor,
        get_room_reflectance_preset_label,
    )

    mf_u = get_maintenance_factor()
    irf_u = get_inter_reflection_fraction()
    ir_lbl_u = get_room_reflectance_preset_label()
    for idx, row in enumerate(results):
        try:
            lum_name = row.get("Luminaire")
            power = float(row.get("Power (W)", 0))
            nf = int(row.get("Fixtures", 0))
            if not lum_name or nf < 1:
                uniformity_report_chunks.append(
                    _uniformity_chunk_placeholder(
                        idx, str(lum_name or "?"), power, "missing luminaire or fixture count"
                    )
                )
                continue
            uni_path = resolve_ies_path(lum_name, power)
            if not uni_path or not os.path.isfile(uni_path):
                uniformity_report_chunks.append(
                    _uniformity_chunk_placeholder(
                        idx,
                        lum_name,
                        power,
                        f"IES file not resolved or not on disk ({uni_path!r})",
                    )
                )
                continue
            eff = float(row.get("Efficacy (lm/W)", 0))
            lumens_pf = power * eff
            nx = row.get("layout_nx")
            ny = row.get("layout_ny")
            if nx is not None and ny is not None:
                best_x, best_y = int(nx), int(ny)
            else:
                best_x, best_y = calculate_spacing(length, width, nf)
            cal_lx = (nf * lumens_pf * mf_u) / max(1e-9, float(length) * float(width))
            met = compute_uniformity_metrics(
                uni_path,
                length,
                width,
                height,
                nf,
                lumens_pf,
                best_x,
                best_y,
                grid_n=u_grid_n,
                calibrate_maintained_avg_lx=cal_lx,
                inter_reflection_fraction=irf_u,
                inter_reflection_label=ir_lbl_u,
                polygon=polygon,
                polygon_orientation_rad=polygon_orientation_rad,
            )
            uniformity_report_chunks.append(
                format_uniformity_report_txt(
                    idx,
                    lum_name,
                    power,
                    required_uniformity,
                    uni_path,
                    met,
                )
            )
        except Exception as ex:
            log_step("uniformity: session chunk failed", str(ex), option_index=idx)
            try:
                p = float(row.get("Power (W)", 0))
                ln = row.get("Luminaire") or "?"
            except Exception:
                p, ln = 0.0, "?"
            uniformity_report_chunks.append(
                _uniformity_chunk_placeholder(
                    idx, str(ln), p, f"computation error: {ex}"
                )
            )


def _add_ascii_safe_result_keys(row: dict) -> None:
    """
    Duplicate selected fields with ASCII-only keys. Some token/DB layers strip or
    alter Unicode in JSON keys (e.g. ``Beam Angle (°)``), which made the UI fall
    back to default beam 120 and hide U0.
    """
    bg = row.get("beam_angle_deg")
    if bg is not None:
        nn = _non_negative_beam_angle_deg(bg)
        if nn is not None:
            row["beam_angle_deg"] = nn
            row["Beam Angle (deg)"] = nn
            row["Beam angle (deg)"] = nn
    elif "Beam Angle (°)" in row:
        nn = _non_negative_beam_angle_deg(row["Beam Angle (°)"])
        if nn is not None:
            row["beam_angle_deg"] = nn
            row["Beam Angle (deg)"] = nn
            row["Beam angle (deg)"] = nn
    elif "Beam Angle (Â°)" in row:
        nn = _non_negative_beam_angle_deg(row["Beam Angle (Â°)"])
        if nn is not None:
            row["beam_angle_deg"] = nn
            row["Beam Angle (deg)"] = nn
            row["Beam angle (deg)"] = nn
    if "Beam Angle nominal (°)" in row:
        row["beam_angle_nominal_deg"] = row["Beam Angle nominal (°)"]
    if "Beam angle max (°)" in row:
        mxv = _non_negative_beam_angle_deg(row["Beam angle max (°)"])
        if mxv is not None:
            row["beam_angle_max_deg"] = mxv
            row["Beam angle max (deg)"] = mxv
    pairs = (
        ("U0_calculated", "u0_calculated"),
        ("U1_calculated", "u1_calculated"),
        ("E_min_grid_lx", "e_min_grid_lx"),
        ("E_avg_grid_lx", "e_avg_grid_lx"),
        ("E_max_grid_lx", "e_max_grid_lx"),
        ("E_avg_grid_direct_calibrated_lx", "e_avg_grid_direct_calibrated_lx"),
        ("E_avg_grid_includes_ir_boost", "e_avg_grid_includes_ir_boost"),
        ("Lux compliance basis", "lux_compliance_basis"),
    )
    for src, dst in pairs:
        if src in row:
            row[dst] = row[src]


def _avg_lux_for_compliance(row: dict) -> float:
    """
    Prefer **IES work-plane spatial mean** (E_avg on the grid) when present — that matches
    maintained illuminance on the task area better than the lumen-method average, which can
    greatly over-predict for real photometry (e.g. panels / wide beams).
    Fall back to lumen-method **Average Lux** when the grid did not run.
    """
    eg = row.get("E_avg_grid_lx")
    if eg is not None:
        try:
            v = float(eg)
            if v >= 0.0:
                return v
        except (TypeError, ValueError):
            pass
    return float(row.get("Average Lux") or 0.0)


def _row_with_compliance_metrics(row: dict, required_lux: float, required_u0: float) -> dict:
    avg = _avg_lux_for_compliance(row)
    u0 = row.get("U0_calculated")
    lux_gap = max(0.0, required_lux - avg)
    u0_gap = required_u0
    if u0 is not None:
        try:
            u0_gap = max(0.0, required_u0 - float(u0))
        except Exception:
            u0_gap = required_u0
    row["Lux gap"] = round(lux_gap, 4)
    row["U0 gap"] = round(float(u0_gap), 4)
    row["is_compliant"] = (lux_gap <= 1e-9) and (float(u0_gap) <= 1e-9)
    if row.get("E_avg_grid_lx") is not None:
        ir = row.get("Inter-reflection fraction (est.)")
        try:
            irv = float(ir) if ir is not None else 0.0
        except (TypeError, ValueError):
            irv = 0.0
        row["Lux compliance basis"] = (
            "IES work plane E_avg (incl. inter-reflection est.)"
            if irv > 1e-8
            else "IES work plane E_avg"
        )
    else:
        row["Lux compliance basis"] = "lumen method (no IES grid)"
    return row


def _uniformity_fallback_sweep_rows(
    closest_candidates: list,
    length: float,
    width: float,
    height: float,
    area: float,
    required_lux: float,
    required_uniformity: float,
    u_grid_n: int,
    max_rows: int = 3,
    max_avg_lux_mult: float = 1.65,
    fixture_span_extra: int = 120,
    max_uniformity_calls: int = 160,
    fast: bool = False,
    polygon=None,
    polygon_orientation_rad: float = 0.0,
) -> list:
    """
    When no layout meets both lux and U₀, sweep **upward** in fixture count (per luminaire
    combo from closest candidates) with a relaxed average-lux cap so spacing tightens and
    grid U₀ often improves. Rows still require lumen-method average ≥ required lux.
    """
    if not closest_candidates:
        return []

    from luxscale.app_settings import (
        get_inter_reflection_fraction,
        get_maintenance_factor,
        get_room_reflectance_preset_label,
    )

    mf_fb = get_maintenance_factor()
    irf_fb = get_inter_reflection_fraction()
    ir_lbl_fb = get_room_reflectance_preset_label()

    seeds: list[dict] = []
    seen_keys: set[tuple] = set()
    for seed in closest_candidates:
        try:
            lum = seed.get("Luminaire")
            pw = seed.get("Power (W)")
            eff = seed.get("Efficacy (lm/W)")
            if not lum or pw is None or eff is None:
                continue
            key = (lum, float(pw), float(eff))
        except (TypeError, ValueError):
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        seeds.append(seed)

    pool: list[dict] = []
    calls = 0
    min_spacing_m = 0.8
    max_avg_lux = float(required_lux) * max_avg_lux_mult
    call_budget = min(max_uniformity_calls, 80) if fast else max_uniformity_calls
    if not fast and required_uniformity >= 0.62:
        call_budget = min(300, max(call_budget, 220))
    span_use = min(fixture_span_extra, 80) if fast else fixture_span_extra
    n_seeds = len(seeds)
    budget_per_seed = (
        max(32, (call_budget + n_seeds - 1) // n_seeds) if n_seeds else call_budget
    )

    for seed in seeds:
        if calls >= call_budget:
            break
        lum_name = seed["Luminaire"]
        power = float(seed["Power (W)"])
        efficacy_display = float(seed["Efficacy (lm/W)"])
        lumens = power * efficacy_display
        if lumens <= 0:
            continue
        n0 = int(seed.get("Fixtures") or 0)
        if n0 < 1:
            continue

        uni_path = resolve_ies_path(lum_name, power)
        if not uni_path or not os.path.isfile(uni_path):
            continue

        ies_meta = None
        if ies_params_for_file:
            try:
                ies_meta = ies_params_for_file(uni_path)
            except Exception:
                ies_meta = None

        beam_deg: Optional[float] = None
        if ies_meta and ies_meta.get("beam_angle_deg") is not None:
            beam_deg = _non_negative_beam_angle_deg(ies_meta["beam_angle_deg"])
        if beam_deg is None and seed.get("Beam Angle (°)") is not None:
            beam_deg = _non_negative_beam_angle_deg(seed["Beam Angle (°)"])
        if (
            beam_deg is not None
            and required_uniformity >= 0.62
            and beam_deg < 34.0
        ):
            continue

        span = max(0, int(span_use))
        if fast:
            step = max(2, span // 25) if span > 25 else 2
        elif required_uniformity >= 0.62:
            step = 1
        else:
            step = max(1, span // 50) if span > 50 else 1
        n_last = n0 + span

        seed_calls = 0
        for num_fixtures in range(n0, n_last + 1, step):
            if calls >= call_budget:
                break
            if seed_calls >= budget_per_seed:
                break

            pairs_fb = spacing_factor_pairs(length, width, num_fixtures, min_spacing_m)
            if not pairs_fb:
                continue
            if polygon is not None:
                pairs_fb = _rank_factor_pairs_for_polygon(
                    pairs_fb, polygon, length, width, polygon_orientation_rad
                )

            avg_lux = (num_fixtures * lumens * mf_fb) / area
            total_power = num_fixtures * power
            if avg_lux > max_avg_lux:
                break
            if avg_lux + 1e-9 < float(required_lux):
                continue

            beam_val = beam_angle
            if ies_meta and ies_meta.get("beam_angle_deg") is not None:
                nn = _non_negative_beam_angle_deg(ies_meta["beam_angle_deg"])
                if nn is not None:
                    beam_val = round(nn, 1)
            elif seed.get("Beam Angle (°)") is not None:
                nn = _non_negative_beam_angle_deg(seed["Beam Angle (°)"])
                if nn is not None:
                    beam_val = round(nn, 1)

            best_row_fb = None
            best_rank_fb = None

            for best_x, best_y in pairs_fb:
                spacing_x = length / best_x
                spacing_y = width / best_y

                row = {
                    "Luminaire": lum_name,
                    "Power (W)": power,
                    "Efficacy (lm/W)": efficacy_display,
                    "Fixtures": num_fixtures,
                    "Spacing X (m)": round(spacing_x, 2),
                    "Spacing Y (m)": round(spacing_y, 2),
                    "Average Lux": round(float(avg_lux), 2),
                    "Uniformity": required_uniformity,
                    "Total Power (W/H)": total_power,
                    "Beam Angle (°)": beam_val,
                    "Beam Angle nominal (°)": beam_angle,
                    "Layout grid": f"{best_x}×{best_y}",
                    "layout_nx": int(best_x),
                    "layout_ny": int(best_y),
                }
                row["Beam source"] = (
                    "IES half-power estimate"
                    if (ies_meta and ies_meta.get("beam_angle_deg") is not None)
                    else "nominal catalog value"
                )
                _apply_ies_file_and_lumens_row(row, ies_meta, power, efficacy_display)
                _sync_beam_angle_output_keys(row, ies_meta)

                try:
                    met = compute_uniformity_metrics(
                        uni_path,
                        length,
                        width,
                        height,
                        num_fixtures,
                        lumens,
                        best_x,
                        best_y,
                        grid_n=u_grid_n,
                        calibrate_maintained_avg_lx=avg_lux,
                        inter_reflection_fraction=irf_fb,
                        inter_reflection_label=ir_lbl_fb,
                        polygon=polygon,
                        polygon_orientation_rad=polygon_orientation_rad,
                    )
                    calls += 1
                    seed_calls += 1
                except Exception as ux:
                    log_step("uniformity: fallback sweep failed", str(ux), path=uni_path)
                    continue

                row["U0_calculated"] = round(float(met["U0"]), 4)
                row["U1_calculated"] = round(float(met["U1"]), 4)
                row["E_min_grid_lx"] = round(float(met["E_min"]), 4)
                row["E_avg_grid_lx"] = round(float(met["E_avg"]), 4)
                row["E_max_grid_lx"] = round(float(met["E_max"]), 4)
                if met.get("e_avg_direct_calibrated_lx") is not None:
                    row["E_avg_grid_direct_calibrated_lx"] = round(
                        float(met["e_avg_direct_calibrated_lx"]), 4
                    )
                if met.get("e_avg_includes_ir_boost") is not None:
                    row["E_avg_grid_includes_ir_boost"] = bool(
                        met["e_avg_includes_ir_boost"]
                    )
                row["Maintenance factor"] = round(float(mf_fb), 4)
                row["Room reflectance preset"] = ir_lbl_fb
                row["Inter-reflection fraction (est.)"] = round(float(irf_fb), 4)
                if met.get("ies_scale_note"):
                    row["Uniformity (IES scale)"] = met["ies_scale_note"]

                _row_with_compliance_metrics(row, required_lux, required_uniformity)
                if required_lux > 0:
                    row["Standard margin (lux %)"] = round(
                        (required_lux - _avg_lux_for_compliance(row))
                        / required_lux
                        * 100,
                        3,
                    )
                if row.get("U0_calculated") is not None and required_uniformity > 0:
                    row["Standard margin (U0 %)"] = round(
                        (
                            required_uniformity
                            - float(row["U0_calculated"])
                        )
                        / required_uniformity
                        * 100,
                        3,
                    )

                emin = float(met.get("E_min") or 0.0)
                if emin > 1e-8 and row.get("U0_calculated") is not None:
                    # After grid↔lumen calibration Lux gap is often ~0 for all layouts; without an
                    # explicit U0 tiebreaker the first factor-pair in iteration order could win.
                    rank_fb = (
                        float(row["U0 gap"]),
                        float(row["Lux gap"]),
                        -float(row.get("U0_calculated") or 0.0),
                    )
                    if best_rank_fb is None or rank_fb < best_rank_fb:
                        best_rank_fb = rank_fb
                        best_row_fb = row

            if best_row_fb is not None:
                pool.append(best_row_fb)

    if not pool:
        return []

    pool.sort(
        key=lambda r: (
            -float(r.get("U0_calculated") or 0.0),
            float(r.get("Lux gap") or 0.0),
            float(r.get("U0 gap") or 0.0),
            float(r.get("Total Power (W/H)") or 0.0),
            int(r.get("Fixtures") or 0),
        )
    )

    out: list[dict] = []
    seen_layout: set[tuple] = set()
    u0_best = float(pool[0].get("U0_calculated") or 0.0)
    u0_rel_floor = (
        u0_best - 0.11 if required_uniformity >= 0.55 else -1.0
    )
    for row in pool:
        key = (
            row.get("Luminaire"),
            float(row.get("Power (W)", 0)),
            float(row.get("Efficacy (lm/W)", 0)),
            int(row.get("Fixtures", 0)),
        )
        if key in seen_layout:
            continue
        u0r = float(row.get("U0_calculated") or 0.0)
        if len(out) > 0 and u0r + 1e-12 < u0_rel_floor:
            continue
        seen_layout.add(key)
        row = dict(row)
        row["Selection"] = "uniformity_fixture_sweep_fallback"
        _sync_beam_angle_output_keys(row, _ies_meta_for_result_row(row))
        _add_ascii_safe_result_keys(row)
        out.append(row)
        if len(out) >= max_rows:
            break
    return out


def _reorder_interior_options_for_compact_room(
    options: list,
    zone: str,
    length: float,
    width: float,
    area: float,
) -> tuple:
    """
    Prefer **SC triproof** (weatherproof linear) first for compact interior plans — often
    easier to fill uniform grids in tight or modest floor plates than downlights alone.
    """
    if zone != "interior":
        return options, False
    compact = float(area) <= 400.0 or min(float(length), float(width)) <= 14.0
    if not compact:
        return options, False
    tri = [o for o in options if o[0] == "SC triproof"]
    rest = [o for o in options if o[0] != "SC triproof"]
    if not tri:
        return options, False
    return tri + rest, True


def _issue_label(issue: str) -> str:
    return {
        "lux": "average illuminance",
        "uniformity": "uniformity (U₀)",
        "lux_and_uniformity": "illuminance and uniformity",
        "not_evaluated": "search / IES availability",
    }.get(issue, issue)


def _recommendation_for_luminaire(
    lum: str,
    issue: str,
    length: float,
    width: float,
    area: float,
    height: float,
    zone: str,
) -> str:
    L = (lum or "").lower()
    if "backlight" in L:
        return (
            "Panel/backlight photometry is typically wide; long narrow rooms or very large floors "
            "can limit U₀ before power density becomes excessive. Consider linear weatherproof (triproof) "
            "rows, downlight grids, or revising mounting height / target lux."
        )
    if "triproof" in L:
        return (
            "Weatherproof linear fittings need enough run length and suitable factors for an even grid; "
            "very small rooms may not fit enough modules. Smaller wattages or mixed layouts (e.g. perimeter + linear) may help."
        )
    if "downlight" in L:
        return (
            "Spot-based optics concentrate candela; reaching high U₀ may require more fixtures or tighter spacing—watch density and glare."
        )
    if "flood" in L or "street" in L:
        return (
            "Exterior-type beams are often asymmetric; high U₀ indoors is difficult—confirm the space type matches the product."
        )
    if "highbay" in L:
        return (
            "High-bay distributions may not match low or very wide rooms; verify ceiling height and spacing vs beam spread."
        )
    return (
        "Review room dimensions, luminaire spacing, and whether another family from the catalog suits the grid better."
    )


def _format_family_shortfall_sentence(
    lum: str,
    n: int,
    required_u0: float,
    u0c: Optional[float],
    issue: str,
) -> str:
    u0s = f"{float(u0c):.3f}" if u0c is not None else "n/a"
    return (
        f"{lum} cannot meet the standard in this room with the lines searched "
        f"({n} luminaire/power/efficacy combination(s)). "
        f"Standard U₀ = {required_u0:.2f}; best calculated U₀ ≈ {u0s}. "
        f"Main limit: {_issue_label(issue)}."
    )


def _build_fixture_family_shortfall_summary(
    closest_candidates: list,
    families_with_compliant: set,
    families_evaluated: set,
    options: list,
    required_uniformity: float,
    length: float,
    width: float,
    area: float,
    height: float,
    zone: str,
) -> list:
    """Per luminaire **family** that was actually searched but never produced a compliant option."""
    offered = {name for name, _powers in options}
    by_lum: dict = {}
    for r in closest_candidates or []:
        lum = r.get("Luminaire")
        if not lum:
            continue
        by_lum.setdefault(str(lum), []).append(r)

    out: list = []
    for lum in sorted(offered):
        if lum in families_with_compliant:
            continue
        if lum not in families_evaluated:
            # Search stopped before this family (e.g. max compliant options reached)—do not
            # report as "IES missing" or failed.
            continue
        rows = by_lum.get(lum) or []
        if not rows:
            out.append(
                {
                    "luminaire": lum,
                    "attempts": 0,
                    "standard_u0": round(float(required_uniformity), 4),
                    "best_calculated_u0": None,
                    "issue": "not_evaluated",
                    "summary": (
                        f"{lum}: no closest candidate was recorded for this family "
                        "(e.g. IES missing for all wattages searched, or no layout evaluated)."
                    ),
                    "recommendation": _recommendation_for_luminaire(
                        lum, "not_evaluated", length, width, area, height, zone
                    ),
                }
            )
            continue
        best = max(rows, key=lambda x: float(x.get("U0_calculated") or 0.0))
        u0c = best.get("U0_calculated")
        n = len(rows)
        lux_gaps = [float(x.get("Lux gap") or 0) for x in rows]
        u0_gaps = [float(x.get("U0 gap") or 0) for x in rows]
        if max(lux_gaps) > 1e-6 and max(u0_gaps) > 1e-6:
            issue = "lux_and_uniformity"
        elif max(lux_gaps) > 1e-6:
            issue = "lux"
        else:
            issue = "uniformity"
        u0f = float(u0c) if u0c is not None else None
        out.append(
            {
                "luminaire": lum,
                "attempts": n,
                "standard_u0": round(float(required_uniformity), 4),
                "best_calculated_u0": round(u0f, 4) if u0f is not None else None,
                "issue": issue,
                "summary": _format_family_shortfall_sentence(
                    lum, n, required_uniformity, u0f, issue
                ),
                "recommendation": _recommendation_for_luminaire(
                    lum, issue, length, width, area, height, zone
                ),
            }
        )
    return out


def _apply_best_effort_compliance_note(
    row: dict,
    required_uniformity: float,
) -> None:
    """Yellow-card style note when the row is not fully compliant but is still a returned option."""
    if row.get("is_compliant"):
        return
    u0 = row.get("U0_calculated")
    u0s = f"{float(u0):.2f}" if u0 is not None else "n/a"
    row["Compliance note"] = (
        f"Standard U₀ = {required_uniformity:.2f}; calculated U₀ = {u0s}. "
        "This is the best achievable solution for this room geometry with the luminaires searched "
        "(this is the best solution in this place)."
    )


def calculate_lighting(
    place,
    sides,
    height,
    standard_row=None,
    trace: Optional[CalculationTrace] = None,
    fast: bool = False,
    *,
    polygon=None,
    polygon_orientation_rad: float = 0.0,
    polygon_fill_ratio: Optional[float] = None,
):
    """
    If standard_row is provided (from standards_cleaned.json), use Em_r_lx as target lux and Uo as uniformity.
    Otherwise use define_places[place] (legacy room-type presets).
    IES catalog supplies beam angle and grid uniformity when available.

    ``fast=True``: cap at 3 compliant options, step fixture count by 2 in the main sweep,
    and use coarser steps + lower budget in the uniformity fallback sweep (less accurate,
    quicker).

    Optional ``polygon`` / ``polygon_orientation_rad`` / ``polygon_fill_ratio`` (Phase B
    ``/cad_calc`` path): when set, U₀ sampling uses a polygon-clipped work-plane grid
    and G is boosted via :func:`uniformity_grid_n_for_polygon` so effective sample
    density tracks the rectangular path. Legacy ``/calculate`` callers omit these
    and behaviour is unchanged.
    """
    log_step(
        "calculate_lighting: start",
        None,
        place=place,
        sides=sides,
        height=height,
        standard_ref_no=str(standard_row.get("ref_no")) if standard_row else None,
        fast=bool(fast),
        polygon_clipped=bool(polygon is not None),
    )
    if trace is not None:
        trace.step(
            "cl_01_calculate_lighting_enter",
            place=place,
            sides=sides,
            height=height,
            standard_ref=str(standard_row.get("ref_no")) if standard_row else None,
            fast=bool(fast),
            polygon_clipped=bool(polygon is not None),
        )

    a, b, c, d = sides
    length = max(a, c)
    width = max(b, d)
    area = cyclic_quadrilateral_area(a, b, c, d)
    zone = determine_zone(height)
    if standard_row is not None:
        required_lux = float(standard_row.get("Em_r_lx") or 300)
        uo = standard_row.get("Uo")
        required_uniformity = float(uo) if uo is not None else 0.6
    else:
        if place is None or place not in define_places:
            raise ValueError(
                f"Unknown place {place!r}; use one of {list(define_places.keys())}"
            )
        required_lux = define_places[place]["lux"]
        required_uniformity = define_places[place]["uniformity"]

    log_step(
        "calculate_lighting: targets",
        None,
        zone=zone,
        required_lux=required_lux,
        required_uniformity=required_uniformity,
        area_m2=round(float(area), 4),
        length_m=length,
        width_m=width,
    )
    if trace is not None:
        trace.step(
            "cl_02_geometry_and_targets",
            zone=zone,
            length_m=length,
            width_m=width,
            area_m2=round(float(area), 2),
            required_lux=required_lux,
            required_Uo=required_uniformity,
        )

    options = determine_luminaire(height)
    options, prioritized_weatherproof_triproof = _reorder_interior_options_for_compact_room(
        options, zone, length, width, area
    )
    if polygon is not None and polygon_fill_ratio is not None:
        u_grid_n = uniformity_grid_n_for_polygon(area, float(polygon_fill_ratio))
    else:
        u_grid_n = uniformity_grid_n_for_room(length, width)
    if trace is not None:
        trace.step(
            "cl_03_options_and_uniformity_grid",
            luminaire_options=len(options),
            workplane_grid_n=u_grid_n,
            polygon_clipped=bool(polygon is not None),
            polygon_fill_ratio=(
                float(polygon_fill_ratio) if polygon_fill_ratio is not None else None
            ),
        )

    try:
        from luxscale.app_settings import (
            get_inter_reflection_fraction,
            get_maintenance_factor,
            get_max_solutions_total,
            get_room_reflectance_preset_label,
        )

        # Admin "max solutions" = max **compliant** options (both lux and U0 meet the standard).
        # Search stops as soon as this many compliant rows are collected (discovery order).
        max_solutions_cap = int(get_max_solutions_total())
        mf = get_maintenance_factor()
        irf = get_inter_reflection_fraction()
        ir_lbl = get_room_reflectance_preset_label()
    except Exception:
        max_solutions_cap = 80
        mf = 0.8
        irf = 0.12
        ir_lbl = "Medium (ρ ≈ 0.7 / 0.5 / 0.2)"

    uniformity_report_chunks = []
    _mode_line = (
        "Mode: FAST (max 3 options, fixture step 2, coarser fallback).\n"
        if fast
        else "Mode: FULL.\n"
    )
    uniformity_header = (
        "LuxScaleAI - Uniformity (point-by-point IES grid)\n"
        f"Timestamp: {datetime.datetime.now().isoformat()}\n"
        f"{_mode_line}"
        f"Room length (m): {length}, width (m): {width}, ceiling height (m): {height}\n"
        f"Required lux: {required_lux}, Standard Uo: {required_uniformity}\n"
        f"Maintenance factor (design): {mf}; room reflectance preset: {ir_lbl}\n"
        f"Work plane z = 0.75 m; fixture grid symmetric on full floor (edge inset = half of "
        f"centre-to-centre spacing); illuminance grid {u_grid_n}x{u_grid_n} same rule.\n"
    )

    results = []
    closest_candidates = []
    if fast:
        max_solutions_cap = min(3, max_solutions_cap)
    fixture_step = 2 if fast else 1
    stop_search = False
    capped_at_max = False
    had_non_compliant_closest = False
    used_uniformity_sweep_fallback = False
    families_with_compliant: set = set()
    families_evaluated: set = set()

    for lum_name, powers in options:
        if stop_search:
            break
        families_evaluated.add(lum_name)
        for power in powers:
            if stop_search:
                break
            ies_meta = None
            ies_path = None
            if resolve_ies_path and ies_params_for_file:
                ies_path = resolve_ies_path(lum_name, power)
                if ies_path:
                    try:
                        ies_meta = ies_params_for_file(ies_path)
                        lm = float(ies_meta["lumens_per_lamp"])
                        if lm <= 0:
                            log_step(
                                "IES: non-positive header lumens; flux uses rated W*lm/W; "
                                "keeping IES for beam angle and uniformity",
                                None,
                                path=os.path.basename(ies_path),
                                lumens=lm,
                                beam_deg=ies_meta.get("beam_angle_deg"),
                            )
                        else:
                            log_step(
                                "IES: parsed",
                                os.path.basename(ies_path),
                                luminaire=lum_name,
                                power_w=power,
                                lumens=round(lm, 2),
                                beam_deg=ies_meta.get("beam_angle_deg"),
                            )
                    except Exception as ex:
                        log_step("IES: parse failed", str(ex), path=ies_path)
                        ies_meta = None
                        ies_path = None

            if trace is not None:
                trace.step(
                    "cl_04_ies_resolve",
                    luminaire=lum_name,
                    power_W=power,
                    ies_ok=bool(ies_meta),
                    ies_file=os.path.basename(ies_path) if ies_path else None,
                )

            efficacy_list = (
                led_efficacy[zone]
                if isinstance(led_efficacy[zone], list)
                else [led_efficacy[zone]]
            )

            for efficacy in efficacy_list:
                if stop_search:
                    break
                uniformity_time_acc = 0.0
                uniformity_calls = 0
                lumens = power * efficacy
                efficacy_display = efficacy
                if ies_meta and ies_meta.get("beam_angle_deg") is not None:
                    nn = _non_negative_beam_angle_deg(ies_meta["beam_angle_deg"])
                    beam_val = round(nn, 1) if nn is not None else beam_angle
                else:
                    beam_val = beam_angle

                if lumens <= 0:
                    log_step(
                        "calculate_lighting: skip non-positive lumens",
                        None,
                        luminaire=lum_name,
                        power=power,
                    )
                    continue

                total_lumens_needed = (required_lux * area) / mf
                min_fixtures = int(total_lumens_needed / lumens) + 1
                # Search for the least fixture count that passes BOTH lux and U0.
                search_span = max(15, min(60, int(min_fixtures * 0.75)))
                if min_fixtures > 200:
                    search_span = min(search_span, 28)
                elif min_fixtures > 120:
                    search_span = min(search_span, 40)
                max_fixtures = min_fixtures + search_span
                min_spacing_m = 0.8  # logical upper-density floor
                max_avg_lux = required_lux * 1.35  # avoid severe over-lighting candidates

                found_pass = False
                closest_rank = None
                closest_row = None

                log_step(
                    "calculate_lighting: fixture sweep",
                    None,
                    luminaire=lum_name,
                    power_w=power,
                    efficacy=efficacy_display,
                    min_fixtures=min_fixtures,
                    max_fixtures=max_fixtures,
                    uniformity_grid_n=u_grid_n,
                    floor_area_m2=round(float(area), 2),
                    fixture_step=fixture_step,
                    fast=bool(fast),
                )

                for num_fixtures in range(min_fixtures, max_fixtures + 1, fixture_step):
                    if stop_search or len(results) >= max_solutions_cap:
                        break

                    factor_pairs = spacing_factor_pairs(
                        length, width, num_fixtures, min_spacing_m
                    )
                    if not factor_pairs:
                        continue
                    if polygon is not None:
                        factor_pairs = _rank_factor_pairs_for_polygon(
                            factor_pairs,
                            polygon,
                            length,
                            width,
                            polygon_orientation_rad,
                        )

                    avg_lux = (num_fixtures * lumens * mf) / area
                    total_power = num_fixtures * power
                    if avg_lux > max_avg_lux:
                        break

                    uni_path = None
                    if resolve_ies_path:
                        uni_path = resolve_ies_path(lum_name, power)

                    best_row_n = None
                    best_rank_n = None
                    found_compliant_n = False

                    for best_x, best_y in factor_pairs:
                        spacing_x = length / best_x
                        spacing_y = width / best_y

                        row = {
                            "Luminaire": lum_name,
                            "Power (W)": power,
                            "Efficacy (lm/W)": efficacy_display,
                            "Fixtures": num_fixtures,
                            "Spacing X (m)": round(spacing_x, 2),
                            "Spacing Y (m)": round(spacing_y, 2),
                            "Average Lux": round(float(avg_lux), 2),
                            "Uniformity": required_uniformity,
                            "Total Power (W/H)": total_power,
                            "Beam Angle (°)": beam_val,
                            "Beam Angle nominal (°)": beam_angle,
                            "Layout grid": f"{best_x}×{best_y}",
                            "layout_nx": int(best_x),
                            "layout_ny": int(best_y),
                        }
                        row["Beam source"] = (
                            "IES half-power estimate"
                            if (ies_meta and ies_meta.get("beam_angle_deg") is not None)
                            else "nominal catalog value"
                        )
                        _apply_ies_file_and_lumens_row(
                            row, ies_meta, float(power), float(efficacy_display)
                        )

                        met = None
                        if (
                            uni_path
                            and os.path.isfile(uni_path)
                            and compute_uniformity_metrics
                            and format_uniformity_report_txt
                        ):
                            try:
                                _log_every = 6 if fast else 12
                                if num_fixtures == min_fixtures or (
                                    (num_fixtures - min_fixtures) % _log_every == 0
                                ):
                                    log_step(
                                        "calculate_lighting: uniformity",
                                        f"n={num_fixtures} grid={best_x}x{best_y}",
                                        luminaire=lum_name,
                                        fixtures=num_fixtures,
                                    )
                                _t_uni = time.perf_counter()
                                maintained_avg_lx = (num_fixtures * lumens * mf) / area
                                met = compute_uniformity_metrics(
                                    uni_path,
                                    length,
                                    width,
                                    height,
                                    num_fixtures,
                                    lumens,
                                    best_x,
                                    best_y,
                                    grid_n=u_grid_n,
                                    calibrate_maintained_avg_lx=maintained_avg_lx,
                                    inter_reflection_fraction=irf,
                                    inter_reflection_label=ir_lbl,
                                    polygon=polygon,
                                    polygon_orientation_rad=polygon_orientation_rad,
                                )
                                uniformity_time_acc += time.perf_counter() - _t_uni
                                uniformity_calls += 1
                                row["U0_calculated"] = round(float(met["U0"]), 4)
                                row["U1_calculated"] = round(float(met["U1"]), 4)
                                row["E_min_grid_lx"] = round(float(met["E_min"]), 4)
                                row["E_avg_grid_lx"] = round(float(met["E_avg"]), 4)
                                row["E_max_grid_lx"] = round(float(met["E_max"]), 4)
                                if met.get("e_avg_direct_calibrated_lx") is not None:
                                    row["E_avg_grid_direct_calibrated_lx"] = round(
                                        float(met["e_avg_direct_calibrated_lx"]), 4
                                    )
                                if met.get("e_avg_includes_ir_boost") is not None:
                                    row["E_avg_grid_includes_ir_boost"] = bool(
                                        met["e_avg_includes_ir_boost"]
                                    )
                                row["Maintenance factor"] = round(float(mf), 4)
                                row["Room reflectance preset"] = ir_lbl
                                row["Inter-reflection fraction (est.)"] = round(float(irf), 4)
                                if met.get("ies_scale_note"):
                                    row["Uniformity (IES scale)"] = met["ies_scale_note"]
                            except Exception as ux:
                                log_step("uniformity: failed", str(ux), path=uni_path)

                        _row_with_compliance_metrics(row, required_lux, required_uniformity)
                        if required_lux > 0:
                            row["Standard margin (lux %)"] = round(
                                (required_lux - _avg_lux_for_compliance(row))
                                / required_lux
                                * 100,
                                3,
                            )
                        if row.get("U0_calculated") is not None and required_uniformity > 0:
                            row["Standard margin (U0 %)"] = round(
                                (
                                    required_uniformity
                                    - float(row["U0_calculated"])
                                )
                                / required_uniformity
                                * 100,
                                3,
                            )
                        lux_ok = float(row["Lux gap"]) <= 1e-9
                        u0_ok = float(row["U0 gap"]) <= 1e-9

                        if lux_ok and u0_ok:
                            row["Selection"] = "least_fixture_count_compliant"
                            _sync_beam_angle_output_keys(row, ies_meta)
                            _annotate_fixture_density(row, area)
                            _add_ascii_safe_result_keys(row)
                            results.append(row)
                            families_with_compliant.add(lum_name)
                            if len(results) >= max_solutions_cap:
                                stop_search = True
                                capped_at_max = True
                            found_pass = True
                            if met is not None and format_uniformity_report_txt:
                                uniformity_report_chunks.append(
                                    format_uniformity_report_txt(
                                        len(results) - 1,
                                        lum_name,
                                        power,
                                        required_uniformity,
                                        uni_path,
                                        met,
                                    )
                                )
                            log_step(
                                "calculate_lighting: option accepted",
                                f"avg_lux={row['Average Lux']} grid={best_x}x{best_y}",
                                luminaire=lum_name,
                                power_w=power,
                                fixtures=num_fixtures,
                                ies=bool(ies_meta),
                            )
                            found_compliant_n = True
                            break

                        rank = (
                            float(row["U0 gap"]),
                            float(row["Lux gap"]),
                            -float(row["U0_calculated"] or 0.0),
                            float(total_power),
                            int(num_fixtures),
                        )
                        if best_rank_n is None or rank < best_rank_n:
                            best_rank_n = rank
                            best_row_n = row

                    if found_compliant_n:
                        break

                    if best_row_n is not None:
                        rank = (
                            float(best_row_n["U0 gap"]),
                            float(best_row_n["Lux gap"]),
                            -float(best_row_n.get("U0_calculated") or 0.0),
                            float(total_power),
                            int(num_fixtures),
                        )
                        if closest_rank is None or rank < closest_rank:
                            closest_rank = rank
                            closest_row = best_row_n

                if trace is not None:
                    trace.step(
                        "cl_05_lumen_search_and_uniformity",
                        luminaire=lum_name,
                        power_W=power,
                        efficacy_lm_per_W=efficacy_display,
                        min_fixtures=min_fixtures,
                        max_fixtures=max_fixtures,
                        uniformity_evaluations=uniformity_calls,
                        uniformity_seconds=round(uniformity_time_acc, 4),
                    )

                if not found_pass and closest_row is not None:
                    closest_row["Selection"] = "closest_non_compliant_candidate"
                    _sync_beam_angle_output_keys(closest_row, ies_meta)
                    _annotate_fixture_density(closest_row, area)
                    _add_ascii_safe_result_keys(closest_row)
                    closest_candidates.append(closest_row)
                    log_step(
                        "calculate_lighting: closest non-compliant",
                        None,
                        luminaire=lum_name,
                        power_w=power,
                        efficacy=efficacy_display,
                        fixtures=closest_row.get("Fixtures"),
                        avg_lux=closest_row.get("Average Lux"),
                        u0=closest_row.get("U0_calculated"),
                        lux_gap=closest_row.get("Lux gap"),
                        u0_gap=closest_row.get("U0 gap"),
                    )

                if stop_search:
                    break

            if stop_search:
                break

        if stop_search:
            break

    if not results and closest_candidates:
        had_non_compliant_closest = True
        closest_candidates.sort(
            key=lambda r: (
                float(r.get("U0 gap", 1e9)),
                float(r.get("Lux gap", 1e9)),
                -float(r.get("U0_calculated") or 0.0),
                float(r.get("Total Power (W/H)", 1e12)),
                int(r.get("Fixtures", 10**9)),
            )
        )
        log_step(
            "calculate_lighting: no compliant options; uniformity fixture sweep fallback",
            f"{len(closest_candidates)} seed candidate(s)",
        )
        fb_rows = _uniformity_fallback_sweep_rows(
            closest_candidates,
            length,
            width,
            height,
            area,
            required_lux,
            required_uniformity,
            u_grid_n,
            fast=bool(fast),
            polygon=polygon,
            polygon_orientation_rad=polygon_orientation_rad,
        )
        for row in fb_rows:
            _sync_beam_angle_output_keys(row, _ies_meta_for_result_row(row))
            _annotate_fixture_density(row, area)
            results.append(row)
            if row.get("is_compliant"):
                ln = row.get("Luminaire")
                if ln:
                    families_with_compliant.add(str(ln))
        if fb_rows:
            used_uniformity_sweep_fallback = True
            log_step(
                "calculate_lighting: fallback options returned",
                f"{len(fb_rows)} row(s)",
            )
        else:
            log_step(
                "calculate_lighting: uniformity sweep produced no extra rows",
                None,
            )

    fixture_family_shortfall = _build_fixture_family_shortfall_summary(
        closest_candidates,
        families_with_compliant,
        families_evaluated,
        options,
        required_uniformity,
        length,
        width,
        area,
        height,
        zone,
    )

    _sync_uniformity_report_chunks(
        results,
        uniformity_report_chunks,
        length,
        width,
        height,
        u_grid_n,
        required_uniformity,
        polygon=polygon,
        polygon_orientation_rad=polygon_orientation_rad,
    )

    if uniformity_report_chunks and write_uniformity_session_txt:
        try:
            rep_path = write_uniformity_session_txt(
                uniformity_header, uniformity_report_chunks
            )
            log_step("uniformity: report file", rep_path)
            if trace is not None:
                trace.step("cl_06_uniformity_report_txt", path=rep_path)
        except Exception as rex:
            log_step("uniformity: report write failed", str(rex))

    for row in results:
        _apply_best_effort_compliance_note(row, required_uniformity)

    log_step(
        "calculate_lighting: done", f"{len(results)} option(s)", count=len(results)
    )
    if trace is not None:
        trace.step(
            "cl_07_calculate_lighting_done",
            result_rows=len(results),
            length_m=length,
            width_m=width,
            fast=bool(fast),
        )
    try:
        from luxscale.app_settings import get_interior_height_max_m

        th = float(get_interior_height_max_m())
    except Exception:
        th = 5.0
    any_compliant = any(bool(r.get("is_compliant")) for r in results)
    meta = {
        "total_solutions_returned": len(results),
        "max_solutions_cap": max_solutions_cap,
        "calc_mode": "fast" if fast else "full",
        "fixture_count_step": fixture_step,
        "capped_at_max": bool(capped_at_max),
        "compliant_cap_only": True,
        "used_closest_non_compliant_fallback": False,
        "used_uniformity_sweep_fallback": bool(used_uniformity_sweep_fallback),
        "no_compliant_options": not any_compliant,
        "had_non_compliant_closest": bool(had_non_compliant_closest),
        "interior_height_threshold_m": th,
        "prioritized_weatherproof_triproof": bool(prioritized_weatherproof_triproof),
        "fixture_family_shortfall": fixture_family_shortfall,
        "workplane_grid_n": u_grid_n,
        "polygon_clipped_uniformity": bool(polygon is not None),
    }
    if polygon is not None:
        try:
            from luxscale.uniformity_calculator import work_plane_grid_polygon

            _pts = work_plane_grid_polygon(
                polygon, length, width, u_grid_n, float(polygon_orientation_rad)
            )
            n_eff = len(_pts)
            meta["effective_sample_count"] = n_eff
            meta["sample_density_per_m2"] = round(n_eff / max(area, 1e-12), 4)
        except Exception:
            pass
    return results, length, width, meta

