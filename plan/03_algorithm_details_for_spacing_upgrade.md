# Algorithm Details For Optional Fixture Spacing

## Algorithm objective

The lighting engine solves for fixture options that satisfy:

```text
maintained average illuminance >= required illuminance
calculated U0 >= required U0
```

The spacing upgrade adds one optional constraint:

```text
use or evaluate requested center-to-center fixture spacing on X and Y
```

The algorithm must still produce physically consistent rows:

```text
Fixtures = layout_nx * layout_ny
Spacing X = length / layout_nx
Spacing Y = width / layout_ny
```

## Baseline algorithm

Inputs:

```text
sides = [a, b, c, d]
height
standard_row or place
fast flag
optional polygon
```

Derived geometry:

```text
L = max(a, c)
W = max(b, d)
A = cyclic_quadrilateral_area(a, b, c, d)
```

Required performance:

```text
E_req = standard_row.Em_r_lx or define_places[place].lux
U0_req = standard_row.Uo or define_places[place].uniformity
```

For each fixture family and power:

```text
Phi_fixture = power_w * efficacy_lm_per_w
N_min = floor((E_req * A) / (Phi_fixture * MF)) + 1
```

For each candidate fixture count:

```text
N in [N_min, N_min + search_span]
```

Generate exact factor pairs:

```text
P(N) = {(nx, ny): nx * ny = N}
```

Reject too-dense layouts:

```text
min(L / nx, W / ny) >= 0.8
```

Sort factor pairs:

```text
sort by abs((L / nx) - (W / ny)), then nx, then ny
```

Evaluate each pair:

```text
Sx = L / nx
Sy = W / ny
E_avg_lumen = (N * Phi_fixture * MF) / A
```

Reject main candidates with:

```text
E_avg_lumen > 1.35 * E_req
```

When IES exists, compute point-by-point uniformity:

```text
metrics = compute_uniformity_metrics(..., N, Phi_fixture, nx, ny, ...)
U0 = metrics.U0
```

Accept when:

```text
E_avg_compliance >= E_req
U0 >= U0_req
```

## New custom spacing algorithm

Inputs:

```text
Sx_req
Sy_req
mode
tolerance
edge policy
```

The first implementation supports:

```text
edge policy = half_spacing
```

Convert requested spacing into an integer grid:

```text
nx_custom = max(1, round(L / Sx_req))
ny_custom = max(1, round(W / Sy_req))
N_custom = nx_custom * ny_custom
Sx_actual = L / nx_custom
Sy_actual = W / ny_custom
```

Check spacing validity:

```text
Sx_req > 0
Sy_req > 0
Sx_actual >= 0.8
Sy_actual >= 0.8
abs(Sx_actual - Sx_req) <= tolerance
abs(Sy_actual - Sy_req) <= tolerance
```

The solver evaluates `(nx_custom, ny_custom)` only for `N_custom`. This preserves the invariant:

```text
layout_nx * layout_ny == Fixtures
```

## Mode behavior

### `include`

The solver evaluates normal layouts and also evaluates the custom spacing layout.

Pseudo-flow:

```text
counts = normal count range
if N_custom not in counts:
    add N_custom to counts

for N in sorted(counts):
    default_pairs = exact factor pairs for N
    if N == N_custom:
        pairs = default_pairs plus (nx_custom, ny_custom)
    else:
        pairs = default_pairs
```

Deduplicate pairs before evaluation.

Ranking remains unchanged. A custom spacing row is accepted only if it satisfies the same math and compliance rules as an automatic row.

### `prefer`

The solver evaluates the custom pair first when `N == N_custom`, then normal pairs.

Pseudo-flow:

```text
if N == N_custom:
    pairs = [(nx_custom, ny_custom)] + default_pairs_without_custom
else:
    pairs = default_pairs
```

Use this mode when UI wants to bias toward the user's requested layout but still recover if it fails.

### `only`

The solver evaluates only the custom count and custom pair.

Pseudo-flow:

```text
counts = [N_custom]
pairs = [(nx_custom, ny_custom)]
```

This is useful for checking a fixed design. It may return non-compliant results or no results if average lux caps reject the design.

## Candidate row algorithm

For each evaluated pair:

```text
row = {
  "Fixtures": N,
  "Spacing X (m)": round(L / nx, 2),
  "Spacing Y (m)": round(W / ny, 2),
  "Layout grid": f"{nx}x{ny}",
  "layout_nx": nx,
  "layout_ny": ny
}
```

If pair came from API spacing:

```text
row["Spacing source"] = "api_custom_spacing"
row["Requested spacing X (m)"] = round(Sx_req, 3)
row["Requested spacing Y (m)"] = round(Sy_req, 3)
row["Spacing X delta (m)"] = round((L / nx) - Sx_req, 3)
row["Spacing Y delta (m)"] = round((W / ny) - Sy_req, 3)
row["Spacing mode"] = mode
```

Then all normal checks run:

