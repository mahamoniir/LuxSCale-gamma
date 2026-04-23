"""Catalog values, presets, and lumen-method constants."""

user_data_file = "all_user_data.json"

luminaire_shapes = {
    "SC highbay": {"shape": "circle", "diameter": 0.464},
    "SC backlight": {"shape": "square", "size": 0.6},
    "SC triproof": {"shape": "rectangle", "width": 1.2, "height": 0.1},
}

define_places = {
    "Room": {"lux": 450, "uniformity": 0.53},
    "Office": {"lux": 450, "uniformity": 0.58},
    "Cafe": {"lux": 450, "uniformity": 0.56},
    "Factory production line": {"lux": 350, "uniformity": 0.54},
    "Factory warehouse": {"lux": 150, "uniformity": 0.56},
}

interior_luminaires = {
    "SC downlight": [9, 10],
    "SC triproof": [30, 40],
    "SC backlight": [32, 35],
}

exterior_luminaires = {
    "SC highbay": [100, 150, 200],
    "SC flood light exterior": [100, 150, 200],
}

led_efficacy = {
    "interior": 110,
    "exterior": [145, 160, 200],
}

beam_angle = 120
# Legacy default only; runtime uses ``luxscale.app_settings.get_maintenance_factor()``.
maintenance_factor = 0.63

# Warn when fixture count implies unusually dense layouts (lumen method can demand many
# small sources). ~0.5/m² ≈ one per 2 m²; adjust per project norms.
fixture_density_warn_per_m2 = 0.5

# IES file lumens vs design lumens (power × efficacy): candela is scaled by design/file.
# Bad or placeholder IES headers can be 10×+ off — unbounded scaling makes grid lx meaningless.
ies_lumen_to_design_ratio_min = 0.25
ies_lumen_to_design_ratio_max = 4.0
