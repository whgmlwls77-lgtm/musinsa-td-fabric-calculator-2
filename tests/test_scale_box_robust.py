# -*- coding: utf-8 -*-
"""
test_scale_box_robust.py
------------------------
스케일 박스 감지 견고성 증진 (사장님 실증 2026-07-14).

배경:
  사장님 PP 파일 스케일 박스 이름 "50x50_32" + Material:SELF (NON 아님) + 19.685²(inch) →
  기존 is_non 게이트에서 제외 → 단위 자동 보정 미실행 → 조각 면적 15.5%로 왜곡
  (MMAPS003 TT 411.5 cm² 표시, CAD 실제 2654.986 cm²).

견고화 원리 (추측 금지 준수):
  A) 이름 키워드 매칭 → Material 무관 (명시적 raw 증거)
  B) off-unit 표준값(inch 19.685 / mm 500) 정사각형 → Material 무관 (자연 치수 아님)
  C) cm 표준값(50) 정사각형 → Material:NON 필요 (자연 치수 가능 → 오검출 방지)
  * 모든 경로 정사각형(±5%) 필수.

검증:
  1. 50X50 / 50x50 / 50_X_50 이름 → 감지 성공
  2. 19.685² 정사각형 (이름 무관) → 감지 성공 (off-unit)
  3. 500² 정사각형 → 감지 성공 (off-unit mm)
  4. 30×20 사각형 → 감지 실패 (정사각형 아님)
  5. 19.685² 이름 "SLEEVE" → 감지 성공 (크기 기반)
  6. 사장님 실증 회귀: name/block "50x50_32" + Material:SELF + 19.685² → 감지 + ×2.54 보정
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import (
    detect_scale_box_50cm,
    apply_unit_correction_50cm_box,
    move_scale_box_to_excluded,
)


def _piece(pid, name, w, h, block_name="", mat_raw="SELF", mat_inferred="주원단"):
    return {
        "piece_id": pid,
        "piece_key": pid,
        "piece_name": name,
        "block_name": block_name,
        "width_cm": w,
        "height_cm": h,
        "material_raw": mat_raw,
        "material_inferred": mat_inferred,
    }


class TestNameKeywordVariants(unittest.TestCase):
    """이름 표기 다양성 — Material 무관 감지 (명시적 이름 = raw 증거)."""

    def test_50X50(self):
        box = detect_scale_box_50cm([_piece("P1", "50X50", 50.0, 50.0)])
        self.assertIsNotNone(box)
        self.assertTrue(box["name_match"])

    def test_50x50_lower(self):
        box = detect_scale_box_50cm([_piece("P1", "50x50", 50.0, 50.0)])
        self.assertIsNotNone(box)

    def test_50_X_50(self):
        box = detect_scale_box_50cm([_piece("P1", "50_X_50", 50.0, 50.0)])
        self.assertIsNotNone(box)

    def test_name_match_material_agnostic(self):
        """Material:SELF 여도 이름 매칭이면 감지 (사장님 핵심 케이스)."""
        box = detect_scale_box_50cm([
            _piece("P1", "50X50", 19.685, 19.685, mat_raw="SELF", mat_inferred="주원단"),
        ])
        self.assertIsNotNone(box)


class TestSizeBasedDetection(unittest.TestCase):
    """크기 기반 감지 — off-unit 표준값 정확 매칭 (Material 무관)."""

    def test_inch_square_no_name(self):
        box = detect_scale_box_50cm([_piece("P1", "PIECE_A", 19.685, 19.685)])
        self.assertIsNotNone(box)
        self.assertFalse(box["name_match"])

    def test_mm_square_no_name(self):
        box = detect_scale_box_50cm([_piece("P1", "PIECE_A", 500.0, 500.0)])
        self.assertIsNotNone(box)

    def test_inch_square_named_sleeve(self):
        """이름이 SLEEVE 여도 off-unit 정사각형이면 감지 (크기 기반)."""
        box = detect_scale_box_50cm([_piece("P1", "SLEEVE", 19.685, 19.685)])
        self.assertIsNotNone(box)
        self.assertFalse(box["name_match"])


class TestRejection(unittest.TestCase):
    """추측 금지 — 정사각형 아니거나 표준값 아니면 감지 X."""

    def test_non_square_rejected(self):
        """30×20 사각형 → 정사각형 아님 → 감지 실패 (NON 이어도)."""
        box = detect_scale_box_50cm([
            _piece("P1", "50X50", 30.0, 20.0, mat_raw="NON", mat_inferred="마카제외"),
        ])
        self.assertIsNone(box)

    def test_cm_square_self_no_name_rejected(self):
        """cm 50 정사각형 + SELF + 이름 무 → 감지 X (자연 조각 오검출 방지).

        cm 표준값은 자연 치수 가능 → Material:NON 필요.
        """
        box = detect_scale_box_50cm([_piece("P1", "FRONT_BODY", 50.0, 50.0)])
        self.assertIsNone(box)

    def test_unknown_size_no_name_rejected(self):
        """정사각형이지만 표준값(19.685/500/50) 아님 + 이름 무 → 감지 X."""
        box = detect_scale_box_50cm([_piece("P1", "PIECE_A", 33.0, 33.0)])
        self.assertIsNone(box)


class TestBossRealRegression(unittest.TestCase):
    """사장님 실증 회귀 가드 (2026-07-14) — 반드시 감지 + 보정."""

    def test_block_name_keyword_match(self):
        """block_name '50x50_32' (piece_name 비어도) → 감지."""
        box = detect_scale_box_50cm([
            _piece("P1", "", 19.685, 19.685, block_name="50x50_32"),
        ])
        self.assertIsNotNone(box)
        self.assertTrue(box["name_match"])

    def test_end_to_end_correction_254(self):
        """SELF + 19.685² + 이름 50X50 → apply_unit_correction ×2.54 적용."""
        parsed = {
            "pieces": [
                {
                    "piece_id": "P1", "piece_name": "50X50", "block_name": "50x50_32",
                    "width_cm": 19.685, "height_cm": 19.685, "area_cm2": 387.5,
                    "material_raw": "SELF", "material_inferred": "주원단",
                    "bbox_cm": (0.0, 0.0, 19.685, 19.685),
                    "centroid_cm": (9.84, 9.84),
                    "coords_cm": [(0, 0), (19.685, 0), (19.685, 19.685), (0, 19.685)],
                },
                {
                    "piece_id": "P2", "piece_name": "TT", "block_name": "TT",
                    "width_cm": 20.0, "height_cm": 20.0, "area_cm2": 411.5,
                    "material_raw": "SELF", "material_inferred": "주원단",
                    "bbox_cm": (0.0, 0.0, 20.0, 20.0),
                    "centroid_cm": (10.0, 10.0),
                    "coords_cm": [(0, 0), (20, 0), (20, 20), (0, 20)],
                },
            ],
        }
        out = apply_unit_correction_50cm_box(parsed)
        self.assertTrue(out["scale_correction_applied"])
        self.assertAlmostEqual(out["scale_correction_ratio"], 2.54, places=2)
        # TT 면적 411.5 × 2.54² = 2654.83 근처
        tt = next(p for p in out["pieces"] if p["piece_name"] == "TT")
        self.assertAlmostEqual(tt["area_cm2"], 411.5 * 2.54 * 2.54, places=1)


def _box_full(pid="BOX", name="50X50", w=19.685, h=19.685,
              mat_raw="SELF", mat_inf="주원단", block=""):
    """apply_unit_correction 가 다루는 전체 필드 포함 스케일 박스 piece."""
    return {
        "piece_id": pid, "piece_name": name, "block_name": block,
        "width_cm": w, "height_cm": h, "area_cm2": w * h,
        "material_raw": mat_raw, "material_inferred": mat_inf,
        "bbox_cm": (0.0, 0.0, w, h), "centroid_cm": (w / 2, h / 2),
        "coords_cm": [(0, 0), (w, 0), (w, h), (0, h)],
    }


def _garment_full(pid="G1", name="FRONT_BODY", w=40.0, h=100.0):
    return {
        "piece_id": pid, "piece_name": name, "block_name": name,
        "width_cm": w, "height_cm": h, "area_cm2": w * h,
        "material_raw": "SELF", "material_inferred": "주원단",
        "bbox_cm": (0.0, 0.0, w, h), "centroid_cm": (w / 2, h / 2),
        "coords_cm": [(0, 0), (w, 0), (w, h), (0, h)],
    }


class TestMoveScaleBoxToExcluded(unittest.TestCase):
    """감지된 스케일 박스 material 무관 pieces → excluded 이동 (사장님 확정 2026-07-15)."""

    def _run(self, pieces):
        parsed = {"pieces": list(pieces), "excluded": []}
        parsed = apply_unit_correction_50cm_box(parsed)
        parsed = move_scale_box_to_excluded(parsed)
        return parsed

    def test_self_material_box_moved(self):
        """Material:SELF 스케일 박스도 excluded 로 자동 이동 (사장님 핵심 케이스)."""
        parsed = self._run([_box_full(mat_raw="SELF", mat_inf="주원단"), _garment_full()])
        self.assertEqual(len(parsed["pieces"]), 1)
        self.assertEqual(parsed["pieces"][0]["piece_name"], "FRONT_BODY")
        self.assertEqual(len(parsed["excluded"]), 1)
        self.assertEqual(parsed["excluded"][0]["reason"], "scale_box")
        self.assertEqual(parsed["excluded"][0]["material_raw"], "SELF")

    def test_non_material_box_moved(self):
        """Material:NON 스케일 박스도 excluded 이동 (기존 표준 케이스)."""
        parsed = self._run([
            _box_full(mat_raw="NON", mat_inf="마카제외"), _garment_full(),
        ])
        self.assertEqual(len(parsed["pieces"]), 1)
        self.assertEqual(len(parsed["excluded"]), 1)

    def test_size_only_detection_moved(self):
        """이름 키워드 없이 크기(off-unit 19.685)로만 감지된 박스도 이동."""
        parsed = self._run([
            _box_full(name="SLEEVE", mat_raw="SELF", mat_inf="주원단"), _garment_full(),
        ])
        self.assertEqual(len(parsed["excluded"]), 1)
        self.assertEqual(len(parsed["pieces"]), 1)

    def test_cm_normal_box_moved(self):
        """보정 불필요한 50cm 정상 박스(NON)도 excluded 이동."""
        parsed = self._run([
            _box_full(name="50X50", w=50.0, h=50.0, mat_raw="NON", mat_inf="마카제외"),
            _garment_full(),
        ])
        self.assertEqual(len(parsed["excluded"]), 1)
        self.assertEqual(len(parsed["pieces"]), 1)

    def test_no_box_no_move(self):
        """스케일 박스 없으면 pieces/excluded 불변."""
        parsed = self._run([_garment_full()])
        self.assertEqual(len(parsed["pieces"]), 1)
        self.assertEqual(len(parsed["excluded"]), 0)

    def test_idempotent_no_scale_box_info(self):
        """scale_box_info 없으면 no-op (이미 처리됐거나 박스 없음)."""
        parsed = {"pieces": [_garment_full()], "excluded": []}
        out = move_scale_box_to_excluded(parsed)
        self.assertEqual(len(out["pieces"]), 1)
        self.assertEqual(len(out["excluded"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
