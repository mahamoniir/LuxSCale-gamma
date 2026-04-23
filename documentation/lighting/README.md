# LuxScaleAI — Lighting science & tool behavior

This folder documents **how lighting is modeled, calculated, and compared to standards** in LuxScaleAI: equations, parameter meanings, IES usage, compliance logic, and what is **not** simulated.

**Audience:** Engineers and developers maintaining `luxscale/lighting_calc`, `luxscale/uniformity_calculator.py`, and IES assets.

| # | Document | Contents |
|---|----------|----------|
| 1 | [01-overview-tool-scope.md](./01-overview-tool-scope.md) | What the tool solves; standards count; code references |
| 2 | [02-input-parameters-room-and-height.md](./02-input-parameters-room-and-height.md) | Sides, area, length/width, ceiling height, interior vs exterior |
| 3 | [03-lumen-method-maintenance-efficacy.md](./03-lumen-method-maintenance-efficacy.md) | Average illuminance formula, MF, rated vs IES lumens |
| 4 | [04-spacing-layout-and-fixture-count.md](./04-spacing-layout-and-fixture-count.md) | Grid factorization, centre-to-centre spacing, min spacing cap |
| 5 | [05-ies-photometry-and-inverse-square.md](./05-ies-photometry-and-inverse-square.md) | LM-63 candela, flux scaling, illuminance equation |
| 6 | [06-uniformity-u0-u1-grid.md](./06-uniformity-u0-u1-grid.md) | Work plane grid, E_min/E_avg/E_max, U₀, U₁ |
| 7 | [07-compliance-vs-standards.md](./07-compliance-vs-standards.md) | Lux gap, U₀ gap, over-lighting cap, fallback |
| 8 | [08-standards-data-fields.md](./08-standards-data-fields.md) | Each JSON field; which drive the solver |
| 9 | [09-beam-angle-and-ies-metadata.md](./09-beam-angle-and-ies-metadata.md) | Half-power beam from candela; effect on result rows |
| 10 | [10-solver-option-picking-fast-fallback.md](./10-solver-option-picking-fast-fallback.md) | Search order, fast mode, uniformity fallback sweep |
| 11 | [11-concepts-not-full-engine.md](./11-concepts-not-full-engine.md) | UGR, wall lux, limits of the model |
| 12 | [12-supporting-modules-catalog-and-settings.md](./12-supporting-modules-catalog-and-settings.md) | `paths`, `app_settings`, IES resolution, JSON blobs vs parse, `plotting` heatmap caveat |

**Related code:** `luxscale/lighting_calc/calculate.py`, `luxscale/lighting_calc/geometry.py`, `luxscale/lighting_calc/constants.py`, `luxscale/uniformity_calculator.py`, `luxscale/ies_fixture_params.py`.

**Related docs:** [../math/](../math/README.md); [../ai/](../ai/README.md) (AI quality scoring on lighting results) (compact formulas, compliance inequalities, pipeline, IES math); [../back-end/](../back-end/README.md); [uniformity/](../../uniformity/) (older design notes — prefer this folder and `luxscale/uniformity_calculator.py` for current behavior).
