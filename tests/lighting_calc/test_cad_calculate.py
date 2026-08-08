"""
Unit tests for :mod:`luxscale.lighting_calc.cad_calculate` and the
``POST /cad_calc`` Flask endpoint (plan 06 phase A).

Runs with plain ``unittest``::

    python -m unittest tests.lighting_calc.test_cad_calculate
"""

from __future__ import annotations

import json
import math
import unittest

from luxscale.lighting_calc.cad_calculate import (
    _dominant_edge_orientation,
    _rotated_bbox,
    build_equivalent_rectangle,
    polygon_from_payload,
)
from luxscale.lighting_calc.polygon import Polygon, PolygonError


class TestEquivalentRectangle(unittest.TestCase):
    def test_square_polygon_returns_same_square(self):
        poly = Polygon.from_vertices([(0, 0), (4, 0), (4, 4), (0, 4)])
        w, l, theta = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, poly.area, places=9)
        self.assertAlmostEqual(w, 4.0, places=9)
        self.assertAlmostEqual(l, 4.0, places=9)
        self.assertAlmostEqual(theta, 0.0, places=9)

    def test_rectangle_preserves_dims(self):
        poly = Polygon.from_vertices([(0, 0), (6, 0), (6, 4), (0, 4)])
        w, l, theta = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, poly.area, places=9)
        self.assertAlmostEqual(w, 6.0, places=9)
        self.assertAlmostEqual(l, 4.0, places=9)
        self.assertAlmostEqual(theta, 0.0, places=9)

    def test_l_shape_area_matches_polygon_not_bbox(self):
        # L-shape area = 36, bbox area = 48
        poly = Polygon.from_vertices(
            [(0, 0), (6, 0), (6, 4), (3, 4), (3, 8), (0, 8)]
        )
        w, l, theta = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, 36.0, places=9)
        self.assertNotAlmostEqual(w * l, 48.0, places=1)
        # Aspect ratio inherited from the 6×8 axis-aligned bbox (0.75)
        # since all L-shape edges align with x/y axes → orientation = 0
        self.assertAlmostEqual(w / l, 6.0 / 8.0, places=9)
        self.assertAlmostEqual(theta, 0.0, places=6)


class TestDominantEdgeOrientation(unittest.TestCase):
    def test_axis_aligned_rectangle_returns_zero(self):
        poly = Polygon.from_vertices([(0, 0), (6, 0), (6, 4), (0, 4)])
        self.assertAlmostEqual(_dominant_edge_orientation(poly), 0.0, places=6)

    def test_rotated_rectangle_recovers_angle(self):
        theta = math.radians(30)
        c, s = math.cos(theta), math.sin(theta)
        corners = [(0.0, 0.0), (6.0, 0.0), (6.0, 8.0), (0.0, 8.0)]
        rotated = [(c * x - s * y, s * x + c * y) for x, y in corners]
        poly = Polygon.from_vertices(rotated)
        detected = _dominant_edge_orientation(poly)
        # Detected in [0, pi/2); 30° should snap to bin 30 (±1° due to binning)
        self.assertAlmostEqual(math.degrees(detected), 30.0, delta=1.0)

    def test_axis_aligned_l_shape_returns_zero(self):
        poly = Polygon.from_vertices(
            [(0, 0), (6, 0), (6, 4), (3, 4), (3, 8), (0, 8)]
        )
        self.assertAlmostEqual(_dominant_edge_orientation(poly), 0.0, places=6)


