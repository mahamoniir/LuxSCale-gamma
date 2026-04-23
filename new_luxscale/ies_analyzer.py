#!/usr/bin/env python3
"""
IES Light Analyzer — Viewer · Editor · Analyzer
================================================
A powerful standalone tool for IES LM-63 photometric files.

Usage:
  python ies_analyzer.py <file.ies>                  # Full analysis report (PDF + PNGs)
  python ies_analyzer.py <file.ies> --no-pdf         # PNGs only
  python ies_analyzer.py <file.ies> --edit           # Interactive CLI editor
  python ies_analyzer.py <file.ies> --export-csv     # Export candela matrix as CSV
  python ies_analyzer.py <file.ies> --scale 1.5      # Scale all candela values
  python ies_analyzer.py <file.ies> --out mydir      # Output directory
  python ies_analyzer.py --demo                      # Generate demo IES + analyze
"""

import sys
import os
import math
import csv
import json
import argparse
import platform
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.backends.backend_pdf import PdfPages
from scipy.interpolate import interp1d

# ──────────────────────────────────────────────────────────────────────────────
# Color palette
# ──────────────────────────────────────────────────────────────────────────────
BLUE   = "#378ADD"
TEAL   = "#1D9E75"
CORAL  = "#D85A30"
AMBER  = "#BA7517"
RED    = "#E24B4A"
PURPLE = "#7F77DD"
GRAY   = "#888780"
GREEN  = "#639922"
PINK   = "#D4537E"

DARK_BG   = "#1a1a1a"
DARK_SURF = "#242424"
DARK_CARD = "#2e2e2e"
DARK_LINE = "#444"
DARK_TEXT = "#d0cec8"
DARK_DIM  = "#888"

MULTI_COLORS = [BLUE, TEAL, CORAL, PURPLE, AMBER, GREEN, PINK, RED]

# Custom candela colormap: deep blue → cyan → yellow → red
_cmap_data = {
    "red":   [(0,.04,0.04),(0.4,.13,.13),(0.7,.95,.95),(1,1,1)],
    "green": [(0,.13,0.13),(0.4,.62,.62),(0.7,.75,.75),(1,.18,.18)],
    "blue":  [(0,.54,0.54),(0.4,.77,.77),(0.7,.1,.1),(1,.12,.12)],
}
CANDELA_CMAP = LinearSegmentedColormap("candela", _cmap_data)

# ──────────────────────────────────────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────────────────────────────────────

class IESParseError(Exception):
    pass


# LM-63 photometric_type codes (data line right after TILT=, index [5]).
#   1 = Type C  (most common — γ from nadir, C-plane azimuth 0–360°)
#   2 = Type B  (lateral — β vertical, B horizontal −90…+90°)
#   3 = Type A  (automotive — α elevation, A horizontal sweep)
PHOTOMETRIC_TYPE_NAMES = {1: "C", 2: "B", 3: "A"}
VERTICAL_ANGLE_LABELS = {
    1: "gamma",
    2: "beta",
    3: "alpha",
}
HORIZONTAL_ANGLE_LABELS = {
    1: "C",
    2: "B",
    3: "A",
}


def photometric_type_name(code) -> str:
    try:
        return PHOTOMETRIC_TYPE_NAMES.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def vertical_angle_label_for_type(code) -> str:
    try:
        return VERTICAL_ANGLE_LABELS.get(int(code), "gamma")
    except (TypeError, ValueError):
        return "gamma"


def horizontal_angle_label_for_type(code) -> str:
    try:
        return HORIZONTAL_ANGLE_LABELS.get(int(code), "C")
    except (TypeError, ValueError):
        return "C"


@dataclass
class IESData:
    vertical_angles:   list
    horizontal_angles: list
    candela_values:    dict          # {h_angle: [cd, ...]}
    max_value:         float
    num_lamps:         int
    lumens_per_lamp:   float
    multiplier:        float
    width:             float
    length:            float
    height:            float
    shape:             str
    # LM-63 photometric_type (1=C, 2=B, 3=A). Default keeps legacy constructors working.
    photometric_type:      int  = 1
    photometric_type_name: str  = "C"
    vertical_angle_label:  str  = "gamma"
    horizontal_angle_label: str = "C"
    header_lines:      list = field(default_factory=list)
    raw_text:          str  = ""

    @property
    def num_vertical(self):   return len(self.vertical_angles)
    @property
    def num_horizontal(self): return len(self.horizontal_angles)

    def candela_array(self) -> np.ndarray:
        """Shape: (n_H, n_V)"""
        return np.array([self.candela_values[h] for h in self.horizontal_angles])

    def symmetry_label(self) -> str:
        last = self.horizontal_angles[-1]
        if last == 0:   return "Full rotational symmetry (H=0 only)"
        if last == 90:  return "Quadrant symmetric (0–90°)"
        if last == 180: return "Half symmetric (0–180°)"
        return f"Asymmetric / full azimuth (0–{last}°)"

    def vertical_span_label(self) -> str:
        v0, v1 = self.vertical_angles[0], self.vertical_angles[-1]
        if abs(v0) < 1 and abs(v1 - 180) < 1: return "0–180° (both hemispheres)"
        if abs(v0) < 1 and abs(v1 - 90)  < 1: return "0–90° (lower hemisphere)"
        if abs(v0 - 90) < 1 and abs(v1 - 180) < 1: return "90–180° (upper hemisphere)"
        if abs(v0 + 90) < 1 and abs(v1 - 90) < 1:  return "−90–+90° (symmetric grid)"
        return f"{v0}–{v1}°"


def _get_next_numbers(lines_iter, count):
    nums = []
    while len(nums) < count:
        line = next(lines_iter, None)
        if line is None:
            raise IESParseError("Unexpected EOF while reading photometric data")
        nums.extend(line.replace(",", " ").split())
    return nums[:count]


