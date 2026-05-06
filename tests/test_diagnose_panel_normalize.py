# -*- coding: utf-8 -*-
"""
test_diagnose_panel_normalize.py
--------------------------------
이슈 1 — dxf_diagnosis.diagnose_panel 가 normalize_piece_name + panel_mapping
표준 어휘집 매칭을 사용하는지 검증 (사장님 본질 2026-05-06).

검증:
  1. 표준 풀네임 100% → OK ✅
  2. 약자 (FB, BB 등) 매칭도 표준으로 인정 → OK ✅
  3. 표준 외 명칭 1개라도 있으면 → WARN ⚠️ "표준 외"
  4. Material:NON 마카제외 piece 는 분류 대상에서 제외 (요약/카운트에 별도 표시)
  5. MMAPS003-test.dxf 시나리오 (14 unique → 13 표준 매칭 + DIA30 마카제외) → OK
  6. 빈 이름 piece → FAIL
  7. build_coop_message 의 panel 분기는 'non_standard' 키 사용 (구 'company_abbr' 폐기)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import diagnose_panel, build_coop_message, OK, WARN, FAIL
from piece_name_normalize import reload_mapping


def _piece(pid: str, name: str, mat_raw: str = "", mat_inferred: str = "주원단") -> dict:
    return {
        "piece_id": pid,
        "piece_key": pid,
        "piece_name": name,
        "material_raw": mat_raw,
        "material_inferred": mat_inferred,
    }


class TestStandardOnly(unittest.TestCase):

    def setUp(self):
        reload_mapping()

    def test_all_full_names(self):
        pieces = [
            _piece("P1", "FRONT_BODY"),
            _piece("P2", "BACK_BODY"),
            _piece("P3", "WAISTBAND_FRONT"),
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["by_class"]["standard"], 3)
        self.assertEqual(d["raw"]["by_class"]["non_standard"], 0)
        self.assertIn("표준", d["summary"])

    def test_aliases_count_as_standard(self):
        """약자 (FB, BB) 도 표준 어휘집 매칭이므로 standard."""
        pieces = [
            _piece("P1", "FB"),
            _piece("P2", "BB"),
            _piece("P3", "WBF"),
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["by_class"]["standard"], 3)


class TestNonStandard(unittest.TestCase):

    def setUp(self):
        reload_mapping()

    def test_unknown_name_warn(self):
        pieces = [
            _piece("P1", "FRONT_BODY"),
            _piece("P2", "BODICE"),  # 표준 외
            _piece("P3", "MY_CUSTOM"),  # 표준 외
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], WARN)
        self.assertEqual(d["raw"]["by_class"]["standard"], 1)
        self.assertEqual(d["raw"]["by_class"]["non_standard"], 2)
        self.assertIn("표준 외", d["summary"])

    def test_company_abbr_old_label_not_used(self):
        """구 'company_abbr' 분기 폐기 — by_class 키는 standard/non_standard/empty만."""
        pieces = [_piece("P1", "TS")]  # 표준 외 약자
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertNotIn("company_abbr", d["raw"]["by_class"])
        self.assertNotIn("english_word", d["raw"]["by_class"])
        self.assertNotIn("digit_only", d["raw"]["by_class"])


class TestExcludedNON(unittest.TestCase):
    """Material:NON 마카제외 piece 는 패널 분류 대상에서 제외."""

    def setUp(self):
        reload_mapping()

    def test_excluded_not_counted_in_non_standard(self):
        """DIA30 같은 마카제외 piece 는 'non_standard' 가 아닌 'n_excluded' 로 별도 집계."""
        pieces = [
            _piece("P1", "FRONT_BODY"),
            _piece("P2", "BACK_BODY"),
            _piece("P3", "DIA30", mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["by_class"]["standard"], 2)
        self.assertEqual(d["raw"]["by_class"]["non_standard"], 0)
        self.assertEqual(d["raw"]["n_excluded"], 1)
        self.assertIn("마카제외 1", d["summary"])

    def test_only_excluded_pieces(self):
        pieces = [
            _piece("P1", "DIA30", mat_raw="NON", mat_inferred="마카제외"),
            _piece("P2", "DIA40", mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], OK)
        self.assertIn("마카제외", d["summary"])


class TestMMAPS003Scenario(unittest.TestCase):
    """사장님 raw 시나리오: 14 unique → 13 표준 + DIA30 마카제외 → OK."""

    def setUp(self):
        reload_mapping()

    def test_mmaps003_realistic_layout(self):
        # 패턴 명칭 표준 어휘집 13개 + DIA30 마카제외
        pieces = [
            _piece("P1", "FRONT_BODY"),
            _piece("P2", "BACK_BODY"),
            _piece("P3", "WAISTBAND_FRONT"),
            _piece("P4", "WAISTBAND_BACK"),
            _piece("P5", "FLY"),
            _piece("P6", "FLY_UNDERLAY"),
            _piece("P7", "FLY_FACING"),
            _piece("P8", "FRONT_POCKET_FACING_UPPER"),
            _piece("P9", "FRONT_POCKET_FACING_BOTTOM"),
            _piece("P10", "BACK_POCKET_FACING_UPPER"),
            _piece("P11", "BACK_POCKET_FACING_BOTTOM"),
            _piece("P12", "FRONT_POCKET_BAG"),
            _piece("P13", "BACK_POCKET_BAG"),
            _piece("P14", "DIA30", mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["by_class"]["standard"], 13)
        self.assertEqual(d["raw"]["by_class"]["non_standard"], 0)
        self.assertEqual(d["raw"]["n_excluded"], 1)


class TestEmptyAndStylePrefix(unittest.TestCase):

    def setUp(self):
        reload_mapping()

    def test_empty_name_fail(self):
        pieces = [
            _piece("P1", ""),
            _piece("P2", ""),
        ]
        d = diagnose_panel({"pieces": pieces, "style": ""})
        self.assertEqual(d["status"], FAIL)
        self.assertEqual(d["raw"]["by_class"]["empty"], 2)

    def test_style_prefix_stripped(self):
        """style 'MMAPS003 FRONT_BODY' → 'FRONT_BODY' 정규화 후 표준 매칭."""
        pieces = [_piece("P1", "MMAPS003 FRONT_BODY")]
        d = diagnose_panel({"pieces": pieces, "style": "MMAPS003"})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["by_class"]["standard"], 1)


class TestBuildCoopMessage(unittest.TestCase):
    """build_coop_message 가 새 by_class 키 (non_standard) 를 사용하는지 검증."""

    def setUp(self):
        reload_mapping()

    def test_message_for_non_standard(self):
        pieces = [_piece("P1", "BODICE")]
        diag = {
            "material": {"status": OK},
            "panel": diagnose_panel({"pieces": pieces, "style": ""}),
            "quantity": {"status": OK},
            "grain": {"status": OK},
        }
        msg = build_coop_message({"style": "TEST"}, diag)
        self.assertIn("piece_name 부위명", msg)
        self.assertIn("panel_mapping", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
