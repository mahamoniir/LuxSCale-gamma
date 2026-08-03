# Non-Symmetric Rooms — Migration Plan

**Goal:** Support rooms of arbitrary polygon shape (N ≥ 3 sides, possibly non-convex, possibly not closable from edge lengths alone) as a first-class input to LuxScale, driven by an external CAD-analysis tool that produces polygon vertices for real building layouts.

**Non-goals (for now):**
- 3D non-planar floors (stairs, split levels).
- Rooms with holes (interior obstructions).
- Real-time collaborative editing of polygons in the UI.

These can layer on later once the polygon model is in place.

---

## 1. Executive summary

Today `sides` is a **4-element list of edge lengths** — not vertices. Everything downstream of it collapses to an **axis-aligned bounding rectangle** `L = max(sides[0], sides[2])`, `W = max(sides[1], sides[3])` for the entire fixture-grid + IES uniformity + PDF drawing pipeline. Only the *lumen-method area* uses `cyclic_quadrilateral_area` (Brahmagupta) — every other stage of the pipeline treats the room as `L × W`.

Consequences for N-sided rooms:

- **Area** must switch from Brahmagupta to the **shoelace formula** on vertices.
- **Fixture placement**, currently `nx × ny` on a rectangle, needs a polygon-aware strategy (see §3.2).
- **Uniformity U₀** work-plane sampling must exclude points outside the polygon.
- **PDF drawings, 3D previews, and every `sides[0]/sides[1]` display** must switch to polygon rendering.
- **Storage / API contracts** (Flask, PHP, chat, AI) must accept + persist the new shape without breaking existing `sides[4]` tokens.

The full code-location inventory is in [`61c7e26a-0508-411b-8085-e164b0ca84c9`](61c7e26a-0508-411b-8085-e164b0ca84c9). This plan turns that inventory into an ordered, deliverable-by-deliverable migration.

---

## 2. Design decisions

Three decisions must be locked before writing code. Recommended answers below; call them out for review.

### 2.1 Geometry representation

**Recommended: vertices as `[[x, y], …]` in metres, closed polygon (first ≠ last), CCW-normalized on ingest.**

| Option | Pros | Cons |
|---|---|---|
| **Vertices `[[x,y],…]`** (recommended) | Uniquely defines any N-gon; trivial shoelace area; easy to render, sample, and clip; ready for non-convex; matches CAD output. | Slightly more input data; requires closure/self-intersection checks. |
| Edge lengths + angles | Compact; still bijective with vertices. | Doesn't survive CAD round-tripping cleanly; two extra fields; error-prone. |
| GeoJSON `Polygon` | Standard; supports holes. | Overkill; adds nested-array indirection everywhere. |
| Keep `sides[N]` (lengths only) | Minimal schema change. | **Does not uniquely determine a polygon for N ≥ 4** without angles — non-starter. |

**Canonical shape in storage & API v2:**

```json
{
  "geometry_version": 2,
  "polygon": {
    "vertices": [[0, 0], [6, 0], [6, 4], [3, 4], [3, 8], [0, 8]],
    "units": "m"
  },
  "height": 3.0
}
```

Vertices are ingested, then **normalized** into memory as: closed CCW list, translated so `min(x)=0, min(y)=0`, cached alongside precomputed `area`, `centroid`, `bbox`, `perimeter`.

### 2.2 Fixture placement strategy

**Recommended: axis-aligned regular grid on the polygon's bounding box, then keep only points inside the polygon (`point-in-polygon` test). Iterate `nx × ny` search on the bbox as today; score by count of *interior* fixtures.**

Why: minimal deviation from the current spacing-search algorithm; deterministic; renders cleanly on the polygon; extensible to non-convex without special-casing.

Alternatives noted for later:
- **Inscribed rectangle** grid (simpler visualization; wastes floor area).
- **Poisson-disk** / centroidal Voronoi (great uniformity; expensive; hard to explain in reports).
- **Zone-based** (partition polygon into rectangles, tile each). *We're already doing this implicitly for L-shapes in §5.*

### 2.3 API + storage backward compatibility

**Recommended: additive schema with `geometry_version`. Old tokens (`sides` present, no `polygon`) keep working forever by being auto-lifted into a `polygon` on read.**

