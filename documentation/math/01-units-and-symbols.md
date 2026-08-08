# Units and symbols

## 1. Base units (SI)

| Symbol | Meaning | Unit |
|--------|---------|------|
| \(L, W\) | Room length (x-axis) and width (y-axis) — see convention note below | m |
| \(A\) | Floor area | m² |
| \(H\) | Ceiling height (luminaire plane) | m |
| \(h_\mathrm{wp}\) | Work plane height above floor | m (default **0.75**) |
| \(\Phi\) | Luminous flux | lm |
| \(E\) | Illuminance on the work plane | lx (= lm/m²) |
| \(I\) | Luminous intensity | cd |
| \(r\) | Distance (fixture centre to sample point) | m |

## 2. Subscripts and names

| Symbol | Meaning |
|--------|---------|
| \(E_{m,r}\) | Required **maintained average** illuminance from standard row (**`Em_r_lx`**) |
| \(U_{0,\mathrm{req}}\) | Required uniformity ratio from standard row (**`Uo`**, e.g. 0.4) |
| \(\mathrm{MF}\) | Maintenance factor (**`maintenance_factor`**, default **0.63**) |
| \(\eta\) | LED efficacy (**lm/W**) |
| \(P\) | Lamp / luminaire electrical power (**W**) |
| \(N\) | Number of fixtures (integer) |
| \(U_0\) | Computed **\(E_\mathrm{min}/E_\mathrm{avg}\)** on the sample grid |
| \(U_1\) | Computed **\(E_\mathrm{min}/E_\mathrm{max}\)** on the sample grid |

## 3. Non-dimensional ratios

- **Uniformity ratios** \(U_0, U_1 \in [0,1]\) in ideal cases; implementation clamps behaviour via denominators.
- **Gaps** (Lux gap, U₀ gap) are **non-negative** by definition in the API row (see [03](./03-compliance-inequalities-and-row-properties.md)).

## 4. Axis convention (L, W)

Throughout this codebase and its documentation, **`L` (length) is the x-axis dimension** of the floor plan (the "horizontal" one in a landscape view) and **`W` (width) is the y-axis dimension**. Concretely, in the sample-grid and fixture-grid formulas of [02](./02-core-equations-lumen-grid-uniformity.md), \(s_x = L / n_x\) and \(s_y = W / n_y\).

This inverts the "width = x, length = y" convention used by some CAD tools. It is inherited from the legacy PHP contract `sides = [width, length, width, length]`, where `length` = the longer edge drawn left-to-right on the plan. Every module in the pipeline honours the same convention, so results are internally consistent; just keep it in mind when comparing symbol tables against outside sources.

---

Next: [02-core-equations-lumen-grid-uniformity.md](./02-core-equations-lumen-grid-uniformity.md)
