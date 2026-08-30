# Non-4-side rooms — math and calculation logic

> **Scope:** every step of the math that runs when the caller submits a polygon room (`POST /cad_calc`) instead of the legacy 4-side rectangle (`POST /calculate`). This is the mathematical companion to [`development_plan/06-non-symmetric-rooms-migration-plan.md`](../../development_plan/06-non-symmetric-rooms-migration-plan.md). Implementation lives in `luxscale/lighting_calc/polygon.py` and `luxscale/lighting_calc/cad_calculate.py`.

Notation follows [01-units-and-symbols.md](./01-units-and-symbols.md); if a symbol isn't redefined here, it means what it does there.

---

## 0. Big picture

Any polygon room (3 ≤ N ≤ ~1000 vertices, non-convex allowed) is turned into an **equivalent-area rectangle** and fed to the existing 4-side calculation engine. Two things make this "accurate" for lighting design instead of a rough approximation:

1. The lumen method — the physics that decides **how many fixtures** the room needs — uses the polygon's **true shoelace area**, not the bounding-box area.
2. The engine's illuminance-per-point search runs on an equivalent rectangle whose **aspect ratio matches the polygon's bounding box**, so fixture spacing (which affects U₀) is not distorted.

Current status: U₀ samples **and** fixture centres are polygon-clipped
(filter + densify/refill). Lumen-method total flux still uses the
equivalent-area rectangle so installed lumens stay polygon-correct.

---

## 1. Symbols specific to this document

In addition to the base symbols from [01-units-and-symbols.md](./01-units-and-symbols.md):

| Symbol | Meaning | Unit |
|--------|---------|------|
| \(V = \{(x_i, y_i)\}_{i=0}^{N-1}\) | Ordered polygon vertices (CCW after normalization, first ≠ last) | m |
| \(N\) | Vertex count, \(N \ge 3\) | — |
| \(A\) | Signed shoelace area of the polygon (positive after normalization) | m² |
| \(P\) | Polygon perimeter | m |
| \((c_x, c_y)\) | Polygon centroid | m |
| \((x_{\min}, y_{\min}, x_{\max}, y_{\max})\) | Axis-aligned bounding box | m |
| \(B_W, B_L\) | Bounding box width and length, \(B_W = x_{\max} - x_{\min}\), \(B_L = y_{\max} - y_{\min}\) | m |
| \(W_\mathrm{eq}, L_\mathrm{eq}\) | Equivalent-area rectangle width and length | m |
| \(G\) | Work-plane sample grid dimension (\(G \times G\) points) | — |

---

## 2. Step 1 — Polygon ingest and normalization

**Inputs:** raw vertex list in any of the three accepted forms (documented at [`POST /cad_calc`](../../docs/api_docs.html)):

- `{"polygon": {"vertices": [[x, y], …]}}` (canonical)
- `{"polygon": [[x, y], …]}`
- Top-level `{"vertices": [[x, y], …]}`
- Dict-form vertices `{"x": .., "y": ..}` are also accepted.

### 2.1 Coordinate coercion

Each entry is coerced to `(float, float)`. Any entry that fails coercion raises `PolygonError`.

### 2.2 Consecutive-duplicate collapse

Two consecutive vertices \((x_i, y_i)\) and \((x_{i+1}, y_{i+1})\) with

\[
|x_{i+1} - x_i| \le \varepsilon \;\wedge\; |y_{i+1} - y_i| \le \varepsilon,
\qquad \varepsilon = 10^{-9}\ \text{m},
\]

are collapsed to a single vertex. If the caller sent a closed polygon (first == last), the trailing duplicate is dropped so the internal representation is always **open** (first ≠ last).

### 2.3 Minimum vertex count

After deduplication we require \(N \ge 3\); otherwise `PolygonError("polygon needs at least 3 distinct vertices")`.

### 2.4 Signed area and orientation (shoelace)

The signed area is computed by the shoelace formula:

\[
\boxed{\;A_\mathrm{signed} \;=\; \tfrac{1}{2}\sum_{i=0}^{N-1}\bigl(x_i\, y_{(i+1)\bmod N} \;-\; x_{(i+1)\bmod N}\, y_i\bigr)\;}
\]

