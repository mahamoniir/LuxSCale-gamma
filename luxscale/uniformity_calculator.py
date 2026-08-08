"""
Point-by-point illuminance on a horizontal work plane from Type C IES candela data.
U0 = E_min / E_avg, U1 = E_min / E_max (per uniformity/*.md).
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from luxscale.ies_fixture_params import _load_ies_data_cached
from luxscale.lighting_calc.constants import (
    ies_lumen_to_design_ratio_max,
    ies_lumen_to_design_ratio_min,
)
from luxscale.paths import project_root

DEFAULT_GRID_N = 10
DEFAULT_WALL_MARGIN_M = 0.5
DEFAULT_WORK_PLANE_HEIGHT_M = 0.75


def uniformity_grid_n_for_room(length_m: float, width_m: float) -> int:
    """
    Large floors need fewer work-plane samples: each sample sums over every fixture,
    and we also sweep num_fixtures many times — O(grid^2 * n_fixtures * steps) grows fast.
    """
    area = float(length_m) * float(width_m)
    if area >= 3500:
        return 5
    if area >= 1800:
        return 6
    if area >= 900:
        return 8
    return DEFAULT_GRID_N


def uniformity_grid_n_for_polygon(polygon_area_m2: float, fill_ratio: float) -> int:
    """
    Grid density for polygon-clipped work-plane sampling.

    Bumps G above the rectangular bracket so ``α · G² ≈ G_rect²`` — the effective
    sample count after ``polygon.contains`` filtering roughly matches what a
    rectangular room of the same polygon area would get.

    Formula::

        G = min(ceil(G_rect / sqrt(α)), G_rect + 4)

    The ``G_rect + 4`` cap fires for α ≲ 0.51 (where ``10/√α`` first exceeds 14
    at the default G_rect=10 bracket). That single cap both bounds runtime (~2×
    vs rectangular) and prevents α→0 from sending G→∞ — there is no separate
    α floor. At α = 0.30 the result is still under rectangular density
    (≈0.59×) but compute stays interactive.
    """
    area = max(float(polygon_area_m2), 1e-12)
    # Square of equal area → same area bracket as the rectangular path.
    side = math.sqrt(area)
    g_rect = uniformity_grid_n_for_room(side, side)
    alpha = max(1e-12, min(1.0, float(fill_ratio)))
    g_raw = math.ceil(g_rect / math.sqrt(alpha))
    # Cap fires here for α ≲ 0.51 when g_rect = 10 (ceil(10/√α) > 14).
    return min(int(g_raw), g_rect + 4)


def _polygon_in_engine_frame(
    poly: Any,
    length: float,
    width: float,
    orientation_rad: float,
) -> Any:
    """
    Map a world-coordinate polygon into the engine's equivalent-rectangle frame
    ``[0, length] × [0, width]`` so sample points and fixtures share one space.

    Steps: rotate by ``-orientation``, take the oriented AABB, then affine-map
    that box onto the engine rectangle (same aspect ratio by construction of
    ``build_equivalent_rectangle``).
    """
    from luxscale.lighting_calc.polygon import Polygon

    c = math.cos(-orientation_rad)
    s = math.sin(-orientation_rad)
    rotated = [(c * x - s * y, s * x + c * y) for x, y in poly.vertices]
    xs = [p[0] for p in rotated]
    ys = [p[1] for p in rotated]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    bw = xmax - xmin
    bl = ymax - ymin
    if bw <= 1e-12 or bl <= 1e-12:
        raise ValueError("oriented bbox is degenerate; cannot map polygon to engine frame")
    L = float(length)
    W = float(width)
    mapped = [
        ((x - xmin) / bw * L, (y - ymin) / bl * W) for x, y in rotated
    ]
    return Polygon.from_vertices(mapped)


def work_plane_grid_polygon(
    poly: Any,
    length: float,
    width: float,
    grid_n: int,
    orientation_rad: float = 0.0,
) -> List[Tuple[float, float]]:
    """
    Sample points on a G×G grid over the equivalent rectangle, filtered to the
    polygon interior.

    Uses the same half-bay inset rule as the rectangular path
    (``(i + 0.5) * L / G``) — samples never sit flush against a wall by
    construction. There is no fixed physical ``wall_margin``; clearance comes
    from the half-bay inset plus ``contains(..., on_edge=False)``.

    The world-coordinate polygon is first mapped into the engine rectangle
    frame (see :func:`_polygon_in_engine_frame`) so fixtures (still laid out on
    the equivalent rectangle in Phase B) and samples share coordinates.
    """
    gn = max(1, int(grid_n))
    candidates = work_plane_grid_symmetric(length, width, gn)
    try:
        proxy = _polygon_in_engine_frame(poly, length, width, orientation_rad)
    except Exception:
        return candidates
    inside = [
        (x, y) for x, y in candidates if proxy.contains(x, y, on_edge=False)
    ]
    # Safety: never return an empty sample set (would break U0 denominators).
    return inside if inside else candidates


def _wrap360(h: float) -> float:
    x = h % 360.0
    return x + 360.0 if x < 0 else x


def _interp1d(x_new: float, xs: np.ndarray, ys: np.ndarray) -> float:
    if xs.size == 0:
        return 0.0
    if xs.size == 1:
        return float(ys[0])
    return float(np.interp(x_new, xs, ys))


def _circ_dist_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _fold_h_azimuth_to_quarter(h_deg: float) -> float:
    """Map any azimuth to [0, 90]° for quarter-symmetric Type C photometry (0–90° H planes)."""
    h = _wrap360(h_deg)
    if h > 180.0:
        h = 360.0 - h
    if h > 90.0:
        h = 180.0 - h
    return h


def candela_at_angle_type_c(ies_data, h_deg: float, v_deg: float) -> float:
    """
    Type C candela: vertical interpolation on each H slice, **linear interpolation between
    adjacent H planes**, and azimuth folding for common symmetric reductions.

    ``candela_at_angle_simple`` only snapped to the nearest H slice, which mis-handles
    asymmetric / multi-plane files (e.g. 50°×20°) where effective spread varies with H.
    """
    v_deg = float(np.clip(v_deg, 0.0, 180.0))
    h_deg = _wrap360(h_deg)

    hs = sorted(ies_data.horizontal_angles)
    va = np.asarray(ies_data.vertical_angles, dtype=float)
    if not hs or va.size < 1:
        return 0.0

    h_max = float(max(hs))

    if h_max <= 90.0 + 1e-6:
        h_use = _fold_h_azimuth_to_quarter(h_deg)
    elif h_max <= 180.0 + 1e-6:
        h_use = h_deg if h_deg <= 180.0 else 360.0 - h_deg
    else:
        h_use = h_deg

    if len(hs) == 1:
        row = np.asarray(ies_data.candela_values[hs[0]], dtype=float)
        return max(0.0, _interp1d(v_deg, va, row))

    if h_use <= hs[0] + 1e-12:
        row = np.asarray(ies_data.candela_values[hs[0]], dtype=float)
        return max(0.0, _interp1d(v_deg, va, row))
    if h_use >= hs[-1] - 1e-12:
        row = np.asarray(ies_data.candela_values[hs[-1]], dtype=float)
        return max(0.0, _interp1d(v_deg, va, row))

    for i in range(len(hs) - 1):
        h_lo, h_hi = hs[i], hs[i + 1]
        if h_lo <= h_use <= h_hi:
            denom = h_hi - h_lo
            t = (h_use - h_lo) / denom if denom > 1e-15 else 0.0
            row_lo = np.asarray(ies_data.candela_values[h_lo], dtype=float)
            row_hi = np.asarray(ies_data.candela_values[h_hi], dtype=float)
            cd_lo = _interp1d(v_deg, va, row_lo)
            cd_hi = _interp1d(v_deg, va, row_hi)
            return max(0.0, cd_lo + t * (cd_hi - cd_lo))

    return 0.0


def candela_at_angle_simple(ies_data, h_deg: float, v_deg: float) -> float:
    """Backward-compatible name; uses :func:`candela_at_angle_type_c`."""
    return candela_at_angle_type_c(ies_data, h_deg, v_deg)


def characterize_beam(ies_data) -> Dict[str, Any]:
    """
    Per horizontal slice: vertical angle where candela first drops below 50 % of that row's peak.
    Useful to see asymmetric beams (min/max half-angle across H planes).
    """
    hs = sorted(ies_data.horizontal_angles)
    va = np.asarray(ies_data.vertical_angles, dtype=float)
    half_angles: Dict[float, float] = {}
    for h in hs:
        row = np.asarray(ies_data.candela_values[h], dtype=float)
        peak = float(np.max(row))
        if peak < 1e-6:
            continue
        threshold = peak * 0.5
        below = np.where(row < threshold)[0]
        if len(below) == 0:
            half_angles[float(h)] = float(va[-1])
        else:
            half_angles[float(h)] = float(va[int(below[0])])
    vals = list(half_angles.values())
    asymmetric = False
    if len(vals) >= 2:
        asymmetric = (max(vals) - min(vals)) > 5.0
    return {
        "half_angles_by_h_plane_deg": half_angles,
        "min_half_angle_deg": min(vals) if vals else 0.0,
        "max_half_angle_deg": max(vals) if vals else 0.0,
        "is_asymmetric": asymmetric,
    }


def angles_fixture_to_point(
    fx: float,
    fy: float,
    ceiling_z: float,
    px: float,
    py: float,
    plane_z: float,
) -> Tuple[float, float, float]:
    dx = px - fx
    dy = py - fy
    dz = plane_z - ceiling_z
    r = math.sqrt(dx * dx + dy * dy + dz * dz)
    if r < 1e-9:
        return 0.0, 0.0, 0.0
    cos_g = (ceiling_z - plane_z) / r
    cos_g = max(-1.0, min(1.0, cos_g))
    v_deg = math.degrees(math.acos(cos_g))
    h_deg = math.degrees(math.atan2(dy, dx))
    return r, v_deg, _wrap360(h_deg)


def illuminance_at_point_horizontal(
    ies_data,
    flux_scale: float,
    ies_total_lm: float,
    fx: float,
    fy: float,
    ceiling_z: float,
    px: float,
    py: float,
    plane_z: float,
) -> float:
    r, v_deg, h_deg = angles_fixture_to_point(fx, fy, ceiling_z, px, py, plane_z)
    if r < 1e-6:
        return 0.0
    I = candela_at_angle_type_c(ies_data, h_deg, v_deg)
    if ies_total_lm > 1e-9:
        I *= flux_scale / ies_total_lm
    cos_i = (ceiling_z - plane_z) / r
    cos_i = max(0.0, cos_i)
    return I * cos_i / (r * r)


def fixture_positions_grid(
    length: float, width: float, margin: float, nx: int, ny: int
) -> List[Tuple[float, float]]:
    if nx < 1:
        nx = 1
    if ny < 1:
        ny = 1
    xs = [margin + (i + 0.5) * (length - 2 * margin) / nx for i in range(nx)]
    ys = [margin + (j + 0.5) * (width - 2 * margin) / ny for j in range(ny)]
    out = []
    for x in xs:
        for y in ys:
            out.append((x, y))
    return out


def fixture_positions_symmetric_grid(
    length: float, width: float, nx: int, ny: int
) -> List[Tuple[float, float]]:
    """
    Fixture centres on a uniform grid over the full floor rectangle.
    Spacing centre-to-centre = length/nx and width/ny; wall to nearest row = half that.
    """
    if nx < 1:
        nx = 1
    if ny < 1:
        ny = 1
    L = float(length)
    W = float(width)
    xs = [(i + 0.5) * L / nx for i in range(nx)]
    ys = [(j + 0.5) * W / ny for j in range(ny)]
    out: List[Tuple[float, float]] = []
    for x in xs:
        for y in ys:
            out.append((x, y))
    return out


def _farthest_point_subset(
    candidates: List[Tuple[float, float]], k: int
) -> List[Tuple[float, float]]:
    """
    Pick ``k`` points from ``candidates`` by greedy farthest-point sampling.
    Starts at the candidate closest to the centroid so the first pick is central,
    then repeatedly adds the point maximizing distance to the nearest already-chosen.
    """
    if k <= 0 or not candidates:
        return []
    if k >= len(candidates):
        return list(candidates)
    cx = sum(p[0] for p in candidates) / len(candidates)
    cy = sum(p[1] for p in candidates) / len(candidates)
    # Seed: closest to centroid
    seed_i = min(
        range(len(candidates)),
        key=lambda i: (candidates[i][0] - cx) ** 2 + (candidates[i][1] - cy) ** 2,
    )
    chosen = [candidates[seed_i]]
    remaining = [p for i, p in enumerate(candidates) if i != seed_i]
    # min-dist² from each remaining point to the chosen set
    min_d2 = [
        (p[0] - chosen[0][0]) ** 2 + (p[1] - chosen[0][1]) ** 2 for p in remaining
    ]
    while len(chosen) < k and remaining:
        best_j = max(range(len(remaining)), key=lambda j: min_d2[j])
        pick = remaining.pop(best_j)
        min_d2.pop(best_j)
        chosen.append(pick)
        for j, p in enumerate(remaining):
            d2 = (p[0] - pick[0]) ** 2 + (p[1] - pick[1]) ** 2
            if d2 < min_d2[j]:
                min_d2[j] = d2
    return chosen


def fixture_positions_polygon(
    poly: Any,
    length: float,
    width: float,
    nx: int,
    ny: int,
    orientation_rad: float = 0.0,
    target_count: Optional[int] = None,
    max_density_scale: int = 8,
) -> List[Tuple[float, float]]:
    """
    Polygon-clipped fixture placement (Phase B).

    1. Build the ``nx × ny`` symmetric grid on the equivalent rectangle.
    2. Map ``poly`` into the engine frame and keep centres with
       ``contains(..., on_edge=False)``.
    3. If fewer than ``target_count`` survive, densify the grid
       (``scale × nx``, ``scale × ny``) until enough interior points appear
       or ``max_density_scale`` is hit.
    4. If more than ``target_count`` survive, thin to exactly that many via
       farthest-point sampling so coverage stays even.

    Returns exactly ``target_count`` positions when geometrically possible;
    otherwise as many interior points as densification can produce (never empty
    if the rectangle grid itself is non-empty — falls back to the unfiltered
    base grid as a last resort).
    """
    nx = max(1, int(nx))
    ny = max(1, int(ny))
    target = int(target_count) if target_count is not None else nx * ny
    target = max(1, target)

    try:
        proxy = _polygon_in_engine_frame(poly, length, width, orientation_rad)
    except Exception:
        return fixture_positions_symmetric_grid(length, width, nx, ny)[:target]

    inside: List[Tuple[float, float]] = []
    base = fixture_positions_symmetric_grid(length, width, nx, ny)
    for scale in range(1, max(1, int(max_density_scale)) + 1):
        if scale == 1:
            candidates = base
        else:
            candidates = fixture_positions_symmetric_grid(
                length, width, nx * scale, ny * scale
            )
        inside = [
            (x, y) for x, y in candidates if proxy.contains(x, y, on_edge=False)
        ]
        if len(inside) >= target:
            break

    if not inside:
        # Pathological: no candidate landed inside — keep rectangular layout.
        return base[:target] if len(base) >= target else list(base)

    if len(inside) == target:
        return inside
    if len(inside) < target:
        return inside  # best effort under densification cap
    return _farthest_point_subset(inside, target)


def polygon_layout_interior_count(
    poly: Any,
    length: float,
    width: float,
    nx: int,
    ny: int,
    orientation_rad: float = 0.0,
) -> int:
    """How many of the ``nx × ny`` rectangular centres fall inside ``poly``."""
    try:
        proxy = _polygon_in_engine_frame(poly, length, width, orientation_rad)
    except Exception:
        return max(1, int(nx)) * max(1, int(ny))
    pts = fixture_positions_symmetric_grid(length, width, nx, ny)
    return sum(1 for x, y in pts if proxy.contains(x, y, on_edge=False))


def work_plane_grid(
    length: float, width: float, margin: float, grid_n: int
) -> List[Tuple[float, float]]:
    return fixture_positions_grid(length, width, margin, grid_n, grid_n)


def work_plane_grid_symmetric(length: float, width: float, grid_n: int) -> List[Tuple[float, float]]:
    """N×N sample points with half-spacing inset from each wall (same rule as fixtures)."""
    return fixture_positions_symmetric_grid(length, width, grid_n, grid_n)


def compute_uniformity_metrics(
    ies_path: str,
    length: float,
    width: float,
    ceiling_height_m: float,
    num_fixtures: int,
    lumens_per_fixture: float,
    best_x: int,
    best_y: int,
    grid_n: int = DEFAULT_GRID_N,
    work_plane_height_m: float = DEFAULT_WORK_PLANE_HEIGHT_M,
    calibrate_maintained_avg_lx: Optional[float] = None,
    inter_reflection_fraction: float = 0.0,
    inter_reflection_label: str = "",
    polygon: Any = None,
    polygon_orientation_rad: float = 0.0,
) -> Dict[str, Any]:
    """
    Point-by-point U₀/U₁ on a work-plane grid.

    When ``polygon`` is provided (Phase B ``/cad_calc`` path):
    * work-plane samples are polygon-clipped via :func:`work_plane_grid_polygon`;
    * fixture centres are polygon-clipped via :func:`fixture_positions_polygon`
      (filter the ``nx × ny`` grid, densify if needed, thin to ``num_fixtures``).

    When ``polygon`` is ``None`` (legacy ``/calculate``), behaviour is unchanged.
    """
    ies_data = _load_ies_data_cached(os.path.normpath(ies_path))
    n_lamps = max(1, int(ies_data.num_lamps))
    phi_ies_file = float(ies_data.lumens_per_lamp) * float(ies_data.multiplier) * n_lamps
    # U0/U1 depend only on relative distribution (ratios), not absolute scale. When the IES
    # header lumens are missing or invalid (common in some files), use design lumens per
    # fixture so candela normalization still runs; absolute lx values follow design intent.
    lumens_pf = max(float(lumens_per_fixture), 1e-9)
    if phi_ies_file > 1e-9:
        ratio_raw = lumens_pf / phi_ies_file
        ratio_eff = min(
            max(ratio_raw, ies_lumen_to_design_ratio_min),
            ies_lumen_to_design_ratio_max,
        )
        # I *= flux_scale / phi_ies; using phi_ies = lumens_pf / ratio_eff preserves behaviour
        # when ratio_raw is in-band; otherwise caps absolute lx blow-ups from bad IES lumens.
        phi_ies = lumens_pf / ratio_eff
        if abs(ratio_raw - ratio_eff) > 1e-6:
            ies_scale_note = (
                f"IES header lumens (design/file ratio {ratio_raw:.3f} → clamped {ratio_eff:.3f})"
            )
        else:
            ies_scale_note = "IES header lumens"
    else:
        phi_ies = lumens_pf
        ies_scale_note = "design lumens (IES header missing or ≤0)"

    nx = max(1, int(best_x))
    ny = max(1, int(best_y))
    n_layout = nx * ny
    target_fixtures = max(1, int(num_fixtures))

    ceiling_z = float(ceiling_height_m)
    plane_z = float(work_plane_height_m)
    L = float(length)
    W = float(width)
    gn = max(1, int(grid_n))

    spacing_cc_x = L / nx
    spacing_cc_y = W / ny
    edge_half_x = spacing_cc_x * 0.5
    edge_half_y = spacing_cc_y * 0.5
    wp_step_x = L / gn
    wp_step_y = W / gn
    wm_report = min(L, W) / (2.0 * gn)

    n_rect_interior = n_layout
    if polygon is not None:
        fxs = fixture_positions_polygon(
            polygon,
            length,
            width,
            nx,
            ny,
            float(polygon_orientation_rad),
            target_count=target_fixtures,
        )
        n_rect_interior = polygon_layout_interior_count(
            polygon, length, width, nx, ny, float(polygon_orientation_rad)
        )
        grid_pts = work_plane_grid_polygon(
            polygon, length, width, gn, float(polygon_orientation_rad)
        )
        layout_symmetric = False
    else:
        fxs = fixture_positions_symmetric_grid(length, width, nx, ny)
        if len(fxs) != n_layout:
            raise ValueError("fixture grid mismatch")
        grid_pts = work_plane_grid_symmetric(length, width, gn)
        layout_symmetric = True

    n_placed = len(fxs)
    if n_placed < 1:
        raise ValueError("no fixture positions available for uniformity grid")
    # Spread total design flux across the positions actually used (equals
    # lumens_per_fixture when n_placed == num_fixtures, the normal case).
    phi_total = float(target_fixtures) * float(lumens_per_fixture)
    phi_each = phi_total / float(n_placed)
    flux_scale = phi_each

    n_effective_samples = len(grid_pts)
    Es: List[float] = []
    for px, py in grid_pts:
        e_sum = 0.0
        for fx, fy in fxs:
            e_sum += illuminance_at_point_horizontal(
                ies_data, flux_scale, phi_ies, fx, fy, ceiling_z, px, py, plane_z
            )
        Es.append(e_sum)

    arr = np.asarray(Es, dtype=float)
    e_avg_raw = float(np.mean(arr))
    cal_suffix = ""
    e_avg_direct_calibrated_lx: Optional[float] = None
    if (
        calibrate_maintained_avg_lx is not None
        and float(calibrate_maintained_avg_lx) > 0
        and e_avg_raw > 1e-15
    ):
        sc = float(calibrate_maintained_avg_lx) / e_avg_raw
        arr = arr * sc
        Es = arr.tolist()
        e_avg_direct_calibrated_lx = float(calibrate_maintained_avg_lx)
        cal_suffix = (
            f"; work-plane grid lx scaled to maintained E_m={float(calibrate_maintained_avg_lx):.2f} lx "
            f"(×{sc:.4f})"
        )
    ies_scale_note = (ies_scale_note or "") + cal_suffix
    e_avg_direct_pre_ir_lx = float(np.mean(arr))

    try:
        f_ir = float(inter_reflection_fraction)
    except (TypeError, ValueError):
        f_ir = 0.0
    f_ir = max(0.0, min(0.5, f_ir))
    ir_note = ""
    if f_ir > 1e-12:
        arr = arr * (1.0 + f_ir)
        Es = arr.tolist()
        ir_note = (
            f"; inter-reflection estimate ×(1+{f_ir:.3f})"
            + (f" ({inter_reflection_label})" if inter_reflection_label else "")
        )
        ies_scale_note = (ies_scale_note or "") + ir_note

    e_min = float(np.min(arr))
    e_max = float(np.max(arr))
    e_avg = float(np.mean(arr))
    u0 = (e_min / e_avg) if e_avg > 1e-12 else 0.0
    u1 = (e_min / e_max) if e_max > 1e-12 else 0.0

    return {
        "E_min": e_min,
        "E_max": e_max,
        "E_avg": e_avg,
        "U0": u0,
        "U1": u1,
        "grid_n": gn,
        "wall_margin_m": wm_report,
        "work_plane_z_m": plane_z,
        "ceiling_z_m": ceiling_z,
        "room_length_m": L,
        "room_width_m": W,
        "layout_symmetric": layout_symmetric,
        "n_effective_samples": n_effective_samples,
        "spacing_cc_x_m": spacing_cc_x,
        "spacing_cc_y_m": spacing_cc_y,
        "edge_half_spacing_x_m": edge_half_x,
        "edge_half_spacing_y_m": edge_half_y,
        "work_plane_sample_spacing_m": (wp_step_x + wp_step_y) * 0.5,
        "spacing_margin_m": edge_half_x,
        "n_fixtures_layout": n_placed,
        "n_fixtures_requested": target_fixtures,
        "n_fixtures_rect_grid": n_layout,
        "n_fixtures_rect_interior": n_rect_interior,
        "phi_each_lm": phi_each,
        "phi_total_lm": phi_total,
        "ies_rated_lm": phi_ies,
        "ies_rated_lm_file": phi_ies_file,
        "ies_scale_note": ies_scale_note,
        "e_avg_includes_ir_boost": bool(f_ir > 1e-12),
        "e_avg_direct_calibrated_lx": e_avg_direct_calibrated_lx,
        "e_avg_direct_pre_ir_lx": e_avg_direct_pre_ir_lx,
        "inter_reflection_fraction": f_ir,
        "inter_reflection_label": inter_reflection_label or "",
        "grid_E": Es,
        "grid_points": grid_pts,
        "fixture_positions": fxs,
    }


def _ascii_fixture_plan(
    length: float,
    width: float,
    margin: float,
    fixture_positions: List[Tuple[float, float]],
    cols: int = 52,
    rows: int = 14,
    *,
    full_room: bool = False,
) -> str:
    """
    Rough plan-view map: *=fixture centre.
    If ``full_room``, map over [0,length]×[0,width] (symmetric grid layout).
    Otherwise map over the inset rectangle (legacy fixed wall margin).
    """
    if not fixture_positions:
        return ""
    if full_room:
        iw = float(length)
        ih = float(width)
        ox = oy = 0.0
    else:
        if length <= 2 * margin or width <= 2 * margin:
            return ""
        iw = length - 2 * margin
        ih = width - 2 * margin
        ox = oy = float(margin)
    lines = [
        f"Fixture layout (plan view, {cols}×{rows} character grid; *=luminaire centre, . = empty):",
        "  (x → length, y ↑ width; origin bottom-left of room)",
    ]
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for fx, fy in fixture_positions:
        cx = int((fx - ox) / iw * (cols - 1)) if iw > 1e-9 else 0
        cy = int((fy - oy) / ih * (rows - 1)) if ih > 1e-9 else 0
        cx = max(0, min(cols - 1, cx))
        cy = max(0, min(rows - 1, rows - 1 - cy))
        grid[cy][cx] = "*"
    lines.append("  +" + "-" * cols + "+")
    for r in range(rows):
        lines.append("  |" + "".join(grid[r]) + "|")
    lines.append("  +" + "-" * cols + "+")
    return "\n".join(lines)


def format_uniformity_report_txt(
    option_index: int,
    luminaire: str,
    power_w: float,
    standard_u0: float,
    ies_path: str,
    metrics: Dict[str, Any],
) -> str:
    e_avg_final = float(metrics["E_avg"])
    e_avg_direct_cal = metrics.get("e_avg_direct_calibrated_lx")
    e_avg_direct_pre_ir = metrics.get("e_avg_direct_pre_ir_lx")
    ir_boosted = bool(metrics.get("e_avg_includes_ir_boost"))
    f_ir = float(metrics.get("inter_reflection_fraction") or 0.0)
    ir_lbl = str(metrics.get("inter_reflection_label") or "").strip()

    scaling_lines: List[str] = []
    if e_avg_direct_cal is not None:
        if ir_boosted:
            scaling_lines.extend(
                [
                    (
                        "Candela scaling: work-plane grid calibrated to lumen-method "
                        f"E_m = {float(e_avg_direct_cal):.2f} lx (direct only),"
                    ),
                    (
                        f"then reflection boost ×(1+{f_ir:.3f}) applied"
                        + (f" ({ir_lbl})" if ir_lbl else "")
                        + f" → final E_avg = {e_avg_final:.2f} lx."
                    ),
                    "U0 and U1 are reflection-blind in this model (uniform boost cancels in the ratio).",
                ]
            )
        else:
            scaling_lines.append(
                "Candela scaling: work-plane grid calibrated to lumen-method "
                f"E_m = {float(e_avg_direct_cal):.2f} lx (direct only); no reflection boost applied."
            )
    else:
        if ir_boosted:
            base_txt = (
                f"{float(e_avg_direct_pre_ir):.2f} lx"
                if e_avg_direct_pre_ir is not None
                else "direct grid E_avg"
            )
            scaling_lines.extend(
                [
                    (
                        "Candela scaling: direct grid computed from IES photometry"
                        f" (pre-IR E_avg = {base_txt}),"
                    ),
                    (
                        f"then reflection boost ×(1+{f_ir:.3f}) applied"
                        + (f" ({ir_lbl})" if ir_lbl else "")
                        + f" → final E_avg = {e_avg_final:.2f} lx."
                    ),
                    "U0 and U1 are reflection-blind in this model (uniform boost cancels in the ratio).",
                ]
            )
        else:
            scaling_lines.append(
                "Candela scaling: direct grid computed from IES photometry; no reflection boost applied."
            )

    lines = [
        "=" * 72,
        f"Option {option_index + 1} — Uniformity (point-by-point, IES candela)",
        "=" * 72,
        f"Luminaire: {luminaire}",
        f"Power (W): {power_w}",
        f"Standard Uo (required): {standard_u0}",
        f"IES file: {ies_path}",
        "",
        "Method:",
        "  - Horizontal work plane at z = work_plane_height (m).",
        "  - Ceiling / luminaire height = room height (m).",
        "  - Grid: N x N points, symmetric on full floor (edge = half sample spacing).",
        "  - For each grid point: E = sum( I(theta,phi) * cos(i) / R^2 ),",
        "    I scaled by per-fixture lumens vs IES-rated lumens.",
        "  - U0 = E_min / E_avg,  U1 = E_min / E_max.",
        "  - Optional: total E ≈ direct E × (1 + f); f is a preset indirect fraction (not full radiosity).",
        "",
        f"Candela scaling / scaling notes: {metrics.get('ies_scale_note', 'IES header lumens')}",
        f"  (φ for I/I_rated: {metrics['ies_rated_lm']:.2f} lm; IES file header: {metrics.get('ies_rated_lm_file', metrics['ies_rated_lm']):.2f} lm)",
        *[f"  {ln}" for ln in scaling_lines],
        "",
        f"Parameters: grid_n={metrics['grid_n']}, "
        f"fixture spacing cc (m) x={metrics.get('spacing_cc_x_m', '?')}, "
        f"y={metrics.get('spacing_cc_y_m', '?')}, "
        f"edge half-spacing (m) x={metrics.get('edge_half_spacing_x_m', '?')}, "
        f"y={metrics.get('edge_half_spacing_y_m', '?')}, "
        f"work_plane_z_m={metrics['work_plane_z_m']}, ceiling_z_m={metrics['ceiling_z_m']}",
        f"Layout fixtures (grid): {metrics['n_fixtures_layout']}, phi_each_lm={metrics['phi_each_lm']:.2f}, "
        f"phi_total_lm={metrics['phi_total_lm']:.2f}",
        "",
        "Results:",
        f"  E_min (lx): {metrics['E_min']:.6f}",
        f"  E_avg (lx): {metrics['E_avg']:.6f}",
        f"  E_max (lx): {metrics['E_max']:.6f}",
        f"  U0 calculated (E_min/E_avg): {metrics['U0']:.6f}",
        f"  U1 (E_min/E_max): {metrics['U1']:.6f}",
        "",
        "Fixture positions (x, y) m:",
    ]
    for i, (fx, fy) in enumerate(metrics["fixture_positions"]):
        lines.append(f"  {i + 1}: ({fx:.4f}, {fy:.4f})")
    lines.append("")
    rl = metrics.get("room_length_m")
    rw = metrics.get("room_width_m")
    if rl is not None and rw is not None:
        sym = bool(metrics.get("layout_symmetric"))
        plan = _ascii_fixture_plan(
            float(rl),
            float(rw),
            0.0,
            metrics["fixture_positions"],
            full_room=sym,
        )
        if plan:
            lines.append(plan)
            lines.append("")
    lines.append("Sample grid illuminance E (lx), row-major (first row = y min):")
    gn = metrics["grid_n"]
    gE = metrics["grid_E"]
    for r in range(gn):
        row = gE[r * gn : (r + 1) * gn]
        lines.append("  " + "  ".join(f"{v:10.4f}" for v in row))
    lines.append("")
    lines.append("=" * 72)
    lines.append("")
    return "\n".join(lines)


def write_uniformity_session_txt(header: str, body_chunks: List[str]) -> str:
    import datetime

    out_dir = os.path.join(project_root(), "uniformity_reports")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"uniformity_calc_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header.rstrip() + "\n\n")
        f.write("\n".join(body_chunks))
    return path
