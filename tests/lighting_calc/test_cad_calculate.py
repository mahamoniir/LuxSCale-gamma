"""
Unit tests for :mod:`luxscale.lighting_calc.cad_calculate` and the
``POST /cad_calc`` Flask endpoint (plan 06 phase A).

Runs with plain ``unittest``::

    python -m unittest tests.lighting_calc.test_cad_calculate
"""

from __future__ import annotations

import json
import unittest

from luxscale.lighting_calc.cad_calculate import (
    build_equivalent_rectangle,
    polygon_from_payload,
)
from luxscale.lighting_calc.polygon import Polygon, PolygonError


class TestEquivalentRectangle(unittest.TestCase):
    def test_square_polygon_returns_same_square(self):
        poly = Polygon.from_vertices([(0, 0), (4, 0), (4, 4), (0, 4)])
        w, l = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, poly.area, places=9)
        self.assertAlmostEqual(w, 4.0, places=9)
        self.assertAlmostEqual(l, 4.0, places=9)

    def test_rectangle_preserves_dims(self):
        poly = Polygon.from_vertices([(0, 0), (6, 0), (6, 4), (0, 4)])
        w, l = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, poly.area, places=9)
        self.assertAlmostEqual(w, 6.0, places=9)
        self.assertAlmostEqual(l, 4.0, places=9)

    def test_l_shape_area_matches_polygon_not_bbox(self):
        # L-shape area = 36, bbox area = 48
        poly = Polygon.from_vertices(
            [(0, 0), (6, 0), (6, 4), (3, 4), (3, 8), (0, 8)]
        )
        w, l = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, 36.0, places=9)
        self.assertNotAlmostEqual(w * l, 48.0, places=1)
        # Aspect ratio inherited from the 6×8 bbox (0.75)
        self.assertAlmostEqual(w / l, 6.0 / 8.0, places=9)


class TestPolygonFromPayload(unittest.TestCase):
    def test_nested_object_form(self):
        poly = polygon_from_payload(
            {"polygon": {"vertices": [[0, 0], [4, 0], [4, 4], [0, 4]]}}
        )
        self.assertAlmostEqual(poly.area, 16.0)

    def test_nested_list_form(self):
        poly = polygon_from_payload(
            {"polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]}
        )
        self.assertAlmostEqual(poly.area, 16.0)

    def test_top_level_vertices_form(self):
        poly = polygon_from_payload({"vertices": [[0, 0], [4, 0], [4, 4], [0, 4]]})
        self.assertAlmostEqual(poly.area, 16.0)

    def test_missing_rejected(self):
        with self.assertRaises(PolygonError):
            polygon_from_payload({"height": 3})

    def test_non_dict_rejected(self):
        with self.assertRaises(PolygonError):
            polygon_from_payload("not a dict")  # type: ignore[arg-type]


class TestCadCalcEndpoint(unittest.TestCase):
    """End-to-end smoke against the Flask test client. Skipped if Flask can't import."""

    @classmethod
    def setUpClass(cls):
        try:
            from app import app  # noqa: WPS433 — importing the live Flask app
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"Flask app import failed: {exc}") from exc
        app.testing = True
        cls.client = app.test_client()

    def test_missing_polygon_returns_400(self):
        r = self.client.post(
            "/cad_calc",
            json={"height": 3.0, "place": "Office"},
        )
        self.assertEqual(r.status_code, 400)
        body = r.get_json() or {}
        self.assertEqual(body.get("status"), "error")
        self.assertIn("polygon", body.get("message", "").lower())

    def test_missing_height_returns_400(self):
        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                "place": "Office",
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_no_place_and_no_standard_returns_400(self):
        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                "height": 3.0,
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_self_intersecting_polygon_returns_400(self):
        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": [[0, 0], [4, 4], [4, 0], [0, 4]]},
                "height": 3.0,
                "place": "Office",
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_rectangle_polygon_matches_legacy_calculate(self):
        """Sanity check: same rectangle via /cad_calc vs /calculate should agree on area."""
        payload_new = {
            "polygon": {"vertices": [[0, 0], [6, 0], [6, 4], [0, 4]]},
            "height": 3.0,
            "place": "Office",
        }
        r_new = self.client.post("/cad_calc", json=payload_new)
        self.assertEqual(r_new.status_code, 200, r_new.get_data(as_text=True))
        body_new = r_new.get_json()
        self.assertEqual(body_new["status"], "success")
        meta = body_new["calculation_meta"]
        self.assertEqual(meta.get("geometry_version"), 2)
        self.assertIn("polygon", meta)
        self.assertAlmostEqual(meta["polygon"]["area_m2"], 24.0, places=6)
        # Equivalent rectangle for a real rectangle equals the rectangle itself
        eq = meta["equivalent_rectangle"]
        self.assertAlmostEqual(eq["width_m"] * eq["length_m"], 24.0, places=6)

        payload_legacy = {
            "sides": [6, 4, 6, 4],
            "height": 3.0,
            "place": "Office",
        }
        r_legacy = self.client.post("/calculate", json=payload_legacy)
        self.assertEqual(r_legacy.status_code, 200, r_legacy.get_data(as_text=True))
        body_legacy = r_legacy.get_json()
        self.assertEqual(body_legacy["status"], "success")

        # Result count and top result should agree closely (same physical room)
        self.assertEqual(
            len(body_new["results"]),
            len(body_legacy["results"]),
            msg="new endpoint should produce same number of solutions as legacy for a rectangle",
        )

    def test_l_shape_uses_polygon_area_not_bbox_area(self):
        """L-shape must be treated with its true area (36), not bbox area (48)."""
        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": [[0, 0], [6, 0], [6, 4], [3, 4], [3, 8], [0, 8]]},
                "height": 3.0,
                "place": "Office",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        meta = body["calculation_meta"]
        self.assertAlmostEqual(meta["polygon"]["area_m2"], 36.0, places=6)
        eq = meta["equivalent_rectangle"]
        self.assertAlmostEqual(eq["width_m"] * eq["length_m"], 36.0, places=6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
