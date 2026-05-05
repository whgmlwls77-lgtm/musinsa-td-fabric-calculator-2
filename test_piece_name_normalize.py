# -*- coding: utf-8 -*-
"""
test_piece_name_normalize.py
----------------------------
패턴명 표준 정규화 단위 테스트 (사장님 결정 2026-05-05).

검증:
  1. 표준 풀네임 매칭 (FRONT_BODY 등)
  2. 약자 매칭 (FB → FRONT_BODY 등)
  3. 대소문자 무시 (front body / Front-Body / FB / fb)
  4. 하이픈/공백 → 언더스코어 정규화
  5. 표준 외 명칭 → (정규화 raw, False) — 위반 알림용
  6. 빈 입력 → ("", False)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from piece_name_normalize import normalize_piece_name, reload_mapping


class TestStandardName(unittest.TestCase):

    def setUp(self):
        reload_mapping()

    def test_full_names_match(self):
        for raw in ["FRONT_BODY", "BACK_BODY", "WAISTBAND_FRONT", "WAISTBAND_BACK",
                    "FLY", "FLY_UNDERLAY", "FLY_FACING",
                    "FRONT_POCKET_FACING_UPPER", "BACK_POCKET_BAG"]:
            std, ok = normalize_piece_name(raw)
            self.assertTrue(ok, f"표준 풀네임 매칭 실패: {raw!r}")
            self.assertEqual(std, raw)


class TestAliasMatch(unittest.TestCase):

    def test_front_body_aliases(self):
        for alias in ["FB", "F_BODY", "fb", "f-body"]:
            std, ok = normalize_piece_name(alias)
            self.assertTrue(ok, f"약자 매칭 실패: {alias!r}")
            self.assertEqual(std, "FRONT_BODY")

    def test_back_body_aliases(self):
        for alias in ["BB", "B_BODY", "bb"]:
            std, ok = normalize_piece_name(alias)
            self.assertTrue(ok)
            self.assertEqual(std, "BACK_BODY")

    def test_waistband_aliases(self):
        for alias, expected in [("WB_F", "WAISTBAND_FRONT"), ("WBF", "WAISTBAND_FRONT"),
                                ("WB_B", "WAISTBAND_BACK"), ("WBB", "WAISTBAND_BACK")]:
            std, ok = normalize_piece_name(alias)
            self.assertTrue(ok, f"{alias!r}")
            self.assertEqual(std, expected)


class TestCaseInsensitive(unittest.TestCase):

    def test_lowercase_full_name(self):
        std, ok = normalize_piece_name("front_body")
        self.assertTrue(ok)
        self.assertEqual(std, "FRONT_BODY")

    def test_mixed_case(self):
        std, ok = normalize_piece_name("Front_Body")
        self.assertTrue(ok)
        self.assertEqual(std, "FRONT_BODY")


class TestHyphenSpaceNormalization(unittest.TestCase):

    def test_space_to_underscore(self):
        std, ok = normalize_piece_name("FRONT BODY")
        self.assertTrue(ok)
        self.assertEqual(std, "FRONT_BODY")

    def test_hyphen_to_underscore(self):
        std, ok = normalize_piece_name("FRONT-BODY")
        self.assertTrue(ok)
        self.assertEqual(std, "FRONT_BODY")

    def test_multiple_spaces(self):
        std, ok = normalize_piece_name("FRONT  BODY")
        self.assertTrue(ok)
        self.assertEqual(std, "FRONT_BODY")


class TestNonStandardName(unittest.TestCase):
    """표준 외 명칭 → (정규화 raw, False) — 위반 알림용."""

    def test_unknown_returns_false(self):
        std, ok = normalize_piece_name("BODICE")
        self.assertFalse(ok)
        self.assertEqual(std, "BODICE")

    def test_unknown_normalized_form(self):
        """대소문자/공백 정규화는 적용되지만 매칭 실패"""
        std, ok = normalize_piece_name("My Custom Piece")
        self.assertFalse(ok)
        self.assertEqual(std, "MY_CUSTOM_PIECE")

    def test_typo_aliases_dont_match(self):
        """ 약자 사전에 없는 임의 약자 → 매칭 실패"""
        std, ok = normalize_piece_name("XYZ_PIECE")
        self.assertFalse(ok)


class TestEmptyInput(unittest.TestCase):

    def test_empty_string(self):
        std, ok = normalize_piece_name("")
        self.assertEqual(std, "")
        self.assertFalse(ok)

    def test_whitespace_only(self):
        std, ok = normalize_piece_name("   ")
        self.assertEqual(std, "")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
