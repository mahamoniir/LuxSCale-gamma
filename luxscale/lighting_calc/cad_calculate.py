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
Fixture placement in phase A is still on a rectangular ``W_eq × L_eq``
grid — not clipped to the true polygon outline. Total lumens & lux are
polygon-correct; per-fixture (x, y) coordinates in the returned rows are
inside the equivalent rectangle, not the original polygon. Phase B swaps
the placement engine for polygon-clipped grid sampling.
"""

from __future__ import annotations

from typing import Optional, Sequence

from luxscale.app_logging import log_step
from luxscale.calculation_trace import CalculationTrace

from .calculate import calculate_lighting
from .polygon import Polygon, PolygonError


def build_equivalent_rectangle(poly: Polygon) -> tuple[float, float]:
    """
    Return ``(width_eq, length_eq)`` s.t.

    * ``width_eq * length_eq == poly.area`` (true shoelace area)
    * ``width_eq / length_eq == poly.bbox_width / poly.bbox_length``
      (aspect ratio preserved from the bounding box)

    Degenerate bboxes (zero-width or zero-length polygons are already rejected
    by :meth:`Polygon.from_vertices`) fall back to a square of the same area.
    """
    bw = poly.bbox_width
    bl = poly.bbox_length
    if bw <= 0 or bl <= 0:
        side = poly.area ** 0.5
        return side, side
    ratio = bw / bl  # width / length
    length_eq = (poly.area / ratio) ** 0.5
    width_eq = ratio * length_eq
    return width_eq, length_eq


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
    width_eq, length_eq = build_equivalent_rectangle(polygon)
    sides = [width_eq, length_eq, width_eq, length_eq]

    log_step(
        "cad_calculate_lighting: enter",
        None,
        polygon_area_m2=polygon.area,
        polygon_bbox_wl=(polygon.bbox_width, polygon.bbox_length),
        equivalent_rectangle_wl=(width_eq, length_eq),
        vertex_count=len(polygon.vertices),
        height=height,
    )
    if trace is not None:
        trace.step(
            "cad_00_enter",
            polygon_area_m2=polygon.area,
            equivalent_rectangle=(width_eq, length_eq),
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
    )

    if not isinstance(calc_meta, dict):
        calc_meta = {}
    calc_meta = dict(calc_meta)  # avoid mutating engine-owned dict
    calc_meta["geometry_version"] = 2
    calc_meta["polygon"] = polygon.to_dict()
    calc_meta["equivalent_rectangle"] = {
        "width_m": width_eq,
        "length_m": length_eq,
        "sides_used": sides,
    }
    calc_meta.setdefault("engine_notes", []).append(
        "phase A: fixtures placed on equivalent-area rectangle; polygon-clipped placement lands in phase B"
    )

    if trace is not None:
        trace.step(
            "cad_99_return",
            result_rows=len(results),
            engine_length_returned=length_out,
            engine_width_returned=width_out,
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
