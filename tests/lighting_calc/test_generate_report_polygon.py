"""
Tests for polygon-aware PDF room drawing helpers.
"""
from __future__ import annotations

import unittest


class TestEngineRoomDims(unittest.TestCase):
    def test_from_sides_matches_engine(self):
        from generate_report import _engine_room_dims

        # sides = [width_eq, length_eq, ...] → engine x = max(a,c), y = max(b,d)
        dims = _engine_room_dims({"sides": [6.0, 4.0, 6.0, 4.0]})
        self.assertAlmostEqual(dims[0], 6.0)
        self.assertAlmostEqual(dims[1], 4.0)

    def test_from_equivalent_rectangle_sides_used(self):
        from generate_report import _engine_room_dims

        dims = _engine_room_dims(
            {
                "calculation_meta": {
                    "equivalent_rectangle": {
                        "width_m": 5.196,
                        "length_m": 6.928,
                        "sides_used": [5.196, 6.928, 5.196, 6.928],
                    }
                }
            }
        )
        self.assertAlmostEqual(dims[0], 5.196, places=3)
        self.assertAlmostEqual(dims[1], 6.928, places=3)


class TestMakeRoomDrawingPolygon(unittest.TestCase):
    def test_polygon_l_shape_returns_png(self):
        from generate_report import make_room_drawing

        payload = {
            "project_name": "L-shape test",
            "height": 3.0,
            "sides": [5.196, 6.928, 5.196, 6.928],
            "length": 6.928,
            "width": 5.196,
            "calculation_meta": {
                "geometry_version": 2,
                "polygon": {
                    "vertices": [
                        [0, 0], [6, 0], [6, 4], [3, 4], [3, 8], [0, 8],
                    ],
                    "area_m2": 36.0,
                    "perimeter_m": 28.0,
                    "vertex_count": 6,
                    "fill_ratio": 0.75,
                    "orientation_deg": 0.0,
                },
                "equivalent_rectangle": {
                    "width_m": 5.196,
                    "length_m": 6.928,
                    "orientation_deg": 0.0,
                    "sides_used": [5.196, 6.928, 5.196, 6.928],
                },
            },
            "results": [
                {
                    "is_compliant": True,
                    "Fixtures": 6,
                    "layout_nx": 3,
                    "layout_ny": 2,
                    "Spacing X (m)": 1.73,
                    "Spacing Y (m)": 3.46,
                    "beam_angle_deg": 60,
                }
            ],
        }
        buf = make_room_drawing(payload, width_pt=200, height_pt=140)
        data = buf.getvalue()
        self.assertGreater(len(data), 1000)
        self.assertTrue(data[:8].startswith(b"\x89PNG"), msg="expected PNG magic")

    def test_rectangle_payload_still_returns_png(self):
        from generate_report import make_room_drawing

        payload = {
            "project_name": "Rect test",
            "height": 3.0,
            "sides": [6.0, 4.0, 6.0, 4.0],
            "results": [
                {
                    "is_compliant": True,
                    "Fixtures": 6,
                    "layout_nx": 3,
                    "layout_ny": 2,
                    "Spacing X (m)": 2.0,
                    "Spacing Y (m)": 2.0,
                    "beam_angle_deg": 60,
                }
            ],
        }
        buf = make_room_drawing(payload, width_pt=200, height_pt=140)
        data = buf.getvalue()
        self.assertGreater(len(data), 1000)
        self.assertTrue(data[:8].startswith(b"\x89PNG"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
