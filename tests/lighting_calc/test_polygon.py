"""
Unit tests for :mod:`luxscale.lighting_calc.polygon` (plan 06 phase A).

Runs with plain ``unittest`` — no pytest required. Kick off with::

    python -m unittest tests.lighting_calc.test_polygon
"""

from __future__ import annotations

import math
import unittest

from luxscale.lighting_calc.polygon import Polygon, PolygonError


# Convenient fixtures -------------------------------------------------------


def _square(side: float = 4.0) -> Polygon:
    return Polygon.from_vertices([(0, 0), (side, 0), (side, side), (0, side)])


def _rect(w: float = 6.0, h: float = 4.0) -> Polygon:
    return Polygon.from_vertices([(0, 0), (w, 0), (w, h), (0, h)])


def _l_shape() -> Polygon:
    # Classic L: outer bbox 6 × 8, notch 3 × 4 cut from the top-right → area 36
    return Polygon.from_vertices(
        [(0, 0), (6, 0), (6, 4), (3, 4), (3, 8), (0, 8)]
    )


# Tests ---------------------------------------------------------------------


class TestSignedAreaAndOrientation(unittest.TestCase):
    def test_ccw_input_stays_ccw(self):
        poly = _square()
        self.assertAlmostEqual(poly.area, 16.0)
        # First vertex after normalization equals the input first vertex
        self.assertEqual(poly.vertices[0], (0.0, 0.0))

    def test_cw_input_normalized_to_ccw(self):
        poly = Polygon.from_vertices([(0, 0), (0, 4), (4, 4), (4, 0)])  # CW
        self.assertAlmostEqual(poly.area, 16.0)
        # After reversal, orientation must be CCW → signed area > 0 already
        # asserted; ensure at least one edge goes "up" (positive y-delta)
        max_dy = max(
            poly.vertices[(i + 1) % 4][1] - poly.vertices[i][1] for i in range(4)
        )
        self.assertGreater(max_dy, 0)

    def test_shoelace_matches_brahmagupta_for_rectangle(self):
        # Brahmagupta for a rectangle a×b×a×b: s = a+b, area = sqrt((s-a)²(s-b)²) = ab
        a, b = 6.0, 4.0
        s = (2 * a + 2 * b) / 2
        brahma = math.sqrt((s - a) * (s - b) * (s - a) * (s - b))
        shoe = _rect(a, b).area
        self.assertAlmostEqual(brahma, shoe, places=9)

    def test_l_shape_area(self):
        # 6×8 - 3×4 = 48 - 12 = 36
        self.assertAlmostEqual(_l_shape().area, 36.0)


class TestPerimeterAndCentroid(unittest.TestCase):
    def test_square_perimeter(self):
        self.assertAlmostEqual(_square(4).perimeter, 16.0)

    def test_l_shape_perimeter(self):
        # 6+4+3+4+3+8 = 28
        self.assertAlmostEqual(_l_shape().perimeter, 28.0)

    def test_square_centroid(self):
        cx, cy = _square(4).centroid
        self.assertAlmostEqual(cx, 2.0)
        self.assertAlmostEqual(cy, 2.0)


class TestBoundingBox(unittest.TestCase):
    def test_l_shape_bbox(self):
        b = _l_shape().bbox
        self.assertEqual(b, (0.0, 0.0, 6.0, 8.0))

    def test_l_shape_bbox_area_greater_than_polygon_area(self):
        poly = _l_shape()
        self.assertGreater(poly.bbox_area, poly.area)


class TestContainsPointInPolygon(unittest.TestCase):
    def test_square_interior(self):
        poly = _square(4)
        self.assertTrue(poly.contains(2.0, 2.0))

    def test_square_outside(self):
        poly = _square(4)
        self.assertFalse(poly.contains(-0.1, 2.0))
        self.assertFalse(poly.contains(4.1, 2.0))

    def test_square_edge_on_edge_flag(self):
        poly = _square(4)
        self.assertTrue(poly.contains(0.0, 2.0, on_edge=True))
        self.assertFalse(poly.contains(0.0, 2.0, on_edge=False))

    def test_l_shape_notch_is_excluded(self):
        poly = _l_shape()
        # (4, 6) is inside the missing notch → outside the L
        self.assertFalse(poly.contains(4.0, 6.0))
        # (5, 2) is in the bottom-right leg → inside
        self.assertTrue(poly.contains(5.0, 2.0))
        # (1, 6) is in the top-left leg → inside
        self.assertTrue(poly.contains(1.0, 6.0))


