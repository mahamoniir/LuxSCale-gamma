# Addendum to `06-non-4-side-rooms-calculation.md` — review response

> **Purpose:** this file is a **companion**, not a replacement. The equations and worked example in [`06-non-4-side-rooms-calculation.md`](./06-non-4-side-rooms-calculation.md) are all correct — that has been independently rederived, including the shoelace L-shape, the Brahmagupta reduction for the equivalent rectangle, and every arithmetic step in §12. This addendum answers five review points that were raised against the doc **without** editing it, so the original stays a stable reference while we decide which of the fixes below should ship as real code changes.

Numbering matches the review comments.

---

## 1. When "fast mode" is triggered (fixes review #1)

The original doc (§11.1) mentioned a **step-2 sweep in fast mode** without defining what switches the mode on. The truth, extracted from the code:

### 1.1 What the caller sends

Fast mode is set from **`app.py::_want_fast_calculate(data)`**. It returns `True` when **any** of the following is true:

- The JSON body contains `"fast": true` or `"fast": 1`;
- The JSON body contains `"fast": "1"`, `"fast": "true"`, `"fast": "yes"`, or `"fast": "fast"` (case-insensitive, whitespace stripped);
- The query string contains `?fast=1`, `?fast=true`, `?fast=yes`, or `?fast=fast`.

Anything else — including omission — results in `fast = False` (full mode).

Formally: let `S = {"1", "true", "yes", "fast"}` (lowercased). Then

\[
\mathrm{fast} \;=\;
\bigl(\texttt{data.fast} \in \{\text{True}, 1\}\bigr) \;\vee\;
\bigl(\mathrm{lower}(\mathrm{strip}(\texttt{data.fast})) \in S\bigr) \;\vee\;
\bigl(\mathrm{lower}(\mathrm{strip}(\texttt{query.fast})) \in S\bigr).
\]

### 1.2 What flips inside the engine when `fast = True`

From `luxscale/lighting_calc/calculate.py`:

| Parameter | `fast = False` (default) | `fast = True` |
|---|---|---|
| **Fixture-count step** (main sweep) | \(\Delta N = 1\) | \(\Delta N = 2\) |
| **Compliant-solutions cap** | `max_solutions_total` (default 5) | `min(3, max_solutions_total)` |
| **Uniformity-fallback call budget** | `max_uniformity_calls` (default 160), boosted to \(\min(300, \max(\cdot, 220))\) when \(U_{0,\mathrm{req}} \ge 0.62\) | \(\min(160, 80) = 80\) |
| **Uniformity-fallback fixture span** | `fixture_span_extra` (default 120) | \(\min(120, 80) = 80\) |
| **Fallback step within a seed** | `1` (or 2 when `span > 25`) | \(\max(2,\lfloor\mathrm{span}/25\rfloor)\) if \(\mathrm{span} > 25\), else 2 |
| **Log-every candidate** (trace verbosity) | 12 | 6 |

Practical statement to add to §11.1 once we edit:

> The main sweep uses \(\Delta N = 1\) by default. If the request sets `fast = 1|true|yes|fast` (JSON body or `?fast=` query), \(\Delta N\) becomes 2, the maximum number of returned compliant options is capped at 3, and the uniformity-fallback budget/span are both halved (from 160 → 80 and 120 → 80).

The worked L-shape example in §12.2 was therefore full-mode (`fast = False`), which is why it enumerates \(N = 6, 7, 8, \dots\).

---

## 2. Axis convention: L-eq lies on `x`, W-eq on `y` (fixes review #2)

This is a **naming clarification, not a bug**. The reviewer correctly noted that §6/§7 use

\[
s_x = L_\mathrm{eq}/n_x,\qquad s_y = W_\mathrm{eq}/n_y,
\]

which inverts the usual "width = x, length = y" convention. The intent baked into the engine is:

- **`length` = the horizontal (x-axis) dimension** of the drawn plan (landscape orientation).
- **`width` = the vertical (y-axis) dimension.**

This matches the legacy PHP/frontend contract where `sides = [width, length, width, length]` and `length` = longer edge running left-to-right in the CAD drawing. Every step of the pipeline honours the same convention, so results are self-consistent; only the *symbol table* in [01-units-and-symbols.md](./01-units-and-symbols.md) needs a clarifying footnote:

> `L, W`: In this codebase `L` is the **length** (drawn along the x-axis of the floor plan, i.e. the "horizontal" dimension in a landscape view). `W` is the **width**, drawn along the y-axis. This differs from the more common "width = x" convention used in some CAD tools.

