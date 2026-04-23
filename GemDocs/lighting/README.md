# Lighting Engineering - GemDocs

LuxScaleAI is built on established lighting engineering principles to provide professional-grade results.

## 🌟 Fundamental Concepts

### 💡 Lux (Illuminance)
The measure of luminous flux per unit area (lumens/m²). LuxScaleAI targets the **Maintained Illuminance (Em)**, which accounts for the gradual reduction of light output over time.

### 🔳 Uniformity (U₀)
The ratio of minimum illuminance to average illuminance across the workplane. High uniformity ensures consistent visibility and comfort. LuxScaleAI aims for **U₀ ≥ 0.40** (Standard) or **U₀ ≥ 0.60** (High Precision), depending on the task.

### 🏗️ Maintenance Factor (MF)
A multiplier (default 0.8) applied to account for lamp aging and dirt accumulation.
`Actual Lux = Initial Lux * MF`

## 📏 EN 12464-1 Compliance

LuxScaleAI uses the `standards/standards_cleaned.json` database to ensure compliance with the **EN 12464-1 European Standard** for indoor workplace lighting.

### 📋 Key Standard Parameters:
- **`Em_r_lx`**: Required maintained illuminance.
- **`Uo`**: Required uniformity.
- **`Ra`**: Minimum Color Rendering Index (CRI).
- **`UGRL`**: Unified Glare Rating limit.

## 🔲 Spacing Heuristics

To ensure a balanced distribution of light, the engine uses the **Spacing Criterion (SC)**:
- **SC ≤ 1.2**: Typical for downlights, requires closer spacing.
- **SC ≥ 1.5**: Typical for wide-beam fixtures, allows wider spacing.

LuxScaleAI's optimizer searches for an (X, Y) grid that respects these SC limits while minimizing total fixture count.

---
*See [Photometric Calculation](./photometric-calculation.md) for how IES files are used to verify these metrics.*
