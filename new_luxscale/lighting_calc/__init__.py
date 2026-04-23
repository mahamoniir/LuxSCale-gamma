"""
LuxScale lighting calculator package.

Public API matches the former monolithic ``lighting_calc.py`` module.
"""

from .ai_lux import ask_ai_lux
from .calculate import calculate_lighting
from .constants import (
    beam_angle,
    define_places,
    exterior_luminaires,
    interior_luminaires,
    led_efficacy,
    luminaire_shapes,
    maintenance_factor,
    user_data_file,
)
from .export_io import (
    export_all_users_to_csv,
    export_csv,
    export_pdf,
    load_all_user_data,
    save_user_data,
)
from .geometry import (
    calculate_spacing,
    cyclic_quadrilateral_area,
    determine_luminaire,
    determine_zone,
    get_spacing_constraints,
    spacing_factor_pairs,
)
from .plotting import draw_heatmap, draw_lighting_distribution
from . import state

results_global = state.results_global
project_info_global = state.project_info_global


def run_gui():
    """Tk desktop UI; imports ``gui`` only when invoked (avoids tkinter on API servers)."""
    from .gui import run_gui as _launch_gui

    _launch_gui()

__all__ = [
    "ask_ai_lux",
    "beam_angle",
    "calculate_lighting",
    "calculate_spacing",
    "spacing_factor_pairs",
    "cyclic_quadrilateral_area",
    "define_places",
    "determine_luminaire",
    "determine_zone",
    "draw_heatmap",
    "draw_lighting_distribution",
    "export_all_users_to_csv",
    "export_csv",
    "export_pdf",
    "exterior_luminaires",
    "get_spacing_constraints",
    "interior_luminaires",
    "led_efficacy",
    "load_all_user_data",
    "luminaire_shapes",
    "maintenance_factor",
    "project_info_global",
    "results_global",
    "run_gui",
    "save_user_data",
    "user_data_file",
]
