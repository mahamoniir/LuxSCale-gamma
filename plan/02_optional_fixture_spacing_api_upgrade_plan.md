# Optional Fixture Spacing API Upgrade Plan

## Goal

Add an optional API interface that lets a caller request separated center-to-center fixture spacing on X and Y. The solver should use these spacings as candidate layout constraints/options, then continue checking all other parameters: required lux, required uniformity, average lux cap, fixture count, IES metrics, compliance, density warnings, reports, and exports.

The default behavior must stay unchanged when the optional spacing payload is absent.

## Proposed request interface

Add one optional top-level object to `/calculate` and `/cad_calc`:

```json
{
  "sides": [8, 12, 8, 12],
  "height": 3.2,
  "standard_ref_no": "6.1.1",
  "fixture_spacing": {
    "mode": "include",
    "x_m": 2.4,
    "y_m": 2.0,
    "tolerance_m": 0.15,
    "edge": "half_spacing"
  }
}
```

### Field meanings

`fixture_spacing.mode`:

```text
include
```

Create the custom spacing-derived layout and evaluate it together with normal solver layouts. The result can win only if its lux/uniformity/compliance rank is better.

```text
prefer
```

Evaluate the custom layout first for each relevant fixture count, then continue normal layouts if it fails.

```text
only
```

Evaluate only layouts compatible with the requested spacing. This is strict and may return no compliant rows.

Recommended first implementation: support `include` and `only`; add `prefer` as a small ordering variant after tests pass.

`fixture_spacing.x_m`:

Center-to-center spacing between fixture columns along the engine `length` axis.

`fixture_spacing.y_m`:

Center-to-center spacing between fixture rows along the engine `width` axis.

`fixture_spacing.tolerance_m`:

Allowed difference between requested spacing and engine-derived spacing when matching factor pairs. Default: `0.05 m`.

`fixture_spacing.edge`:

Initial implementation should support only `half_spacing`, matching the current engine:

```text
edge_offset_x = spacing_x / 2
edge_offset_y = spacing_y / 2
```

Future extension can add explicit edge offsets.

## Response additions

Every result row already has:

```text
Spacing X (m)
Spacing Y (m)
Layout grid
layout_nx
layout_ny
Fixtures
```

Add these row fields when custom spacing influenced the row:

```json
{
  "Spacing source": "api_custom_spacing",
  "Requested spacing X (m)": 2.4,
  "Requested spacing Y (m)": 2.0,
  "Spacing X delta (m)": 0.0,
  "Spacing Y delta (m)": 0.0,
  "Spacing mode": "include"
}
```

Add these metadata fields:

```json
{
  "calculation_meta": {
    "custom_fixture_spacing": {
      "enabled": true,
      "mode": "include",
      "x_m": 2.4,
      "y_m": 2.0,
      "tolerance_m": 0.15,
      "edge": "half_spacing",
      "validated": true
    }
  }
}
```

For invalid spacing input, return HTTP 400 with a specific message.

## Creation order for the upgrade

### Step 1: Create a spacing request model/parser

Create a small parser in a focused module:

```text
luxscale/lighting_calc/spacing_request.py
```

Functions:

```python
parse_fixture_spacing_request(data: dict) -> CustomFixtureSpacing | None
spacing_request_to_meta(req: CustomFixtureSpacing | None) -> dict
```

Rules:

1. Missing `fixture_spacing` returns `None`.
2. `x_m` and `y_m` must be finite positive numbers.
3. Minimum spacing must respect the solver floor unless a later business rule says otherwise:
   - `x_m >= 0.8`
   - `y_m >= 0.8`
4. `mode` defaults to `include`.
5. Unknown `mode` returns a 400 from the API parser path.
6. `tolerance_m` defaults to `0.05`.
7. `edge` defaults to `half_spacing`.
8. Unknown `edge` returns a 400 in the first implementation.

Why a separate module:

1. Keeps `app.py` small.
2. Lets `/calculate`, `/cad_calc`, tests, and future chat flows share validation.
3. Avoids mixing API parsing with math logic.

### Step 2: Add layout generation helpers

Add helpers near existing spacing logic in `luxscale/lighting_calc/geometry.py` or in the new spacing module.

Recommended functions:

```python
layout_from_requested_spacing(length, width, sx, sy) -> tuple[int, int, float, float]
custom_spacing_factor_pairs(length, width, count, request) -> list[tuple[int, int]]
merge_factor_pairs(default_pairs, custom_pairs, mode) -> list[tuple[int, int]]
```

Core conversion:

```text
nx_float = length / requested_spacing_x
ny_float = width / requested_spacing_y
nx = max(1, round(nx_float))
ny = max(1, round(ny_float))
actual_spacing_x = length / nx
actual_spacing_y = width / ny
fixtures_from_spacing = nx * ny
```