def parse_ies(text: str) -> IESData:
    lines = text.splitlines()
    tilt_idx = None
    tilt_value = None
    header = []
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("TILT="):
            tilt_idx = i
            tilt_value = stripped
            break
        header.append(ln)
    if tilt_idx is None:
        raise IESParseError("TILT= line not found — not a valid IES file")
    if tilt_value != "TILT=NONE":
        raise IESParseError(
            f"Unsupported TILT value: {tilt_value} (only TILT=NONE is handled)"
        )

    it = iter(lines[tilt_idx + 1:])
    nums = _get_next_numbers(it, 13)
    num_lamps          = int(float(nums[0]))
    lumens_per_lamp    = float(nums[1])
    multiplier         = float(nums[2])
    num_vertical_ang   = int(float(nums[3]))
    num_horizontal_ang = int(float(nums[4]))
    # LM-63 photometric_type: 1=C, 2=B, 3=A. Needed so B/A files aren't silently
    # treated as C (see documentation/ies_types.md).
    try:
        ptype_code = int(float(nums[5]))
    except (TypeError, ValueError):
        ptype_code = 1
    if ptype_code not in (1, 2, 3):
        ptype_code = 1
    ptype_name = PHOTOMETRIC_TYPE_NAMES.get(ptype_code, "C")
    vertical_angle_label = vertical_angle_label_for_type(ptype_code)
    horizontal_angle_label = horizontal_angle_label_for_type(ptype_code)
    unit               = int(float(nums[6]))  # 1=feet 2=meters
    k = 1.0 if unit == 2 else 0.3048
    width  = abs(float(nums[7])) * k
    length = abs(float(nums[8])) * k
    height = abs(float(nums[9])) * k

    # Determine shape
    w0, l0, h0 = float(nums[7]), float(nums[8]), float(nums[9])
    if all(v == 0 for v in [w0, l0, h0]):
        shape = "point"
    elif h0 == 0 and w0 < 0 and w0 == l0:
        shape = "circular"
    elif h0 == 0 and w0 < 0:
        shape = "ellipse"
    elif h0 == 0:
        shape = "rectangular"
    elif w0 < 0 and w0 == l0:
        shape = "vertical cylinder"
    elif h0 < 0 and w0 == l0 == h0:
        shape = "sphere"
    else:
        shape = "rectangular with luminous sides"

    # Vertical angles
    va_raw = _get_next_numbers(it, num_vertical_ang)
    va = [float(x) for x in va_raw]

    # Horizontal angles
    ha_raw = _get_next_numbers(it, num_horizontal_ang)
    ha = [float(x) for x in ha_raw]

    # Candela values
    total = num_vertical_ang * num_horizontal_ang
    cd_raw = _get_next_numbers(it, total)
    cd_flat = [float(x) for x in cd_raw]
    cd_dict = {
        ha[j]: cd_flat[j * num_vertical_ang: (j + 1) * num_vertical_ang]
        for j in range(num_horizontal_ang)
    }
    max_val = max(cd_flat)

    # Apply multiplier to candela values per IESNA standard
    if abs(multiplier - 1.0) > 1e-6:
        cd_dict = {h: [c * multiplier for c in vals]
                   for h, vals in cd_dict.items()}
        max_val = max_val * multiplier

    return IESData(
        vertical_angles       = va,
        horizontal_angles     = ha,
        candela_values        = cd_dict,
        max_value             = max_val,
        num_lamps             = num_lamps,
        lumens_per_lamp       = lumens_per_lamp,
        multiplier            = multiplier,
        width                 = width,
        length                = length,
        height                = height,
        shape                 = shape,
        photometric_type      = ptype_code,
        photometric_type_name = ptype_name,
        vertical_angle_label  = vertical_angle_label,
        horizontal_angle_label = horizontal_angle_label,
        header_lines          = header,
        raw_text              = text,
    )


def parse_ies_file(path: str) -> IESData:
    enc = "Windows-1252" if platform.system() != "Windows" else None
    with open(path, "r", encoding=enc, errors="replace") as f:
        return parse_ies(f.read())


# ──────────────────────────────────────────────────────────────────────────────
# Beam angle calculations
# ──────────────────────────────────────────────────────────────────────────────

def compute_beam_angle(va, candela_slice, peak, threshold=0.5) -> Optional[float]:
    """
    Compute full beam angle in degrees using linear interpolation.
    threshold=0.5 → beam angle (FWHM)
    threshold=0.1 → field angle
    """
    cutoff = peak * threshold
    for i in range(len(candela_slice) - 1):
        c0, c1 = candela_slice[i], candela_slice[i + 1]
        a0, a1 = float(va[i]), float(va[i + 1])
        if c0 >= cutoff >= c1:
            denom = c0 - c1
            t = (c0 - cutoff) / denom if abs(denom) > 1e-12 else 0.0
            half = a0 + t * (a1 - a0)
            return 2.0 * half
    return None


def compute_all_metrics(ies: IESData) -> dict:
    """Compute beam angles for all H slices + aggregate stats."""
    results = {}
    first_h     = ies.horizontal_angles[0]
    first_slice = ies.candela_values[first_h]
    global_peak = ies.max_value

    # IES standard: beam/field angle reported at C0 plane, threshold vs global peak
    results["beam_angle"]    = compute_beam_angle(ies.vertical_angles, first_slice, global_peak, 0.50)
    results["field_angle"]   = compute_beam_angle(ies.vertical_angles, first_slice, global_peak, 0.10)
    results["peak_cd"]       = global_peak
    results["first_h_angle"] = first_h

    # Per-H: each plane's beam angle uses that plane's own peak as threshold
    # (matches VISO per-plane iso-candela percentages)
    per_h = {}
    for h in ies.horizontal_angles:
        sl         = ies.candela_values[h]
        slice_peak = max(sl)
        per_h[h]   = {
            "beam":  compute_beam_angle(ies.vertical_angles, sl, slice_peak, 0.50),
            "field": compute_beam_angle(ies.vertical_angles, sl, slice_peak, 0.10),
            "peak":  slice_peak,
        }
    results["per_h"] = per_h

    # Estimated lumens — now with wrap-around fix
    results["total_lumens"] = estimate_lumens(ies)
    results["efficacy_approx"] = None
    if ies.lumens_per_lamp > 0 and ies.num_lamps > 0:
        results["efficacy_approx"] = (results["total_lumens"]
                                      / (ies.lumens_per_lamp * ies.num_lamps) * 100)

    return results


def estimate_lumens(ies: IESData) -> float:
    """
    IES LM-63 standard zonal flux method.

    Each vertical measurement angle represents the centre of a zone bounded
    by the midpoints to its neighbours. Solid angle of zone i:
        Delta_Omega_i = 2pi * (cos theta_lo - cos theta_hi)
    Lumens per H-plane = Sum_i  I_i * Delta_Omega_i
    Total flux = horizontal trapezoidal integral of per-plane flux.

    For full-azimuth files (last H < 360), the 360-wrap slice is added
    with the IES convention that the distribution at 360 equals that at 0.

    NOTE:
    This integration is exact for Type C photometry. Type B/A use different
    coordinate systems (beta/alpha), so treating their raw grids as Type C
    can introduce large flux errors. Until a full Type B/A solid-angle remap
    is implemented, we conservatively fall back to header lumens for non-C.
    """
    ptype = int(getattr(ies, "photometric_type", 1) or 1)
    if ptype != 1:
        # TODO: implement full Type B/Type A zonal integration by remapping
        # vertical/horizontal axes to a consistent nadir-referenced system.
        header_lm = (
            float(ies.lumens_per_lamp)
            * max(1, int(ies.num_lamps))
            * float(ies.multiplier)
        )
        return max(0.0, header_lm)

    va_deg = np.array(ies.vertical_angles,   dtype=float)
    ha_deg = np.array(ies.horizontal_angles, dtype=float)
    va_rad = np.radians(va_deg)
    ha_rad = np.radians(ha_deg)
    arr    = ies.candela_array()          # shape (nH, nV)
    nH, nV = arr.shape
    last_h = float(ha_deg[-1])

    # Vertical zonal boundaries (midpoints between adjacent angles)
    vb       = np.empty(nV + 1)
    vb[0]    = va_rad[0]
    vb[1:-1] = (va_rad[:-1] + va_rad[1:]) / 2.0
    vb[-1]   = va_rad[-1]

    # Solid-angle weight per zone per radian of azimuth
    zc = np.cos(vb[:-1]) - np.cos(vb[1:])   # shape (nV,)

    # Lumens per radian of azimuth for each H-plane
    phi_per_rad = arr @ zc                    # shape (nH,)

    # Horizontal integration
    if nH == 1:
        return float(phi_per_rad[0]) * 2.0 * math.pi

    def _trapz_h(ppr):
        return float(np.dot((ppr[:-1] + ppr[1:]) * 0.5,
                            ha_rad[1:] - ha_rad[:-1]))

    if abs(last_h - 90.0) < 1.0:
        return _trapz_h(phi_per_rad) * 4.0

    if abs(last_h - 180.0) < 1.0:
        return _trapz_h(phi_per_rad) * 2.0

    # Full azimuth: integrate + wrap last_h -> 360
    total = _trapz_h(phi_per_rad)
    wrap_dh = math.radians(360.0 - last_h)
    if wrap_dh > 1e-6:
        total += (phi_per_rad[-1] + phi_per_rad[0]) * 0.5 * wrap_dh
    return total

