"""Room area, zone, luminaire choice, and spacing helpers."""

import numpy as np

from luxscale.fixture_ies_catalog import catalog_luminaire_power_options


def _interior_height_threshold_m() -> float:
    try:
        from luxscale.app_settings import get_interior_height_max_m

        return float(get_interior_height_max_m())
    except Exception:
        return 5.0


def cyclic_quadrilateral_area(a, b, c, d):
    s = (a + b + c + d) / 2
    return np.sqrt((s - a) * (s - b) * (s - c) * (s - d))


def determine_zone(height):
    """LED efficacy zone: uses settings ``interior_height_max_m`` (same as luminaire split)."""
    th = _interior_height_threshold_m()
    return "interior" if height < th else "exterior"


def determine_luminaire(height):
    """
    Luminaire options come from the merged IES catalog (active ``ies_dataset_config`` examples folder).

    Below ``interior_height_max_m`` (admin settings): only **indoor** families (downlight, triproof,
    backlight). Street/flood/high-bay are **not** offered for low ceilings so small offices do not
    get exterior road or flood products.

    At or above the threshold: high-bay, flood, street, and related outdoor / tall-space types.
    """
    cat = catalog_luminaire_power_options()
    th = _interior_height_threshold_m()
    if height < th:
        names = [
            "SC downlight",
            "SC triproof",
            "SC backlight",
        ]
    else:
        names = [
            "SC highbay",
            "SC flood light exterior",
            "SV flood",
            "SC street",
        ]
    out = []
    for n in names:
        if n in cat and cat[n]:
            out.append((n, cat[n]))
    return out


def get_spacing_constraints(zone):
    return (2, 4, 4, 4) if zone == "interior" else (4, 6, 7, 12)


def calculate_spacing(length, width, count, margin=None):
    """
    Integer grid with **exactly** ``best_x * best_y == count``, minimizing
    ``|spacing_x - spacing_y|``.

    **Why exact:** The old rule ``x*y >= count`` often picked the **same** large grid (e.g.
    5×4=20) for 16, 18, and 20 fixtures. Total flux was spread across 20 virtual positions
    with ``phi_each = (count * lm) / 20``, so **every** work-plane illuminance scaled
    proportionally with ``count`` — **U₀ = E_min/E_avg stayed unchanged** when adding
    fixtures, which is wrong for lighting design.

    **Symmetric layout:** centres are evenly spaced across the **full** length and width.
    Centre-to-centre spacing is ``length/best_x`` and ``width/best_y``; wall inset is half
    of that spacing on each axis.

    ``margin`` is accepted for backward compatibility and **ignored**.
    """
    if count < 1:
        count = 1
    best_x, best_y = 1, count
    min_diff = float("inf")
    L = float(length)
    W = float(width)
    for x in range(1, count + 1):
        if count % x != 0:
            continue
        y = count // x
        spacing_x = L / x
        spacing_y = W / y
        diff = abs(spacing_x - spacing_y)
        if spacing_x > 0 and spacing_y > 0 and diff < min_diff:
            min_diff = diff
            best_x, best_y = x, y
    return best_x, best_y


def spacing_factor_pairs(
    length: float,
    width: float,
    count: int,
    min_spacing_m: float = 0.0,
):
    """
    All ``(bx, by)`` with ``bx * by == count`` and
    ``min(length/bx, width/by) >= min_spacing_m``.

    Sorted by **|spacing_x - spacing_y|** (most square bays first), then ``bx``, ``by``.
    Different pairs can yield **different U₀** for the same fixture count (non-square rooms
    or transposed grids), so the solver may evaluate several layouts per ``count``.
    """
    if count < 1:
        count = 1
    L, W = float(length), float(width)
    m = float(min_spacing_m)
    scored = []
    for x in range(1, count + 1):
        if count % x != 0:
            continue
        y = count // x
        sx, sy = L / x, W / y
        if min(sx, sy) < m - 1e-12:
            continue
        diff = abs(sx - sy)
        scored.append((diff, x, y, sx, sy))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [(t[1], t[2]) for t in scored]