class TestRotatedRectangleEquivalentRectangle(unittest.TestCase):
    def test_rotated_6x8_recovers_original_dims(self):
        """
        A 6×8 rectangle rotated by 30° must have equivalent rectangle with
        aspect ratio 6/8 (or 8/6 modulo axis swap) — NOT the inflated
        axis-aligned bbox ratio (~9.196/9.928 ≈ 0.926).
        """
        theta = math.radians(30)
        c, s = math.cos(theta), math.sin(theta)
        corners = [(0.0, 0.0), (6.0, 0.0), (6.0, 8.0), (0.0, 8.0)]
        rotated = [(c * x - s * y, s * x + c * y) for x, y in corners]
        poly = Polygon.from_vertices(rotated)
        w, l, orient = build_equivalent_rectangle(poly)
        self.assertAlmostEqual(w * l, 48.0, places=6)
        aspect = w / l
        recovered = min(aspect, 1.0 / aspect)
        self.assertAlmostEqual(recovered, 0.75, delta=0.02)
        self.assertAlmostEqual(math.degrees(orient), 30.0, delta=1.0)

    def test_regression_axis_aligned_bbox_would_have_given_wrong_ratio(self):
        """
        Sanity: confirm the axis-aligned bbox of the rotated 6×8 really is
        ~9.2×9.9 (r ≈ 0.926), which is the bug we fixed.
        """
        theta = math.radians(30)
        c, s = math.cos(theta), math.sin(theta)
        corners = [(0.0, 0.0), (6.0, 0.0), (6.0, 8.0), (0.0, 8.0)]
        rotated = [(c * x - s * y, s * x + c * y) for x, y in corners]
        poly = Polygon.from_vertices(rotated)
        # Raw axis-aligned bbox ratio would be ~0.926 — the bug case
        naive_ratio = poly.bbox_width / poly.bbox_length
        self.assertAlmostEqual(naive_ratio, 9.196 / 9.928, delta=0.01)
        # But the rotated bbox (used by the fix) recovers 6×8
        bw, bl = _rotated_bbox(poly, math.radians(30))
        self.assertAlmostEqual(min(bw, bl), 6.0, delta=0.01)
        self.assertAlmostEqual(max(bw, bl), 8.0, delta=0.01)