def apply_dark_style(fig, axes_list):
    fig.patch.set_facecolor(DARK_BG)
    for ax in axes_list:
        ax.set_facecolor(DARK_SURF)
        ax.tick_params(colors=DARK_TEXT, labelsize=8)
        ax.spines[:].set_color(DARK_LINE)
        ax.xaxis.label.set_color(DARK_TEXT)
        ax.yaxis.label.set_color(DARK_TEXT)
        ax.title.set_color(DARK_TEXT)
        ax.grid(color=DARK_LINE, linewidth=0.4, alpha=0.6)


# ── 1. Polar diagram ──────────────────────────────────────────────────────────

def plot_polar(ies: IESData, metrics: dict, h_idx: int = 0,
               scale: str = "linear", ax=None, show_beam=True) -> plt.Figure:
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(6, 6))
        fig.patch.set_facecolor(DARK_BG)
    else:
        fig = ax.get_figure()

    h = ies.horizontal_angles[h_idx]
    h_axis_label = getattr(ies, "horizontal_angle_label", "C")
    cd = np.array(ies.candela_values[h], dtype=float)
    va = np.array(ies.vertical_angles, dtype=float)
    peak = ies.max_value

    # Scale
    cd_norm = cd / (peak or 1)
    if scale == "sqrt":   cd_plot = np.sqrt(cd_norm)
    elif scale == "log":  cd_plot = np.log10(1 + 9 * cd_norm)
    else:                 cd_plot = cd_norm

    # Convert VA to polar: 0° at top, going outward
    theta = np.radians(va)

    # Plot mirrored (symmetric display)
    ax.set_facecolor(DARK_SURF)
    ax.plot(theta, cd_plot, color=BLUE, linewidth=2, label=f"{h_axis_label}={h}°")
    ax.plot(-theta, cd_plot, color=BLUE, linewidth=2)
    ax.fill_between(theta, 0, cd_plot, alpha=0.15, color=BLUE)
    ax.fill_between(-theta, 0, cd_plot, alpha=0.15, color=BLUE)

    # Beam/field lines
    if show_beam:
        for key, color, label, thresh in [
            ("field", AMBER, "Field 10%", 0.10),
            ("beam",  RED,   "Beam 50%",  0.50),
        ]:
            ba = compute_beam_angle(va.tolist(), cd.tolist(), peak, thresh)
            if ba is not None:
                ha_rad = math.radians(ba / 2)
                r = 1.0 if scale == "linear" else (math.sqrt(thresh) if scale == "sqrt" else math.log10(1 + 9 * thresh))
                ax.plot([ha_rad, ha_rad], [0, r], color=color, lw=1.5, ls="--", alpha=0.9, label=f"{label}: {ba:.1f}°")
                ax.plot([-ha_rad, -ha_rad], [0, r], color=color, lw=1.5, ls="--", alpha=0.9)
                ax.plot(np.linspace(-ha_rad, ha_rad, 60), np.full(60, r * 0.4), color=color, lw=1, ls=":", alpha=0.7)

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetalim(-math.pi / 2, math.pi / 2) if ies.vertical_angles[-1] <= 90 else None

    ax.tick_params(colors=DARK_TEXT, labelsize=7)
    ax.spines["polar"].set_color(DARK_LINE)
    ax.grid(color=DARK_LINE, alpha=0.5, linewidth=0.4)
    ax.set_facecolor(DARK_SURF)

    r_labels = {"linear": ["25%","50%","75%","100%"],
                "sqrt":   ["6%","25%","56%","100%"],
                "log":    ["11%","37%","68%","100%"]}
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(r_labels[scale], fontsize=6, color=DARK_DIM)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])

    ax.legend(loc="lower center", fontsize=7, facecolor=DARK_CARD,
              labelcolor=DARK_TEXT, framealpha=0.8, ncol=2,
              bbox_to_anchor=(0.5, -0.12))
    ax.set_title(
        f"Polar — {h_axis_label}={h}°  ({scale})",
        color=DARK_TEXT,
        fontsize=9,
        pad=10,
    )

    if standalone:
        fig.tight_layout()
    return fig


# ── 2. Candela vertical profile ───────────────────────────────────────────────

def plot_candela_profile(ies: IESData, metrics: dict, h_indices=None, ax=None) -> plt.Figure:
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(7, 4))
        fig.patch.set_facecolor(DARK_BG)
    else:
        fig = ax.get_figure()

    if h_indices is None:
        h_indices = list(range(min(8, len(ies.horizontal_angles))))

    va = np.array(ies.vertical_angles, dtype=float)
    v_axis_label = getattr(ies, "vertical_angle_label", "gamma")
    h_axis_label = getattr(ies, "horizontal_angle_label", "C")
    peak = ies.max_value

    ax.set_facecolor(DARK_SURF)
    ax.grid(color=DARK_LINE, alpha=0.5, linewidth=0.4, zorder=0)

    for idx, col in zip(h_indices, MULTI_COLORS):
        h = ies.horizontal_angles[idx]
        cd = np.array(ies.candela_values[h], dtype=float) / peak * 100
        lw = 2 if idx == 0 else 1.2
        ax.plot(va, cd, color=col, lw=lw, label=f"{h_axis_label}={h}°", zorder=3)

    # 50% and 10% lines
    ax.axhline(50, color=RED,   ls="--", lw=1, alpha=0.7, label="50% (beam)")
    ax.axhline(10, color=AMBER, ls="--", lw=1, alpha=0.7, label="10% (field)")

    # Shade beam region
    ba = metrics.get("beam_angle")
    fa = metrics.get("field_angle")
    if fa: ax.axvspan(0, fa / 2, alpha=0.06, color=AMBER, zorder=1)
    if ba: ax.axvspan(0, ba / 2, alpha=0.10, color=RED, zorder=1)

    ax.set_xlabel(f"{v_axis_label} angle (°)", color=DARK_TEXT, fontsize=8)
    ax.set_ylabel("Intensity (% of peak)", color=DARK_TEXT, fontsize=8)
    ax.set_title("Candela vertical profiles", color=DARK_TEXT, fontsize=9)
    ax.tick_params(colors=DARK_TEXT, labelsize=7)
    ax.spines[:].set_color(DARK_LINE)
    ax.set_xlim(va[0], va[-1])
    ax.set_ylim(0, 110)
    ax.legend(loc="upper right", fontsize=7, facecolor=DARK_CARD,
              labelcolor=DARK_TEXT, framealpha=0.8, ncol=2)

    if standalone:
        fig.tight_layout()
    return fig


# ── 3. Heat map ───────────────────────────────────────────────────────────────

def plot_heatmap(ies: IESData, ax=None) -> plt.Figure:
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor(DARK_BG)
    else:
        fig = ax.get_figure()

    arr = ies.candela_array() / (ies.max_value or 1) * 100  # (nH, nV)
    va = ies.vertical_angles
    ha = ies.horizontal_angles
    v_axis_label = getattr(ies, "vertical_angle_label", "gamma")
    h_axis_label = getattr(ies, "horizontal_angle_label", "C")

    im = ax.imshow(arr, aspect="auto", origin="upper",
                   extent=[va[0], va[-1], ha[-1], ha[0]],
                   cmap=CANDELA_CMAP, vmin=0, vmax=100)

    cbar = ax.get_figure().colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("% of peak", color=DARK_TEXT, fontsize=8)
    cbar.ax.tick_params(colors=DARK_TEXT, labelsize=7)
    cbar.outline.set_edgecolor(DARK_LINE)

    ax.set_xlabel(f"{v_axis_label} angle (°)", color=DARK_TEXT, fontsize=8)
    ax.set_ylabel(f"{h_axis_label} angle (°)", color=DARK_TEXT, fontsize=8)
    ax.set_title(
        f"Candela heat map ({h_axis_label} × {v_axis_label})",
        color=DARK_TEXT,
        fontsize=9,
    )
    ax.tick_params(colors=DARK_TEXT, labelsize=7)
    ax.spines[:].set_color(DARK_LINE)
    ax.set_facecolor(DARK_SURF)

    if standalone:
        fig.tight_layout()
    return fig