Rules:

1. **Write path (new studies)** — always writes `geometry_version: 2` + `polygon`. Also writes a legacy `sides` field derived from the polygon's bounding rectangle, so old readers (frontends we haven't updated yet) still render *something*.
2. **Read path** — if `polygon` is present, use it. Else construct one from `sides[4]` using the current `max(a,c) × max(b,d)` bounding rectangle (a legacy rectangle model that keeps existing tokens loadable).
3. **PHP `submit.php` / `get.php`** — accept both shapes; the lift/derive helpers live in one file each (see §4.4).
4. **No breaking changes to `sides` on the wire.** After Phase 2 lands, `sides` still appears in responses; it just no longer *drives* the calculation.

---

## 3. New geometry model in code

### 3.1 New module `luxscale/lighting_calc/polygon.py`

A single home for polygon math. Everything else imports from here.

```python
# luxscale/lighting_calc/polygon.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

Vertex = tuple[float, float]


@dataclass(frozen=True)
class Polygon:
    vertices: tuple[Vertex, ...]      # closed CCW, first != last
    area: float                        # m²
    perimeter: float                   # m
    centroid: Vertex
    bbox: tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)

    @classmethod
    def from_vertices(cls, verts: Sequence[Vertex]) -> "Polygon": ...

    @classmethod
    def from_legacy_sides(cls, sides: Sequence[float]) -> "Polygon":
        """Build a rectangle from the legacy 4-side model using max(a,c) × max(b,d)."""
        ...

    def contains(self, x: float, y: float) -> bool:            # ray-casting PIP
    def sample_grid(self, nx: int, ny: int,
                    margin: float = 0.0) -> list[Vertex]:      # bbox grid ∩ polygon
    def shrink(self, margin: float) -> "Polygon":              # inward offset (Minkowski)
    def is_simple(self) -> bool:                               # self-intersection check
    def is_convex(self) -> bool:
```

Deliverables:

- `_shoelace_area(vs)` → signed area (`> 0` when CCW). Negative → reverse to CCW.
- `_polygon_centroid(vs)` — classic vertex-averaged centroid formula.
- `_point_in_polygon(x, y, vs)` — ray-casting, robust to edges/vertices with a small epsilon.
- `_polygon_perimeter(vs)` — sum of edge lengths.
- `Polygon.shrink(margin)` — offset each edge inward by `margin`; used to enforce wall clearance for fixtures. For non-convex shapes use a straight-skeleton or Minkowski erosion library (`shapely.buffer(-margin)`).
- `Polygon.sample_grid(nx, ny, margin)` — regular grid on `shrink(margin).bbox`, filtered by `contains`.

Recommend adding **`shapely>=2.0`** to `requirements.txt`; use it as the workhorse for `contains`, `buffer`, and `is_valid`. Keep our own thin dataclass on top so the rest of the code never imports shapely directly.

### 3.2 New spacing search in `geometry.py`

Rename current functions → keep alive under `_legacy_*` for the rectangle fallback path; add new versions:

```python
def polygon_area(poly: Polygon) -> float: ...

def calculate_spacing_polygon(
    poly: Polygon,
    count: int,
    margin: float = 0.3,
) -> list[SpacingOption]:
    """Search integer nx×ny grids on poly.bbox; score by interior_count and uniformity."""
```

Behavior:

- Enumerate `(nx, ny)` where `nx * ny >= count` and `nx, ny <= some_cap`.
- For each candidate, compute `spacing_x = bbox_w / nx`, `spacing_y = bbox_h / ny`.
- Generate the full bbox grid, filter to interior points (`poly.shrink(margin).contains`).
- If interior count ≥ `count`, keep the option. Score by `abs(interior_count - count)` and `1 / max(sx, sy)`.
- Return top-K.

Cyclic-quadrilateral area sticks around **only** as `_legacy_cyclic_quadrilateral_area` for the fallback path in `Polygon.from_legacy_sides`; `__init__.py` re-exports both.

### 3.3 Uniformity engine — polygon-aware

`luxscale/uniformity_calculator.py` needs three surgical changes:

