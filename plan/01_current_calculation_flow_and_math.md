# LuxScaleAI Current Calculation Flow And Math

## Purpose

This file documents the current working flow before adding any optional fixture spacing input. It is the baseline that the upgrade must preserve when the API request does not provide separated fixture spacings for X and Y.

## Current created-before-created order

1. The browser or API client creates a JSON request.
2. `app.py` validates the request body, room geometry, height, and lighting target.
3. `app.py` resolves a standards row from `standards/standards_cleaned.json` or falls back to a legacy `place` entry from `luxscale/lighting_calc/constants.py`.
4. `app.py` creates a `CalculationTrace` for observability.
5. `app.py` calls `luxscale/lighting_calc/calculate.py::calculate_lighting(...)`.
6. `calculate_lighting(...)` creates room geometry values: equivalent rectangular length, width, cyclic quadrilateral area, and interior/exterior zone.
7. `calculate_lighting(...)` creates the calculation targets: required maintained illuminance and required uniformity.
8. `calculate_lighting(...)` creates the candidate luminaire family list from the active fixture catalog.
9. `calculate_lighting(...)` creates the work-plane uniformity grid size.
10. `calculate_lighting(...)` creates candidate options by looping over luminaire family, power, efficacy, fixture count, and layout grid.
11. For each candidate layout, `calculate_lighting(...)` creates a result row with fixture count, spacing, average lux, power, beam angle, layout grid, and IES metadata.
12. When an IES file exists, `luxscale/uniformity_calculator.py::compute_uniformity_metrics(...)` creates point-by-point illuminance metrics for that row.
13. `calculate_lighting(...)` creates compliance fields: lux gap, U0 gap, compliance flag, standard margins, and selection reason.
14. If compliant rows exist, the first accepted rows are returned up to the configured solution cap.
15. If no compliant rows exist, closest non-compliant candidates are created and optionally passed into `_uniformity_fallback_sweep_rows(...)`.
16. Uniformity text report chunks are created after result rows are known.
17. `app.py` creates the final JSON response with results, length, width, calculation metadata, UI settings, trace path, and standard row when used.
18. Result pages, CSV export, browser PDF export, and server PDF export consume the returned rows.

## HTTP flow: rectangular `/calculate`

1. `POST /calculate` receives JSON.
2. Required fields:
   - `sides`: four numeric side lengths.
   - `height`: ceiling or mounting height in meters.
3. Target fields:
   - Preferred: `standard_ref_no` or `project_info.standard_ref_no`.
   - Legacy: `place`.
4. Optional fields already supported:
   - `fast`: reduces option count and fixture-count sweep detail.
   - `material_physics`: optional reflectance/IRF payload.
   - `ceiling_hex`, `walls_hex`, `floor_hex`: legacy surface-color path.
5. `_resolve_calculate_inputs(data)` loads the standards row when a valid reference exists.
6. `validate_ceiling_height_m(height)` rejects invalid height before the engine runs.
7. `_want_fast_calculate(data)` chooses full or fast mode.
8. `calculate_lighting(...)` returns:
   - `results`
   - `length`
   - `width`
   - `calculation_meta`
9. `app.py` wraps these into the JSON response.

## HTTP flow: polygon `/cad_calc`

1. `POST /cad_calc` receives polygon vertices and normal calculation fields.
2. `polygon_from_payload(data)` creates a validated `Polygon`.
3. `cad_calculate_lighting(...)` creates an equivalent-area rectangle.
4. The rectangle is passed into `calculate_lighting(...)` through `sides = [width_eq, length_eq, width_eq, length_eq]`.
5. `calculate_lighting(...)` uses the same rectangular solver but receives the original polygon as optional metadata.
6. `compute_uniformity_metrics(...)` clips fixture centers and sample points to the polygon when polygon data is present.
7. The response returns normal result rows plus polygon metadata in `calculation_meta`.

## Function flow

```text
app.py::api_calculate
  -> request.get_json()
  -> validate required sides and height
  -> validate_ceiling_height_m(height)
  -> _resolve_calculate_inputs(data)
  -> _extract_irf_from_request(data)
  -> _want_fast_calculate(data)
  -> CalculationTrace("POST /calculate")
  -> calculate_lighting(...)
       -> cyclic_quadrilateral_area(a, b, c, d)
       -> determine_zone(height)
       -> determine_luminaire(height)
       -> uniformity_grid_n_for_room(length, width)
       -> get_maintenance_factor()
       -> get_inter_reflection_fraction()
       -> luminaire family loop
       -> power loop
       -> efficacy loop
       -> fixture-count loop
       -> spacing_factor_pairs(length, width, num_fixtures, 0.8)
       -> candidate layout loop over (best_x, best_y)
       -> compute lumen-method average lux
       -> resolve IES path
       -> compute_uniformity_metrics(...)
       -> _row_with_compliance_metrics(...)
       -> accept compliant row or track closest row
       -> _uniformity_fallback_sweep_rows(...) when needed
       -> _sync_uniformity_report_chunks(...)
       -> return results, length, width, meta
  -> trace.save()
  -> jsonify(response)
```