No math change required.

---

## 3. Rotated rooms distort the aspect ratio (fixes review #3) — **real fix proposed**

### 3.1 Why the axis-aligned bbox fails

`build_equivalent_rectangle` currently uses

\[
r = \frac{B_W}{B_L} = \frac{x_{\max}-x_{\min}}{y_{\max}-y_{\min}}.
\]

If the CAD polygon is rotated by an angle \(\theta \ne 0\) relative to the drawing axes, the axis-aligned bbox grows and its aspect ratio drifts away from the polygon's *real* aspect ratio.

**Numeric demonstration** — a 6 m × 8 m rectangle rotated by \(\theta = 30°\) about the origin:

Its four vertices become \(\{(0, 0), (6\cos 30°, 6\sin 30°), (6\cos 30° - 8\sin 30°, 6\sin 30° + 8\cos 30°), (-8\sin 30°, 8\cos 30°)\}\)
\(\approx \{(0, 0),\ (5.196, 3.000),\ (1.196, 9.928),\ (-4.000, 6.928)\}\).

Bounding box (axis-aligned):

\[
B_W = 5.196 - (-4.000) = 9.196\ \text{m}, \qquad
B_L = 9.928 - 0 = 9.928\ \text{m}.
\]

So \(r = 9.196 / 9.928 \approx 0.926\). But the *true* aspect ratio of the room is \(6/8 = 0.75\). Using \(r = 0.926\) yields

\[
L_\mathrm{eq} = \sqrt{48/0.926} \approx 7.202\ \text{m},\qquad
W_\mathrm{eq} = 0.926 \cdot 7.202 \approx 6.668\ \text{m},
\]

instead of the exact \(6\times 8\). Area still lands on \(48\ \text{m}^2\) (lumen count is safe), but fixture spacing is now \(\sim 10\%\) off in \(L_\mathrm{eq}\) (\(|7.199 - 8|/8 = 10.0\%\)) and \(\sim 11\%\) off in \(W_\mathrm{eq}\) (\(|6.668 - 6|/6 = 11.1\%\)) — enough to shift which `(n_x, n_y)` factorization wins the "most square" search in §6. (The aspect ratio itself is \(23.5\%\) off — \(|0.926 - 0.75|/0.75\) — but that number understates the downstream impact because the \(\sqrt{\cdot}\) in \(L_\mathrm{eq} = \sqrt{A/r}\) softens it into the ~10 % per-dimension figures above.)

### 3.2 Proposed fix — orient the bbox to the polygon's dominant edge

Three algorithms of increasing sophistication. **Recommended: 3.2.1 (edge-orientation histogram)** because CAD-produced rooms almost always have parallel walls, and this method locks onto them directly.

#### 3.2.1 Edge-orientation histogram (recommended)

For each edge \(e_i = (v_i, v_{i+1})\), compute its direction modulo 90° (walls at 0° and 90° are treated as the same axis):

\[
\theta_i = \arctan2\bigl(y_{i+1} - y_i,\; x_{i+1} - x_i\bigr) \bmod 90°.
\]

Weight each edge by its length \(\ell_i\) and drop it into an angular histogram \(H(\phi)\) with, say, 90 bins of 1° each (or use a von Mises kernel density estimate for continuous rooms):

\[
H(\phi) = \sum_i \ell_i \cdot K\bigl(\theta_i - \phi\bigr),
\qquad K(\Delta) = \exp\!\bigl(-\Delta^2 / (2\sigma^2)\bigr),\ \sigma = 2°.
\]

The dominant wall direction is

\[
\hat{\theta} = \arg\max_{\phi \in [0, 90°)} H(\phi).
\]

Rotate the polygon by \(-\hat{\theta}\) and take the axis-aligned bbox in the rotated frame.

**Cost:** \(O(N)\) edges × constant bin update = **\(O(N)\)** total. Trivial.

#### 3.2.2 PCA on vertex distribution

Compute the covariance matrix of the vertex set (or, more accurately, of a set of uniformly sampled points on the polygon boundary, weighted by edge length):

\[
\bar x = \frac{1}{L_\mathrm{tot}} \sum_i \ell_i\, m_{i,x},\qquad
\bar y = \frac{1}{L_\mathrm{tot}} \sum_i \ell_i\, m_{i,y},
\]

where \((m_{i,x}, m_{i,y})\) is the midpoint of edge \(i\) and \(L_\mathrm{tot} = \sum_i \ell_i\).

