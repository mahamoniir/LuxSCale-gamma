"""
Phase B: polygon-clipped work-plane grid density and sampling.
"""
from __future__ import annotations

import math
import unittest

from luxscale.lighting_calc.polygon import Polygon
from luxscale.uniformity_calculator import (
    fixture_positions_polygon,
    fixture_positions_symmetric_grid,
    polygon_layout_interior_count,
    uniformity_grid_n_for_polygon,
    uniformity_grid_n_for_room,
    work_plane_grid_polygon,
    work_plane_grid_symmetric,
)


class TestUniformityGridNForPolygon(unittest.TestCase):
    def test_rectangle_alpha_one_matches_rect_bracket(self):
        g = uniformity_grid_n_for_polygon(36.0, 1.0)
        self.assertEqual(g, uniformity_grid_n_for_room(6.0, 6.0))
        self.assertEqual(g, 10)

    def test_l_shape_alpha_075_gives_12(self):
        # ceil(10 / sqrt(0.75)) = ceil(11.547) = 12; cap does not fire
        self.assertEqual(uniformity_grid_n_for_polygon(36.0, 0.75), 12)

    def test_plus_sign_alpha_05_cap_fires(self):
        # raw = ceil(10 / sqrt(0.5)) = 15; capped to 10+4 = 14
        self.assertEqual(uniformity_grid_n_for_polygon(100.0, 0.50), 14)

    def test_corridor_alpha_030_cap_fires(self):
        # raw = ceil(10 / sqrt(0.30)) = 19; capped to 14
        self.assertEqual(uniformity_grid_n_for_polygon(100.0, 0.30), 14)

    def test_very_small_alpha_same_as_cap_without_floor(self):
        # Confirms alpha_floor is dead weight: α→0 still returns g_rect+4
        self.assertEqual(uniformity_grid_n_for_polygon(100.0, 0.001), 14)
        self.assertEqual(uniformity_grid_n_for_polygon(100.0, 0.25), 14)


class TestWorkPlaneGridPolygon(unittest.TestCase):
    L_VERTS = [
        (0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (3.0, 4.0), (3.0, 8.0), (0.0, 8.0),
    ]

    def test_l_shape_filters_notch_samples(self):
        """
        Engine frame for the L-shape eq-rect is L=width_eq≈5.196, W=length_eq≈6.928
        (sides = [W_eq, L_eq, ...]). Notch samples must be excluded.
        """
        poly = Polygon.from_vertices(self.L_VERTS)
        # Match cad_calculate / calculate_lighting axis convention:
        # sides=[width_eq, length_eq,...] → engine length=width_eq, width=length_eq
        length_eng = math.sqrt(27.0)  # width_eq
        width_eng = math.sqrt(48.0)   # length_eq
        g = 12
        pts = work_plane_grid_polygon(poly, length_eng, width_eng, g, 0.0)
        full = work_plane_grid_symmetric(length_eng, width_eng, g)
        self.assertEqual(len(full), g * g)
        # Roughly α·G² ≈ 0.75·144 = 108; allow a band for discrete cells.
        self.assertGreater(len(pts), 80)
        self.assertLess(len(pts), len(full))
        # Every surviving point must be in the full candidate set.
        full_set = set((round(x, 9), round(y, 9)) for x, y in full)
        for x, y in pts:
            self.assertIn((round(x, 9), round(y, 9)), full_set)

    def test_rectangle_keeps_all_samples(self):
        poly = Polygon.from_vertices([(0, 0), (6, 0), (6, 4), (0, 4)])
        # Axis-aligned rectangle of area 24 → eq-rect is itself; engine L=6, W=4
        # (sides would be [6,4,6,4] → length=max(6,6)=6, width=max(4,4)=4)
        pts = work_plane_grid_polygon(poly, 6.0, 4.0, 10, 0.0)
        self.assertEqual(len(pts), 100)

    def test_never_returns_empty(self):
        # Degenerate-ish thin room still yields at least one sample via fallback.
        poly = Polygon.from_vertices([(0, 0), (10, 0), (10, 0.5), (0, 0.5)])
        pts = work_plane_grid_polygon(poly, 10.0, 0.5, 10, 0.0)
        self.assertGreaterEqual(len(pts), 1)


class TestFixturePositionsPolygon(unittest.TestCase):
    L_VERTS = [
        (0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (3.0, 4.0), (3.0, 8.0), (0.0, 8.0),
    ]

    def test_rectangle_keeps_full_grid(self):
        poly = Polygon.from_vertices([(0, 0), (6, 0), (6, 4), (0, 4)])
        fxs = fixture_positions_polygon(poly, 6.0, 4.0, 3, 2, 0.0, target_count=6)
        self.assertEqual(len(fxs), 6)
        rect = fixture_positions_symmetric_grid(6.0, 4.0, 3, 2)
        self.assertEqual(
            sorted((round(x, 9), round(y, 9)) for x, y in fxs),
            sorted((round(x, 9), round(y, 9)) for x, y in rect),
        )

    def test_l_shape_returns_exact_target_count(self):
        poly = Polygon.from_vertices(self.L_VERTS)
        length_eng = math.sqrt(27.0)
        width_eng = math.sqrt(48.0)
        target = 6
        fxs = fixture_positions_polygon(
            poly, length_eng, width_eng, 3, 2, 0.0, target_count=target
        )
        self.assertEqual(len(fxs), target)

    def test_l_shape_all_fixtures_inside_proxy(self):
        poly = Polygon.from_vertices(self.L_VERTS)
        length_eng = math.sqrt(27.0)
        width_eng = math.sqrt(48.0)
        from luxscale.uniformity_calculator import _polygon_in_engine_frame

        proxy = _polygon_in_engine_frame(poly, length_eng, width_eng, 0.0)
        fxs = fixture_positions_polygon(
            poly, length_eng, width_eng, 3, 2, 0.0, target_count=6
        )
        for x, y in fxs:
            self.assertTrue(
                proxy.contains(x, y, on_edge=False),
                msg=f"fixture ({x}, {y}) landed outside the polygon proxy",
            )

    def test_l_shape_rect_interior_less_than_full_grid(self):
        """Notch means some of the base 3×2 centres fall outside."""
        poly = Polygon.from_vertices(self.L_VERTS)
        length_eng = math.sqrt(27.0)
        width_eng = math.sqrt(48.0)
        interior = polygon_layout_interior_count(
            poly, length_eng, width_eng, 3, 2, 0.0
        )
        self.assertLess(interior, 6)
        self.assertGreater(interior, 0)

    def test_densify_refills_when_base_grid_too_sparse(self):
        """
        A 1×N strip layout on an L-shape may lose most centres; densify must
        still reach the target count.
        """
        poly = Polygon.from_vertices(self.L_VERTS)
        length_eng = math.sqrt(27.0)
        width_eng = math.sqrt(48.0)
        target = 8
        fxs = fixture_positions_polygon(
            poly, length_eng, width_eng, 1, 8, 0.0, target_count=target
        )
        self.assertEqual(len(fxs), target)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