- \(A_\mathrm{signed} > 0\) → the vertex order is **counter-clockwise (CCW)**.
- \(A_\mathrm{signed} < 0\) → **clockwise (CW)**; we reverse the vertex list *in place* so the internal representation is always CCW. This makes downstream cross-product signs unambiguous (used by `is_convex` in §14).
- \(|A_\mathrm{signed}| < 10^{-12}\) → collinear or degenerate; rejected with `PolygonError("polygon has zero area")`.

After normalization the (unsigned) area is:

\[
A \;=\; |A_\mathrm{signed}|.
\]

### 2.5 Self-intersection check

Every non-adjacent edge pair \((e_i, e_j)\) is tested with a proper-intersection predicate (see §15). If any pair intersects *not* at a shared endpoint, the polygon is rejected with `PolygonError("polygon is self-intersecting")`.

Complexity: \(O(N^2)\). Fine for typical CAD rooms (N < 100); a sweep-line refinement is an easy future upgrade if we ever see 10k-vertex inputs.

---

## 3. Step 2 — Perimeter, centroid, bounding box

### 3.1 Perimeter

\[
\boxed{\;P \;=\; \sum_{i=0}^{N-1}\sqrt{(x_{(i+1)\bmod N} - x_i)^2 + (y_{(i+1)\bmod N} - y_i)^2}\;}
\]

### 3.2 Centroid

The area-weighted centroid (correct for any simple polygon, not just convex):

\[
\boxed{\;
\begin{aligned}
c_x &= \frac{1}{6 A_\mathrm{signed}}\sum_{i=0}^{N-1}(x_i + x_{i+1})\,(x_i y_{i+1} - x_{i+1} y_i), \\
c_y &= \frac{1}{6 A_\mathrm{signed}}\sum_{i=0}^{N-1}(y_i + y_{i+1})\,(x_i y_{i+1} - x_{i+1} y_i),
\end{aligned}
\;}
\]

where indices are taken modulo \(N\). If \(|A_\mathrm{signed}| < 10^{-15}\) (numerical degeneracy) we fall back to the arithmetic mean of vertices, but at that point the polygon would already have been rejected at step 2.4.

### 3.3 Bounding box

\[
x_{\min} = \min_i x_i,\quad
y_{\min} = \min_i y_i,\quad
x_{\max} = \max_i x_i,\quad
y_{\max} = \max_i y_i.
\]

\[
B_W = x_{\max} - x_{\min},\qquad
B_L = y_{\max} - y_{\min},\qquad
A_\mathrm{bbox} = B_W \cdot B_L.
\]

**Invariant:** \(A \le A_\mathrm{bbox}\), with equality iff the polygon *is* its bounding box. For an L-shape this inequality is strict — that gap is exactly what makes the equivalent-area trick necessary in step 4.

---

## 4. Step 3 — Equivalent-area rectangle bridge

**Goal:** produce a rectangle \((W_\mathrm{eq}, L_\mathrm{eq})\) that the existing engine can consume via its `sides = [W_eq, L_eq, W_eq, L_eq]` interface, such that:

1. \(W_\mathrm{eq} \cdot L_\mathrm{eq} = A\) — total lumens will come out right.
2. \(W_\mathrm{eq} / L_\mathrm{eq} = B_W / B_L\) — fixture-grid aspect ratio mirrors what a designer sees on the plan.

Let \(r = B_W / B_L\). Solving the two constraints:

\[
\boxed{\;
L_\mathrm{eq} = \sqrt{A / r}, \qquad
W_\mathrm{eq} = r \cdot L_\mathrm{eq} = \sqrt{A \cdot r}.
\;}
\]

Degenerate case \(B_W \le 0\) or \(B_L \le 0\) (already blocked in §2.4) — we fall back to a square, \(W_\mathrm{eq} = L_\mathrm{eq} = \sqrt{A}\).

### 4.1 Why this preserves lumen physics

The rectangle-area path of the engine uses Brahmagupta on `sides = [a, b, c, d]`. For a rectangle \(a = c\), \(b = d\):

