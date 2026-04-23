# Photometric Verification with IES Files

The "Lumen Method" provides a fast estimate, but IES files provide the **truth**.

## 📄 What is an IES File?
An IES (.ies) file is a standard photometric data format (LM-63) that describes the 3D distribution of light from a luminaire.

## 📊 Photometric Processing Steps

1.  **Parsing**: The `ies-render` module extracts the **Candela Multiplier** and the **Luminous Intensity** values at various vertical and horizontal angles.
2.  **Point-by-Point Grid**: The room is divided into a grid (e.g., 20x20).
3.  **Inverse Square Law Application**:
    `E = (I * cos(θ)) / d²`
    Where `I` is the intensity at angle `θ` toward the point, and `d` is the distance.
4.  **Inter-reflection (The "Gemini" Enhancement)**:
    Since simple IES analysis only accounts for direct light, LuxScaleAI adds a reflective component based on room surface reflectance (Ceiling/Wall/Floor) to provide a more realistic "Average Lux" and "U₀".

## 🖼️ Thumbnail Generation
The `ies-render` module can also generate a 2D "render" of the light pattern against a wall, which is used in the UI to help designers visualize the beam spread.

---
*See [IES Catalog](./ies-catalog.md) for how files are mapped to real luminaires.*