1. `uniformity_grid_n_for_room` → take `Polygon` (or `area, bbox`) instead of `length, width`. Grid density scales with `area`, not `L * W`.
2. `fixture_positions_grid` and `fixture_positions_symmetric_grid` → accept `Polygon`; generate bbox grid, filter by `contains`. Signature evolves to `fixture_positions_grid(poly, nx, ny, margin)`.
3. `work_plane_grid` → same treatment: sample within `poly.shrink(work_plane_margin)`.
4. `compute_uniformity_metrics` → all internal math still operates on point clouds; the only change is *which points* enter the cloud. `E_avg`, `E_min`, `U0` are unchanged.

This is the single most impactful change in the whole plan; it's also self-contained inside one file.

### 3.4 `calculate.py` entry point

`calculate_lighting(...)` currently takes `sides` and returns `(results, length, width, meta)`.

New signature (backward-compatible via kwarg):

```python
def calculate_lighting(
    place,
    sides: Sequence[float] | None = None,
    height: float = 3.0,
    *,
    polygon: Polygon | None = None,       # NEW — takes precedence over `sides`
    standard_row=None,
    trace=None,
    fast=False,
):
    poly = polygon or Polygon.from_legacy_sides(sides)
    ...
    return results, poly, calc_meta       # NEW — returns Polygon, not L/W
```

`(length, width)` are derived properties on `Polygon` for the callers who still want them (`polygon.bbox_width`, `polygon.bbox_length`). This is a deliberate breaking change *inside* Python; all external HTTP responses stay stable via §4.

---

## 4. Migration by phase

Each phase is independently shippable and testable. Ship them in order, keep `main` green throughout.

### Phase 0 — Foundations (no behavioral change)

- Add `luxscale/lighting_calc/polygon.py` with the `Polygon` class + unit tests.
- Add `shapely>=2.0.5` to `requirements.txt`.
- Add `_legacy_cyclic_quadrilateral_area` alias in `geometry.py`; nothing else moves.

**Ship criterion:** `pytest luxscale/tests/test_polygon.py` passes for square, non-square rectangle, general quadrilateral, L-shape, and non-convex hexagon fixtures.

### Phase 1 — Engine polygon-aware, legacy input still works

- Update `calculate.py::calculate_lighting` to build a `Polygon` from `sides` on entry, delegate area to `polygon_area(poly)` (shoelace), keep spacing/uniformity **on the bbox** for one release so behavior is identical to today.
- Update `uniformity_calculator.py` to take `Polygon` but still emit rectangular grids (just remove the interior filter for now).
- Add `calc_meta.geometry = {"version": 2, "vertices": [...], "bbox": [...], "area": ...}` to every result.

**Ship criterion:** Existing regression suite passes; results for a rectangle input match the previous release within a documented ε (≤ 1 % on `E_avg`, `U0`).

### Phase 2 — Storage & API accept `polygon`

- **Flask `POST /calculate`, `POST /pdf`:** accept `polygon: {"vertices": [...]}` **or** legacy `sides: [...]`. Both build the same `Polygon` internally. Return both shapes in the response.
- **Flask `POST /api/submit`:** if `polygon` present, validate it (`len(vertices) >= 3`, `Polygon.is_simple()`); if only `sides`, keep the current `len == 4` rule. Persist `geometry_version` + `polygon` alongside the raw payload.
- **Flask `GET /api/get` and `_study_payload_to_api_response`:** on read, if only `sides` present, synthesize `polygon` via `Polygon.from_legacy_sides`. Always include both in the response.
- **PHP `api/submit.php` / `api/get.php`:** mirror the Flask changes with a tiny helper `_polygon_from_payload($data)`.
- **`_resolve_report_payload` in Flask:** accept a body containing either `sides` or `polygon`.
- **Chat / AI (`luxscale/chat_service.py`, `luxscale/ai_prompt.py`):** Gemini schema gains an optional `polygon` field; validation switches from `len(sides) != 4` to `len(sides) != 4 and not payload.get("polygon")`.

**Ship criterion:** New payload with `polygon` end-to-end round-trips through submit → get → PDF → chat. Legacy `sides` payloads produce identical results to Phase 1.

### Phase 3 — Polygon-aware placement + uniformity