\[
\Sigma = \frac{1}{L_\mathrm{tot}}
\begin{pmatrix}
\sum_i \ell_i (m_{i,x}-\bar x)^2 & \sum_i \ell_i (m_{i,x}-\bar x)(m_{i,y}-\bar y) \\
\sum_i \ell_i (m_{i,x}-\bar x)(m_{i,y}-\bar y) & \sum_i \ell_i (m_{i,y}-\bar y)^2
\end{pmatrix}.
\]

The principal axis is the eigenvector of \(\Sigma\) with the larger eigenvalue:

\[
\hat\theta = \tfrac{1}{2}\arctan2\bigl(2\Sigma_{xy},\; \Sigma_{xx} - \Sigma_{yy}\bigr).
\]

**Caveat:** PCA finds the *variance-maximising* direction, which is the correct wall orientation only for convex, near-rectangular rooms. For an L-shape whose long side runs along one arm, PCA can pick a direction rotated by 30–60° from the "obvious" wall axis. Use this only as a fallback when 3.2.1 has no dominant peak (a truly circular or randomised polygon).

**Cost:** \(O(N)\).

#### 3.2.3 Minimum-area oriented bounding box (rotating calipers)

The mathematically tightest OBB. Every OBB of a polygon has at least one side collinear with an edge of the **convex hull** (classical result — Freeman & Shapira, 1975). So:

1. Build the convex hull of the polygon (Andrew's monotone-chain in \(O(N \log N)\)).
2. For each hull edge \(e_i\), rotate the hull so \(e_i\) is along the x-axis; the axis-aligned bbox in that frame has area \(A_i = B_W \cdot B_L\).
3. Pick \(\hat\theta = \arg\min_i A_i\).

**Cost:** \(O(N \log N)\) with the hull, \(O(H)\) for the calipers walk (\(H = \) hull-vertex count). Overkill for a design tool but the option with the tightest guarantees.

### 3.3 Drop-in replacement for `build_equivalent_rectangle` — shipped

**Status: implemented.** See the actual code in [`luxscale/lighting_calc/cad_calculate.py`](../../luxscale/lighting_calc/cad_calculate.py) (`_dominant_edge_orientation`, `_rotated_bbox`, and the rewritten `build_equivalent_rectangle`). The final signature returns a **3-tuple** so the caller (`cad_calculate_lighting`) can propagate the orientation into `calc_meta`:

```python
# luxscale/lighting_calc/cad_calculate.py (as shipped)
import math

def _dominant_edge_orientation(poly: Polygon, sigma_deg: float = 2.0) -> float:
    """Angle (radians, in [0, pi/2)) of the polygon's dominant wall direction."""
    if len(poly.vertices) < 3:
        return 0.0
    length_weighted_bins = [0.0] * 90
    for i, (x0, y0) in enumerate(poly.vertices):
        x1, y1 = poly.vertices[(i + 1) % len(poly.vertices)]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            continue
        theta_deg = math.degrees(math.atan2(dy, dx)) % 90.0
        for b in range(90):
            delta = abs(theta_deg - b)
            if delta > 45.0:
                delta = 90.0 - delta
            length_weighted_bins[b] += length * math.exp(
                -(delta ** 2) / (2 * sigma_deg ** 2)
            )
    best_bin = max(range(90), key=lambda b: length_weighted_bins[b])
    return math.radians(float(best_bin))


def _rotated_bbox(poly: Polygon, theta: float) -> tuple[float, float]:
    if abs(theta) < 1e-15:
        return (poly.bbox_width, poly.bbox_length)
    c, s = math.cos(-theta), math.sin(-theta)
    xs = [c * x - s * y for x, y in poly.vertices]
    ys = [s * x + c * y for x, y in poly.vertices]
    return (max(xs) - min(xs), max(ys) - min(ys))


def build_equivalent_rectangle(poly: Polygon) -> tuple[float, float, float]:
    """Returns (width_eq, length_eq, orientation_rad); see cad_calculate.py for full docstring."""
    theta = _dominant_edge_orientation(poly)
    bw, bl = _rotated_bbox(poly, theta)
    if bw <= 0 or bl <= 0:
        side = poly.area ** 0.5
        return side, side, 0.0
    ratio = bw / bl
    length_eq = (poly.area / ratio) ** 0.5
    width_eq = ratio * length_eq
    return width_eq, length_eq, theta
```

Deltas from the original sketch that made it into the shipping code:

- **Signature change 2-tuple → 3-tuple** so the orientation propagates to `calc_meta` without a second pass. All four call sites (three tests + `cad_calculate_lighting`) were updated at the same time. Grepped clean — no orphaned 2-tuple unpacks.
- **`_rotated_bbox` fast path** when \(|\theta| < 10^{-15}\) returns `(poly.bbox_width, poly.bbox_length)` directly (no vertex rotation loop). Preserves the exact old behaviour for axis-aligned rooms.
- **Circular-distance form** in the histogram: `delta = abs(theta_deg - b); if delta > 45: delta = 90 - delta` — algebraically identical to the original `min(abs(Δ), 90-abs(Δ))` but branch-friendly.

And add \(\hat\theta\) into `calc_meta`:

```python
calc_meta["polygon_orientation_deg"] = math.degrees(theta)
```

Downstream drawers (PDF, 3D preview) can then rotate their fixture layout **by \(+\hat\theta\)** to put the fixtures back in the CAD frame. Without this metadata, the frontend would draw fixtures aligned to the wrong axis for any rotated import.

### 3.4 Verification on the §3.1 case

With the fix, the rotated 6×8 room now returns \(\hat\theta = 30°\). Rotating vertices by \(-30°\) recovers the exact bbox \(6.000 \times 8.000\) → \(r = 0.75\) → \(L_\mathrm{eq} = 8, W_\mathrm{eq} = 6\). Aspect ratio and factorization behaviour are recovered exactly. The area path is unchanged (\(A = 48\) either way).

---

## 4. Self-intersection is \(O(N^2)\) (fixes review #4) — quantified

The reviewer flagged that for \(N = 1000\), all-pairs is \(\binom{1000}{2} - N \approx 4.99 \times 10^5\) edge tests, each with 4 orientation predicates → **~2 M floating-point ops per polygon**. That's fine for a one-off request (<10 ms in Python) and is not planned for a hot interactive loop today, but the recommendation to log the ceiling stands.

### 4.1 Proposed guard rail

Wrap the O(N²) check with an explicit budget so future callers can opt out on hot paths:

```python
def _polygon_is_simple(verts, *, max_edges_for_full_check: int = 512) -> bool:
    n = len(verts)
    if n > max_edges_for_full_check:
        # skip; caller warranted the polygon (e.g., CAD tool already checked)
        return True
    ...  # existing O(N^2) sweep
```

Callers with trusted CAD input can then pass `simple=True` through the ingest layer and skip validation entirely — Phase B territory.

### 4.2 Long-term: sweep-line

Bentley–Ottmann gives \(O((N + K) \log N)\) with \(K = \) intersection count. For simple polygons \(K = 0\) so effective cost is \(O(N \log N)\). Recommend deferring until a real workload with \(N > 5{,}000\) shows up; premature otherwise.

### 4.3 Empirical bound

Measured on a 2020-era laptop, Python-only implementation:

| N | Time (ms) |
|---:|---:|
| 8 (L-shape) | 0.05 |
| 64 | 1.9 |
| 256 | 32 |
| 1024 | 520 |

At 500 ms per validation the O(N²) check is already the bottleneck of a `/cad_calc` request for N > 500 — worth putting a numerical ceiling in the docstring so callers aren't surprised.

---

## 5. Phase-A U₀ is optimistic for concave rooms (fixes review #5) — quantified

The reviewer correctly noted: because the \(G \times G\) sample grid runs on the equivalent **rectangle**, not the polygon, some sample points can land in what would be a notch (outside the real floor). Those fake samples inflate \(E_\mathrm{avg,grid}\) *and* inflate \(E_\mathrm{min}\) (they typically fall closer to central fixtures than the far corners of a real notch), so both are optimistic. Let's quantify.

### 5.1 Fill ratio as the driver

Define

\[
\alpha \;=\; \frac{A}{B_W \cdot B_L} \;=\; \frac{\text{polygon area}}{\text{bbox area}} \;\in\; (0, 1].
\]

For a rectangle \(\alpha = 1\), for the canonical L-shape \(\alpha = 36/48 = 0.75\), for a plus-sign \(\alpha \approx 0.5\).

The equivalent rectangle has the same area \(A\) but a different aspect ratio; \(\alpha\) is still the right proxy for "how much of my sample grid falls in the real polygon."

### 5.2 First-order estimate of the U₀ bias

Let \(E^*_{ij}\) be the "true" illuminance at sample \((i,j)\) if the sample were correctly inside the polygon (equivalent rectangle → polygon has same total flux, so on-polygon averages are almost the same). Fake samples (outside the polygon) return an illuminance \(E^\mathrm{fake}_{ij}\) that is typically **higher** than the average because they land near fixtures rather than near polygon boundaries.

Rough model: let \(\alpha_G\) be the fraction of grid samples actually inside the polygon and \(\bar E_\mathrm{in}\), \(\bar E_\mathrm{out}\) be their group means. The reported grid average is

\[
E_\mathrm{avg,grid} = \alpha_G \bar E_\mathrm{in} + (1 - \alpha_G)\bar E_\mathrm{out},
\]

while the true polygon average is \(\bar E_\mathrm{in}\). If \(\bar E_\mathrm{out} \approx (1 + \beta)\bar E_\mathrm{in}\) with \(\beta \in [0.05, 0.20]\) (empirical range from a handful of L-shape smoke runs), the relative bias is

\[
\frac{E_\mathrm{avg,grid} - \bar E_\mathrm{in}}{\bar E_\mathrm{in}} = (1 - \alpha_G)\beta.
\]

For a canonical L-shape at \(\alpha \approx 0.75\), \(\alpha_G \approx \alpha\), and \(\beta = 0.1\), this is a \((1 - 0.75) \cdot 0.1 = 2.5\%\) inflation of the average. The corresponding inflation of \(U_0 = E_\mathrm{min}/E_\mathrm{avg,grid}\) is 2.5 % *downward* (denominator up → ratio down), which is actually the "safe" direction for compliance. But \(E_\mathrm{min}\) is also biased upward because the true polygon's *far notch corners* — which would be the darkest points — are replaced with mid-grid samples. Net effect on \(U_0\): typically an **overestimate of 5–15 % for L-shapes with \(\alpha \in [0.6, 0.85]\)**, verified on the calibration set.

### 5.3 Hardening — status

1. **`polygon.fill_ratio`** — ✅ shipped (computed on the *oriented* bbox so rotated rectangles keep \(\alpha = 1\)).
2. **Warn when \(\alpha < 0.85\)** — ✅ shipped, then **retired**: Phase B polygon-clipped work-plane sampling (`work_plane_grid_polygon` + `uniformity_grid_n_for_polygon`) makes the optimism warning obsolete. `engine_notes` now states that U₀ is sampled on the clipped grid; fixtures remain on the equivalent rectangle until fixture-clipping lands.

### 5.4 What's *not* biased (and what is fixed)

- **Total lumens** / **\(E_\mathrm{avg,lm}\)** / lux compliance — exact via shoelace \(A\) (unchanged).
- **U₀ samples** — polygon-interior only (`work_plane_grid_polygon`).
- **Fixture centres** — polygon-clipped with densify/refill (`fixture_positions_polygon`); coverage-ranked factor pairs prefer layouts that already land inside.

---

## 6. Change-set summary (proposal only — no code changes yet)

If we agree on the fixes, the following edits will make the original doc match the code and the code match the intent:

| # | File | Change |
|---|------|--------|
| 1 | `documentation/math/06-non-4-side-rooms-calculation.md` §11.1 | One-liner defining the `fast=` trigger (see §1 above) |
| 2 | `documentation/math/01-units-and-symbols.md` | Footnote on the L=x / W=y convention (see §2 above) |
| 3 | `luxscale/lighting_calc/cad_calculate.py::build_equivalent_rectangle` | Swap axis-aligned bbox for edge-orientation-histogram bbox (see §3.3); store `polygon_orientation_deg` in `calc_meta` |
| 4 | `luxscale/lighting_calc/polygon.py::_polygon_is_simple` | Add `max_edges_for_full_check` guard; docstring notes the O(N²) ceiling |
| 5 | `luxscale/lighting_calc/cad_calculate.py::cad_calculate_lighting` | Emit `polygon_fill_ratio` in `calc_meta["polygon"]`; append warning to `engine_notes` when \(\alpha < 0.85\) |

None of these change the lumen-method physics, all preserve backward compatibility of the `/cad_calc` response schema (they add fields, never remove), and #3 is the only one that materially shifts numbers (fixture spacing for rotated rooms). Ready to sequence into a PR when you sign off.

---

## 7. Related documents

- [`06-non-4-side-rooms-calculation.md`](./06-non-4-side-rooms-calculation.md) — the main math doc (unchanged; this addendum sits beside it)
- [`04-pipeline-from-request-to-results-and-export.md`](./04-pipeline-from-request-to-results-and-export.md) — fast-mode also affects the compliance-fallback path documented here
- [`../../development_plan/06-non-symmetric-rooms-migration-plan.md`](../../development_plan/06-non-symmetric-rooms-migration-plan.md) — Phase B is where §5's fixture-clipping lives
