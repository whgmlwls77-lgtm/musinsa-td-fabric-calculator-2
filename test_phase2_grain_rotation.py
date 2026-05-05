# -*- coding: utf-8 -*-
"""
test_phase2_grain_rotation.py
-----------------------------
Phase 2 sparrow 식서 사전 회전 단위 테스트 (사장님 결정 2026-05-05).

배경:
  "식서 못 읽으면 요척 의미 없음" — 사장님 본질.
  sparrow 호출 전 grain.kind 에 따라 polygon 을 회전해 식서를 Y축으로 통일.

검증:
  1. STRAIGHT_GRAIN_X piece → 90° 회전 적용 (식서 X → Y)
  2. STRAIGHT_GRAIN_Y piece → 회전 없음 (이미 Y)
  3. BIAS piece → 회전 없음 (사선 유지)
  4. UNKNOWN/NONSTANDARD → 회전 없음 (caller 처리)
  5. polygons (mm shapely) 도 동일 회전 적용
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from shapely.geometry import Polygon as ShapelyPolygon

from auto_nesting_v2 import _align_pieces_to_grain


def _piece(pid: str, kind: str, w: float = 10.0, h: float = 20.0) -> dict:
    """가로 w, 세로 h 직사각형 piece (식서 종류 다양)."""
    return {
        "piece_id": pid,
        "piece_name": pid,
        "size": "L",
        "quantity": 1,
        "mirror": None,
        "coords_cm": [(0, 0), (w, 0), (w, h), (0, h)],
        "width_cm": w,
        "height_cm": h,
        "grain": {
            "kind": kind,
            "angle_deg": 0.0 if kind == "STRAIGHT_GRAIN_X" else 90.0,
            "length_mm": 100.0,
            "raw_layer": "7",
        },
    }


class TestGrainRotation(unittest.TestCase):

    def test_grain_x_rotates_90(self):
        """STRAIGHT_GRAIN_X piece → 90° 회전. 가로 10, 세로 20 → 가로 20, 세로 10."""
        p = _piece("X1", kind="STRAIGHT_GRAIN_X", w=10, h=20)
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(len(out), 1)
        new_coords = out[0]["coords_cm"]
        # 회전 후 bbox 크기 swap
        xs = [c[0] for c in new_coords]
        ys = [c[1] for c in new_coords]
        new_w = max(xs) - min(xs)
        new_h = max(ys) - min(ys)
        self.assertAlmostEqual(new_w, 20.0, places=2, msg=f"회전 후 폭: {new_w}")
        self.assertAlmostEqual(new_h, 10.0, places=2, msg=f"회전 후 높이: {new_h}")
        # grain.kind 갱신
        self.assertEqual(out[0]["grain"]["kind"], "STRAIGHT_GRAIN_Y")
        self.assertEqual(out[0]["grain"]["angle_deg"], 90.0)
        self.assertEqual(out[0]["grain"]["_rotated_by"], 90.0)

    def test_grain_y_unchanged(self):
        """STRAIGHT_GRAIN_Y piece → 회전 없음."""
        p = _piece("Y1", kind="STRAIGHT_GRAIN_Y", w=10, h=20)
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(out[0]["coords_cm"], p["coords_cm"])
        self.assertEqual(out[0]["grain"]["kind"], "STRAIGHT_GRAIN_Y")
        self.assertNotIn("_rotated_by", out[0]["grain"])

    def test_grain_bias_unchanged(self):
        """BIAS piece → 회전 없음 (사선 유지)."""
        p = _piece("B1", kind="BIAS", w=10, h=20)
        p["grain"]["angle_deg"] = 45.0
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(out[0]["coords_cm"], p["coords_cm"])
        self.assertEqual(out[0]["grain"]["kind"], "BIAS")

    def test_grain_unknown_unchanged(self):
        """UNKNOWN piece → 회전 없음."""
        p = _piece("U1", kind="UNKNOWN", w=10, h=20)
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(out[0]["coords_cm"], p["coords_cm"])

    def test_polygons_rotate_with_pieces(self):
        """polygons (mm shapely) 도 동일 회전."""
        coords_mm = [(0, 0), (100, 0), (100, 200), (0, 200)]  # 100 × 200 mm
        poly = ShapelyPolygon(coords_mm)
        p = _piece("X2", kind="STRAIGHT_GRAIN_X", w=10, h=20)
        out, out_polys = _align_pieces_to_grain([p], polygons={"X2": poly})
        rotated_poly = out_polys["X2"]
        # 회전 후 bbox 크기 swap
        minx, miny, maxx, maxy = rotated_poly.bounds
        self.assertAlmostEqual(maxx - minx, 200.0, places=1)
        self.assertAlmostEqual(maxy - miny, 100.0, places=1)


class TestRegression(unittest.TestCase):
    """기존 STRAIGHT_GRAIN_Y 일관 piece 들에 영향 없음."""

    def test_all_y_pieces_unchanged(self):
        pieces = [_piece(f"P{i}", "STRAIGHT_GRAIN_Y") for i in range(5)]
        out, _ = _align_pieces_to_grain(pieces, polygons=None)
        for orig, new in zip(pieces, out):
            self.assertEqual(orig["coords_cm"], new["coords_cm"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
