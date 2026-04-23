# `luxscale` package map

Repository root is the parent of this folder (`luxscale.paths.project_root()`). Data dirs (`ies-render/`, `standards/`, `uniformity_reports/`) and `luxscale_app.log` stay at repo root.

## Layout

```
luxscale/
  __init__.py           # package marker
  paths.py              # project_root()
  app_logging.py        # log_step / log_exception → luxscale_app.log at repo root
  ies_fixture_params.py # SC-Database .ies paths + candela/lumen metadata
  uniformity_calculator.py  # grid U0/U1; writes uniformity_reports/*.txt
  map.md                # this file
  lighting_calc/        # lumen-method engine + optional Tk GUI
    __init__.py         # public API + lazy run_gui()
    constants.py        # presets, efficacy, maintenance factor
    geometry.py         # area, zone, spacing
    calculate.py        # calculate_lighting (+ IES + uniformity hooks)
    plotting.py         # heatmap / distribution PNGs
    export_io.py        # CSV/PDF + JSON user data
    gui.py              # Tk desktop UI
    ai_lux.py           # optional OpenAI helper
    state.py            # GUI session globals
```

## How pieces connect

| Module | Role |
|--------|------|
| `paths` | Single source for repo root; all file paths that must live beside `app.py`/`standards/` use this. |
| `app_logging` | Structured step logging to console and `luxscale_app.log`. |
| `ies_fixture_params` | Resolves catalog IES paths under `ies-render/SC-Database` and parses photometry (beam, lumens). |
| `uniformity_calculator` | Point-by-point illuminance on a work plane from Type C candela; used for reported U0/U1. |
| `lighting_calc.calculate` | Orchestrates targets, fixture options, spacing, and calls IES + uniformity when a file exists. |
| `lighting_calc` (package) | Same public surface as before: `calculate_lighting`, `draw_heatmap`, `define_places`, exports, `run_gui`. |

## Import examples

Run Flask or scripts with the repo root on `PYTHONPATH` (or `cd` to the repo first).

```python
from luxscale.paths import project_root
from luxscale.app_logging import log_step, LOG_FILE
from luxscale.lighting_calc import calculate_lighting, draw_heatmap, define_places
from luxscale.lighting_calc import run_gui  # Tk; import only when needed
```

Internal to `lighting_calc` submodules, use relative imports (e.g. `from .constants import …`).