- Turn on the interior-filter in `uniformity_calculator.fixture_positions_grid` and `work_plane_grid`.
- Switch `calculate_spacing` to `calculate_spacing_polygon` (see §3.2). For legacy rectangle inputs, the interior filter is a no-op — results stay identical.
- Add a new metric `interior_coverage = interior_count / bbox_count` to `calc_meta` so we can see what fraction of the bbox was actually the room.

**Ship criterion:** For a synthetic L-shaped room, fixtures placed outside the L are excluded; U₀ is computed only on interior samples; `E_avg` recomputed against `polygon.area`, not `L*W`.

### Phase 4 — PDF report renders general polygons

- In `generate_report.py::make_room_drawing`, replace the `MRect` primitive with a polyline drawn from `polygon.vertices` (already scaled to page units). Draw fixture markers only at points inside the polygon. Add a dashed bbox for reference.
- `sec_project_info`: replace `area = W_m * L_m` with `polygon.area`. Room index becomes `RI = area / (mount_h * perimeter/2)` (equivalent-rectangle projection).
- Duplicate the change in `luxscale_deploy/generate_report.py` (or drop the dupe — see §7).

**Ship criterion:** A study with an L-shaped `polygon` produces a PDF whose plan-view actually shows the L, with fixture dots only inside the L.

### Phase 5 — Front-end polygon input

- **`result.html`:** replace every `sides[0]`/`sides[1]` room display with `polygon.bbox` or `polygon.vertices`; update `buildReportPayload()` to include `polygon` in the POST body to Flask.
- **`draw.html` / `draw_v10.html`:** render polygon via SVG polyline; fixtures scattered inside; support panning/zooming to non-rectangular rooms.
- **`index2.html` (and `index3/4.html`):** add a mode toggle: **"Simple rectangle"** (four inputs, unchanged) vs **"Polygon"** (paste-a-JSON-of-vertices or draw-on-canvas). CAD tool integration just POSTs the vertices JSON directly to `/api/submit` — no UI needed until users want it.
- **`assets/js/core-integration.js`:** update wall-area formula from `2*W*H + 2*L*H` to `polygon.perimeter * H` for IRF estimation.

**Ship criterion:** A CAD-produced JSON hitting `POST /api/submit` yields a working `result.html` view + PDF, no rectangle assumptions bleeding through.

### Phase 6 — Cleanup + docs

- Delete `_legacy_cyclic_quadrilateral_area` if no callers remain (grep in ci).
- Rewrite `documentation/lighting/02-input-parameters-room-and-height.md`, `documentation/math/02-core-equations-lumen-grid-uniformity.md`, `PYTHON_TECHNICAL_DESCRIPTION.md`, `README.md`, `CLAUDE.md`.
- Add `documentation/lighting/12-polygon-rooms.md` with the geometry contract and CAD-integration examples.
- Delete or archive `new_luxscale/`, `luxscale_deploy/`, `maha/lighting_calc.py`, `lighting_calc_old.py`, `app-old.py` (see §7).

---

## 5. Zoned polygons (L-shapes and worse) — an intermediate concept

Some layouts really are **two rectangles joined at an edge**. We can offer a shortcut input:

```json
"zones": [
  { "origin": [0, 0], "size": [6, 4] },
  { "origin": [3, 4], "size": [3, 4] }
]
```

Backend union-of-zones → polygon via `shapely.unary_union` → single `Polygon`. This is worth exposing to CAD tools that already segment floors into rectangular regions — it's cheaper to author and less error-prone than tracing every vertex.

Treat this as a Phase 5.5 nice-to-have, not blocking.

---

## 6. Testing strategy

Add `luxscale/tests/`:

- `test_polygon.py`
  - Shoelace area vs. Brahmagupta for cyclic quadrilaterals (must agree to 1e-9).
  - Centroid of a unit square is `(0.5, 0.5)`; of an L-shape, compute by hand.
  - `contains` on grid of 10 000 points for a known L-shape → matches shapely reference.
  - `is_simple` catches figure-8; `is_convex` correctly labels L-shape as non-convex.
  - `from_legacy_sides([6, 4, 6, 4])` gives a rectangle whose area is 24 and bbox is `(0, 0, 6, 4)` — matches `max(a,c) × max(b,d)` legacy.