```text
apply IES metadata
compute U0/U1 when IES exists
compute lux gap
compute U0 gap
compute standard margins
compute density warning
rank or accept row
```

## Uniformity algorithm with custom spacing

No new photometric equation is needed. Custom spacing works by producing different `nx` and `ny` inputs for the existing uniformity function.

Fixture positions:

```text
fx_i = (i + 0.5) * L / nx
fy_j = (j + 0.5) * W / ny
```

For custom spacing:

```text
L / nx ~= Sx_req
W / ny ~= Sy_req
```

IES point illuminance:

```text
E_point_from_fixture = I(h_angle, v_angle) * cos(theta) / distance^2
```

Total point illuminance:

```text
E_point = sum(E_point_from_fixture for every fixture)
```

Grid metrics:

```text
E_min = min(E_point values)
E_avg = average(E_point values)
E_max = max(E_point values)
U0 = E_min / E_avg
U1 = E_min / E_max
```

Calibration:

```text
E_grid_raw_avg = average(raw IES grid)
scale = E_avg_lumen_method / E_grid_raw_avg
E_grid_calibrated = E_grid_raw * scale
```

Inter-reflection:

```text
E_grid_final = E_grid_calibrated * (1 + IRF)
```

Because all grid points are multiplied by the same factor, `U0` and `U1` are unchanged by a uniform inter-reflection multiplier. `E_min`, `E_avg`, and `E_max` increase.

## Average lux algorithm with custom spacing

Custom spacing changes fixture count through `N_custom`. It does not directly change the lumen-method formula.

```text
E_avg = (N_custom * Phi_fixture * MF) / A
```

Consequences:

1. Smaller requested spacing usually creates a larger fixture count and higher average lux.
2. Larger requested spacing usually creates a smaller fixture count and lower average lux.
3. A custom layout can fail because it under-lights the room.
4. A custom layout can fail because it over-lights the room beyond the main or fallback cap.
5. A custom layout can pass average lux but fail U0 if the fixture distribution is uneven or optics are narrow.

## Polygon mode algorithm

For `/cad_calc`, the custom spacing is interpreted in the equivalent-rectangle engine frame:

```text
L = equivalent rectangle length
W = equivalent rectangle width
```

The custom grid is created in that frame:

```text
nx_custom = round(L / Sx_req)
ny_custom = round(W / Sy_req)
```

Then the existing polygon logic applies:

1. Create symmetric rectangular fixture centers.
2. Transform polygon into the engine frame.
3. Keep centers inside the polygon.
4. If too few centers survive, densify candidate positions.
5. If too many centers survive, thin to target count using farthest-point sampling.
6. Clip work-plane sample points to the polygon.

Important metadata:

```text
n_fixtures_requested = N_custom
n_fixtures_layout = actual centers used after polygon clipping/densification
n_fixtures_rect_grid = nx_custom * ny_custom
n_fixtures_rect_interior = centers inside polygon before densification
```

## Ranking algorithm

Current row ranking should remain:

```text
rank = (
  U0 gap,
  Lux gap,
  -U0 calculated,
  total power,
  fixture count
)
```

This means:

1. Compliance gaps matter first.
2. Better U0 wins when gaps are otherwise similar.
3. Lower power wins after compliance quality.
4. Lower fixture count wins after power.

Custom spacing should not automatically win unless `mode=only`. In `include` mode, it is another candidate layout.

## Error handling algorithm

Reject before entering the expensive solver when:

```text
fixture_spacing is not an object
x_m is missing or invalid
y_m is missing or invalid
mode is unknown
tolerance_m is invalid
edge is unknown
converted spacing violates min spacing
converted spacing is outside tolerance
```

Suggested response:

```json
{
  "status": "error",
  "message": "fixture_spacing.x_m/y_m cannot be represented within tolerance for this room",
  "details": {
    "requested_x_m": 2.4,
    "requested_y_m": 2.0,
    "actual_x_m": 2.5,
    "actual_y_m": 2.0,
    "tolerance_m": 0.05
  }
}
```

## Backward compatibility algorithm

When `fixture_spacing` is absent:

```text
custom_fixture_spacing = None
count loop = unchanged
factor_pairs = spacing_factor_pairs(...)
row fields = unchanged except any intentionally added metadata
uniformity inputs = unchanged
response shape = unchanged
```

This must be verified with at least one snapshot-style test or a focused field invariant test.

## Final implementation sequence

1. Add parser/data model.
2. Add custom grid conversion helpers.
3. Add unit tests for parser and grid conversion.
4. Extend `calculate_lighting(...)` signature.
5. Update main sweep count/pair generation.
6. Annotate rows when custom spacing is used.
7. Update fallback sweep count/pair generation.
8. Thread request parsing through `/calculate`.
9. Thread request parsing through `/cad_calc`.
10. Add API tests.
11. Verify report/export consumers still read existing row fields.
12. Add short documentation to public API docs after behavior is confirmed.
