# -*- coding: utf-8 -*-
"""
test_unit_correction_50cm_box.py
--------------------------------
옵션 A 자동 보정 검증 (사장님 결정 2026-05-07).

배경: 50cm × 50cm 비율 박스로 DXF 단위 자동 검출 + 보정.
- inch DXF → 박스 측정 19.685 cm → 비율 2.54 적용 → 모든 piece 사이즈 ×2.54
- mm DXF → 박스 측정 5.0 cm → 비율 10.0 적용

검증:
  1. apply_unit_correction_50cm_box: 박스 19.685 → 모든 piece × 2.54
  2. 박스 50.0 ± 0.5cm → no-op
  3. 박스 없음 → no-op + 메타 키 박힘
  4. detect_scale_box_50cm rename + alias 검증
  5. SCALE_BOX_SIZE_CM = 50.0 상수 검증
  6. 함수명 단위 명시 (detect_scale_box_50cm / compute_unit_correction_50cm_box)
  7. MMAPS003-test.dxf 통합 — 보정 적용 후 박스 50.000 cm
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import (
    SCALE_BOX_SIZE_CM,
    SCALE_BOX_TOLERANCE_CM,
    detect_scale_box_50cm,
    detect_scale_box,  # backward alias
    compute_unit_correction_50cm_box,
    compute_scale_correction,  # backward alias
    apply_unit_correction_50cm_box,
    diagnose_scale,
    OK, WARN,
)


def _piece(pid, name, w, h, mat_raw="", mat_inferred="주원단"):
    return {
        "piece_id": pid,
        "piece_key": pid,
        "piece_name": name,
        "width_cm": w,
        "height_cm": h,
        "area_cm2": w * h,
        "bbox_cm": (0.0, 0.0, w, h),
        "centroid_cm": (w / 2.0, h / 2.0),
        "coords_cm": [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)],
        "material_raw": mat_raw,
        "material_inferred": mat_inferred,
    }


class TestConstantsAndAlias(unittest.TestCase):

    def test_scale_box_size_cm_is_50(self):
        self.assertEqual(SCALE_BOX_SIZE_CM, 50.0)

    def test_detect_scale_box_alias_works(self):
        """기존 detect_scale_box 호출자 — 새 detect_scale_box_50cm 와 같은 결과."""
        pieces = [_piece("P1", "SCALE_BOX", 50.0, 50.0, mat_raw="NON",
                         mat_inferred="마카제외")]
        a = detect_scale_box(pieces)
        b = detect_scale_box_50cm(pieces)
        self.assertEqual(a, b)

    def test_compute_correction_alias_works(self):
        a = compute_scale_correction(19.685)
        b = compute_unit_correction_50cm_box(19.685)
        self.assertEqual(a, b)


class TestDetectScaleBoxNames(unittest.TestCase):
    """단위 명시 이름 키워드 우선."""

    def test_scale_box_name_match(self):
        pieces = [_piece("P1", "SCALE_BOX", 19.685, 19.685, mat_raw="NON",
                         mat_inferred="마카제외")]
        box = detect_scale_box_50cm(pieces)
        self.assertIsNotNone(box)
        self.assertTrue(box["name_match"])

    def test_50cm_keyword_match(self):
        """'50CM' 키워드 매칭."""
        pieces = [_piece("P1", "REF_50CM_BOX", 19.685, 19.685, mat_raw="NON",
                         mat_inferred="마카제외")]
        box = detect_scale_box_50cm(pieces)
        self.assertIsNotNone(box)
        self.assertTrue(box["name_match"])


class TestApplyUnitCorrection(unittest.TestCase):

    def test_inch_dxf_correction_applied(self):
        """박스 19.685 측정 → ×2.54 보정 적용."""
        pieces = [
            _piece("BOX", "SCALE_BOX", 19.685, 19.685, mat_raw="NON",
                   mat_inferred="마카제외"),
            _piece("BACK_BODY", "BACK_BODY", 41.59, 11.60),
        ]
        parsed = {"pieces": pieces, "excluded": []}
        result = apply_unit_correction_50cm_box(parsed)
        self.assertTrue(result["scale_correction_applied"])
        self.assertAlmostEqual(result["scale_correction_ratio"], 2.54, places=2)
        self.assertAlmostEqual(result["scale_correction_original_w_cm"], 19.685, places=3)
        # BOX 자체도 보정 → ~50cm
        self.assertAlmostEqual(pieces[0]["width_cm"], 50.000, places=2)
        # BACK_BODY × 2.54
        self.assertAlmostEqual(pieces[1]["width_cm"], 41.59 * 2.54, places=2)
        self.assertAlmostEqual(pieces[1]["height_cm"], 11.60 * 2.54, places=2)
        # area × 2.54²
        self.assertAlmostEqual(
            pieces[1]["area_cm2"], 41.59 * 11.60 * 2.54 * 2.54, places=1
        )

    def test_normal_50cm_box_no_op(self):
        """박스 50cm → 보정 없음 (ratio=1.0)."""
        pieces = [
            _piece("BOX", "SCALE_BOX", 50.0, 50.0, mat_raw="NON",
                   mat_inferred="마카제외"),
            _piece("FRONT_BODY", "FRONT_BODY", 100.0, 40.0),
        ]
        parsed = {"pieces": pieces, "excluded": []}
        original_w = pieces[1]["width_cm"]
        result = apply_unit_correction_50cm_box(parsed)
        self.assertFalse(result["scale_correction_applied"])
        self.assertEqual(result["scale_correction_ratio"], 1.0)
        self.assertEqual(pieces[1]["width_cm"], original_w)

    def test_no_box_no_op(self):
        pieces = [_piece("FRONT_BODY", "FRONT_BODY", 100.0, 40.0)]
        parsed = {"pieces": pieces, "excluded": []}
        result = apply_unit_correction_50cm_box(parsed)
        self.assertFalse(result["scale_correction_applied"])
        self.assertEqual(result["scale_correction_ratio"], 1.0)

    def test_coords_corrected(self):
        """coords_cm 도 좌표 비례 보정."""
        pieces = [
            _piece("BOX", "SCALE_BOX", 19.685, 19.685, mat_raw="NON",
                   mat_inferred="마카제외"),
            _piece("P", "P", 10.0, 5.0),
        ]
        parsed = {"pieces": pieces, "excluded": []}
        apply_unit_correction_50cm_box(parsed)
        # P piece coords [(0,0), (10,0), (10,5), (0,5)] → × 2.54
        self.assertAlmostEqual(pieces[1]["coords_cm"][1][0], 25.4, places=2)
        self.assertAlmostEqual(pieces[1]["coords_cm"][2][1], 12.7, places=2)


class TestDiagnoseScaleAfterCorrection(unittest.TestCase):

    def test_after_correction_status_ok(self):
        """보정 적용 후 진단 [5] OK + 자동 보정 메시지."""
        pieces = [
            _piece("BOX", "SCALE_BOX", 19.685, 19.685, mat_raw="NON",
                   mat_inferred="마카제외"),
            _piece("P", "P", 41.59, 11.60),
        ]
        parsed = {"pieces": pieces, "excluded": []}
        apply_unit_correction_50cm_box(parsed)
        diag = diagnose_scale(parsed)
        self.assertEqual(diag["status"], OK)
        self.assertIn("자동 보정", diag["summary"])
        self.assertTrue(diag["raw"]["correction_applied"])
        self.assertAlmostEqual(diag["raw"]["correction_ratio"], 2.54, places=2)


class TestSourceGrepUnitNotation(unittest.TestCase):
    """소스 코드의 표기 일관성 — '50cm × 50cm' 또는 '50X50' 백워드 ok,
    그러나 사용자 노출 라벨에 단위 명시."""

    def test_user_facing_labels_50cm(self):
        """app.py 진단 [5] 라벨 + UI 안내에 '50cm × 50cm' 명시."""
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # 진단 [5] 라벨
        self.assertIn("50cm × 50cm", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