\[
s = \frac{2a + 2b}{2} = a + b, \quad
A_\mathrm{engine} = \sqrt{(s-a)(s-b)(s-a)(s-b)} = \sqrt{(a b)^2} = a \cdot b.
\]

Feeding `sides = [W_eq, L_eq, W_eq, L_eq]` gives \(A_\mathrm{engine} = W_\mathrm{eq} \cdot L_\mathrm{eq} = A\), so the engine's lumen-method area is *literally* the polygon's shoelace area. No override was needed; the algebra falls out.

### 4.2 What this does not preserve

The fixture-grid coordinates the engine returns are inside a \(W_\mathrm{eq} \times L_\mathrm{eq}\) rectangle, not inside the original polygon. For a rectangle input this is exactly correct. For an L-shape:

- The **count** of fixtures is correct (physics driven by \(A\)).
- The **average lux** is correct on the polygon.
- The **fixture (x, y)** positions may fall in what would be the notch — Phase B replaces the placement engine with polygon-clipped sampling to fix this.

---

## 5. Step 4 — Lumen-method fixture count

Same as [02-core-equations-lumen-grid-uniformity.md §2](./02-core-equations-lumen-grid-uniformity.md), with \(A\) now = polygon area (not bbox area).

### 5.1 Rated and effective flux per fixture

\[
\Phi_\mathrm{rated} = P \cdot \eta,\qquad
\Phi_\mathrm{eff} = \Phi_\mathrm{rated} \cdot \mathrm{MF},
\]

where \(\eta\) is the LED efficacy in lm/W (looked up per luminaire family + zone from `led_efficacy`) and \(\mathrm{MF}\) is the maintenance factor from `luxscale.app_settings.get_maintenance_factor()` (default 0.63).

### 5.2 Required total flux for target lux

Given target lux \(E_{m,r}\) (from the standards row's `Em_r_lx`, or the calculator `place`'s `lux` field):

\[
\boxed{\;\Phi_\mathrm{needed} \;=\; \frac{E_{m,r} \cdot A}{\mathrm{MF}}\;}
\]

### 5.3 Minimum fixture count

\[
\boxed{\;N_\mathrm{min} \;=\; \left\lfloor \frac{\Phi_\mathrm{needed}}{\Phi_\mathrm{rated}} \right\rfloor + 1\;}
\]

The `+1` guarantees the search starts at a candidate that could conceivably meet the target after maintenance loss — the engine never begins below the theoretical minimum.

### 5.4 Achieved spatial-average illuminance for \(N\) fixtures

\[
\boxed{\;E_\mathrm{avg,lm}(N) \;=\; \frac{N \cdot \Phi_\mathrm{rated} \cdot \mathrm{MF}}{A}\;}
\]

Because \(A\) here is the true polygon area (not \(B_W \cdot B_L\)), this equation gives the physically correct maintained average lux for a non-convex room. If we had used \(A_\mathrm{bbox}\) instead — the naive approach — the required fixture count for an L-shape would be underestimated by the factor \(A_\mathrm{bbox} / A\) (25 % low for the canonical L-shape in §12).

### 5.5 Main-sweep stop rule (over-lighting)

If \(E_\mathrm{avg,lm}(N) > 1.35\,E_{m,r}\) the inner loop breaks — no reason to keep adding fixtures once we're 35 % over target. The relaxed fallback sweep uses 1.65× the target instead (see §11).

---

## 6. Step 5 — Fixture placement grid

For a candidate count \(N\), the engine searches all integer factorizations \(N = n_x \cdot n_y\) and picks the pair that **minimizes \(|s_x - s_y|\)** (most-square bay). On the equivalent rectangle:

\[
s_x = \frac{L_\mathrm{eq}}{n_x}, \qquad
s_y = \frac{W_\mathrm{eq}}{n_y}.
\]

Fixture centers use a half-bay inset — same rule as the rectangular path — so no fixture sits on a wall:

\[
\bigl(x_i, y_j\bigr) \;=\; \Bigl(\bigl(i + \tfrac{1}{2}\bigr)\,s_x,\;\; \bigl(j + \tfrac{1}{2}\bigr)\,s_y\Bigr),
\qquad 0 \le i < n_x,\; 0 \le j < n_y.
\]

