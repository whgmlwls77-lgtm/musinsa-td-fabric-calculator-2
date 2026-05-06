# -*- coding: utf-8 -*-
"""
test_partner_message_template.py
--------------------------------
협력사 메시지 평이화 테스트 (사장님 결정 2026-05-05).

검증:
  1. 7 케이스 메시지 생성
  2. 기술 용어 0건 (DXF/Material/Quantity/DOUBLE/메타/PAIRED/SELF/LINING 등)
  3. 평이한 한국어 키워드 포함 ("패턴 조각 갯수", "원단 종류", "식서", ...)
  4. 위반 리스트 → 통합 메시지 생성 + 중복 제거
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from partner_message import build_partner_message, build_messages


# 협력사가 알아듣지 못하는 기술 용어 (사장님 본질 위반)
TECH_TERMS = [
    "DXF", "Material", "Quantity", "PAIRED", "DOUBLE",
    "SELF", "LINING", "POCKETING", "CONTRAST", "FUSE",
    "메타", "metadata", "TEXT 엔티티", "annotation",
    "block", "layer", "polygon", "vertex",
    "raw", "piece_id",
]


def _has_tech_term(msg: str) -> str | None:
    """메시지에 기술 용어가 들어있으면 그 용어 반환, 없으면 None.
    NON 은 사장님이 가이드에 박은 표준이므로 예외 (메시지 안내 시 노출 OK)."""
    upper = msg.upper()
    for t in TECH_TERMS:
        # NON 은 가이드 표준 — 협력사가 직접 표기할 코드이므로 메시지에 노출 OK
        if t == "NON":
            continue
        if t.upper() in upper:
            return t
    return None


class TestNoTechTerms(unittest.TestCase):
    """모든 메시지에 기술 용어 0건."""

    def test_pattern_name_invalid_plain(self):
        msg = build_messages["pattern_name_invalid"]("FRONT_BODY")
        bad = _has_tech_term(msg)
        self.assertIsNone(bad, f"기술 용어 발견: {bad!r} in {msg!r}")

    def test_quantity_missing_plain(self):
        msg = build_messages["quantity_missing"]("앞판")
        self.assertIsNone(_has_tech_term(msg), msg)
        self.assertIn("패턴 조각 갯수", msg)

    def test_material_missing_plain(self):
        msg = build_messages["material_missing"]("앞판")
        self.assertIsNone(_has_tech_term(msg), msg)
        self.assertIn("원단 종류", msg)

    def test_grain_missing_plain(self):
        msg = build_messages["grain_missing"]("앞판")
        self.assertIsNone(_has_tech_term(msg), msg)
        self.assertIn("식서", msg)

    def test_paired_missing_plain(self):
        msg = build_messages["paired_missing"]("앞판")
        self.assertIsNone(_has_tech_term(msg), msg)
        self.assertIn("좌우 대칭", msg)

    def test_marker_exclude_plain(self):
        msg = build_messages["marker_exclude"]()
        self.assertIsNone(_has_tech_term(msg), msg)
        self.assertIn("마카 제외", msg)

    def test_seam_missing_plain(self):
        msg = build_messages["seam_missing"]("앞판")
        self.assertIsNone(_has_tech_term(msg), msg)
        self.assertIn("시접", msg)


class TestBuildPartnerMessage(unittest.TestCase):

    def test_empty_violations(self):
        self.assertEqual(build_partner_message([]), "")

    def test_single_violation(self):
        v = [{"type": "quantity_missing", "piece_name": "앞판", "raw_name": "앞판"}]
        msg = build_partner_message(v)
        self.assertIn("앞판", msg)
        self.assertIn("패턴 조각 갯수", msg)
        # 안내 인사말
        self.assertIn("안녕하세요", msg)

    def test_multiple_violations(self):
        v = [
            {"type": "quantity_missing", "raw_name": "앞판"},
            {"type": "material_missing", "raw_name": "뒤판"},
            {"type": "grain_missing", "raw_name": "허리단"},
        ]
        msg = build_partner_message(v)
        self.assertIn("1.", msg)
        self.assertIn("2.", msg)
        self.assertIn("3.", msg)
        self.assertIn("앞판", msg)
        self.assertIn("뒤판", msg)
        self.assertIn("허리단", msg)

    def test_dedup_same_type_same_piece(self):
        """같은 type + 같은 piece 두 번 들어오면 1번만"""
        v = [
            {"type": "quantity_missing", "raw_name": "앞판"},
            {"type": "quantity_missing", "raw_name": "앞판"},
        ]
        msg = build_partner_message(v)
        # 1번만 등장 — "2." 가 없어야 함
        self.assertNotIn("2.", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