# ── 4. 3D surface ─────────────────────────────────────────────────────────────

def plot_3d_surface(ies: IESData) -> plt.Figure:
    from mpl_toolkits.mplot3d import Axes3D  # noqa
    fig = plt.figure(figsize=(7, 5))
    fig.patch.set_facecolor(DARK_BG)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(DARK_SURF)

    va = np.radians(np.array(ies.vertical_angles, dtype=float))
    ha = ies.horizontal_angles
    arr = ies.candela_array() / (ies.max_value or 1)  # (nH, nV)

    # Build 3D spherical coords X,Y,Z using first H slice mirrored into full circle
    # Expand symmetric data to full 360 for a nice sphere
    h_full = np.radians(np.linspace(0, 360, 73))
    if len(ha) == 1:
        cd_full = np.tile(arr[0], (73, 1))
    elif ha[-1] <= 90:
        # quadrant symmetric → mirror to 360
        cd_q = arr  # (nH, nV)
        angles_4q = np.concatenate([ha, [180-h for h in reversed(ha[:-1])],
                                     [180+h for h in ha[1:]],
                                     [360-h for h in reversed(ha[1:-1])]])
        cd_4q = np.concatenate([cd_q,
                                  cd_q[1:][::-1],
                                  cd_q[1:],
                                  cd_q[1:-1][::-1]], axis=0)
        interp = interp1d(np.radians(angles_4q), cd_4q, axis=0,
                          kind="linear", fill_value="extrapolate")
        cd_full = interp(h_full)
    elif ha[-1] <= 180:
        angles_2h = np.concatenate([ha, [360-h for h in reversed(ha[1:-1])]])
        cd_2h = np.concatenate([arr, arr[1:-1][::-1]], axis=0)
        interp = interp1d(np.radians(angles_2h), cd_2h, axis=0,
                          kind="linear", fill_value="extrapolate")
        cd_full = interp(h_full)
    else:
        interp = interp1d(np.radians(ha), arr, axis=0,
                          kind="linear", fill_value="extrapolate")
        cd_full = interp(h_full)

    V, H = np.meshgrid(va, h_full)
    R = cd_full
    X = R * np.sin(V) * np.cos(H)
    Y = R * np.sin(V) * np.sin(H)
    Z = R * np.cos(V)

    surf = ax.plot_surface(X, Y, Z, cmap=CANDELA_CMAP, linewidth=0,
                           antialiased=True, alpha=0.85)
    fig.colorbar(surf, ax=ax, fraction=0.025, pad=0.05, label="Normalised cd")
    ax.set_xlabel("X", color=DARK_TEXT, fontsize=7)
    ax.set_ylabel("Y", color=DARK_TEXT, fontsize=7)
    ax.set_zlabel("Z", color=DARK_TEXT, fontsize=7)
    ax.tick_params(colors=DARK_TEXT, labelsize=6)
    ax.set_title("3-D candela distribution", color=DARK_TEXT, fontsize=9)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor(DARK_LINE)
    ax.yaxis.pane.set_edgecolor(DARK_LINE)
    ax.zaxis.pane.set_edgecolor(DARK_LINE)

    fig.tight_layout()
    return fig


# ── 5. Beam angle per H slice bar chart ──────────────────────────────────────

def plot_beam_bar(ies: IESData, metrics: dict, ax=None) -> plt.Figure:
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        fig.patch.set_facecolor(DARK_BG)
    else:
        fig = ax.get_figure()

    ha = ies.horizontal_angles
    h_axis_label = getattr(ies, "horizontal_angle_label", "C")
    beams  = [metrics["per_h"][h]["beam"]  or 0 for h in ha]
    fields = [metrics["per_h"][h]["field"] or 0 for h in ha]
    x = np.arange(len(ha))
    w = 0.35

    ax.set_facecolor(DARK_SURF)
    ax.grid(color=DARK_LINE, alpha=0.4, linewidth=0.4, axis="y", zorder=0)
    ax.bar(x - w/2, fields, w, color=AMBER, alpha=0.7, label="Field angle (10%)", zorder=3)
    ax.bar(x + w/2, beams,  w, color=RED,   alpha=0.7, label="Beam angle (50%)",  zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}°" for h in ha], color=DARK_TEXT, fontsize=7)
    ax.set_ylabel("Angle (°)", color=DARK_TEXT, fontsize=8)
    ax.set_xlabel(f"{h_axis_label} angle slice", color=DARK_TEXT, fontsize=8)
    ax.set_title(
        f"Beam / field angle per {h_axis_label} slice",
        color=DARK_TEXT,
        fontsize=9,
    )
    ax.tick_params(colors=DARK_TEXT, labelsize=7)
    ax.spines[:].set_color(DARK_LINE)
    ax.legend(loc="upper right", fontsize=7, facecolor=DARK_CARD,
              labelcolor=DARK_TEXT, framealpha=0.8)

    if standalone:
        fig.tight_layout()
    return fig


# ── 6. Cumulative flux curve ───────────────────────────────────────────────────

def plot_flux_curve(ies: IESData, ax=None) -> plt.Figure:
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        fig.patch.set_facecolor(DARK_BG)
    else:
        fig = ax.get_figure()

    # Flux integration in this plot uses Type C geometry (gamma from nadir).
    # For Type B/A, this curve is misleading; show a clear placeholder instead.
    if int(getattr(ies, "photometric_type", 1) or 1) != 1:
        ax.set_facecolor(DARK_SURF)
        ptype_name = getattr(ies, "photometric_type_name", "?")
        ax.text(
            0.5,
            0.5,
            f"Flux curve not available\nfor Type {ptype_name} photometry",
            ha="center",
            va="center",
            color=DARK_DIM,
            fontsize=9,
            transform=ax.transAxes,
        )
        ax.axis("off")
        if standalone:
            fig.tight_layout()
        return fig

    va = np.radians(np.array(ies.vertical_angles, dtype=float))
    first_h = ies.horizontal_angles[0]
    cd = np.array(ies.candela_values[first_h], dtype=float)
    # Integrand: cd(θ) * sin(θ) dθ
    integrand = cd * np.sin(va)
    cum = np.cumsum(np.concatenate([[0], 0.5 * (integrand[:-1] + integrand[1:]) * np.diff(va)]))
    cum_pct = cum / (cum[-1] or 1) * 100

    va_deg = np.degrees(va)
    ax.set_facecolor(DARK_SURF)
    ax.grid(color=DARK_LINE, alpha=0.4, linewidth=0.4, zorder=0)
    ax.plot(va_deg, cum_pct, color=TEAL, lw=2, zorder=3)
    ax.fill_between(va_deg, cum_pct, alpha=0.12, color=TEAL)
    ax.axhline(50, color=RED,   ls="--", lw=1, alpha=0.7, label="50% flux")
    ax.axhline(90, color=AMBER, ls="--", lw=1, alpha=0.7, label="90% flux")

    v_axis_label = getattr(ies, "vertical_angle_label", "gamma")
    ax.set_xlabel(f"{v_axis_label} angle (°)", color=DARK_TEXT, fontsize=8)
    ax.set_ylabel("Cumulative flux (%)", color=DARK_TEXT, fontsize=8)
    ax.set_title(
        f"Cumulative flux vs {v_axis_label} angle",
        color=DARK_TEXT,
        fontsize=9,
    )
    ax.tick_params(colors=DARK_TEXT, labelsize=7)
    ax.spines[:].set_color(DARK_LINE)
    ax.set_xlim(va_deg[0], va_deg[-1])
    ax.set_ylim(0, 105)
    ax.legend(fontsize=7, facecolor=DARK_CARD, labelcolor=DARK_TEXT, framealpha=0.8)

    if standalone:
        fig.tight_layout()
    return fig


