# Mathematical Foundation - GemDocs

The accuracy of LuxScaleAI's results is rooted in its mathematical model for light distribution.

## 📐 Core Equations

### 🔲 Cyclic Quadrilateral Area (Brahmagupta's Formula)
To compute the area of a room with four sides (a, b, c, d):
`s = (a + b + c + d) / 2` (Semi-perimeter)
`Area = sqrt((s - a) * (s - b) * (s - c) * (s - d))`

*Note: For a perfect rectangle where a=c and b=d, this reduces to Area = a * b.*

### 💡 Lumen Method Formula
`E_avg = (N * Φ * MF) / Area`
- `E_avg`: Average Illuminance (Lux)
- `N`: Total number of fixtures
- `Φ`: Initial lumens per fixture (Luminous Flux)
- `MF`: Maintenance Factor (default 0.8)

### 🔳 Inverse Square Law (Point Source)
For point-by-point uniformity (U₀) calculation:
`E_p = (I_θ * cos(α)) / d²`
- `E_p`: Illuminance at a specific point `P`
- `I_θ`: Intensity from the IES file at angle `θ`
- `α`: Angle of incidence on the workplane
- `d`: Direct distance from the fixture to the point `P`

## ⚙️ Optimization Algorithms

### 🔳 Spacing Layout Search
The engine uses a factors-based grid search:
1.  For a given `N`, find all factor pairs `(x, y)` such that `x * y ≈ N`.
2.  Calculate `Spacing_X = Length / x` and `Spacing_Y = Width / y`.
3.  Compute the "Aspect Score": `Score = |Spacing_X - Spacing_Y|`.
4.  Select the `(x, y)` pair with the lowest Score to ensure a balanced grid.

### 📊 Uniformity Calculation (U₀)
`U₀ = E_min / E_avg`
- `E_min`: The lowest illuminance value recorded in the 20x20 grid.
- `E_avg`: The calculated average lux (including reflections).

---
*See [AI Pipeline](../ai/README.md) for how these metrics are scored and analyzed.*