Important design decision:

The current engine requires rectangular layouts where `layout_nx * layout_ny == Fixtures`. Therefore custom spacing should be converted into integer `nx` and `ny`, and the resulting fixture count should be `nx * ny`. Do not create a row where the displayed fixture count differs from the layout capacity.

### Step 3: Extend `calculate_lighting(...)` signature

Add a keyword-only parameter:

```python
def calculate_lighting(
    place,
    sides,
    height,
    standard_row=None,
    trace=None,
    fast=False,
    *,
    polygon=None,
    polygon_orientation_rad=0.0,
    polygon_fill_ratio=None,
    custom_fixture_spacing=None,
):
```

Backward compatibility:

1. Existing positional callers still work.
2. Existing keyword callers still work.
3. Default `None` uses the current exact-factorization behavior.

### Step 4: Thread spacing through `/calculate`

In `app.py::api_calculate`:

1. Parse `fixture_spacing` after height validation and before creating the trace.
2. Include parsed spacing in `trace.step("api_00_ready", ...)`.
3. Pass `custom_fixture_spacing=spacing_req` into `calculate_lighting(...)`.
4. Add `custom_fixture_spacing` metadata into the final `calculation_meta`.

### Step 5: Thread spacing through `/cad_calc`

In `app.py::api_cad_calc`:

1. Parse the same `fixture_spacing` object.
2. Pass it into `cad_calculate_lighting(...)`.
3. Extend `cad_calculate_lighting(...)` to pass it into `calculate_lighting(...)`.
4. Add equivalent-rectangle notes to clarify that X/Y spacing is applied in the engine/equivalent-rectangle frame, then transformed by the existing polygon drawing/export paths.

### Step 6: Insert custom spacing into the main fixture sweep

Current main loop:

```python
for num_fixtures in range(min_fixtures, max_fixtures + 1, fixture_step):
    factor_pairs = spacing_factor_pairs(length, width, num_fixtures, min_spacing_m)
```

Upgrade logic:

```text
1. Create default factor pairs exactly as today.
2. If custom spacing is absent, continue exactly as today.
3. If custom spacing is present:
   a. Convert requested sx/sy to nx/ny and actual fixture count.
   b. Ensure the layout is only evaluated at num_fixtures = nx * ny.
   c. Depending on mode:
      - include: default pairs plus custom pair when count matches.
      - prefer: custom pair first, then default pairs when count matches.
      - only: custom pair only; skip all other counts/pairs.
4. Keep all existing lux, over-lighting, IES, U0, and compliance checks.
```

Recommended implementation:

Before the fixture-count loop, compute:

```text
custom_nx
custom_ny
custom_count = custom_nx * custom_ny
actual_sx = length / custom_nx
actual_sy = width / custom_ny
```

Then adjust the counts:

```text
mode include/prefer:
  iterate normal min_fixtures..max_fixtures
  also include custom_count if it falls outside the normal range but remains under avg-lux cap

mode only:
  iterate [custom_count] only
```

This avoids trying to force requested spacing into unrelated fixture counts.

### Step 7: Insert custom spacing into fallback sweep

Current fallback sweep creates factor pairs per fixture count:

```python
pairs_fb = spacing_factor_pairs(length, width, num_fixtures, min_spacing_m)
```

Upgrade:

1. Add `custom_fixture_spacing=None` to `_uniformity_fallback_sweep_rows(...)`.
2. Pass it from `calculate_lighting(...)`.
3. Use the same merge logic as the main sweep.
4. For `mode=only`, evaluate only the custom count.
5. Keep fallback ranking unchanged.

### Step 8: Update row creation

When the custom pair is evaluated, annotate the row:

```text
Spacing source = api_custom_spacing
Requested spacing X (m)
Requested spacing Y (m)
Spacing X delta (m)
Spacing Y delta (m)
Spacing mode
```

When the row is default, optionally annotate:

```text
Spacing source = auto_factorized
```

For backward compatibility, this can be omitted on default rows.

### Step 9: Update uniformity text reports

`format_uniformity_report_txt(...)` already receives metrics containing the actual spacing. Add a short line to the uniformity header when custom spacing is active:

```text
Requested fixture spacing: x=2.4 m, y=2.0 m, mode=include, edge=half_spacing
```

No physics change is required inside report formatting if `layout_nx` and `layout_ny` are correct.

### Step 10: Update PDF/export consumers only if needed

Current export code reads:

```text
Fixtures
Spacing X (m)
Spacing Y (m)
layout_nx
layout_ny
```

Because the upgrade preserves those fields, report and layout rendering should continue working. Verify:

1. `generate_report.py::_fixtures_world_coords(...)`
2. `result.html` layout and selected option display.
3. CSV export headers.
4. Any DXF/STL path that uses `layout_nx`, `layout_ny`, or spacing fields.

Only add display text for requested spacing if product wants it visible.

## Math details for custom spacing conversion

Requested:

```text
Sx_req = fixture_spacing.x_m
Sy_req = fixture_spacing.y_m
```

Room:

```text
L = engine length
W = engine width
```

Convert to grid:

```text
nx = max(1, round(L / Sx_req))
ny = max(1, round(W / Sy_req))
N = nx * ny
```

Actual spacing used by the engine:

```text
Sx_actual = L / nx
Sy_actual = W / ny
```

Spacing error:

```text
dx = abs(Sx_actual - Sx_req)
dy = abs(Sy_actual - Sy_req)
```

Valid custom layout:

```text
Sx_actual >= 0.8
Sy_actual >= 0.8
dx <= tolerance_m
dy <= tolerance_m
```

If tolerance fails, the API should either:

1. Return 400 with suggested nearest values, for `mode=only`.
2. Keep normal solver results and include metadata warning, for `mode=include`.

Recommended first behavior: fail fast with HTTP 400 for invalid requested spacing. It is simpler and prevents silent mismatch.

## Optional alternate interface for multiple spacing options

After the single-spacing version is stable, allow:

```json
{
  "fixture_spacing_options": [
    {"x_m": 2.4, "y_m": 2.0, "mode": "include"},
    {"x_m": 2.0, "y_m": 2.0, "mode": "include"}
  ]
}
```

Do not implement this first unless needed by UI. The single object covers the requested upgrade and keeps ranking understandable.

## Tests to create

### Unit tests

Create:

```text
tests/lighting_calc/test_custom_fixture_spacing.py
```

Cases:

1. Missing spacing returns `None`.
2. Valid spacing parses to a structured request.
3. Negative, zero, non-numeric, and unknown mode fail.
4. Requested spacing converts to expected `nx`, `ny`, and actual spacing.
5. `mode=only` returns only the custom layout count.
6. `mode=include` preserves normal factor pairs and adds custom count.

### Engine tests

Add or extend calculate tests:

1. Same request without `fixture_spacing` returns unchanged fields.
2. Request with `fixture_spacing={"x_m": 2, "y_m": 2, "mode": "only"}` returns rows whose `Spacing X/Y` match actual converted spacing.
3. `layout_nx * layout_ny == Fixtures`.
4. `U0_calculated` is computed using the same layout grid shown in the row.
5. Invalid spacing returns a clear API 400.

### API tests

Use Flask test client:

1. `/calculate` accepts valid spacing.
2. `/calculate` rejects invalid spacing.
3. `/cad_calc` accepts valid spacing.
4. Response metadata includes `calculation_meta.custom_fixture_spacing`.

## Implementation risk notes

1. The current reflectance override mutates app settings during a request. Do not use that pattern for custom spacing.
2. Custom spacing must be request-scoped and passed as a normal function argument.
3. Do not let `Fixtures` differ from `layout_nx * layout_ny` for rectangular rows.
4. Do not let custom spacing bypass lux, U0, average-lux cap, height validation, or standards target resolution.
5. For polygon mode, custom spacing is applied in the equivalent-rectangle frame. The polygon clipping step may place fewer effective centers if geometry is tight; keep existing `n_fixtures_requested` vs `n_fixtures_layout` metadata.
6. If requested spacing creates too many fixtures, the average lux cap may reject it. That is correct unless product explicitly wants an over-lit warning row.

## Recommended first PR scope

1. Parser and data model.
2. Main `/calculate` support.
3. Main engine support in the normal sweep.
4. Fallback sweep support.
5. Metadata and row annotations.
6. Focused tests.

Defer:

1. Multiple spacing options.
2. Explicit edge offsets.
3. Frontend controls.
4. PDF design changes.
5. Custom spacing for chat-generated studies.

## Acceptance checklist

1. Old `/calculate` payloads return successfully.
2. Old `/cad_calc` payloads return successfully.
3. New `/calculate` payload with `fixture_spacing` returns actual spacing in result rows.
4. New `/cad_calc` payload with `fixture_spacing` returns actual spacing in result rows.
5. Invalid spacing returns HTTP 400 with a useful error.
6. Every result row still includes `Fixtures`, `Spacing X (m)`, `Spacing Y (m)`, `layout_nx`, and `layout_ny`.
7. For rectangular rows, `layout_nx * layout_ny == Fixtures`.
8. U0 and lux compliance are still checked after applying spacing.
9. Uniformity reports show the actual spacing used.
10. Tests cover default behavior and custom spacing behavior.
