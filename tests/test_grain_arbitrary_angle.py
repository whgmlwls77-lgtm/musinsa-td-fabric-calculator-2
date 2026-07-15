# -*- coding: utf-8 -*-
"""
test_grain_arbitrary_angle.py
-----------------------------
결방향(식서) 로직 근본 재설계 검증 (사장님 확정 2026-07-13).

배경 (사장님 실증 MMCDJ706):
  협력사가 조각을 임의 각도로 CAD 배치 + 결방향 선은 조각 실제 축 표시.
  BLK_22_1(107.5°) / BLK_26_1(111.5°) 등 이전 NONSTANDARD 오분류.
  → grain_rotation_deg(angle) = -angle 로 임의 각도 정렬.

검증:
  1. grain_rotation_deg = -angle (표준 + 임의 각도)
  2. 임의 각도 5종 회전 후 결방향 선이 X축(0°)에 정렬
  3. get_alignment_rotation 이 kind 무관 angle 기반 동작
  4. _align_pieces_to_grain 이 임의 각도 piece 를 회전 (NONSTANDARD 개념 제거)
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grain_extractor import grain_rotation_deg, get_alignment_rotation
from auto_nesting_v2 import _align_pieces_to_grain


ARBITRARY_ANGLES = [30.0, 60.0, 107.5, 135.0, 165.0]


def _rotate_point(x: float, y: float, deg: float) -> tuple[float, float]:
    r = math.radians(deg)
    return (x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r))


def _grain_piece(pid: str, grain_angle: float) -> dict:
    """결방향 선이 grain_angle° 인 직사각형 piece.

    coords_cm 은 그 각도로 기울어진 조각 (결방향 선 = 조각 세로 축 가정).
    검증 목적상 조각 자체를 grain_angle 로 회전한 직사각형으로 둔다.
    """
    base = [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0)]
    coords = [_rotate_point(x, y, grain_angle) for x, y in base]
    return {
        "piece_id": pid,
        "piece_name": pid,
        "size": "L",
        "quantity": 1,
        "coords_cm": coords,
        "width_cm": 10.0,
        "height_cm": 20.0,
        "grain": {
            "kind": "NONSTANDARD",  # 이전 오분류 — 새 로직은 kind 무시
            "angle_deg": grain_angle,
            "length_mm": 100.0,
            "raw_layer": "7",
        },
    }


class TestGrainRotationDeg(unittest.TestCase):

    def test_returns_negative_angle(self):
        for a in [0.0, 45.0, 90.0, 107.5, 111.5, 135.0, 165.0]:
            self.assertAlmostEqual(grain_rotation_deg(a), -a, places=6)

    def test_standard_angles_backward_compatible(self):
        """표준 각도 결과: 0→0, 90→-90 (기존 Y 90° 정렬과 동일 X 정렬)."""
        self.assertEqual(grain_rotation_deg(0.0), 0.0)
        self.assertEqual(grain_rotation_deg(90.0), -90.0)


class TestGetAlignmentRotation(unittest.TestCase):

    def test_uses_angle_not_kind(self):
        """kind 가 NONSTANDARD 여도 angle_deg 기반 회전각 반환."""
        g = {"kind": "NONSTANDARD", "angle_deg": 107.5}
        self.assertAlmostEqual(get_alignment_rotation(g), -107.5, places=3)

    def test_none_and_missing_angle(self):
        self.assertEqual(get_alignment_rotation(None), 0.0)
        self.assertEqual(get_alignment_rotation({"kind": "STRAIGHT_GRAIN_X"}), 0.0)


class TestArbitraryAngleAlignment(unittest.TestCase):

    def test_grain_line_aligns_to_x_axis(self):
        """임의 각도 5종: 회전 후 결방향 선이 X축(0°)에 정렬."""
        for theta in ARBITRARY_ANGLES:
            rot = grain_rotation_deg(theta)
            # 결방향 선 벡터 (theta°) 를 rot 만큼 회전 → 각도 0 이어야
            vx, vy = _rotate_point(math.cos(math.radians(theta)),
                                   math.sin(math.radians(theta)), rot)
            aligned = math.degrees(math.atan2(vy, vx)) % 180.0
            self.assertAlmostEqual(aligned, 0.0, places=4,
                                   msg=f"theta={theta} 정렬 실패: {aligned}")

    def test_align_pieces_rotates_arbitrary(self):
        """_align_pieces_to_grain: 임의 각도 piece 회전 + kind→X (NONSTANDARD 제거)."""
        for theta in ARBITRARY_ANGLES:
            p = _grain_piece(f"P_{theta}", theta)
            out, _ = _align_pieces_to_grain([p], polygons=None)
            g = out[0]["grain"]
            self.assertEqual(g["kind"], "STRAIGHT_GRAIN_X",
                             msg=f"theta={theta} kind 미정렬")
            self.assertEqual(g["angle_deg"], 0.0)
            self.assertAlmostEqual(g["_rotated_by"], -theta, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