### 6.1 Minimum-spacing constraint

If \(\min(s_x, s_y) < 0.8\text{ m}\) (interior zone) or \(< 4\text{ m}\) (exterior), the pair is rejected and the sweep continues with the next factorization / count. This prevents fixtures from being physically closer than a designer would ever allow.

### 6.2 Multiple layouts per \(N\)

`spacing_factor_pairs(L_eq, W_eq, N, min_spacing_m)` returns every valid \((n_x, n_y)\) pair sorted by \(|s_x - s_y|\). Different pairs can produce different U₀ on the same room + count, so the solver may try more than one before accepting or rejecting the count.

### 6.3 Polygon clipping (Phase B)

For `/cad_calc` rooms the rectangular centres are filtered by `polygon.contains` (after mapping into the engine frame). If fewer than \(N\) survive, the grid is densified (\(\mathrm{scale}\cdot n_x \times \mathrm{scale}\cdot n_y\), \(\mathrm{scale}=2\ldots 8\)) until enough interior points appear; surplus points are thinned to exactly \(N\) by farthest-point sampling. Factor pairs are also re-ranked by **coverage score** (fraction of the base \(n_x\times n_y\) centres that land inside) before the most-square tie-break.

---

## 7. Step 6 — Work-plane sampling grid

### 7.1 Rectangular baseline density

Grid density \(G_\mathrm{rect}\) is chosen by area (bigger rooms use fewer samples to keep runtime in check):

\[
G_\mathrm{rect} \;=\;
\begin{cases}
10, & A < 900\ \text{m}^2 \\
8,  & 900 \le A < 1800 \\
6,  & 1800 \le A < 3500 \\
5,  & A \ge 3500
\end{cases}
\]

### 7.2 Polygon-clipped density (Phase B)

When the room is a polygon with fill ratio \(\alpha = A / A_\mathrm{oriented\text{-}bbox}\), \(G\) is boosted so the *effective* sample count after clipping roughly matches the rectangular path:

\[
\boxed{\;G \;=\; \min\!\bigl(\lceil G_\mathrm{rect}/\sqrt{\alpha}\rceil,\; G_\mathrm{rect}+4\bigr)\;}
\]

The \(G_\mathrm{rect}+4\) cap fires for \(\alpha \lesssim 0.51\) (where \(10/\sqrt{\alpha}\) first exceeds 14 at the default bracket). That single cap both bounds runtime (~2× vs rectangular) and prevents \(\alpha \to 0\) from sending \(G \to \infty\) — there is no separate \(\alpha\) floor.

### 7.3 Sample placement

Candidate points use the same half-bay inset rule as fixtures on the equivalent rectangle:

\[
\bigl(p_{ix}, p_{jy}\bigr) \;=\; \Bigl(\bigl(i + \tfrac{1}{2}\bigr)\,\tfrac{L_\mathrm{eq}}{G},\;\; \bigl(j + \tfrac{1}{2}\bigr)\,\tfrac{W_\mathrm{eq}}{G}\Bigr),
\quad 0 \le i, j < G.
\]

There is **no fixed physical wall margin** (the legacy `DEFAULT_WALL_MARGIN_M = 0.5` is unused dead weight). Clearance comes from the half-bay inset. For polygon rooms, candidates are then filtered by `polygon.contains(..., on_edge=False)` after the world-coordinate polygon is affine-mapped into the engine rectangle frame — so notch / exterior points drop out of \(E_\mathrm{avg}\) and \(U_0\). Effective sample count \(n_\mathrm{eff} \approx \alpha \cdot G^2\) is emitted in `calc_meta.polygon.effective_sample_count`.

Work-plane height defaults to \(h_\mathrm{wp} = 0.75\ \text{m}\); ceiling / luminaire plane is at \(H\).

---

## 8. Step 7 — Point-by-point illuminance from the IES

For each fixture-sample pair \((f_k, p_{ij})\), the horizontal illuminance contribution is the inverse-square law with oblique-incidence cosine:

\[
\boxed{\;
E_{k \to ij} \;=\; \frac{I\bigl(\theta_h,\, \theta_v\bigr)}{R^2}\cdot\cos i,
\;}
\]

