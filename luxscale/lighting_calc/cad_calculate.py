"""
Polygon-based lighting calculation entry point (plan 06 phase A).

This module wraps the existing rectangular :func:`calculate_lighting` engine
so a polygon-shaped room can drive it **without any change** to
``calculate.py`` / ``geometry.py``.

Strategy
--------
1. Build a :class:`Polygon` from the caller's vertices.
2. Compute the **equivalent-area rectangle** whose ``W_eq × L_eq`` equals
   the polygon's true (shoelace) area and whose aspect ratio matches the
   polygon's bounding box.
3. Call the legacy :func:`calculate_lighting` with
   ``sides = [W_eq, L_eq, W_eq, L_eq]``. The engine's cyclic-quadrilateral
   area function for a rectangle collapses to ``W * L`` = polygon area, so
   the lumen-method illuminance ``E_avg = Φ_total / area`` uses the
   polygon's real area — even for L-shapes and other non-convex forms.
4. Attach polygon geometry metadata to ``calc_meta`` and return the
   original results untouched.

Trade-off, documented for the caller
------------------------------------
U₀ work-plane sampling **and** fixture centres are polygon-clipped (Phase B):
points / centres outside the true outline are excluded (fixtures densify +
refill to keep the requested count). The lumen-method average still uses the
equivalent-area rectangle so total installed flux stays polygon-correct.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from luxscale.app_logging import log_step
from luxscale.calculation_trace import CalculationTrace

from .calculate import calculate_lighting
from .polygon import Polygon, PolygonError


def _dominant_edge_orientation(poly: Polygon, sigma_deg: float = 2.0) -> float:
    """
    Return the polygon's dominant wall-direction angle, in radians, in
    ``[0, pi/2)``.

    Method: length-weighted Gaussian KDE on edge angles taken mod 90°. Each
    edge (from vertex i to i+1) contributes weight ``length_i * exp(-Δ²/2σ²)``
    to every 1° bin, where ``Δ`` is the *circular* distance between the edge
    angle and the bin centre (so 89° and 1° are treated as neighbours). The
    dominant orientation is the bin with the largest total weight.

    Why mod 90° and not mod 180°: parallel walls at 0° and 90° should both
    pull the equivalent rectangle to the same orientation — a room is a
    "rectangle" whether its long axis is horizontal or vertical.

    Complexity: O(N) edges × O(90) bins = O(N). Trivial vs the O(N²)
    self-intersection check that already ran during ingest.
    """
    verts = poly.vertices
    n = len(verts)
    if n < 2:
        return 0.0

    n_bins = 90
    two_sigma_sq = 2.0 * sigma_deg * sigma_deg
    bin_sums = [0.0] * n_bins

    for i in range(n):
        x0, y0 = verts[i]
        x1, y1 = verts[(i + 1) % n]
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            continue
        theta_deg = math.degrees(math.atan2(dy, dx)) % 90.0
        for b in range(n_bins):
            delta = abs(theta_deg - b)
            if delta > 45.0:
                delta = 90.0 - delta
            bin_sums[b] += length * math.exp(-(delta * delta) / two_sigma_sq)

    best_bin = max(range(n_bins), key=lambda b: bin_sums[b])
    return math.radians(float(best_bin))


def _rotated_bbox(poly: Polygon, theta: float) -> tuple[float, float]:
    """
    Axis-aligned bounding box (width, length) of the polygon *after* rotating
    its vertices by ``-theta`` radians. When ``theta == 0`` this reduces to
    ``(poly.bbox_width, poly.bbox_length)``.

    "Width" corresponds to the rotated-frame x-axis extent; "length" to the
    rotated-frame y-axis extent — matching the L=x, W=y axis convention
    documented in ``documentation/math/01-units-and-symbols.md``.
    """
    if abs(theta) < 1e-15:
        return (poly.bbox_width, poly.bbox_length)
    c = math.cos(-theta)
    s = math.sin(-theta)
    xs = [c * x - s * y for x, y in poly.vertices]
    ys = [s * x + c * y for x, y in poly.vertices]
    return (max(xs) - min(xs), max(ys) - min(ys))


def build_equivalent_rectangle(poly: Polygon) -> tuple[float, float, float]:
    """
    Return ``(width_eq, length_eq, orientation_rad)`` s.t.

    * ``width_eq * length_eq == poly.area`` (true shoelace area)
    * ``width_eq / length_eq`` equals the aspect ratio of the polygon's
      **oriented** bounding box — the bbox after rotating vertices into
      the frame aligned with the polygon's dominant wall direction. For
      axis-aligned rooms this collapses to the raw ``bbox_width / bbox_length``
      ratio used previously; for rooms rotated by ``θ`` this recovers the
      real aspect ratio rather than the inflated axis-aligned one.
    * ``orientation_rad`` is the angle (radians, in ``[0, pi/2)``) by which
      the equivalent rectangle is rotated relative to the world x-axis.
      Zero means the equivalent rectangle is axis-aligned. Downstream
      drawers can rotate their fixture layout by ``+orientation_rad`` to
      put fixtures back in the CAD frame.

    Degenerate bboxes (zero-width or zero-length polygons are already rejected
    by :meth:`Polygon.from_vertices`) fall back to a square of the same area
    with orientation 0.

    History: prior to Sep-2026 this returned only ``(width_eq, length_eq)``
    and used the raw axis-aligned bbox for the aspect ratio, which distorted
    fixture spacing for polygons rotated relative to the CAD axes. See
    ``documentation/math/06a-non-4-side-rooms-review-addendum.md §3``.
    """
    theta = _dominant_edge_orientation(poly)
    bw, bl = _rotated_bbox(poly, theta)
    if bw <= 0 or bl <= 0:
        side = poly.area ** 0.5
        return side, side, 0.0
    ratio = bw / bl  # width / length in the rotated frame
    length_eq = (poly.area / ratio) ** 0.5
    width_eq = ratio * length_eq
    return width_eq, length_eq, theta


def cad_calculate_lighting(
    polygon: Polygon,
    height: float,
    place: Optional[str] = None,
    *,
    standard_row: Optional[dict] = None,
    trace: Optional[CalculationTrace] = None,
    fast: bool = False,
):
    """
    Polygon-aware wrapper around :func:`calculate_lighting`.

    Parameters
    ----------
    polygon
        A validated :class:`Polygon`.
    height
        Ceiling height (m).
    place
        Optional legacy place-key (e.g. ``"office"``) — mutually exclusive
        with ``standard_row`` (both may be ``None``; the engine defaults).
    standard_row
        Optional row from ``standards_cleaned.json``. Same semantics as
        :func:`calculate_lighting`.
    trace, fast
        Passed straight through.

    Returns
    -------
    tuple
        ``(results, length_eq, width_eq, calc_meta)`` where ``calc_meta``
        is the engine's dict augmented with a ``polygon`` key describing
        the input geometry.
    """
    width_eq, length_eq, orientation_rad = build_equivalent_rectangle(polygon)
    sides = [width_eq, length_eq, width_eq, length_eq]
    orientation_deg = math.degrees(orientation_rad)

    # Fill ratio uses the *oriented* bbox — for a rotated rectangle this is
    # 1.0 (no fill loss), for an axis-aligned L-shape it collapses to the
    # familiar A/(bbox_w*bbox_l) form. See addendum §5 for the derivation.
    _bw_rot, _bl_rot = _rotated_bbox(polygon, orientation_rad)
    oriented_bbox_area = _bw_rot * _bl_rot
    fill_ratio = (
        polygon.area / oriented_bbox_area if oriented_bbox_area > 1e-12 else 1.0
    )

    log_step(
        "cad_calculate_lighting: enter",
        None,
        polygon_area_m2=polygon.area,
        polygon_bbox_wl=(polygon.bbox_width, polygon.bbox_length),
        equivalent_rectangle_wl=(width_eq, length_eq),
        orientation_deg=orientation_deg,
        polygon_fill_ratio=fill_ratio,
        vertex_count=len(polygon.vertices),
        height=height,
    )
    if trace is not None:
        trace.step(
            "cad_00_enter",
            polygon_area_m2=polygon.area,
            equivalent_rectangle=(width_eq, length_eq),
            orientation_deg=orientation_deg,
            polygon_fill_ratio=fill_ratio,
            bbox=list(polygon.bbox),
            vertex_count=len(polygon.vertices),
        )

    results, length_out, width_out, calc_meta = calculate_lighting(
        place,
        sides,
        height,
        standard_row=standard_row,
        trace=trace,
        fast=fast,
        polygon=polygon,
        polygon_orientation_rad=orientation_rad,
        polygon_fill_ratio=fill_ratio,
    )

    if not isinstance(calc_meta, dict):
        calc_meta = {}
    calc_meta = dict(calc_meta)  # avoid mutating engine-owned dict
    calc_meta["geometry_version"] = 2
    polygon_meta = polygon.to_dict()
    polygon_meta["fill_ratio"] = fill_ratio
    polygon_meta["orientation_deg"] = orientation_deg
    polygon_meta["oriented_bbox_width_m"] = _bw_rot
    polygon_meta["oriented_bbox_length_m"] = _bl_rot
    if "effective_sample_count" in calc_meta:
        polygon_meta["effective_sample_count"] = calc_meta["effective_sample_count"]
    if "sample_density_per_m2" in calc_meta:
        polygon_meta["sample_density_per_m2"] = calc_meta["sample_density_per_m2"]
    calc_meta["polygon"] = polygon_meta
    calc_meta["equivalent_rectangle"] = {
        "width_m": width_eq,
        "length_m": length_eq,
        "orientation_deg": orientation_deg,
        "sides_used": sides,
    }
    engine_notes = calc_meta.setdefault("engine_notes", [])
    engine_notes.append(
        "phase B: U0 samples and fixture centres are polygon-clipped "
        "(filter + densify/refill to requested count); lumen method still uses "
        "the equivalent-area rectangle for total flux"
    )

    if trace is not None:
        trace.step(
            "cad_99_return",
            result_rows=len(results),
            engine_length_returned=length_out,
            engine_width_returned=width_out,
            polygon_fill_ratio=fill_ratio,
            effective_sample_count=calc_meta.get("effective_sample_count"),
        )
    return results, length_eq, width_eq, calc_meta


def polygon_from_payload(payload: dict) -> Polygon:
    """
    Build a Polygon from a ``/cad_calc`` request body.

    Accepts three shapes so callers can be flexible:

    1. ``{"polygon": {"vertices": [[x, y], ...]}}``  ← preferred
    2. ``{"polygon": [[x, y], ...]}``
    3. ``{"vertices": [[x, y], ...]}`` (top-level)

    Raises
    ------
    PolygonError
        If the payload does not carry a recognizable vertex list.
    """
    if not isinstance(payload, dict):
        raise PolygonError("payload must be a JSON object")

    poly_field = payload.get("polygon")
    verts: Optional[Sequence] = None
    if isinstance(poly_field, dict):
        v = poly_field.get("vertices")
        if isinstance(v, list):
            verts = v
    elif isinstance(poly_field, list):
        verts = poly_field

    if verts is None:
        v = payload.get("vertices")
        if isinstance(v, list):
            verts = v

    if verts is None:
        raise PolygonError(
            "no polygon vertices found. expected keys: polygon.vertices, polygon (list), or vertices"
        )
    return Polygon.from_vertices(verts)
