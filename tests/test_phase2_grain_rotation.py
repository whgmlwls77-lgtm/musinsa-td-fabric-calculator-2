# -*- coding: utf-8 -*-
"""
test_phase2_grain_rotation.py
-----------------------------
Phase 2 sparrow 식서 사전 회전 단위 테스트 (angle 기반 재설계 2026-07-13).

배경:
  "식서 = 원단 길이방향 = 마카 가로" — 사장님 본질 (2026-05-08).
  회전각 = grain_rotation_deg(angle_deg) = -angle_deg (임의 각도 지원, 스냅 폐기).

검증:
  1. 세로 식서(90°) piece → -90° 회전 (식서 → X 통일)
  2. 가로 식서(0°) piece → 회전 없음 (이미 가로 = 정상)
  3. 바이어스(45°) piece → -45° 회전 (결방향 선을 X 에 정렬, 사장님 확정 2026-07-13)
  4. grain 없음 / angle_deg 없음 → 회전 없음
  5. polygons (mm shapely) 도 동일 회전 적용
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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

    def test_grain_y_rotates_minus_90(self):
        """세로 식서(90°) piece → -90° 회전. 가로 10, 세로 20 → 가로 20, 세로 10
        (angle 기반 재설계 2026-07-13: grain_rotation_deg(90) = -90)."""
        p = _piece("Y1", kind="STRAIGHT_GRAIN_Y", w=10, h=20)
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(len(out), 1)
        new_coords = out[0]["coords_cm"]
        # 회전 후 bbox 크기 swap (±90 어느 쪽이든 직사각형 bbox 동일)
        xs = [c[0] for c in new_coords]
        ys = [c[1] for c in new_coords]
        new_w = max(xs) - min(xs)
        new_h = max(ys) - min(ys)
        self.assertAlmostEqual(new_w, 20.0, places=2, msg=f"회전 후 폭: {new_w}")
        self.assertAlmostEqual(new_h, 10.0, places=2, msg=f"회전 후 높이: {new_h}")
        # grain.kind 갱신 — 회전 후 X (마카 가로 통일)
        self.assertEqual(out[0]["grain"]["kind"], "STRAIGHT_GRAIN_X")
        self.assertEqual(out[0]["grain"]["angle_deg"], 0.0)
        self.assertEqual(out[0]["grain"]["_rotated_by"], -90.0)

    def test_grain_x_unchanged(self):
        """STRAIGHT_GRAIN_X piece → 회전 없음 (이미 식서 가로 = 정상)."""
        p = _piece("X1", kind="STRAIGHT_GRAIN_X", w=10, h=20)
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(out[0]["coords_cm"], p["coords_cm"])
        self.assertEqual(out[0]["grain"]["kind"], "STRAIGHT_GRAIN_X")
        self.assertNotIn("_rotated_by", out[0]["grain"])

    def test_grain_bias_rotates_minus_45(self):
        """바이어스(45°) piece → -45° 회전 (결방향 선을 X 에 정렬).
        사장님 확정 2026-07-13: 바이어스 별도 처리 X — 그대로 정렬."""
        p = _piece("B1", kind="BIAS", w=10, h=20)
        p["grain"]["angle_deg"] = 45.0
        out, _ = _align_pieces_to_grain([p], polygons=None)
        # 회전됨 (좌표 변경) + kind→X + _rotated_by=-45
        self.assertNotEqual(out[0]["coords_cm"], p["coords_cm"])
        self.assertEqual(out[0]["grain"]["kind"], "STRAIGHT_GRAIN_X")
        self.assertEqual(out[0]["grain"]["angle_deg"], 0.0)
        self.assertAlmostEqual(out[0]["grain"]["_rotated_by"], -45.0, places=2)

    def test_grain_none_no_rotation(self):
        """grain 없음 → 회전 없음 (DXF 그대로)."""
        p = _piece("U1", kind="STRAIGHT_GRAIN_X", w=10, h=20)
        p["grain"] = None
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(out[0]["coords_cm"], p["coords_cm"])

    def test_grain_missing_angle_no_rotation(self):
        """angle_deg 없음 → 회전 없음."""
        p = _piece("U2", kind="STRAIGHT_GRAIN_X", w=10, h=20)
        p["grain"] = {"kind": "STRAIGHT_GRAIN_X", "raw_layer": "7"}  # angle_deg 없음
        out, _ = _align_pieces_to_grain([p], polygons=None)
        self.assertEqual(out[0]["coords_cm"], p["coords_cm"])

    def test_polygons_rotate_with_pieces(self):
        """polygons (mm shapely) 도 동일 회전 (Y → X 정정 후)."""
        coords_mm = [(0, 0), (100, 0), (100, 200), (0, 200)]  # 100 × 200 mm
        poly = ShapelyPolygon(coords_mm)
        p = _piece("Y2", kind="STRAIGHT_GRAIN_Y", w=10, h=20)
        out, out_polys = _align_pieces_to_grain([p], polygons={"Y2": poly})
        rotated_poly = out_polys["Y2"]
        # 회전 후 bbox 크기 swap (200×100)
        minx, miny, maxx, maxy = rotated_poly.bounds
        self.assertAlmostEqual(maxx - minx, 200.0, places=1)
        self.assertAlmostEqual(maxy - miny, 100.0, places=1)


class TestRegression(unittest.TestCase):
    """기존 STRAIGHT_GRAIN_X 일관 piece 들에 영향 없음 (정상 식서)."""

    def test_all_x_pieces_unchanged(self):
        pieces = [_piece(f"P{i}", "STRAIGHT_GRAIN_X") for i in range(5)]
        out, _ = _align_pieces_to_grain(pieces, polygons=None)
        for orig, new in zip(pieces, out):
            self.assertEqual(orig["coords_cm"], new["coords_cm"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