with:

- \(R = \sqrt{(f_{k,x} - p_{ij,x})^2 + (f_{k,y} - p_{ij,y})^2 + (H - h_\mathrm{wp})^2}\) — 3D distance in metres.
- \(\theta_v\) — angle from the fixture's downward normal to the ray \(f_k \to p_{ij}\).
- \(\theta_h\) — azimuth of the ray about the fixture axis; folded into the IES file's H-range (0–90°, 0–180°, or 0–360°) using quarter- or half-symmetry.
- \(I(\theta_h, \theta_v)\) — candela at that angle, interpolated bilinearly on the Type C table.
- \(\cos i = (H - h_\mathrm{wp}) / R\) — component of the ray along the work-plane's upward normal.

### 8.1 Candela scaling to design lumens

The raw candela table \(I_\mathrm{ies}\) is scaled so total luminous flux matches the design intent per fixture:

\[
\Phi_\mathrm{ies} = \Phi_\mathrm{lamp} \cdot n_\mathrm{lamps} \cdot m_\mathrm{ies},\qquad
\rho = \frac{\Phi_\mathrm{design}}{\Phi_\mathrm{ies}}.
\]

The engine clamps \(\rho\) to a plausible range \([\rho_{\min}, \rho_{\max}]\) (constants `ies_lumen_to_design_ratio_{min,max}`) to catch header mis-declarations; then

\[
I(\theta_h, \theta_v) = \rho \cdot I_\mathrm{ies}(\theta_h, \theta_v).
\]

### 8.2 Superposition

Every fixture contributes independently at every sample point:

\[
\boxed{\;E_{ij} \;=\; \sum_{k=1}^{N} E_{k \to ij}\;}
\]

This is what fills the \(G \times G\) matrix.

---

## 9. Step 8 — Grid statistics and uniformity

Let \(\{E_{ij}\}\) be the \(G^2\) illuminance values from step 8.2. The engine computes:

\[
E_{\min} = \min_{i,j} E_{ij}, \qquad
E_{\max} = \max_{i,j} E_{ij}, \qquad
E_\mathrm{avg,grid} = \frac{1}{G^2}\sum_{i,j} E_{ij}.
\]

**Uniformity ratios:**

\[
\boxed{\;
U_0 \;=\;
\begin{cases}
\dfrac{E_{\min}}{E_\mathrm{avg,grid}}, & E_\mathrm{avg,grid} > 0, \\
0, & \text{otherwise.}
\end{cases}
\qquad
U_1 \;=\;
\begin{cases}
\dfrac{E_{\min}}{E_{\max}}, & E_{\max} > 0, \\
0, & \text{otherwise.}
\end{cases}
\;}
\]

Compliance uses \(U_0\) against the standard row's `Uo`. \(U_1\) is reported for completeness.

---

## 10. Step 9 — Inter-reflection boost

Direct IES illuminance is *only the first bounce*. Real rooms reflect light off ceilings, walls, and floors, adding to the work-plane average. The engine models this as a single scalar boost \(f_\mathrm{IR} \in [0, 0.5]\) from the reflectance preset (or explicit `material_physics.irf` on the request):

\[
E_{ij}' = E_{ij} \cdot (1 + f_\mathrm{IR}),
\]

applied element-wise to the grid *before* re-computing \(E_\mathrm{avg,grid}\), \(E_{\min}\), \(E_{\max}\), \(U_0\), \(U_1\).

Because it's a uniform scaling, \(U_0\) and \(U_1\) are invariant under the boost. Only the absolute lux values shift up.

---

## 11. Step 10 — Compliance and the fallback sweep

For each option row the engine emits:

