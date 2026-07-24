# -*- coding: utf-8 -*-
"""
test_axis_verdict.py
--------------------
축율 대조 판정 검증 (사장님 확정 2026-07-15 — Task #36).

판정 규칙 (오차 범위 없음 — 사장님 원칙 #1):
  - ✅ ok       : 실측 ≤ 신고
  - ⚠️ warning  : 실측 > 신고
  - 🚨 critical : 실측 > 5% (INDUSTRY_MAX_AXIS_PCT — 신고 무관)

우선순위: 5% 상한(critical) > 신고 초과(warning) > 정상(ok).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from axis_verdict import INDUSTRY_MAX_AXIS_PCT, verdict_pair, verdict_single


class TestVerdictSingle(unittest.TestCase):
    """사장님 확정 4 케이스."""

    def test_normal_below_declared(self):
        """실측 2.5%, 신고 3.0% → ✅ 정상."""
        v = verdict_single(2.5, 3.0, "가로")
        self.assertEqual(v["severity"], "ok")
        self.assertEqual(v["label"], "✅")

    def test_warning_over_declared(self):
        """실측 3.5%, 신고 3.0% → ⚠️ 신고 초과."""
        v = verdict_single(3.5, 3.0, "세로")
        self.assertEqual(v["severity"], "warning")
        self.assertEqual(v["label"], "⚠️")

    def test_critical_over_industry_max(self):
        """실측 5.5%, 신고 5.0% → 🚨 상한 초과 (신고 만족 여부 무관)."""
        v = verdict_single(5.5, 5.0, "가로")
        self.assertEqual(v["severity"], "critical")
        self.assertEqual(v["label"], "🚨")

    def test_boundary_equal_is_ok(self):
        """실측 5.0%, 신고 5.0% → ✅ (경계값 — 초과 아님, 상한도 아님)."""
        v = verdict_single(5.0, 5.0, "세로")
        self.assertEqual(v["severity"], "ok")
        self.assertEqual(v["label"], "✅")

    def test_industry_max_is_5(self):
        """상한 상수 = 5.0 고정 (사장님 확정 — 변경 X)."""
        self.assertEqual(INDUSTRY_MAX_AXIS_PCT, 5.0)

    def test_critical_beats_warning(self):
        """실측 6.0% (신고 2.0%) → warning 조건도 성립하지만 critical 우선."""
        v = verdict_single(6.0, 2.0, "가로")
        self.assertEqual(v["severity"], "critical")

    def test_negative_actual_is_ok(self):
        """실측 축소(-1.0%) → 신고 이하 → ✅ (음수는 항상 정상)."""
        v = verdict_single(-1.0, 0.0, "세로")
        self.assertEqual(v["severity"], "ok")

    # ── Task #38-f: BLK_7_1 정밀도 불일치 버그 회귀 가드 (round 비교) ──
    def test_blk7_float_residual_is_ok(self):
        """bbox 부동소수점 잔여(~1e-13, 표시 '+0.0%') → 정상 (기존 strict > 는 신고초과 버그)."""
        v = verdict_single(9.47e-14, 0.0, "가로")
        self.assertEqual(v["severity"], "ok")

    def test_sub_display_growth_is_ok(self):
        """실측 0.03%(화면 '+0.0%') vs 신고 0.0% → 정상 (화면과 판정 일치)."""
        self.assertEqual(verdict_single(0.03, 0.0, "가로")["severity"], "ok")
        self.assertEqual(verdict_single(0.049, 0.0, "세로")["severity"], "ok")

    def test_rounds_to_tenth_boundary(self):
        """0.05%(화면 '+0.1%')부터는 신고초과 (반올림 경계 — 화면과 일치)."""
        self.assertEqual(verdict_single(0.05, 0.0, "가로")["severity"], "warning")
        self.assertEqual(verdict_single(0.04, 0.0, "가로")["severity"], "ok")

    def test_blk5_visible_growth_still_warning(self):
        """실측 +0.2%(화면 표시값) vs 신고 0.0% → 신고초과 유지 (표시되는 성장은 판정)."""
        self.assertEqual(verdict_single(0.2, 0.0, "가로")["severity"], "warning")

    def test_reason_present(self):
        """모든 판정에 사유 문자열 포함 (사장님 확정 — 사유 알림)."""
        for actual, declared in [(2.5, 3.0), (3.5, 3.0), (5.5, 5.0)]:
            v = verdict_single(actual, declared, "가로")
            self.assertTrue(v["reason"])
            self.assertIn("가로", v["reason"])


class TestVerdictPair(unittest.TestCase):
    """가로 + 세로 통합 판정."""

    def test_both_ok(self):
        r = verdict_pair(2.0, 3.0, 2.5, 3.0)
        self.assertEqual(r["worst_severity"], "ok")
        self.assertEqual(r["worst_label"], "✅")
        self.assertEqual(r["reasons"], [])  # 정상은 사유 목록 제외

    def test_worst_is_critical(self):
        """가로 정상 + 세로 상한초과 → 통합 최악 = critical."""
        r = verdict_pair(2.0, 3.0, 6.0, 3.0)
        self.assertEqual(r["worst_severity"], "critical")
        self.assertEqual(r["worst_label"], "🚨")

    def test_worst_is_warning(self):
        """가로 신고초과 + 세로 정상 → 통합 최악 = warning."""
        r = verdict_pair(3.5, 3.0, 2.0, 3.0)
        self.assertEqual(r["worst_severity"], "warning")

    def test_reasons_exclude_ok(self):
        """사유 목록엔 경고/상한만 (정상 방향 제외)."""
        r = verdict_pair(3.5, 3.0, 2.0, 3.0)  # 가로 warning, 세로 ok
        self.assertEqual(len(r["reasons"]), 1)
        self.assertIn("가로", r["reasons"][0])

    def test_reasons_both_violate(self):
        r = verdict_pair(3.5, 3.0, 6.0, 3.0)  # 가로 warning, 세로 critical
        self.assertEqual(len(r["reasons"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
