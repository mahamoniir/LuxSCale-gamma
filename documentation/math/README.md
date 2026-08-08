# LuxScaleAI — Mathematical documentation

This folder collects **equations**, **inequalities used for compliance**, **relations between result fields**, **step-by-step calculation and export flows**, and **IES (LM-63) extraction** in one place. Implementation lives under `luxscale/`; conceptual overlap with [../lighting/](../lighting/README.md) is intentional — **math** here emphasizes **symbols, bounds, and logical order**.

| # | Document | Contents |
|---|----------|----------|
| 1 | [01-units-and-symbols.md](./01-units-and-symbols.md) | Quantities, units, subscripts |
| 2 | [02-core-equations-lumen-grid-uniformity.md](./02-core-equations-lumen-grid-uniformity.md) | Area, lumen method, inverse-square lux, \(U_0\), \(U_1\) |
| 3 | [03-compliance-inequalities-and-row-properties.md](./03-compliance-inequalities-and-row-properties.md) | Targets, Lux gap, U₀ gap, `is_compliant`, margins |
| 4 | [04-pipeline-from-request-to-results-and-export.md](./04-pipeline-from-request-to-results-and-export.md) | API / solver steps, JSON, PDF, CSV, traces, reports |
| 5 | [05-ies-lm63-fields-beam-angle-and-flux.md](./05-ies-lm63-fields-beam-angle-and-flux.md) | Parser header, candela table, beam angle algorithm, tool outputs |
| 6 | [06-non-4-side-rooms-calculation.md](./06-non-4-side-rooms-calculation.md) | Polygon ingest, shoelace area, equivalent-area rectangle, lumen method + U₀ for N-sided rooms (`/cad_calc`) |
| 6a | [06a-non-4-side-rooms-review-addendum.md](./06a-non-4-side-rooms-review-addendum.md) | Review response — fast-mode trigger, L/W axis convention, rotated-room bbox fix (edge-orientation histogram), self-intersection O(N²) ceiling, Phase-A U₀ optimism quantified |

**Related:** [../lighting/](../lighting/README.md), [../back-end/calculation-engine.md](../back-end/calculation-engine.md), [`../../development_plan/06-non-symmetric-rooms-migration-plan.md`](../../development_plan/06-non-symmetric-rooms-migration-plan.md).
