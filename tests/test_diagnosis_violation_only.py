# -*- coding: utf-8 -*-
"""
test_diagnosis_violation_only.py
--------------------------------
진단 리포트 본질 변경 단위 테스트 (사장님 결정 2026-05-05).

검증:
  1. build_raw_table — raw 정보 표 (항상)
  2. detect_violations — 위반 시만:
     · quantity_missing
     · material_missing
     · grain_missing (estimated)
     · pattern_name_invalid 폐기 (사장님 확정 2026-07-14 — 부위명 필수 아님)
  3. Material:NON → 위반 X (정보성)
  4. 정상 piece → 위반 0
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import build_raw_table, detect_violations


def _piece(piece_name="FRONT_BODY", quantity=1, material="SELF",
           material_inferred="주원단", mirror=None,
           is_standard=True, grain_estimated=False):
    return {
        "piece_id": piece_name,
        "piece_name": piece_name,
        "piece_name_raw": piece_name,
        "is_standard_name": is_standard,
        "quantity": quantity,
        "material_raw": material,
        "material_inferred": material_inferred,
        "mirror": mirror,
        "grain": {"kind": "STRAIGHT_GRAIN_Y", "angle_deg": 90.0,
                  "estimated": grain_estimated},
    }


class TestRawTable(unittest.TestCase):

    def test_table_always_built(self):
        parsed = {"pieces": [_piece(), _piece(piece_name="BACK_BODY")]}
        table = build_raw_table(parsed)
        self.assertEqual(len(table), 2)
        self.assertEqual(table[0]["패턴 명칭"], "FRONT_BODY")
        self.assertEqual(table[1]["패턴 명칭"], "BACK_BODY")

    def test_paired_label(self):
        parsed = {"pieces": [_piece(mirror=True), _piece(mirror=False),
                              _piece(mirror=None)]}
        table = build_raw_table(parsed)
        self.assertEqual(table[0]["좌우 대칭"], "✅ 페어")
        self.assertEqual(table[1]["좌우 대칭"], "단독")
        self.assertEqual(table[2]["좌우 대칭"], "(미표기)")

    def test_quantity_missing_label(self):
        parsed = {"pieces": [_piece(quantity=None)]}
        table = build_raw_table(parsed)
        self.assertEqual(table[0]["갯수"], "(미표기)")


class TestViolations(unittest.TestCase):

    def test_no_violations_for_clean_piece(self):
        parsed = {"pieces": [_piece()]}
        v = detect_violations(parsed)
        self.assertEqual(v, [])

    def test_pattern_name_invalid_deprecated(self):
        """부위명 위반(pattern_name_invalid) 폐기 (사장님 확정 2026-07-14).

        표준 외 부위명이어도 더 이상 위반으로 잡지 않음 — 다른 위반(수량/원단/식서)
        이 없는 clean piece 면 위반 0.
        """
        parsed = {"pieces": [_piece(piece_name="BODICE", is_standard=False)]}
        v = detect_violations(parsed)
        types = [x["type"] for x in v]
        self.assertNotIn("pattern_name_invalid", types)
        self.assertEqual(v, [])

    def test_quantity_missing(self):
        parsed = {"pieces": [_piece(quantity=None)]}
        v = detect_violations(parsed)
        types = [x["type"] for x in v]
        self.assertIn("quantity_missing", types)

    def test_material_missing(self):
        parsed = {"pieces": [_piece(material="", material_inferred="주원단")]}
        v = detect_violations(parsed)
        types = [x["type"] for x in v]
        self.assertIn("material_missing", types)

    def test_grain_missing(self):
        parsed = {"pieces": [_piece(grain_estimated=True)]}
        v = detect_violations(parsed)
        types = [x["type"] for x in v]
        self.assertIn("grain_missing", types)

    def test_marker_excluded_no_violation(self):
        """Material:NON → 위반 X (정보성 — diagnose_excluded 가 별도 처리)"""
        parsed = {"pieces": [_piece(material="NON", material_inferred="마카제외")]}
        v = detect_violations(parsed)
        types = [x["type"] for x in v]
        # NON 은 material_raw 명시되어 있으므로 material_missing 도 X
        self.assertNotIn("material_missing", types)

    def test_multiple_violations_same_piece(self):
        """한 piece 에 여러 위반 가능 (부위명 위반은 폐기 — 수량/원단만)."""
        parsed = {"pieces": [_piece(
            piece_name="BAD_NAME", is_standard=False,
            quantity=None, material="",
        )]}
        v = detect_violations(parsed)
        types = [x["type"] for x in v]
        self.assertNotIn("pattern_name_invalid", types)
        self.assertIn("quantity_missing", types)
        self.assertIn("material_missing", types)


if __name__ == "__main__":
    unittest.main(verbosity=2)