- `test_calculate_lighting_polygon.py`
  - Rectangle-input regression: results identical to a locked golden JSON at ε ≤ 1 %.
  - L-shape input: `E_avg` computed on shoelace area, uniformity grid excludes the missing square, fixture count ≤ `nx * ny` of the bbox.
  - Legacy `sides[4]` input matches an equivalent `polygon.vertices` input bit-for-bit.

- `test_uniformity_polygon.py`
  - `work_plane_grid` on a triangle returns exactly the interior points.
  - `fixture_positions_grid(margin=0.3)` never returns a point outside `polygon.shrink(0.3)`.

- `test_api_polygon.py` (Flask test client)
  - `POST /calculate` accepts `polygon`, rejects self-intersecting polygons with a clean 400.
  - `POST /api/submit` round-trips both `sides` and `polygon`; `GET /api/get` returns both in the response for either input.
  - `POST /api/report/full` with polygon-based payload returns a valid PDF (magic-bytes check).

CI must run all four suites on every PR touching `luxscale/lighting_calc/`.

---

## 7. Housekeeping (opportunistic, not blocking)

While we're rewriting geometry, tidy the graveyard the exploration turned up:

- `new_luxscale/lighting_calc/` — appears to duplicate `luxscale/lighting_calc/`. Confirm which is live and delete the other before Phase 3.
- `luxscale_deploy/` — mirror of the deploy tree; if it's still deployed anywhere, that's a fork-drift risk when we ship. Either wire it to the live tree or archive it.
- `maha/lighting_calc.py`, `lighting_calc_old.py`, `app-old.py` — legacy. Move to `archive/` or delete outright.

Skipping this is fine, but every extra copy is one more place a `len(sides) != 4` check hides.

---

## 8. Rollback plan

If a phase ships and breaks something, we roll back cleanly because:

- Phases 0–1 add code but change no HTTP contracts → revert = single commit.
- Phase 2 is additive on both wire schemas; feature-flag it behind `LUXSCALE_POLYGON_API=1` for one release if you want extra caution.
- Phases 3–4 gate the polygon-aware placement on `payload.geometry_version == 2`. Any incoming legacy `sides[4]` payload takes the exact same code path as before → automatically rolled back per-request.

We should never be in a state where legacy `sides[4]` studies can't render their PDFs.

---

## 9. Open questions for you

1. **Angular front-end vs `index2.html`.** The GitHub Pages Angular app (`short-circuit-r-d.github.io/LuxSCale-dev`) — is that becoming the primary UI or staying secondary? If primary, Phase 5's canvas polygon editor should live there, not in `index2.html`.
2. **CAD tool output format.** Does the CAD tool emit metres directly, or DXF/DWG that we're expected to parse? If the latter, add a Phase 2.5 for a `POST /api/import/dxf` endpoint (server-side parse → polygon).
3. **Non-convex support level.** Are simple L/T shapes enough for now, or do you need general non-convex polygons (with concavities that make regular grids look sparse)? The former is basically free once vertices are in; the latter probably needs Poisson-disk placement (Phase 3.5).
4. **Rooms with obstructions.** Columns in the middle of the room? Different lighting zones (task areas vs. corridors)? These are polygons-with-holes, which shapely handles cleanly. Worth calling out as a *v3* target, not v2.
5. **`sides` output for legacy clients** — leave forever? Retire after 6 months once the Angular UI is polygon-only?

---

## 10. Summary checklist

- [ ] Phase 0 — `Polygon` module + `shapely` dep + unit tests.
- [ ] Phase 1 — engine reads polygons internally; rectangle bbox pipeline unchanged; regression tests locked.
- [ ] Phase 2 — Flask + PHP accept `polygon`; storage carries `geometry_version: 2`; chat schema updated.
- [ ] Phase 3 — polygon-aware fixture placement + uniformity grid interior filter.
- [ ] Phase 4 — PDF renders general polygons + fixture-in-polygon markers.
- [ ] Phase 5 — front-end polygon rendering + optional editor; CAD tool integration end-to-end.
- [ ] Phase 6 — docs rewrite + legacy tree cleanup.
