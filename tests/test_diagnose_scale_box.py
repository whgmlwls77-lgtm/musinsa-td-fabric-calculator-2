# -*- coding: utf-8 -*-
"""
test_diagnose_scale_box.py
--------------------------
이슈 D — 50x50 비율 박스로 DXF 스케일 검증 (사장님 본질 2026-05-07).

배경: 사장님 새 DXF (MMAPS003-test.dxf) 50x50cm Material:NON 박스 추가.
raw 측정 19.685 cm = 50/2.54 → DXF 좌표 inch 단위 적발.

검증:
  1. detect_scale_box — name keyword (50X50) / NON / 정사각형 조건 매칭
  2. compute_scale_correction — 측정값별 보정 비율 + 단위 가설
  3. diagnose_scale — OK (50.0) / WARN (19.685 inch / 5.0 mm) / OK (박스 없음)
  4. run_full_diagnosis — scale 키 통합
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import (
    OK, WARN, FAIL,
    detect_scale_box,
    compute_scale_correction,
    diagnose_scale,
    run_full_diagnosis,
)


def _piece(pid, name, w, h, mat_raw="", mat_inferred="주원단"):
    return {
        "piece_id": pid,
        "piece_key": pid,
        "piece_name": name,
        "width_cm": w,
        "height_cm": h,
        "material_raw": mat_raw,
        "material_inferred": mat_inferred,
    }


class TestDetectScaleBox(unittest.TestCase):

    def test_name_keyword_50x50(self):
        pieces = [
            _piece("P1", "FRONT_BODY", 40, 100),
            _piece("P2", "50X50", 19.685, 19.685, mat_raw="NON", mat_inferred="마카제외"),
        ]
        box = detect_scale_box(pieces)
        self.assertIsNotNone(box)
        self.assertEqual(box["piece_name"], "50X50")
        self.assertTrue(box["name_match"])
        self.assertTrue(box["is_square"])

    def test_square_only_no_name(self):
        """정사각형 + NON 만 있어도 검출."""
        pieces = [
            _piece("P1", "MARKER_BOX", 50.0, 50.0, mat_raw="NON", mat_inferred="마카제외"),
        ]
        box = detect_scale_box(pieces)
        self.assertIsNotNone(box)
        self.assertFalse(box["name_match"])
        self.assertTrue(box["is_square"])

    def test_only_self_pieces_no_box(self):
        """Material:NON 없으면 검출 X — 일반 piece 는 후보 X."""
        pieces = [_piece("P1", "FRONT_BODY", 50, 50)]  # 정사각형이지만 NON X
        self.assertIsNone(detect_scale_box(pieces))

    def test_empty_pieces(self):
        self.assertIsNone(detect_scale_box([]))

    def test_name_match_priority(self):
        """이름 매칭이 정사각형보다 우선."""
        pieces = [
            _piece("P1", "RECT_BOX", 30.0, 60.0, mat_raw="NON", mat_inferred="마카제외"),
            _piece("P2", "50X50", 19.685, 19.685, mat_raw="NON", mat_inferred="마카제외"),
        ]
        box = detect_scale_box(pieces)
        self.assertEqual(box["piece_name"], "50X50")


class TestComputeScaleCorrection(unittest.TestCase):

    def test_cm_normal(self):
        ratio, hyp = compute_scale_correction(50.0)
        self.assertEqual(ratio, 1.0)
        self.assertIn("정상", hyp)

    def test_inch_19685(self):
        """19.685 cm = 50/2.54 → inch 가설."""
        ratio, hyp = compute_scale_correction(19.685)
        self.assertAlmostEqual(ratio, 2.54, places=2)
        self.assertIn("inch", hyp)

    def test_mm_5(self):
        """5.0 cm = 50/10 → mm 가설."""
        ratio, hyp = compute_scale_correction(5.0)
        self.assertAlmostEqual(ratio, 10.0, places=2)
        self.assertIn("mm", hyp)

    def test_unknown_ratio(self):
        """0.5 cm 측정 → 100배 보정 (비표준)."""
        ratio, hyp = compute_scale_correction(0.5)
        self.assertAlmostEqual(ratio, 100.0)
        self.assertIn("비표준", hyp)

    def test_zero_measurement(self):
        ratio, hyp = compute_scale_correction(0.0)
        self.assertEqual(ratio, 1.0)
        self.assertIn("측정 불가", hyp)


class TestDiagnoseScale(unittest.TestCase):

    def test_normal_50cm_box_ok(self):
        pieces = [
            _piece("P1", "50X50", 50.0, 50.0, mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_scale({"pieces": pieces})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["correction_ratio"], 1.0)
        self.assertIn("정상", d["summary"])

    def test_inch_dxf_warn(self):
        """사장님 raw 시나리오: 박스 19.685 측정 (보정 미적용) → WARN.

        사장님 본질 정정 (2026-05-07): 사용자 노출 메시지에 raw 수치/단위/비율 명시 X.
        내부 raw dict 만 unit_hypothesis / correction_ratio 보유 (디버그용).
        """
        pieces = [
            _piece("P1", "50X50", 19.685, 19.685, mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_scale({"pieces": pieces})
        self.assertEqual(d["status"], WARN)
        # 내부 raw — 디버그/audit 용 (사용자 노출 X)
        self.assertAlmostEqual(d["raw"]["correction_ratio"], 2.54, places=2)
        self.assertIn("inch", d["raw"]["unit_hypothesis"])
        # 사용자 노출 메시지에는 raw 수치 / 단위 / 비율 X
        self.assertNotIn("19.685", d["summary"])
        self.assertNotIn("inch", d["summary"])
        self.assertNotIn("2.54", d["summary"])
        self.assertNotIn("×", d.get("algo_state", ""))

    def test_no_box_returns_ok_info(self):
        pieces = [_piece("P1", "FRONT_BODY", 40, 100)]
        d = diagnose_scale({"pieces": pieces})
        self.assertEqual(d["status"], OK)
        self.assertFalse(d["raw"]["detected"])
        self.assertIn("박스 없음", d["summary"])

    def test_within_tolerance_ok(self):
        """50.3 cm 측정 (±0.5cm 이내) → OK."""
        pieces = [
            _piece("P1", "50X50", 50.3, 49.8, mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_scale({"pieces": pieces})
        self.assertEqual(d["status"], OK)


class TestRunFullDiagnosisIntegration(unittest.TestCase):

    def test_scale_key_present(self):
        pieces = [
            _piece("P1", "FRONT_BODY", 40, 100),
            _piece("P2", "50X50", 50.0, 50.0, mat_raw="NON", mat_inferred="마카제외"),
        ]
        diag = run_full_diagnosis({
            "pieces": pieces,
            "style": "TEST",
            "diagnosis_raw": {},
        })
        self.assertIn("scale", diag)
        self.assertEqual(diag["scale"]["status"], OK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
