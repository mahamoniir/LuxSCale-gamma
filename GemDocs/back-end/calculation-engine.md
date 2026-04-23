# Lighting Calculation Engine

The LuxScaleAI engine uses the **Lumen Method** enhanced with real-world photometric data.

## 📐 Geometry Model

The engine handles non-rectangular rooms by approximating them as cyclic quadrilaterals.
- **Formula**: `s = (a+b+c+d)/2`; `Area = sqrt((s-a)(s-b)(s-c)(s-d))`
- **Refinement**: For true rectangles, this simplifies to standard `L * W`.

## 💡 Lumen Method Implementation

The fundamental equation used is:
`Average Lux (E) = (N * Φ * CU * LLF) / Area`

Where:
- `N`: Number of fixtures.
- `Φ`: Initial lumens per fixture (Power * Efficacy).
- `CU`: Coefficient of Utilization (derived from room cavity ratio and reflectance).
- `LLF`: Light Loss Factor (Maintenance Factor, default 0.8).

## 🔳 Spacing & Layout Heuristics

The engine doesn't just return a count; it calculates a physical grid.
- **Search Space**: Factors of the total count `N` are tested (e.g., 12 fixtures could be 3x4 or 2x6).
- **Optimization Target**: Minimize the difference between `Spacing_X` and `Spacing_Y` to ensure a balanced layout.
- **Constraints**: Spacing must not exceed the Luminaire Spacing Criterion (S/MH).

## 📉 Photometric Uniformity (U₀)

While the Lumen Method provides average lux, LuxScaleAI uses IES files for point-by-point analysis:
1.  **Grid Generation**: A 10x10 to 20x20 grid of points is generated on the workplane.
2.  **Inverse Square Law**: For every point, the illuminance contribution from every fixture is summed.
3.  **Uniformity**: `U₀ = Minimum Lux / Average Lux`.

This dual-layer approach (Heuristic + Photometric) ensures both speed and accuracy.