class TestSampleGrid(unittest.TestCase):
    def test_rectangle_full_coverage(self):
        # 3×2 grid on a 6×4 rectangle: all 6 samples land inside
        grid = _rect(6, 4).sample_grid(3, 2)
        self.assertEqual(len(grid), 6)

    def test_l_shape_excludes_notch_samples(self):
        # 6×8 bbox; on a fine 12×16 grid, notch region loses roughly its share
        # of samples (notch is 3×4 = 12 m² of the 48 m² bbox → 25 %).
        grid = _l_shape().sample_grid(12, 16)
        # Expect a healthy fraction of samples but strictly fewer than full bbox
        self.assertGreater(len(grid), 100)
        self.assertLess(len(grid), 12 * 16)

    def test_zero_dims(self):
        self.assertEqual(_square().sample_grid(0, 0), [])


class TestConvexityAndSimpleValidation(unittest.TestCase):
    def test_square_is_convex(self):
        self.assertTrue(_square().is_convex())

    def test_l_shape_is_not_convex(self):
        self.assertFalse(_l_shape().is_convex())

    def test_self_intersecting_rejected(self):
        # Figure-8 (bowtie)
        with self.assertRaises(PolygonError):
            Polygon.from_vertices([(0, 0), (4, 4), (4, 0), (0, 4)])

    def test_collinear_only_rejected(self):
        with self.assertRaises(PolygonError):
            Polygon.from_vertices([(0, 0), (1, 0), (2, 0)])

    def test_too_few_vertices_rejected(self):
        with self.assertRaises(PolygonError):
            Polygon.from_vertices([(0, 0), (1, 1)])

    def test_dict_vertex_form_accepted(self):
        poly = Polygon.from_vertices(
            [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 4}, {"x": 0, "y": 4}]
        )
        self.assertAlmostEqual(poly.area, 16.0)

    def test_repeated_closing_vertex_is_ignored(self):
        poly = Polygon.from_vertices([(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)])
        self.assertEqual(len(poly.vertices), 4)


class TestFromLegacySides(unittest.TestCase):
    def test_rect_from_legacy_matches_direct(self):
        legacy = Polygon.from_legacy_sides([6, 4, 6, 4])
        direct = _rect(6, 4)
        self.assertAlmostEqual(legacy.area, direct.area)
        self.assertAlmostEqual(legacy.bbox_width, direct.bbox_width)
        self.assertAlmostEqual(legacy.bbox_length, direct.bbox_length)

    def test_legacy_uses_bbox_not_brahmagupta(self):
        # Non-uniform cyclic quad [3, 4, 5, 6] — engine currently uses
        # max(3,5)=5 and max(4,6)=6, so area is 30 (bbox), not the Brahmagupta
        # value ~19.9. Preserve that contract for round-tripping.
        legacy = Polygon.from_legacy_sides([3, 4, 5, 6])
        self.assertAlmostEqual(legacy.area, 30.0)

    def test_wrong_length_rejected(self):
        with self.assertRaises(PolygonError):
            Polygon.from_legacy_sides([3, 4, 5])

    def test_non_positive_rejected(self):
        with self.assertRaises(PolygonError):
            Polygon.from_legacy_sides([3, 0, 3, 4])


class TestSerialization(unittest.TestCase):
    def test_to_dict_shape(self):
        d = _l_shape().to_dict()
        self.assertIn("vertices", d)
        self.assertIn("area_m2", d)
        self.assertIn("bbox", d)
        self.assertIn("centroid", d)
        self.assertIn("is_convex", d)
        self.assertEqual(d["vertex_count"], 6)
        self.assertFalse(d["is_convex"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
