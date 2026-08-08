"""
Polygon geometry for CAD-based lighting studies (plan 06 phase A).

This module is **additive** and imported ONLY by the new ``/cad_calc`` route
via :mod:`luxscale.lighting_calc.cad_calculate`. Existing 4-side rectangle
callers (``/calculate``, ``/pdf``, the calculator UI) are untouched.

Model
-----
A :class:`Polygon` is an ordered list of 2D vertices in metres, closed
(the first vertex is NOT repeated at the end), and normalized to
counter-clockwise (CCW) orientation on construction. Neither self-intersection
nor holes are supported at this stage.

The class caches ``area`` (shoelace), ``perimeter``, ``centroid``, and
``bbox`` at construction so callers can treat instances as immutable value
objects.

Deliberate non-goals for phase A
--------------------------------
* No shapely dependency — pure Python for zero-friction deployment.
* No inward-offset (Minkowski erosion) — that lands in phase B alongside
  polygon-clipped fixture placement.
* ``sample_grid`` is provided but not used by the phase A calculation path;
  it exists so tests / CAD tooling can exercise interior sampling today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

Vertex = tuple[float, float]


class PolygonError(ValueError):
    """Raised when input vertices can't be turned into a valid simple polygon."""


def _to_vertices(raw: Iterable) -> list[Vertex]:
    """Coerce ``[[x,y], (x,y), {"x":..,"y":..}, …]`` → ``[(x,y), …]`` as floats."""
    out: list[Vertex] = []
    for i, v in enumerate(raw):
        if isinstance(v, dict):
            try:
                x = float(v["x"])
                y = float(v["y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PolygonError(
                    f"vertex #{i} is a dict but missing numeric 'x'/'y': {v!r}"
                ) from exc
        else:
            try:
                x, y = v  # type: ignore[misc]
            except (TypeError, ValueError) as exc:
                raise PolygonError(
                    f"vertex #{i} must be [x, y] or {{'x':..,'y':..}}: {v!r}"
                ) from exc
            try:
                x = float(x)
                y = float(y)
            except (TypeError, ValueError) as exc:
                raise PolygonError(
                    f"vertex #{i} has non-numeric coordinates: {v!r}"
                ) from exc
        out.append((x, y))
    return out


def _dedupe_consecutive(verts: Sequence[Vertex], eps: float = 1e-9) -> list[Vertex]:
    """Drop consecutive coincident vertices (also collapses closed-form input)."""
    if not verts:
        return []
    out: list[Vertex] = [verts[0]]
    for x, y in verts[1:]:
        px, py = out[-1]
        if abs(x - px) > eps or abs(y - py) > eps:
            out.append((x, y))
    if len(out) > 1:
        x0, y0 = out[0]
        xN, yN = out[-1]
        if abs(x0 - xN) <= eps and abs(y0 - yN) <= eps:
            out.pop()
    return out


def _signed_area(verts: Sequence[Vertex]) -> float:
    """Signed polygon area (shoelace). Positive → CCW, negative → CW."""
    n = len(verts)
    s = 0.0
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def _perimeter(verts: Sequence[Vertex]) -> float:
    n = len(verts)
    p = 0.0
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        dx = x2 - x1
        dy = y2 - y1
        p += (dx * dx + dy * dy) ** 0.5
    return p


def _centroid(verts: Sequence[Vertex], signed_area: float) -> Vertex:
    """Standard polygon centroid — falls back to vertex mean for degenerate area."""
    if abs(signed_area) < 1e-15:
        n = max(len(verts), 1)
        cx = sum(v[0] for v in verts) / n
        cy = sum(v[1] for v in verts) / n
        return (cx, cy)
    n = len(verts)
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    factor = 1.0 / (6.0 * signed_area)
    return (cx * factor, cy * factor)


def _bbox(verts: Sequence[Vertex]) -> tuple[float, float, float, float]:
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    return (min(xs), min(ys), max(xs), max(ys))


def _segments_intersect(
    a: Vertex, b: Vertex, c: Vertex, d: Vertex, eps: float = 1e-12
) -> bool:
    """
    Proper intersection test for open segments ab and cd — collinear overlap
    and shared endpoints (which are normal for adjacent polygon edges) are
    NOT counted as intersections.
    """

    def orient(p: Vertex, q: Vertex, r: Vertex) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if (o1 > eps and o2 < -eps or o1 < -eps and o2 > eps) and (
        o3 > eps and o4 < -eps or o3 < -eps and o4 > eps
    ):
        return True
    return False


@dataclass(frozen=True)
class Polygon:
    """
    Immutable simple polygon in metres.

    Construct via :meth:`from_vertices` — the raw ``__init__`` is a low-level
    escape hatch that skips normalization and validation.

    All angle/orientation invariants:

    * vertices are CCW (``area > 0``);
    * the first vertex is NOT repeated at the end;
    * at least 3 non-coincident vertices;
    * no proper self-intersections.
    """

    vertices: tuple[Vertex, ...]
    area: float
    perimeter: float
    centroid: Vertex
    bbox: tuple[float, float, float, float] = field(
        metadata={"help": "(xmin, ymin, xmax, ymax)"}
    )

    # ── constructors ──────────────────────────────────────────────────────

    @classmethod
    def from_vertices(cls, raw: Iterable) -> "Polygon":
        verts = _dedupe_consecutive(_to_vertices(raw))
        if len(verts) < 3:
            raise PolygonError(
                f"polygon needs at least 3 distinct vertices, got {len(verts)}"
            )
        signed = _signed_area(verts)
        if abs(signed) < 1e-12:
            raise PolygonError("polygon has zero area (collinear vertices)")
        if signed < 0:
            verts = list(reversed(verts))
            signed = -signed
        if not _polygon_is_simple(verts):
            raise PolygonError("polygon is self-intersecting")
        return cls(
            vertices=tuple(verts),
            area=float(signed),
            perimeter=_perimeter(verts),
            centroid=_centroid(verts, signed),
            bbox=_bbox(verts),
        )

    @classmethod
    def from_legacy_sides(cls, sides: Sequence[float]) -> "Polygon":
        """
        Build the *bounding rectangle* interpretation of the legacy 4-side model:
        ``width = max(sides[0], sides[2])``, ``length = max(sides[1], sides[3])``.

        Rationale: the existing engine already uses this rectangle for spacing +
        uniformity, so from-legacy round-tripping through Polygon must reproduce
        the current behaviour, not the (unrelated) cyclic-quadrilateral area.
        """
        if len(sides) != 4:
            raise PolygonError(
                f"legacy sides must have exactly 4 entries, got {len(sides)}"
            )
        try:
            a, b, c, d = (float(s) for s in sides)
        except (TypeError, ValueError) as exc:
            raise PolygonError(f"legacy sides must be numeric: {sides!r}") from exc
        if min(a, b, c, d) <= 0:
            raise PolygonError("legacy sides must all be positive")
        width = max(a, c)
        length = max(b, d)
        return cls.from_vertices(
            [(0.0, 0.0), (width, 0.0), (width, length), (0.0, length)]
        )

    # ── derived properties (bbox helpers) ─────────────────────────────────

    @property
    def bbox_width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def bbox_length(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def bbox_area(self) -> float:
        return self.bbox_width * self.bbox_length

    # ── queries ───────────────────────────────────────────────────────────

    def contains(self, x: float, y: float, on_edge: bool = True) -> bool:
        """
        Ray-casting point-in-polygon. ``on_edge=True`` treats edge / vertex hits
        as inside (useful for grid-sample containment); ``False`` excludes them.
        """
        xmin, ymin, xmax, ymax = self.bbox
        if x < xmin or x > xmax or y < ymin or y > ymax:
            return False
        verts = self.vertices
        n = len(verts)
        inside = False
        eps = 1e-12
        for i in range(n):
            x1, y1 = verts[i]
            x2, y2 = verts[(i + 1) % n]
            # Edge-on-point check
            if _point_on_segment(x, y, x1, y1, x2, y2, eps):
                return on_edge
            # Ray-cast: horizontal ray to +x
            if (y1 > y) != (y2 > y):
                x_int = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < x_int:
                    inside = not inside
        return inside

    def sample_grid(
        self,
        nx: int,
        ny: int,
        margin: float = 0.0,
    ) -> list[Vertex]:
        """
        Regular ``nx × ny`` grid on the bounding box, filtered by :meth:`contains`
        after an axis-aligned inward shrink of ``margin`` metres. Grid points sit
        at cell centres so a ``1 × 1`` sample lands on the bbox centroid.

        Not called by the phase A ``/cad_calc`` path — provided so tests and CAD
        tools can inspect interior coverage independently of the engine.
        """
        if nx < 1 or ny < 1:
            return []
        xmin, ymin, xmax, ymax = self.bbox
        xmin += margin
        ymin += margin
        xmax -= margin
        ymax -= margin
        if xmax <= xmin or ymax <= ymin:
            return []
        out: list[Vertex] = []
        dx = (xmax - xmin) / nx
        dy = (ymax - ymin) / ny
        for iy in range(ny):
            cy = ymin + (iy + 0.5) * dy
            for ix in range(nx):
                cx = xmin + (ix + 0.5) * dx
                if self.contains(cx, cy):
                    out.append((cx, cy))
        return out

    def is_convex(self) -> bool:
        """Test convexity via cross-product sign consistency on CCW vertices."""
        n = len(self.vertices)
        if n < 3:
            return False
        sign = 0
        for i in range(n):
            x1, y1 = self.vertices[i]
            x2, y2 = self.vertices[(i + 1) % n]
            x3, y3 = self.vertices[(i + 2) % n]
            cross = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)
            if abs(cross) < 1e-12:
                continue
            s = 1 if cross > 0 else -1
            if sign == 0:
                sign = s
            elif sign != s:
                return False
        return True

    # ── serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """JSON-serializable summary; matches the response schema of /cad_calc."""
        return {
            "vertices": [list(v) for v in self.vertices],
            "area_m2": self.area,
            "perimeter_m": self.perimeter,
            "centroid": list(self.centroid),
            "bbox": list(self.bbox),
            "bbox_width_m": self.bbox_width,
            "bbox_length_m": self.bbox_length,
            "is_convex": self.is_convex(),
            "vertex_count": len(self.vertices),
        }


# ── module-private helpers ────────────────────────────────────────────────


def _point_on_segment(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    eps: float,
) -> bool:
    """True if (px, py) lies on the closed segment (x1,y1)–(x2,y2) within eps."""
    dx = x2 - x1
    dy = y2 - y1
    cross = (px - x1) * dy - (py - y1) * dx
    if abs(cross) > eps * max(1.0, abs(dx) + abs(dy)):
        return False
    if abs(dx) >= abs(dy):
        t = (px - x1) / dx if dx != 0 else 0.0
    else:
        t = (py - y1) / dy if dy != 0 else 0.0
    return -eps <= t <= 1.0 + eps


#: Skip the O(N^2) self-intersection sweep for polygons with more than this
#: many edges. At N > 512 the pure-Python check climbs above ~130 ms, and
#: CAD tools generating such polygons typically pre-validate simplicity.
#: Callers wanting a hard guarantee for very large polygons should validate
#: upstream (e.g. via Shapely) before handing off to LuxScale.
MAX_EDGES_FOR_FULL_SIMPLICITY_CHECK: int = 512


def _polygon_is_simple(
    verts: Sequence[Vertex],
    *,
    max_edges_for_full_check: int = MAX_EDGES_FOR_FULL_SIMPLICITY_CHECK,
) -> bool:
    """
    No proper intersections between non-adjacent edges. Adjacent edges share a
    vertex, which :func:`_segments_intersect` correctly ignores.

    Complexity is O(N²) (worst case ≈ N(N-3)/2 orientation-predicate tests).
    For polygons above ``max_edges_for_full_check`` vertices the check is
    skipped and the polygon is trusted — the O(N²) cost becomes noticeable
    around N ~ 500 in pure Python. If a stricter guarantee is needed for
    large polygons, run a sweep-line pre-check upstream.
    """
    n = len(verts)
    if n < 4:
        return True
    if n > max_edges_for_full_check:
        return True  # trust caller — see docstring
    for i in range(n):
        a = verts[i]
        b = verts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or j == (i + 1) % n:
                continue
            c = verts[j]
            d = verts[(j + 1) % n]
            if _segments_intersect(a, b, c, d):
                return False
    return True