# ── 7. Summary metrics panel ─────────────────────────────────────────────────

def plot_metrics_panel(ies: IESData, metrics: dict, filename: str, ax=None) -> plt.Figure:
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(8, 3))
        fig.patch.set_facecolor(DARK_BG)
    else:
        fig = ax.get_figure()

    ax.set_facecolor(DARK_CARD)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    def fmt(v, unit="", fallback="n/a"):
        if v is None: return fallback
        if isinstance(v, float): return f"{v:.1f}{unit}"
        return f"{v}{unit}"

    rows = [
        ("File", os.path.basename(filename)),
        ("Photometric type", f"Type {ies.photometric_type_name}"),
        ("Shape", ies.shape),
        ("Symmetry", ies.symmetry_label()),
        ("Vertical span", ies.vertical_span_label()),
        (f"Vertical angles ({ies.vertical_angle_label})", str(ies.num_vertical)),
        (f"Horizontal angles ({ies.horizontal_angle_label})", str(ies.num_horizontal)),
        ("Peak candela", f"{ies.max_value:,.0f} cd"),
        ("Beam angle (50%)", fmt(metrics.get("beam_angle"), "°")),
        ("Field angle (10%)", fmt(metrics.get("field_angle"), "°")),
        ("Lamps", str(ies.num_lamps)),
        ("Lumens/lamp", f"{ies.lumens_per_lamp:,.0f}" if ies.lumens_per_lamp > 0 else "measured"),
        ("Est. lumens", f"{metrics.get('total_lumens', 0):,.0f}"),
        ("Size (W×L×H)", f"{ies.width:.3f}m × {ies.length:.3f}m × {ies.height:.3f}m"),
    ]

    cols = 3
    per_col = math.ceil(len(rows) / cols)
    for ci in range(cols):
        chunk = rows[ci * per_col: (ci + 1) * per_col]
        x = 0.02 + ci * 0.34
        for ri, (label, val) in enumerate(chunk):
            y = 0.92 - ri * 0.14
            ax.text(x, y, label + ":", color=DARK_DIM,   fontsize=7.5, va="top", ha="left")
            ax.text(x + 0.18, y, val, color=DARK_TEXT, fontsize=7.5, va="top", ha="left", fontweight="bold")

    if standalone:
        fig.tight_layout()
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Master PDF report
# ──────────────────────────────────────────────────────────────────────────────