## Geometry creation

Current rectangular inputs use four sides:

```text
a, b, c, d = sides
length = max(a, c)
width = max(b, d)
area = cyclic_quadrilateral_area(a, b, c, d)
```

The cyclic quadrilateral area uses Brahmagupta's formula:

```text
s = (a + b + c + d) / 2
area = sqrt((s - a) * (s - b) * (s - c) * (s - d))
```

For a rectangle represented as `[width, length, width, length]`, this becomes `width * length`.

## Target creation

When a standards row exists:

```text
required_lux = standard_row["Em_r_lx"]
required_uniformity = standard_row["Uo"] or 0.6
```

When a legacy place is used:

```text
required_lux = define_places[place]["lux"]
required_uniformity = define_places[place]["uniformity"]
```

## Fixture-count math

For each luminaire power and efficacy:

```text
lumens_per_fixture = power_w * efficacy_lm_per_w
total_lumens_needed = (required_lux * area) / maintenance_factor
min_fixtures = int(total_lumens_needed / lumens_per_fixture) + 1
```

The engine then searches from `min_fixtures` upward:

```text
max_fixtures = min_fixtures + search_span
fixture_step = 1 in full mode
fixture_step = 2 in fast mode
```

Average maintained lux is:

```text
avg_lux = (num_fixtures * lumens_per_fixture * maintenance_factor) / area
```

The current main sweep rejects severe over-lighting:

```text
avg_lux <= required_lux * 1.35
```

The fallback sweep uses a relaxed cap:

```text
avg_lux <= required_lux * 1.65
```

## Current spacing math

The current solver does not accept explicit X/Y spacing from the request. It derives spacing from exact factorization of fixture count.

For a candidate `num_fixtures`, `spacing_factor_pairs(length, width, num_fixtures, min_spacing_m)` returns all exact integer pairs:

```text
best_x * best_y == num_fixtures
spacing_x = length / best_x
spacing_y = width / best_y
min(spacing_x, spacing_y) >= 0.8
```

Pairs are sorted by:

```text
abs(spacing_x - spacing_y), best_x, best_y
```

The row exposes:

```text
"Spacing X (m)" = round(length / best_x, 2)
"Spacing Y (m)" = round(width / best_y, 2)
"Layout grid" = f"{best_x}x{best_y}"
"layout_nx" = best_x
"layout_ny" = best_y
```

## Uniformity math flow

`compute_uniformity_metrics(...)` receives:

```text
ies_path
length
width
height
num_fixtures
lumens_per_fixture
best_x
best_y
grid_n
maintenance calibrated average lux
inter-reflection fraction
polygon metadata when present
```

It creates fixture centers using:

```text
x_i = (i + 0.5) * length / best_x
y_j = (j + 0.5) * width / best_y
```

Therefore:

```text
fixture_spacing_x = length / best_x
fixture_spacing_y = width / best_y
edge_offset_x = fixture_spacing_x / 2
edge_offset_y = fixture_spacing_y / 2
```

For each work-plane sample point, it sums illuminance from every fixture:

```text
E_point = sum(I_angle * cos(theta) / r^2)
```

The direct IES grid is calibrated to the lumen-method maintained average lux when calibration is supplied:

```text
scale = avg_lux_lumen_method / E_avg_raw_ies
E_grid = E_grid_raw * scale
```

Then optional inter-reflection is applied:

```text
E_grid = E_grid * (1 + inter_reflection_fraction)
```

Uniformity metrics are:

```text
E_min = min(E_grid)
E_avg = average(E_grid)
E_max = max(E_grid)
U0 = E_min / E_avg
U1 = E_min / E_max
```

## Compliance flow

Each row is checked against the target:

```text
lux_gap = max(0, required_lux - compliance_average_lux)
u0_gap = max(0, required_uniformity - U0_calculated)
is_compliant = lux_gap == 0 and u0_gap == 0
```

Rows are selected as:

```text
least_fixture_count_compliant
closest_non_compliant_candidate
uniformity_fixture_sweep_fallback
best_effort_non_compliant
```

## Baseline behavior to preserve

The upgrade must not change these behaviors when the request does not include custom fixture spacing:

1. Exact factorization remains the default layout method.
2. `Spacing X (m)` and `Spacing Y (m)` remain center-to-center distances.
3. `layout_nx * layout_ny == Fixtures` for rectangular layouts.
4. The lumen-method average uses the actual fixture count, not virtual grid capacity.
5. IES uniformity uses the same `layout_nx` and `layout_ny` values shown in the result row.
6. Polygon mode continues clipping fixture centers and work-plane sample points.
7. Fast mode remains coarse but backward compatible.
8. Existing clients can keep sending the old JSON shape.