class TestRotatedLShapeEquivalentRectangle(unittest.TestCase):
    """
    The critical case: a *rotated non-rectangular* polygon. This is where the
    orientation fix and the fill-ratio calculation have to work together —
    the histogram must lock onto the room's true wall angle from a concave
    shape (an internal notch), and the fill ratio must still come out
    ≈0.75 (not inflated or deflated) once the rotation is corrected for.
    """

    L_VERTS = [
        (0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (3.0, 4.0), (3.0, 8.0), (0.0, 8.0),
    ]  # A = 36, axis-aligned bbox = 6 × 8

    def _rotate(self, theta_deg: float) -> Polygon:
        theta = math.radians(theta_deg)
        c, s = math.cos(theta), math.sin(theta)
        return Polygon.from_vertices(
            [(c * x - s * y, s * x + c * y) for x, y in self.L_VERTS]
        )

    def test_rotated_l_shape_area_preserved(self):
        for angle_deg in (20.0, 25.0, 35.0, 40.0):
            with self.subTest(angle_deg=angle_deg):
                poly = self._rotate(angle_deg)
                self.assertAlmostEqual(poly.area, 36.0, places=6)

    def test_rotated_l_shape_recovers_orientation(self):
        for angle_deg in (20.0, 25.0, 30.0, 35.0, 40.0):
            with self.subTest(angle_deg=angle_deg):
                poly = self._rotate(angle_deg)
                _, _, orient = build_equivalent_rectangle(poly)
                self.assertAlmostEqual(
                    math.degrees(orient), angle_deg, delta=1.0,
                    msg=f"orientation should be recovered from a rotated L-shape at {angle_deg}°",
                )

    def test_rotated_l_shape_recovers_aspect_ratio(self):
        """
        After the orientation fix, the rotated L-shape's equivalent rectangle
        must have aspect ratio 6/8 (from the axis-aligned bbox of the un-rotated
        L-shape), NOT the inflated axis-aligned bbox aspect ratio of the
        rotated version.
        """
        for angle_deg in (20.0, 25.0, 30.0, 35.0):
            with self.subTest(angle_deg=angle_deg):
                poly = self._rotate(angle_deg)
                w, l, _ = build_equivalent_rectangle(poly)
                self.assertAlmostEqual(w * l, 36.0, places=6)
                aspect = min(w / l, l / w)
                self.assertAlmostEqual(
                    aspect, 6.0 / 8.0, delta=0.02,
                    msg=f"aspect ratio should recover to 6/8 for a rotated L-shape at {angle_deg}°",
                )

    def test_rotated_l_shape_fill_ratio_is_polygon_geometry_not_rotation_artifact(self):
        """
        The oriented-bbox fill ratio for an L-shape must be ≈0.75 (its true
        polygon-vs-bbox ratio) regardless of rotation angle. If we had used
        the axis-aligned bbox for fill_ratio, this test would drift with the
        rotation angle — that would be the false-positive path.
        """
        for angle_deg in (20.0, 25.0, 30.0, 35.0):
            with self.subTest(angle_deg=angle_deg):
                poly = self._rotate(angle_deg)
                _, _, orient = build_equivalent_rectangle(poly)
                bw, bl = _rotated_bbox(poly, orient)
                fill_ratio = poly.area / (bw * bl)
                self.assertAlmostEqual(
                    fill_ratio, 0.75, delta=0.01,
                    msg=f"fill_ratio must be geometry-only (~0.75) at {angle_deg}° — "
                        "if this drifts with angle we're computing α on the axis-aligned bbox",
                )

    def test_sub_degree_rotation_stays_within_known_quantization_bias(self):
        """
        Pins down the residual bias from the 1°-wide histogram bins.

        The current ``_dominant_edge_orientation`` uses integer-degree bins
        (n_bins = 90). For a rotation angle that is NOT close to an integer
        degree, the detected orientation snaps to the nearest bin — leaving
        a residual rotation of up to ~0.5° between the equivalent-rectangle
        frame and the room's true wall direction. That residual inflates
        the oriented bbox by a small amount (≤ ~1 % on the 6×8 L-shape at
        typical CAD scales) and therefore deflates ``fill_ratio`` by the
        same amount below the geometry-only 0.75 baseline.

        This test locks in that ≤ 1 % ceiling. A refactor that tightens the
        histogram (e.g. sub-degree bins, quadratic-interpolated peak, or a
        continuous rotating-calipers pass) should keep this passing with
        room to spare; a regression to a coarser method will trip it.
        """
        angle_deg = 23.7  # non-integer — deliberately between bins 23 and 24
        poly = self._rotate(angle_deg)

        w, l, orient = build_equivalent_rectangle(poly)
        detected_deg = math.degrees(orient)
        self.assertAlmostEqual(
            detected_deg, angle_deg, delta=1.0,
            msg="orientation must land in an adjacent bin (±1° for 1°-wide bins)",
        )

        bw, bl = _rotated_bbox(poly, orient)
        fill_ratio = poly.area / (bw * bl)
        # 0.75 is the geometry-only baseline. Current quantization bias
        # gives fill_ratio ≈ 0.7444 at 23.7° (~0.7 % relative deflation);
        # 1 % is the ceiling we hold the line at.
        rel_error = abs(fill_ratio - 0.75) / 0.75
        self.assertLess(
            rel_error, 0.01,
            msg=(
                f"sub-degree quantization bias exceeded 1 % ceiling: "
                f"fill_ratio={fill_ratio:.6f}, expected ~0.75, rel_error={rel_error:.4f}"
            ),
        )
        # And the direction of the bias must be downward — an inflated
        # bbox area yields a smaller fill_ratio, never a larger one.
        self.assertLessEqual(
            fill_ratio, 0.75 + 1e-9,
            msg="fill_ratio must never exceed the geometry-only 0.75 baseline",
        )


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

    def test_l_shape_emits_fill_ratio_and_effective_samples(self):
        """Concave rooms expose fill_ratio + Phase-B clipped sample count; no optimism warning."""
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

        self.assertIn("fill_ratio", meta["polygon"])
        alpha = meta["polygon"]["fill_ratio"]
        # L-shape: A=36, oriented bbox=48 → α = 0.75 exactly (axes align).
        self.assertAlmostEqual(alpha, 36.0 / 48.0, places=3)

        self.assertIn("orientation_deg", meta["polygon"])
        self.assertAlmostEqual(meta["polygon"]["orientation_deg"], 0.0, places=3)

        # Phase B: optimism warning is retired; clipped sampling is live.
        notes = meta.get("engine_notes", [])
        for n in notes:
            self.assertNotIn("may over-report", n.lower(), msg=n)
        self.assertTrue(
            any("polygon-clipped" in n.lower() for n in notes),
            f"expected Phase-B polygon-clipped note in engine_notes, got {notes!r}",
        )
        self.assertIn("effective_sample_count", meta["polygon"])
        n_eff = meta["polygon"]["effective_sample_count"]
        # G=12 for α=0.75 → 144 bbox candidates; ~α·G² ≈ 108 survive.
        self.assertGreater(n_eff, 60)
        self.assertLess(n_eff, 144)

    def test_rectangle_full_fill_and_phase_b_note(self):
        """α = 1.0 rectangles keep full fill and still advertise Phase-B clipping."""
        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": [[0, 0], [6, 0], [6, 4], [0, 4]]},
                "height": 3.0,
                "place": "Office",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        meta = r.get_json()["calculation_meta"]
        self.assertAlmostEqual(meta["polygon"]["fill_ratio"], 1.0, places=6)
        notes = meta.get("engine_notes", [])
        for n in notes:
            self.assertNotIn("may over-report", n.lower(), msg=n)
        self.assertEqual(
            meta["polygon"].get("effective_sample_count"),
            meta.get("workplane_grid_n", 10) ** 2,
        )

    def test_rotated_rectangle_reports_orientation_and_full_fill(self):
        """A rotated true rectangle keeps α=1 and reports its rotation angle."""
        theta = math.radians(30)
        c, s = math.cos(theta), math.sin(theta)
        corners = [(0.0, 0.0), (6.0, 0.0), (6.0, 8.0), (0.0, 8.0)]
        rotated = [[c * x - s * y, s * x + c * y] for x, y in corners]
        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": rotated},
                "height": 3.0,
                "place": "Office",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        meta = r.get_json()["calculation_meta"]
        # α = A / oriented_bbox_area = 48 / 48 = 1.0
        self.assertAlmostEqual(meta["polygon"]["fill_ratio"], 1.0, delta=1e-3)
        # Orientation recovered to ~30° (within histogram bin resolution)
        self.assertAlmostEqual(
            meta["polygon"]["orientation_deg"], 30.0, delta=1.0
        )
        eq = meta["equivalent_rectangle"]
        self.assertAlmostEqual(eq["width_m"] * eq["length_m"], 48.0, delta=0.1)

    def test_rotated_l_shape_end_to_end(self):
        """
        The critical combined case, exercised through the /cad_calc endpoint:
        rotate the canonical L-shape by 25° and confirm the response reports
        BOTH the correct orientation AND the correct fill_ratio (~0.75).
        """
        angle_deg = 25.0
        theta = math.radians(angle_deg)
        c, s = math.cos(theta), math.sin(theta)
        l_verts = [
            (0.0, 0.0), (6.0, 0.0), (6.0, 4.0),
            (3.0, 4.0), (3.0, 8.0), (0.0, 8.0),
        ]
        rotated = [[c * x - s * y, s * x + c * y] for x, y in l_verts]

        r = self.client.post(
            "/cad_calc",
            json={
                "polygon": {"vertices": rotated},
                "height": 3.0,
                "place": "Office",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        meta = r.get_json()["calculation_meta"]

        self.assertAlmostEqual(meta["polygon"]["area_m2"], 36.0, places=6)
        self.assertAlmostEqual(
            meta["polygon"]["orientation_deg"], angle_deg, delta=1.0,
            msg="rotated L-shape must expose its rotation angle in polygon.orientation_deg",
        )
        self.assertAlmostEqual(
            meta["polygon"]["fill_ratio"], 0.75, delta=0.01,
            msg="rotated L-shape fill_ratio must remain 0.75 (polygon geometry, "
                "not a rotation artifact of the axis-aligned bbox)",
        )
        eq = meta["equivalent_rectangle"]
        self.assertAlmostEqual(eq["width_m"] * eq["length_m"], 36.0, places=4)
        self.assertAlmostEqual(
            eq["orientation_deg"], angle_deg, delta=1.0,
        )

        # Phase B: clipped sampling live; optimism warning retired.
        notes = meta.get("engine_notes", [])
        for n in notes:
            self.assertNotIn("may over-report", n.lower(), msg=n)
        self.assertIn("effective_sample_count", meta["polygon"])
        self.assertGreater(meta["polygon"]["effective_sample_count"], 60)


class TestPolygonSimplicityGuard(unittest.TestCase):
    """The O(N^2) self-intersection check must skip above the ceiling."""

    def test_large_convex_polygon_ingests_without_o_n_squared_cost(self):
        """A 600-vertex circle would take ~200ms under the O(N^2) sweep;
        with the guard rail it should ingest without raising and without
        performing the check (correctness is delegated to the caller)."""
        n = 600
        verts = [
            (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n))
            for i in range(n)
        ]
        poly = Polygon.from_vertices(verts)
        self.assertEqual(len(poly.vertices), n)
        self.assertGreater(poly.area, 3.0)  # ~π for unit circle
        self.assertLess(poly.area, 3.2)

    def test_small_self_intersecting_polygon_still_rejected(self):
        """Below the ceiling, the check must still fire."""
        with self.assertRaises(PolygonError):
            Polygon.from_vertices([(0, 0), (4, 4), (4, 0), (0, 4)])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