def generate_pdf_report(ies: IESData, metrics: dict, ies_path: str, out_dir: str) -> str:
    stem = Path(ies_path).stem
    pdf_path = os.path.join(out_dir, f"{stem}_analysis.pdf")

    with PdfPages(pdf_path) as pdf:

        # ── Page 1: Overview dashboard ─────────────────────────────────────
        fig = plt.figure(figsize=(11, 8.5), facecolor=DARK_BG)
        gs = gridspec.GridSpec(3, 3, figure=fig,
                               hspace=0.45, wspace=0.35,
                               top=0.93, bottom=0.07, left=0.07, right=0.97)

        # Title bar
        fig.text(0.5, 0.97, f"IES Analysis — {os.path.basename(ies_path)}",
                 ha="center", va="top", color=DARK_TEXT, fontsize=12, fontweight="bold")
        fig.text(0.5, 0.945, ies.symmetry_label() + "  |  " + ies.vertical_span_label(),
                 ha="center", va="top", color=DARK_DIM, fontsize=8)

        # Polar (top-left, spans 1×1)
        ax_polar = fig.add_subplot(gs[0:2, 0], projection="polar")
        plot_polar(ies, metrics, h_idx=0, scale="linear", ax=ax_polar)

        # Candela profiles (top-mid/right, spans 1×2)
        ax_cd = fig.add_subplot(gs[0, 1:3])
        plot_candela_profile(ies, metrics, ax=ax_cd)

        # Heat map (mid-mid/right)
        ax_hm = fig.add_subplot(gs[1, 1:3])
        plot_heatmap(ies, ax=ax_hm)

        # Flux curve (bottom-left)
        ax_flux = fig.add_subplot(gs[2, 0])
        plot_flux_curve(ies, ax=ax_flux)

        # Beam bar (bottom-mid/right)
        ax_bar = fig.add_subplot(gs[2, 1:3])
        plot_beam_bar(ies, metrics, ax=ax_bar)

        pdf.savefig(fig, facecolor=DARK_BG)
        plt.close(fig)

        # ── Page 2: Multi-scale polars ─────────────────────────────────────
        fig2 = plt.figure(figsize=(11, 8.5), facecolor=DARK_BG)
        fig2.text(0.5, 0.97, "Polar Diagrams — Multiple Scales & Slices",
                  ha="center", color=DARK_TEXT, fontsize=11, fontweight="bold")
        gs2 = gridspec.GridSpec(2, 3, figure=fig2, hspace=0.5, wspace=0.4,
                                top=0.90, bottom=0.05, left=0.05, right=0.97)

        n_h = len(ies.horizontal_angles)
        scales = ["linear", "sqrt", "log"]
        # Row 0: three scales for H=0
        for ci, sc in enumerate(scales):
            ax = fig2.add_subplot(gs2[0, ci], projection="polar")
            plot_polar(ies, metrics, h_idx=0, scale=sc, ax=ax, show_beam=(ci == 0))

        # Row 1: up to 3 H slices at linear scale
        h_picks = [0, n_h // 3, 2 * n_h // 3] if n_h >= 3 else list(range(n_h))
        h_picks = list(dict.fromkeys(h_picks))[:3]
        for ci, hi in enumerate(h_picks):
            ax = fig2.add_subplot(gs2[1, ci], projection="polar")
            plot_polar(ies, metrics, h_idx=hi, scale="linear", ax=ax, show_beam=True)

        pdf.savefig(fig2, facecolor=DARK_BG)
        plt.close(fig2)

        # ── Page 3: 3D + metrics table ─────────────────────────────────────
        fig3 = plt.figure(figsize=(11, 8.5), facecolor=DARK_BG)
        fig3.text(0.5, 0.97, "3-D Distribution & Metrics",
                  ha="center", color=DARK_TEXT, fontsize=11, fontweight="bold")

        ax3d = fig3.add_axes([0.05, 0.38, 0.55, 0.55], projection="3d")
        ax3d.set_facecolor(DARK_SURF)
        va = np.radians(np.array(ies.vertical_angles, dtype=float))
        ha_arr = ies.horizontal_angles
        arr = ies.candela_array() / (ies.max_value or 1)
        h_full = np.radians(np.linspace(0, 360, 73))
        if len(ha_arr) == 1:
            cd_full = np.tile(arr[0], (73, 1))
        elif ha_arr[-1] <= 90:
            ha_rad_arr = np.radians(ha_arr)
            ha_ext = np.concatenate([ha_rad_arr, np.pi - ha_rad_arr[::-1][1:],
                                     np.pi + ha_rad_arr[1:], 2*np.pi - ha_rad_arr[::-1][1:-1]])
            arr_ext = np.concatenate([arr, arr[::-1][1:], arr[1:], arr[::-1][1:-1]])
            interp = interp1d(ha_ext, arr_ext, axis=0, kind="linear", fill_value="extrapolate")
            cd_full = interp(h_full)
        else:
            interp = interp1d(np.radians(ha_arr), arr, axis=0, kind="linear", fill_value="extrapolate")
            cd_full = interp(h_full)

        V2, H2 = np.meshgrid(va, h_full)
        R2 = cd_full
        X2 = R2 * np.sin(V2) * np.cos(H2)
        Y2 = R2 * np.sin(V2) * np.sin(H2)
        Z2 = R2 * np.cos(V2)
        surf = ax3d.plot_surface(X2, Y2, Z2, cmap=CANDELA_CMAP,
                                 linewidth=0, antialiased=True, alpha=0.85)
        ax3d.set_xlabel("X", color=DARK_TEXT, fontsize=7)
        ax3d.set_ylabel("Y", color=DARK_TEXT, fontsize=7)
        ax3d.set_zlabel("Z (nadir)", color=DARK_TEXT, fontsize=7)
        ax3d.tick_params(colors=DARK_TEXT, labelsize=5)
        ax3d.set_title("3-D candela sphere", color=DARK_TEXT, fontsize=9)
        ax3d.xaxis.pane.fill = ax3d.yaxis.pane.fill = ax3d.zaxis.pane.fill = False
        fig3.colorbar(surf, ax=ax3d, fraction=0.02, pad=0.05, label="Norm. cd")

        # Metrics table (right side)
        ax_m = fig3.add_axes([0.63, 0.38, 0.34, 0.55])
        ax_m.set_facecolor(DARK_CARD)
        ax_m.axis("off")
        rows = [
            ("Peak candela",    f"{ies.max_value:,.0f} cd"),
            ("Beam angle 50%",  f"{metrics['beam_angle']:.1f}°" if metrics['beam_angle'] else "n/a"),
            ("Field angle 10%", f"{metrics['field_angle']:.1f}°" if metrics['field_angle'] else "n/a"),
            ("Est. lumens",     f"{metrics['total_lumens']:,.0f} lm"),
            ("Num lamps",       str(ies.num_lamps)),
            ("Lumens/lamp",     f"{ies.lumens_per_lamp:,.0f}"),
            ("Multiplier",      str(ies.multiplier)),
            ("Shape",           ies.shape),
            ("Width",           f"{ies.width:.4f} m"),
            ("Length",          f"{ies.length:.4f} m"),
            ("Height",          f"{ies.height:.4f} m"),
            ("Vert angles",     str(ies.num_vertical)),
            ("Horiz angles",    str(ies.num_horizontal)),
        ]
        for ri, (lbl, val) in enumerate(rows):
            y = 0.96 - ri * 0.072
            ax_m.text(0.02, y, lbl, color=DARK_DIM, fontsize=8, va="top")
            ax_m.text(0.98, y, val, color=DARK_TEXT, fontsize=8, va="top",
                      ha="right", fontweight="bold")
            if ri < len(rows) - 1:
                ax_m.axhline(y - 0.014, color=DARK_LINE, linewidth=0.4, xmin=0.02, xmax=0.98)

        # Per-H table (bottom)
        ax_ph = fig3.add_axes([0.05, 0.05, 0.90, 0.28])
        ax_ph.set_facecolor(DARK_SURF)
        ax_ph.axis("off")
        ax_ph.set_title("Per-horizontal-angle beam metrics", color=DARK_TEXT,
                         fontsize=9, loc="left", pad=6)
        col_labels = ["H angle", "Peak cd", "Beam °", "Field °"]
        col_xs = [0.05, 0.30, 0.55, 0.78]
        for cx, cl in zip(col_xs, col_labels):
            ax_ph.text(cx, 0.90, cl, color=DARK_DIM, fontsize=7.5,
                       va="top", fontweight="bold")
        for ri, h in enumerate(ies.horizontal_angles):
            ph = metrics["per_h"][h]
            row_vals = [
                f"{h}°",
                f"{ph['peak']:,.0f}",
                f"{ph['beam']:.1f}" if ph['beam'] else "n/a",
                f"{ph['field']:.1f}" if ph['field'] else "n/a",
            ]
            y_r = 0.82 - ri * 0.105
            if y_r < 0.02: break
            for cx, rv in zip(col_xs, row_vals):
                ax_ph.text(cx, y_r, rv, color=DARK_TEXT, fontsize=7, va="top")

        pdf.savefig(fig3, facecolor=DARK_BG)
        plt.close(fig3)

        # ── Metadata ───────────────────────────────────────────────────────
        d = pdf.infodict()
        d["Title"]   = f"IES Analysis — {os.path.basename(ies_path)}"
        d["Author"]  = "ies_analyzer.py"
        d["Subject"] = "IES LM-63 Photometric Report"

    return pdf_path


# ──────────────────────────────────────────────────────────────────────────────
# PNG exports (individual)
# ──────────────────────────────────────────────────────────────────────────────

def save_individual_pngs(ies: IESData, metrics: dict, ies_path: str, out_dir: str) -> list:
    stem = Path(ies_path).stem
    saved = []

    figs = {
        "polar_linear":   lambda: plot_polar(ies, metrics, scale="linear"),
        "polar_sqrt":     lambda: plot_polar(ies, metrics, scale="sqrt"),
        "polar_log":      lambda: plot_polar(ies, metrics, scale="log"),
        "candela":        lambda: plot_candela_profile(ies, metrics),
        "heatmap":        lambda: plot_heatmap(ies),
        "beam_bar":       lambda: plot_beam_bar(ies, metrics),
        "flux_curve":     lambda: plot_flux_curve(ies),
    }
    for name, fn in figs.items():
        f = fn()
        path = os.path.join(out_dir, f"{stem}_{name}.png")
        f.savefig(path, dpi=150, facecolor=DARK_BG, bbox_inches="tight")
        plt.close(f)
        saved.append(path)
        print(f"  Saved: {path}")

    # 3D
    try:
        f3d = plot_3d_surface(ies)
        path = os.path.join(out_dir, f"{stem}_3d.png")
        f3d.savefig(path, dpi=120, facecolor=DARK_BG, bbox_inches="tight")
        plt.close(f3d)
        saved.append(path)
        print(f"  Saved: {path}")
    except Exception as e:
        print(f"  3D plot skipped: {e}")

    return saved


# ──────────────────────────────────────────────────────────────────────────────
# CSV export
# ──────────────────────────────────────────────────────────────────────────────

def export_csv(ies: IESData, ies_path: str, out_dir: str) -> str:
    stem = Path(ies_path).stem
    path = os.path.join(out_dir, f"{stem}_candela.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        # Header: H angles across columns
        w.writerow(["V_angle \\ H_angle"] + [str(h) for h in ies.horizontal_angles])
        for vi, va in enumerate(ies.vertical_angles):
            row = [va] + [ies.candela_values[h][vi] for h in ies.horizontal_angles]
            w.writerow(row)
    print(f"  CSV saved: {path}")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# JSON metrics export
# ──────────────────────────────────────────────────────────────────────────────

def export_json(ies: IESData, metrics: dict, ies_path: str, out_dir: str) -> str:
    stem = Path(ies_path).stem
    path = os.path.join(out_dir, f"{stem}_metrics.json")
    out = {
        "file": os.path.basename(ies_path),
        "shape": ies.shape,
        "photometric_type": ies.photometric_type,
        "photometric_type_name": ies.photometric_type_name,
        "vertical_angle_label": ies.vertical_angle_label,
        "horizontal_angle_label": ies.horizontal_angle_label,
        "symmetry": ies.symmetry_label(),
        "vertical_span": ies.vertical_span_label(),
        "num_vertical_angles": ies.num_vertical,
        "num_horizontal_angles": ies.num_horizontal,
        "peak_candela": ies.max_value,
        "beam_angle_deg": metrics.get("beam_angle"),
        "field_angle_deg": metrics.get("field_angle"),
        "estimated_lumens": metrics.get("total_lumens"),
        "num_lamps": ies.num_lamps,
        "lumens_per_lamp": ies.lumens_per_lamp,
        "multiplier": ies.multiplier,
        "width_m": ies.width,
        "length_m": ies.length,
        "height_m": ies.height,
        "per_h_metrics": {
            str(h): {
                "peak_cd": v["peak"],
                "beam_angle_deg": v["beam"],
                "field_angle_deg": v["field"],
            }
            for h, v in metrics["per_h"].items()
        },
    }
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  JSON saved: {path}")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# IES Writer (for editing)
# ──────────────────────────────────────────────────────────────────────────────

def write_ies(ies: IESData, out_path: str, header_override: list = None):
    """Write IES data back to a .ies file."""
    lines = []
    hdr = header_override if header_override is not None else ies.header_lines
    lines.extend(hdr)
    lines.append("TILT=NONE")

    nV = ies.num_vertical
    nH = ies.num_horizontal
    unit = 2  # always write meters; parser normalizes all dimensions to metres on read
    ptype = int(getattr(ies, "photometric_type", 1) or 1)
    if ptype not in (1, 2, 3):
        ptype = 1

    lines.append(
        f" {ies.num_lamps}  {ies.lumens_per_lamp:.4f}  {ies.multiplier:.4f}"
        f"  {nV}  {nH}  {ptype}  {unit}"
        f"  {ies.width:.4f}  {ies.length:.4f}  {ies.height:.4f}"
        f"  1  1  1"
    )

    def fmt_nums(vals, per_line=10):
        rows = []
        for i in range(0, len(vals), per_line):
            rows.append(" ".join(f"{v:.4f}" for v in vals[i:i+per_line]))
        return rows

    lines.extend(fmt_nums(ies.vertical_angles))
    lines.extend(fmt_nums(ies.horizontal_angles))
    for h in ies.horizontal_angles:
        lines.extend(fmt_nums(ies.candela_values[h]))

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Written: {out_path}")


# ──────────────────────────────────────────────────────────────────────────────
# Interactive CLI editor
# ──────────────────────────────────────────────────────────────────────────────

def interactive_editor(ies: IESData, ies_path: str, out_dir: str):
    import copy
    stem = Path(ies_path).stem
    edited = copy.deepcopy(ies)
    print("\n" + "═" * 60)
    print("  IES EDITOR — interactive mode")
    print("  Type 'help' for commands, 'quit' to exit")
    print("═" * 60)

    def print_summary():
        print(f"\n  Peak cd:    {edited.max_value:,.1f}")
        print(f"  Beam angle: {compute_beam_angle(edited.vertical_angles, edited.candela_values[edited.horizontal_angles[0]], edited.max_value, 0.5) or 'n/a'}")
        print(f"  VA range:   {edited.vertical_angles[0]}° – {edited.vertical_angles[-1]}°")
        print(f"  HA range:   {edited.horizontal_angles[0]}° – {edited.horizontal_angles[-1]}°")

    HELP = """
Commands:
  info              — show current summary
  scale <factor>    — multiply all candela by factor (e.g. scale 1.5)
  clamp <max_cd>    — clamp all values to max_cd
  normalize         — normalize peak to 1000 cd
  set_lumens <val>  — change lumens_per_lamp value
  set_mult <val>    — change multiplier
  smooth <sigma>    — Gaussian smooth vertical profile (sigma in degrees)
  add_header <text> — append a header line
  show_headers      — show current header lines
  save [filename]   — write edited IES file
  analyze           — re-run analysis and regenerate plots
  reset             — reset to original
  help              — this message
  quit / exit       — exit editor
"""

    import copy
    original = copy.deepcopy(ies)

    while True:
        try:
            cmd = input("\nies> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting editor.")
            break

        if not cmd:
            continue
        parts = cmd.split()
        op = parts[0].lower()

        if op in ("quit", "exit", "q"):
            break

        elif op == "help":
            print(HELP)

        elif op == "info":
            print_summary()

        elif op == "scale" and len(parts) == 2:
            try:
                f = float(parts[1])
                for h in edited.horizontal_angles:
                    edited.candela_values[h] = [c * f for c in edited.candela_values[h]]
                edited.max_value = max(max(v) for v in edited.candela_values.values())
                print(f"  Scaled by {f}. New peak: {edited.max_value:,.1f} cd")
            except ValueError:
                print("  Error: invalid factor")

        elif op == "clamp" and len(parts) == 2:
            try:
                mx = float(parts[1])
                for h in edited.horizontal_angles:
                    edited.candela_values[h] = [min(c, mx) for c in edited.candela_values[h]]
                edited.max_value = max(max(v) for v in edited.candela_values.values())
                print(f"  Clamped to {mx} cd. New peak: {edited.max_value:,.1f} cd")
            except ValueError:
                print("  Error: invalid value")

        elif op == "normalize":
            pk = edited.max_value or 1
            for h in edited.horizontal_angles:
                edited.candela_values[h] = [c / pk * 1000 for c in edited.candela_values[h]]
            edited.max_value = 1000.0
            print("  Normalized peak to 1000 cd")

        elif op == "set_lumens" and len(parts) == 2:
            try:
                edited.lumens_per_lamp = float(parts[1])
                print(f"  Lumens/lamp set to {edited.lumens_per_lamp}")
            except ValueError:
                print("  Error: invalid value")

        elif op == "set_mult" and len(parts) == 2:
            try:
                edited.multiplier = float(parts[1])
                print(f"  Multiplier set to {edited.multiplier}")
            except ValueError:
                print("  Error: invalid value")

        elif op == "smooth" and len(parts) == 2:
            try:
                from scipy.ndimage import gaussian_filter1d
                va = np.array(edited.vertical_angles, dtype=float)
                step = (va[-1] - va[0]) / (len(va) - 1) if len(va) > 1 else 1
                sigma_samples = float(parts[1]) / step
                for h in edited.horizontal_angles:
                    arr = np.array(edited.candela_values[h], dtype=float)
                    smoothed = gaussian_filter1d(arr, sigma=sigma_samples)
                    edited.candela_values[h] = smoothed.tolist()
                edited.max_value = max(max(v) for v in edited.candela_values.values())
                print(f"  Smoothed (sigma={parts[1]}°). New peak: {edited.max_value:,.1f} cd")
            except Exception as e:
                print(f"  Error: {e}")

        elif op == "add_header":
            text = " ".join(parts[1:])
            edited.header_lines.append(text)
            print(f"  Added header: {text}")

        elif op == "show_headers":
            for ln in edited.header_lines:
                print(f"  {ln}")

        elif op == "save":
            fname = parts[1] if len(parts) > 1 else f"{stem}_edited.ies"
            if not fname.endswith(".ies"):
                fname += ".ies"
            out_path = os.path.join(out_dir, fname)
            write_ies(edited, out_path)

        elif op == "analyze":
            print("  Re-analyzing...")
            m2 = compute_all_metrics(edited)
            tmp_path = os.path.join(out_dir, f"{stem}_edited_temp.ies")
            write_ies(edited, tmp_path)
            generate_pdf_report(edited, m2, tmp_path, out_dir)
            save_individual_pngs(edited, m2, tmp_path, out_dir)
            print("  Done.")

        elif op == "reset":
            edited = copy.deepcopy(original)
            print("  Reset to original.")

        else:
            print(f"  Unknown command: {op}. Type 'help'.")


# ──────────────────────────────────────────────────────────────────────────────
# Demo IES generation
# ──────────────────────────────────────────────────────────────────────────────

DEMO_IES = """IESNA:LM-63-2002
[TEST] Demo Narrow Spot
[MANUFAC] Demo Lighting Co
[LUMCAT] DEMO-SPOT-2024
[LUMINAIRE] 15-degree narrow spot — generated for testing
[LAMP] LED MR16
TILT=NONE
1 1200 1 37 5 1 2 0.08 0.08 0
1 1 1
0 2.5 5 7.5 10 12.5 15 17.5 20 22.5 25 27.5 30 32.5 35 37.5 40 42.5 45 47.5 50 52.5 55 57.5 60 62.5 65 67.5 70 72.5 75 77.5 80 82.5 85 87.5 90
0 22.5 45 67.5 90
1200 1198 1193 1182 1163 1133 1090 1033 960 872 770 660 546 435 336 253 185 131 89 59 37 22 12 7 3 1 0 0 0 0 0 0 0 0 0 0 0
1190 1188 1183 1172 1153 1123 1080 1023 950 862 760 650 536 425 326 243 175 123 83 55 34 20 11 6 3 1 0 0 0 0 0 0 0 0 0 0 0
1170 1168 1163 1152 1133 1103 1060 1003 930 842 740 630 516 405 306 223 158 111 76 51 32 19 11 6 2 1 0 0 0 0 0 0 0 0 0 0 0
1130 1128 1123 1112 1093 1063 1020 963 890 802 700 590 476 365 266 183 125 89 61 41 26 16 9 5 2 0 0 0 0 0 0 0 0 0 0 0 0
1060 1058 1053 1042 1023 993 950 893 820 732 630 520 406 300 210 143 103 74 52 35 22 13 8 4 2 0 0 0 0 0 0 0 0 0 0 0 0
"""


def load_demo(out_dir: str) -> tuple:
    demo_path = os.path.join(out_dir, "demo_spot.ies")
    with open(demo_path, "w") as f:
        f.write(DEMO_IES)
    ies = parse_ies(DEMO_IES)
    return ies, demo_path


# ──────────────────────────────────────────────────────────────────────────────
# Pretty console report
# ──────────────────────────────────────────────────────────────────────────────

def print_report(ies: IESData, metrics: dict, ies_path: str):
    W = 62
    SEP = "─" * W
    def row(label, value, unit=""):
        line = f"  {label:<28} {value}{unit}"
        print(line)

    print("\n" + "═" * W)
    print(f"  IES ANALYSIS REPORT")
    print(f"  {os.path.basename(ies_path)}")
    print("═" * W)
    print(f"\n  PHOTOMETRIC GEOMETRY")
    print(SEP)
    row(
        "Photometric type",
        f"Type {ies.photometric_type_name} (LM-63 code {ies.photometric_type})",
    )
    row("Symmetry",        ies.symmetry_label())
    row("Vertical span",   ies.vertical_span_label())
    row(f"Vertical angles ({ies.vertical_angle_label})", str(ies.num_vertical))
    row(f"Horizontal angles ({ies.horizontal_angle_label})", str(ies.num_horizontal))
    row("Shape",           ies.shape)
    row("Dimensions",      f"{ies.width:.4f}m × {ies.length:.4f}m × {ies.height:.4f}m")

    print(f"\n  BEAM METRICS (@ H={ies.horizontal_angles[0]}°)")
    print(SEP)
    ba  = metrics.get("beam_angle")
    fa  = metrics.get("field_angle")
    row("Peak candela",    f"{ies.max_value:,.1f}", " cd")
    row("Beam angle (50%)", f"{ba:.1f}" if ba else "n/a", "°")
    row("Field angle (10%)", f"{fa:.1f}" if fa else "n/a", "°")

    if len(ies.horizontal_angles) > 1:
        print(f"\n  PER-H BEAM ANGLES")
        print(SEP)
        print(f"  {'H':>6}  {'Peak cd':>10}  {'Beam °':>8}  {'Field °':>8}")
        for h in ies.horizontal_angles:
            ph = metrics["per_h"][h]
            b = f"{ph['beam']:.1f}" if ph["beam"] else " n/a"
            ff = f"{ph['field']:.1f}" if ph["field"] else " n/a"
            print(f"  {h:>6.1f}°  {ph['peak']:>10,.1f}  {b:>8}  {ff:>8}")

    print(f"\n  LAMP DATA")
    print(SEP)
    row("Lamps",           str(ies.num_lamps))
    row("Lumens/lamp",     f"{ies.lumens_per_lamp:,.1f}" if ies.lumens_per_lamp > 0 else "measured")
    row("Multiplier",      str(ies.multiplier))
    row("Est. lumens",     f"{metrics.get('total_lumens', 0):,.0f}", " lm")
    print("\n" + "═" * W + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Powerful IES LM-63 viewer / editor / analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ies_file", nargs="?", help="Path to .ies file")
    parser.add_argument("--demo",       action="store_true",  help="Generate and analyze a demo IES file")
    parser.add_argument("--no-pdf",     action="store_true",  help="Skip PDF, save PNGs only")
    parser.add_argument("--no-png",     action="store_true",  help="Skip individual PNGs")
    parser.add_argument("--edit",       action="store_true",  help="Open interactive CLI editor")
    parser.add_argument("--export-csv", action="store_true",  help="Export candela matrix as CSV")
    parser.add_argument("--export-json",action="store_true",  help="Export metrics as JSON")
    parser.add_argument("--scale",      type=float, default=None, help="Scale all candela by this factor then export")
    parser.add_argument("--out",        type=str,   default=None, help="Output directory (default: same as IES file)")
    args = parser.parse_args()

    # Resolve paths
    if args.demo:
        out_dir = args.out or "/tmp/ies_demo"
        os.makedirs(out_dir, exist_ok=True)
        print(f"  Generating demo IES → {out_dir}")
        ies, ies_path = load_demo(out_dir)
    elif args.ies_file:
        ies_path = args.ies_file
        if not os.path.exists(ies_path):
            print(f"Error: file not found: {ies_path}")
            sys.exit(1)
        out_dir = args.out or os.path.dirname(os.path.abspath(ies_path))
        os.makedirs(out_dir, exist_ok=True)
        print(f"  Parsing: {ies_path}")
        ies = parse_ies_file(ies_path)
    else:
        parser.print_help()
        sys.exit(0)

    # Optional scale transform
    if args.scale is not None:
        f = args.scale
        for h in ies.horizontal_angles:
            ies.candela_values[h] = [c * f for c in ies.candela_values[h]]
        ies.max_value = max(max(v) for v in ies.candela_values.values())
        print(f"  Scaled by {f}. New peak: {ies.max_value:,.1f} cd")

    # Compute metrics
    print("  Computing metrics...")
    metrics = compute_all_metrics(ies)

    # Console report
    print_report(ies, metrics, ies_path)

    # Optional exports
    if args.export_csv:
        export_csv(ies, ies_path, out_dir)

    if args.export_json:
        export_json(ies, metrics, ies_path, out_dir)

    # Plots
    if not args.no_pdf:
        print("  Generating PDF report...")
        pdf = generate_pdf_report(ies, metrics, ies_path, out_dir)
        print(f"  PDF saved: {pdf}")

    if not args.no_png:
        print("  Generating PNG plots...")
        save_individual_pngs(ies, metrics, ies_path, out_dir)

    # Interactive editor
    if args.edit:
        interactive_editor(ies, ies_path, out_dir)

    print("\n  Done.")


if __name__ == "__main__":
    main()
