"""
Surface reflectance (ρ) from HEX color codes and room inter-reflection estimation.

Equations source: LuxScaleAI_Equations.md §5
  Step A — Normalize RGB          : C_norm = C_hex / 255
  Step B — Gamma linearize (sRGB) : C_linear = C_norm ^ 2.2
  Step C — BT.709 luminance       : ρ = 0.2126 R + 0.7152 G + 0.0722 B

Usage:
    from luxscale.reflectance import hex_to_reflectance, room_indirect_fraction

    rho   = hex_to_reflectance('#D6C8B0')          # → e.g. 0.591
    irf   = room_indirect_fraction(0.85, 0.59, 0.18)  # → e.g. 0.163
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Core equation — HEX → luminous reflectance ρ
# ---------------------------------------------------------------------------

def hex_to_reflectance(hex_color: str) -> float:
    """
    Convert a HEX color string to CIE luminous reflectance ρ ∈ [0.0, 1.0].

    Accepts '#RRGGBB', 'RRGGBB', '#RGB', or 'RGB' formats.

    Steps (LuxScaleAI_Equations.md §5):
        A  Normalize:   C_norm   = C_hex / 255
        B  Linearize:   C_linear = C_norm ^ 2.2          (simplified sRGB gamma)
        C  Luminance:   ρ = 0.2126 R_lin + 0.7152 G_lin + 0.0722 B_lin  (ITU-R BT.709)

    Examples:
        '#ffffff' → 1.000   (perfect white)
        '#000000' → 0.000   (perfect black)
        '#808080' → 0.216   (mid grey)
        '#cccccc' → 0.600   (light grey — SC brand SCGrey)
    """
    h = hex_color.strip().lstrip('#')

    # Expand 3-digit shorthand  →  6 digits
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)

    if len(h) != 6:
        raise ValueError(
            f"Invalid HEX color {hex_color!r}. "
            "Expected '#RRGGBB', 'RRGGBB', '#RGB', or 'RGB'."
        )

    try:
        r_hex = int(h[0:2], 16)
        g_hex = int(h[2:4], 16)
        b_hex = int(h[4:6], 16)
    except ValueError:
        raise ValueError(f"Invalid HEX digits in color {hex_color!r}.")

    # Step A — Normalize
    r_norm = r_hex / 255.0
    g_norm = g_hex / 255.0
    b_norm = b_hex / 255.0

    # Step B — Gamma linearize  (sRGB simplified γ = 2.2)
    r_lin = r_norm ** 2.2
    g_lin = g_norm ** 2.2
    b_lin = b_norm ** 2.2

    # Step C — ITU-R BT.709 luminous reflectance
    rho = 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    return float(max(0.0, min(1.0, rho)))


# ---------------------------------------------------------------------------
# Weighted room inter-reflection fraction from three surface reflectances
# ---------------------------------------------------------------------------

def room_indirect_fraction(
    rho_ceiling: float,
    rho_walls: float,
    rho_floor: float,
    ceiling_weight: float = 0.40,
    wall_weight: float = 0.45,
    floor_weight: float = 0.15,
    irf_scale: float = 0.232,
) -> float:
    """
    Estimate the inter-reflection fraction (IRF) from three surface reflectances.

    IRF is the multiplier added to the direct illuminance grid in
    ``uniformity_calculator.compute_uniformity_metrics()`` as:
        E_final = E_direct * (1 + IRF)

    Method:
        1. Compute weighted average reflectance across ceiling, walls, floor.
        2. Scale to the IRF range: ρ_avg × irf_scale → IRF.

    Default weights (ceiling 0.40, walls 0.45, floor 0.15) reflect the
    proportion of each surface's contribution to horizontal work-plane
    inter-reflection for typical downlit interiors.

    irf_scale = 0.232 is least-squares calibrated to match the three existing
    app_settings presets (dark / medium / light):
        ρ_avg = 0.00  →  IRF = 0.000  (all-black room, no reflection)
        ρ_avg = 0.365 →  IRF ≈ 0.085  (dark preset: ρ ≈ 0.5/0.3/0.2)
        ρ_avg = 0.535 →  IRF ≈ 0.124  (medium preset: ρ ≈ 0.7/0.5/0.2)
        ρ_avg = 0.680 →  IRF ≈ 0.158  (light preset: ρ ≈ 0.8/0.7/0.3)
        ρ_avg = 1.00  →  IRF = 0.232  (theoretical perfect white room)

    Returns: IRF clamped to [0.0, 0.40].
    """
    rho_ceiling = float(max(0.0, min(1.0, rho_ceiling)))
    rho_walls   = float(max(0.0, min(1.0, rho_walls)))
    rho_floor   = float(max(0.0, min(1.0, rho_floor)))

    rho_avg = (
        ceiling_weight * rho_ceiling +
        wall_weight    * rho_walls   +
        floor_weight   * rho_floor
    )

    irf = rho_avg * irf_scale
    return float(max(0.0, min(0.40, irf)))


# ---------------------------------------------------------------------------
# Convenience: parse three HEX strings directly to IRF + label
# ---------------------------------------------------------------------------

def reflectance_from_hex_surfaces(
    ceiling_hex: str,
    walls_hex: str,
    floor_hex: str,
) -> dict:
    """
    Parse three HEX color strings and return a dict with ρ per surface,
    weighted IRF, and a human-readable label.

    Returns:
        {
            'rho_ceiling': float,
            'rho_walls':   float,
            'rho_floor':   float,
            'irf':         float,
            'label':       str,
        }

    Raises ValueError if any HEX string is invalid.
    """
    rho_c = hex_to_reflectance(ceiling_hex)
    rho_w = hex_to_reflectance(walls_hex)
    rho_f = hex_to_reflectance(floor_hex)
    irf   = room_indirect_fraction(rho_c, rho_w, rho_f)

    label = (
        f"Custom HEX "
        f"(\u03c1 ceiling={rho_c:.2f} / walls={rho_w:.2f} / floor={rho_f:.2f})"
    )

    return {
        'rho_ceiling': round(rho_c, 4),
        'rho_walls':   round(rho_w, 4),
        'rho_floor':   round(rho_f, 4),
        'irf':         round(irf,   4),
        'label':       label,
    }