\[
\Delta E = \max\bigl(0,\; E_{m,r} - E_\mathrm{avg,grid}'\bigr) \quad (\text{lux gap}), \qquad
\Delta U = \max\bigl(0,\; U_{0,\mathrm{req}} - U_0\bigr) \quad (\text{U₀ gap}),
\]

with `is_compliant = (ΔE == 0) and (ΔU == 0)`.

### 11.1 Main sweep

Fixture counts sweep \(N = N_\mathrm{min}, N_\mathrm{min}+1, \dots\) with step \(\Delta N\) until either

- enough compliant options accumulate (\(\le\) `max_solutions_total`, default 5), or
- \(E_\mathrm{avg,lm}(N) > 1.35\,E_{m,r}\) — stop; we're 35 % over target.

**Fast-mode trigger.** The step is \(\Delta N = 1\) by default and \(\Delta N = 2\) when *fast mode* is on. Fast mode fires when the caller sets `fast: true` / `fast: 1` (or the strings `"1" | "true" | "yes" | "fast"`, case-insensitive) in the JSON body, **or** attaches `?fast=…` in the query string with any of those values. Anything else — including omission — runs full mode. In addition to the step change, fast mode caps the returned compliant options at 3 and halves the uniformity-fallback budget (`160 → 80`) and span (`120 → 80`). Wired in `app.py::_want_fast_calculate`; propagated through `calculate_lighting(..., fast=…)`.

### 11.2 Uniformity fallback

If the main sweep produces zero compliant options, the engine relaxes the over-lighting cap to \(1.65\,E_{m,r}\) and re-sweeps looking specifically for \(U_0 \ge U_{0,\mathrm{req}}\). This adds N until the layout gets tight enough to satisfy uniformity, even if the average is well above the standard's minimum.

Both sweeps produce identical result-row schemas, so downstream consumers (PDF, AI analysis) don't have to branch.

---

## 12. Worked example — L-shape

Consider the canonical L-shape used in the test suite:

```
vertices = [(0,0), (6,0), (6,4), (3,4), (3,8), (0,8)]
height   = 3.0 m
place    = "Office"  (target Em_r = 500 lx, Uo_req ≈ 0.6)
```

### 12.1 Geometry

Shoelace signed area:

\[
\begin{aligned}
2 A_\mathrm{signed}
&= (0)(0) - (6)(0) + (6)(4) - (6)(0) + (6)(4) - (3)(4) \\
&\quad + (3)(8) - (3)(4) + (3)(8) - (0)(8) + (0)(0) - (0)(8) \\
&= 72.
\end{aligned}
\]

So \(A = 36\ \text{m}^2\). Cross-check: the outer 6×8 = 48 m² minus the 3×4 = 12 m² notch = 36 ✓. The bounding box is \(6 \times 8 = 48\ \text{m}^2\), so the polygon covers **75 %** of its bbox — an L that ignored this would over-count by 33 %.

Perimeter: \(6 + 4 + 3 + 4 + 3 + 8 = 28\ \text{m}\).

Equivalent rectangle (aspect ratio \(r = 6/8 = 0.75\)):

\[
L_\mathrm{eq} = \sqrt{36/0.75} = \sqrt{48} \approx 6.928\ \text{m},\qquad
W_\mathrm{eq} = 0.75 \cdot L_\mathrm{eq} = \sqrt{27} \approx 5.196\ \text{m}.
\]

Check: \(W_\mathrm{eq} \cdot L_\mathrm{eq} = \sqrt{27} \cdot \sqrt{48} = \sqrt{1296} = 36\ \text{m}^2\) ✓.

### 12.2 Lumen method

Assume a 40 W downlight, \(\eta = 130\) lm/W, \(\mathrm{MF} = 0.63\):

\[
\Phi_\mathrm{rated} = 40 \cdot 130 = 5{,}200\ \text{lm},\qquad
\Phi_\mathrm{eff} = 5{,}200 \cdot 0.63 = 3{,}276\ \text{lm}.
\]

Required total flux:

\[
\Phi_\mathrm{needed} = \frac{500 \cdot 36}{0.63} = 28{,}571\ \text{lm}.
\]

Minimum fixture count:

\[
N_\mathrm{min} = \left\lfloor \frac{28{,}571}{5{,}200} \right\rfloor + 1 = 5 + 1 = 6.
\]

Achieved \(E_\mathrm{avg,lm}\) for \(N = 6\):

\[
E_\mathrm{avg,lm}(6) = \frac{6 \cdot 5{,}200 \cdot 0.63}{36} = \frac{19{,}656}{36} \approx 546\ \text{lx}.
\]

That's slightly above the 500 lx target, well below the 1.35 × 500 = 675 lx over-lighting cap → the sweep will evaluate this option and try \(N = 7, 8, \dots\) up to the cap.

### 12.3 Fixture-grid factorization

For \(N = 6\) the possible layouts are \((1,6), (2,3), (3,2), (6,1)\). Spacings on the equivalent rectangle (\(L_\mathrm{eq} = 6.928, W_\mathrm{eq} = 5.196\)):

| \((n_x, n_y)\) | \(s_x = L_\mathrm{eq} / n_x\) | \(s_y = W_\mathrm{eq} / n_y\) | \(\lvert s_x - s_y \rvert\) |
|:--:|:--:|:--:|:--:|
| (1, 6) | 6.928 | 0.866 | 6.062 |
| (2, 3) | 3.464 | 1.732 | 1.732 |
| (3, 2) | 2.309 | 2.598 | **0.289** ✓ |
| (6, 1) | 1.155 | 5.196 | 4.041 |

The 3×2 grid wins — it's the closest to square. Both spacings are ≥ 0.8 m so the minimum-spacing constraint is satisfied.

### 12.4 U₀ evaluation

The engine samples on a \(G \times G\) grid with \(G = 10\) (area 36 < 900 m² → default), computes \(E_{ij}\) by summing IES contributions from the 6 fixtures, applies the inter-reflection factor, and emits \(U_0 = E_{\min}/E_\mathrm{avg,grid}'\). If \(U_0 \ge 0.6\), the row is compliant; otherwise the engine keeps increasing \(N\) or invokes the fallback sweep.

---

## 13. Point-in-polygon (auxiliary math)

Not used in the Phase A calculation path itself, but exposed via `polygon.contains(x, y)` and consumed by Phase B's polygon-clipped sample grid.

### 13.1 Ray-casting predicate

To test whether \((x, y)\) is inside a polygon, cast a horizontal ray to \(+x\) and count crossings with polygon edges:

\[
\text{crossings}(x, y) = \Bigl|\bigl\{ i : (y_i > y) \ne (y_{i+1} > y) \;\wedge\; x < x_\mathrm{int}(i) \bigr\}\Bigr|,
\]

where the edge \(x\)-intercept at height \(y\) is:

\[
x_\mathrm{int}(i) = \frac{(x_{i+1} - x_i)(y - y_i)}{y_{i+1} - y_i} + x_i.
\]

- Odd count → inside; even count → outside. This is the classic Jordan-curve theorem in code.

### 13.2 Edge-on point handling

The implementation adds an *edge test* before the ray cast: if \((x, y)\) lies on any segment (colinearity + parameter \(t \in [0, 1]\)), the boolean `on_edge` argument decides the return. The public API defaults `on_edge=True` so grid samples exactly on the polygon boundary are counted as inside (matches how designers reason about work-plane coverage).

Complexity per query: \(O(N)\). Complexity for a full \(G \times G\) sampling: \(O(G^2 N)\) — small enough that Phase B can afford it directly, no acceleration structure needed at typical CAD sizes.

---

## 14. Convexity check

`polygon.is_convex()` walks the CCW-normalized vertices and inspects the cross products of consecutive edges:

\[
z_i = (x_{i+1} - x_i)(y_{i+2} - y_{i+1}) - (y_{i+1} - y_i)(x_{i+2} - x_{i+1}).
\]

If every \(z_i \ge 0\) (equivalently, all left turns) the polygon is convex. Any sign flip signals a right turn → concave. Values with \(|z_i| < 10^{-12}\) (colinear triples) are ignored so a hexagon with a collinear degenerate vertex is still called convex.

This flag is metadata only — the calculation path treats convex and non-convex the same in Phase A. In Phase B it lets the engine pick a fast path for convex rooms (no PIP needed on the interior grid).

---

## 15. Segment-intersection predicate (used by §2.5)

Two segments \(\overline{ab}\) and \(\overline{cd}\) *properly intersect* iff the endpoints of one straddle the line of the other, and vice versa:

\[
\begin{aligned}
o_1 &= \operatorname{orient}(a, b, c), \\
o_2 &= \operatorname{orient}(a, b, d), \\
o_3 &= \operatorname{orient}(c, d, a), \\
o_4 &= \operatorname{orient}(c, d, b),
\end{aligned}
\qquad
\operatorname{orient}(p, q, r) = (q_x - p_x)(r_y - p_y) - (q_y - p_y)(r_x - p_x).
\]

Proper intersection ⇔ \((o_1 o_2 < 0) \wedge (o_3 o_4 < 0)\). Collinear overlaps and shared endpoints (which are normal for adjacent polygon edges) are **not** counted as intersections — this is what lets the check correctly ignore adjacent edges without extra bookkeeping.

The epsilon in the implementation is \(10^{-12}\); anything below floats to the "on the line" case, which we treat as *not* a proper crossing.

---

## 16. Phase status

| Step | Status |
|-----:|--------|
| §5 lumen method — \(A\) = polygon shoelace area | ✅ shipped |
| §7 sample grid — polygon-clipped via `work_plane_grid_polygon` + G boost | ✅ shipped |
| §9 U₀ — denominator uses \(n_\mathrm{eff}\) interior samples | ✅ shipped |
| §6 fixture grid — `fixture_positions_polygon` (filter + densify/refill) | ✅ shipped |
| §12.3 factorization — coverage-score tie-breaker on factor pairs | ✅ shipped |

`calc_meta.polygon` carries `fill_ratio`, `orientation_deg`, `effective_sample_count`, and `sample_density_per_m2`.

---

## 17. Where to look in the code

| Concept | File · Function |
|---|---|
| Vertex ingest + normalization | `luxscale/lighting_calc/polygon.py` — `Polygon.from_vertices` |
| Shoelace area | `polygon.py` — `_signed_area` |
| Perimeter, centroid, bbox | `polygon.py` — `_perimeter`, `_centroid`, `_bbox` |
| Self-intersection | `polygon.py` — `_segments_intersect`, `_polygon_is_simple` |
| PIP + grid sampling | `polygon.py` — `Polygon.contains`, `Polygon.sample_grid` |
| Equivalent rectangle | `luxscale/lighting_calc/cad_calculate.py` — `build_equivalent_rectangle` |
| Wrapper into the engine | `cad_calculate.py` — `cad_calculate_lighting` |
| Lumen method, sweeps | `luxscale/lighting_calc/calculate.py` — `calculate_lighting` |
| IES point illuminance | `luxscale/uniformity_calculator.py` — `compute_uniformity_metrics`, `candela_at_angle_type_c`, `illuminance_at_point_horizontal` |
| Grid density (rect) | `uniformity_calculator.py` — `uniformity_grid_n_for_room` |
| Grid density (polygon) | `uniformity_calculator.py` — `uniformity_grid_n_for_polygon` |
| Polygon-clipped samples | `uniformity_calculator.py` — `work_plane_grid_polygon`, `_polygon_in_engine_frame` |
| Polygon-clipped fixtures | `uniformity_calculator.py` — `fixture_positions_polygon`, `polygon_layout_interior_count` |
| PDF floor plan (polygon) | `generate_report.py` — `make_room_drawing`, `_fixtures_world_coords`, `_engine_room_dims` |
| Route wiring | `app.py` — `POST /cad_calc` (via `luxscale.lighting_calc.cad_calculate.cad_calculate_lighting`) |

---

## 18. Related documents

- [`01-units-and-symbols.md`](./01-units-and-symbols.md) — base symbols
- [`02-core-equations-lumen-grid-uniformity.md`](./02-core-equations-lumen-grid-uniformity.md) — rectangular-room math (parent of §5–§10)
- [`03-compliance-inequalities-and-row-properties.md`](./03-compliance-inequalities-and-row-properties.md) — compliance gaps definition
- [`04-pipeline-from-request-to-results-and-export.md`](./04-pipeline-from-request-to-results-and-export.md) — where this step fits in the overall API flow
- [`05-ies-lm63-fields-beam-angle-and-flux.md`](./05-ies-lm63-fields-beam-angle-and-flux.md) — photometric data model
- [`../../development_plan/06-non-symmetric-rooms-migration-plan.md`](../../development_plan/06-non-symmetric-rooms-migration-plan.md) — architecture-level plan and phased rollout
