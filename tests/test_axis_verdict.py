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

from axis_verdict import (
    AXIS_CONSISTENCY_TOL_PCT,
    AXIS_SYMMETRY_TOL_PCT,
    INDUSTRY_MAX_AXIS_PCT,
    verdict_area,
    verdict_from_measures,
    verdict_pair,
    verdict_single,
)


def _edge_measure(ptype, left, right, top, bottom, center_v=None, center_h=None):
    return {"piece_type": ptype,
            "edges": {"left": left, "right": right, "top": top, "bottom": bottom},
            "circle": None,
            "center_axes": {"vertical": center_v, "horizontal": center_h},
            "warnings": []}


def _circle_measure(v_d, h_d):
    return {"piece_type": "circle", "edges": None,
            "circle": {"centroid": (0.0, 0.0), "v_diameter": v_d, "h_diameter": h_d},
            "warnings": []}


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


class TestVerdictArea(unittest.TestCase):
    """Task #38-g 재설계 (2026-07-26) — 판정 = 면적 확대율만."""

    def test_area_critical_over_5pct_abs(self):
        """면적 -6% (abs > 5) → 🚨 (양방향 상한 · BLK_1_1 케이스)."""
        v = verdict_area(-6.13, 0.0)
        self.assertEqual(v["severity"], "critical")
        self.assertEqual(v["label"], "🚨")

    def test_area_positive_critical(self):
        v = verdict_area(6.0, 0.0)
        self.assertEqual(v["severity"], "critical")

    def test_area_warning_over_declared(self):
        v = verdict_area(3.5, 3.0)
        self.assertEqual(v["severity"], "warning")

    def test_area_shrink_declared0_is_ok(self):
        """면적 -0.30% · 신고 0 → ✅ (축소는 신고 초과 아님 · BLK_5_1 케이스)."""
        v = verdict_area(-0.30, 0.0)
        self.assertEqual(v["severity"], "ok")

    def test_area_round_tolerance(self):
        """면적 0.04% (표시 +0.0%) · 신고 0 → ✅ (Task #38-f round 유지)."""
        self.assertEqual(verdict_area(0.04, 0.0)["severity"], "ok")
        self.assertEqual(verdict_area(0.05, 0.0)["severity"], "warning")


class TestVerticalIsLRAverage(unittest.TestCase):
    """G-F 폐기 (2026-07-27) — 세로 축율 = 좌우변 평균 (모든 조각 · 각도 4코너로 정확)."""

    def test_vertical_is_lr_average(self):
        pp = _edge_measure("rectangle", 100, 100, 40, 40)
        main = _edge_measure("rectangle", 98, 98, 40, 40)      # 좌우 -2%
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-2.0)
        self.assertAlmostEqual(r["height_actual"], -2.0)       # 좌우평균
        self.assertNotIn("gf_expansion", r)
        self.assertNotIn("curved_top", r)

    def test_center_axes_expansion_evidence(self):
        """정중앙 세로/가로 확대율 = 근거 (판정 무영향)."""
        pp = _edge_measure("rectangle", 100, 100, 40, 40, center_v=50.0, center_h=20.0)
        main = _edge_measure("rectangle", 98, 98, 40, 40, center_v=48.0, center_h=20.0)
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-2.0)
        self.assertAlmostEqual(r["center_v_expansion"], -4.0)   # 50→48
        self.assertAlmostEqual(r["center_h_expansion"], 0.0)


class TestVerdictFromMeasures(unittest.TestCase):
    """Task #38-g 재설계 — 판정=면적 · 세로/가로=근거 · 정합성 진단."""

    def test_area_drives_verdict(self):
        """판정은 면적 확대율 기준 (세로/가로 아님). 면적 -6% → 🚨."""
        pp = _edge_measure("curved_rectangle", 100, 100, 50, 50)
        main = _edge_measure("curved_rectangle", 94, 95, 49, 49)
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-6.13)
        self.assertEqual(r["verdict"]["severity"], "critical")

    def test_edges_are_evidence_only(self):
        """세로/가로 = 근거로 리턴 (판정 안 함)."""
        pp = _edge_measure("rectangle", 100, 100, 50, 50)
        main = _edge_measure("rectangle", 98, 98, 49, 49)
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-2.0)
        self.assertAlmostEqual(r["height_actual"], -2.0)   # 세로 = (좌+우)/2 근거
        self.assertAlmostEqual(r["width_actual"], -2.0)    # 가로 = (상+하)/2 근거
        self.assertEqual(r["verdict"]["severity"], "ok")   # 면적 -2% ≤ 0? -2 ≤ 0 → ok

    def test_symmetry_evidence_retained(self):
        """대칭성 = 근거 정보로 유지 (판정 X)."""
        pp = _edge_measure("curved_rectangle", 100, 100, 50, 50)
        main = _edge_measure("curved_rectangle", 100, 97, 50, 50)
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-1.5)
        self.assertEqual(len(r["symmetry"]), 1)
        self.assertIn("세로 축 비대칭", r["symmetry"][0])

    def test_consistency_tol_is_2pct(self):
        self.assertEqual(AXIS_CONSISTENCY_TOL_PCT, 2.0)

    def test_consistency_flag_on_mismatch(self):
        """세로 -5·가로 -1 → 이론 면적 ≈ -5.95%. 실제 면적 -1% → 차 ~5%p → 이상 신호."""
        pp = _edge_measure("rectangle", 100, 100, 100, 100)
        main = _edge_measure("rectangle", 95, 95, 99, 99)
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-1.0)
        self.assertTrue(r["consistency"]["flag"])
        self.assertIn("이상 신호", r["consistency"]["msg"])

    def test_consistency_ok_when_matched(self):
        """세로 -2·가로 -2 → 이론 -3.96%. 실제 -3.96% → 정합."""
        pp = _edge_measure("rectangle", 100, 100, 100, 100)
        main = _edge_measure("rectangle", 98, 98, 98, 98)
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-3.96)
        self.assertFalse(r["consistency"]["flag"])

    def test_circle_method_diameters(self):
        pp = _circle_measure(20.0, 20.0)
        main = _circle_measure(19.0, 20.4)
        r = verdict_from_measures(pp, main, 3.0, 3.0, area_exp=-3.0)
        self.assertEqual(r["method"], "circle")
        self.assertAlmostEqual(r["height_actual"], -5.0)   # 세로 지름 근거
        self.assertAlmostEqual(r["width_actual"], 2.0)     # 가로 지름 근거
        self.assertEqual(r["symmetry"], [])                # 원형 대칭성 제외

    def test_fallback_area_still_judged(self):
        """측정 실패여도 판정은 면적 기준 유지 · 세로/가로는 bbox 참고."""
        pp = {"piece_type": "unknown", "edges": None, "circle": None, "warnings": []}
        main = {"piece_type": "unknown", "edges": None, "circle": None, "warnings": []}
        r = verdict_from_measures(pp, main, 0.0, 0.0, area_exp=-6.0,
                                  bbox_width_exp=0.19, bbox_height_exp=-3.34)
        self.assertEqual(r["method"], "fallback_bbox")
        self.assertEqual(r["verdict"]["severity"], "critical")   # 면적 -6% → 🚨
        self.assertAlmostEqual(r["width_actual"], 0.19)          # bbox 참고
        self.assertAlmostEqual(r["height_actual"], -3.34)

    def test_symmetry_tol_is_half_pct(self):
        self.assertEqual(AXIS_SYMMETRY_TOL_PCT, 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
