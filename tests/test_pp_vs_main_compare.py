# -*- coding: utf-8 -*-
"""
test_pp_vs_main_compare.py
--------------------------
PP vs 메인 패턴 면적 비교 검증 (사장님 원문 2026-07-09, 확정 사양 2026-07-14).

검증:
  1. 동일 조각 (면적 100) → 확대율 0%
  2. PP 100 vs 메인 103 → 확대율 3%
  3. 블록 이름 매칭 (match_method='block_name')
  4. 도형 유사도 매칭 (블록명 다름 + 모양 유사 → match_method='shape' + similarity_score)
  5. 크기 순 fallback 폐기 확인 (match_method='size_order' 반환 안 됨 — 사장님 확정 2026-07-15)
  6. 사이즈 불일치 (PP는 32, 메인은 33) → 매칭 0, unmatched 처리
  7. Material:NON 마카제외 / 스케일 박스 제외
  8. 갯수 불일치 초과분 unmatched
  9. PP 면적 0 → 확대율 None (계산 불가)
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp_vs_main_compare import (
    compare_pp_vs_main,
    filter_pairs_by_material,
    pair_material_code,
    SHAPE_MATCH_THRESHOLD,
)


# ── 테스트 도형 (raw 좌표) ─────────────────────────────────────────
# 의류 앞판 유사 도형 (어깨 사선 있는 L 자형).
PIECE_COORDS = [(0, 0), (30, 0), (30, 60), (18, 90), (0, 90)]
# 정사각형 — 앞판과 도형 유사도 0.5064 (실측) → 임계값 0.85 미만 = 매칭 X.
SQUARE_COORDS = [(0, 0), (40, 0), (40, 40), (0, 40)]


def _scaled(coords, s):
    """균등 확대 (축율 모사) — 도형은 동일, 면적만 s² 배."""
    return [(x * s, y * s) for x, y in coords]


def _piece(block_name="FB", size="32", area=100.0,
           material_inferred="주원단", material_raw="SELF", coords_cm=None):
    return {
        "block_name": block_name,
        "size": size,
        "area_cm2": area,
        "material_inferred": material_inferred,
        "material_raw": material_raw,
        "coords_cm": coords_cm,
    }


class TestExpansionBasic(unittest.TestCase):

    def test_identical_zero_expansion(self):
        pp = [_piece("FB", "32", 100.0)]
        main = [_piece("FB", "32", 100.0)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertAlmostEqual(r["pp_total_area_cm2"], 100.0)
        self.assertAlmostEqual(r["main_total_area_cm2"], 100.0)
        self.assertAlmostEqual(r["total_expansion_pct"], 0.0)
        self.assertAlmostEqual(r["matched_pairs"][0]["expansion_pct"], 0.0)

    def test_3pct_expansion(self):
        pp = [_piece("FB", "32", 100.0)]
        main = [_piece("FB", "32", 103.0)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertAlmostEqual(r["total_expansion_pct"], 3.0)
        self.assertAlmostEqual(r["matched_pairs"][0]["expansion_pct"], 3.0)

    def test_total_expansion_multi_piece(self):
        pp = [_piece("FB", "32", 100.0), _piece("BB", "32", 100.0)]
        main = [_piece("FB", "32", 110.0), _piece("BB", "32", 90.0)]
        r = compare_pp_vs_main(pp, main, "32")
        # 총면적 200 → 200, 확대율 0% (개별은 +10/-10)
        self.assertAlmostEqual(r["total_expansion_pct"], 0.0)


class TestMatching(unittest.TestCase):

    def test_block_name_match(self):
        pp = [_piece("FRONT_BODY", "32", 100.0), _piece("BACK_BODY", "32", 80.0)]
        main = [_piece("BACK_BODY", "32", 82.0), _piece("FRONT_BODY", "32", 105.0)]
        r = compare_pp_vs_main(pp, main, "32")
        methods = {m["match_method"] for m in r["matched_pairs"]}
        self.assertEqual(methods, {"block_name"})
        # FRONT_BODY 짝 확인 (순서 무관 이름 기준)
        fb = next(m for m in r["matched_pairs"] if m["block_name_pp"] == "FRONT_BODY")
        self.assertEqual(fb["block_name_main"], "FRONT_BODY")
        self.assertAlmostEqual(fb["pp_area"], 100.0)
        self.assertAlmostEqual(fb["main_area"], 105.0)

    def test_block_name_match_similarity_none(self):
        """이름 매칭 성사 → similarity_score 는 None (도형 계산 불필요)."""
        pp = [_piece("FB", "32", 100.0)]
        main = [_piece("FB", "32", 103.0)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertEqual(r["matched_pairs"][0]["match_method"], "block_name")
        self.assertIsNone(r["matched_pairs"][0]["similarity_score"])

    def test_shape_match_when_names_differ(self):
        """이름 다름 + 도형 동일 → match_method='shape' + similarity_score 반환.

        사장님 통찰 2026-07-15: PP → 메인 이관 시 이름은 바뀌어도 모양은 유지됨.
        """
        pp = [_piece("LTH", "32", 100.0, coords_cm=PIECE_COORDS)]
        main = [_piece("CAPS", "32", 110.0, coords_cm=_scaled(PIECE_COORDS, 1.05))]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertEqual(len(r["matched_pairs"]), 1)
        m = r["matched_pairs"][0]
        self.assertEqual(m["match_method"], "shape")
        self.assertGreaterEqual(m["similarity_score"], SHAPE_MATCH_THRESHOLD)
        self.assertEqual(m["block_name_pp"], "LTH")
        self.assertEqual(m["block_name_main"], "CAPS")
        # 면적 확대율은 raw area_cm2 기준 (도형 정규화와 무관).
        self.assertAlmostEqual(m["expansion_pct"], 10.0)

    def test_shape_mismatch_unmatched(self):
        """이름 다름 + 도형도 다름 → 매칭 X (임의 짝짓기 금지 — 원칙 #1).

        앞판 vs 정사각형 도형 유사도 0.5064 (실측) < 시스템 표준 임계값 0.85.
        """
        pp = [_piece("LTH", "32", 100.0, coords_cm=PIECE_COORDS)]
        main = [_piece("CAPS", "32", 104.0, coords_cm=SQUARE_COORDS)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertEqual(len(r["matched_pairs"]), 0)
        self.assertEqual(len(r["unmatched_pp"]), 1)
        self.assertEqual(len(r["unmatched_main"]), 1)

    def test_size_order_fallback_removed(self):
        """크기 순 매칭 폐기 확인 — 면적만 비슷하고 좌표 없으면 매칭 X.

        기존(폐기) 로직이면 A(100)↔Y(104), B(50)↔X(52) 로 짝지어졌음.
        사장님 실증 2026-07-15: 모양이 완전 다른데 면적만 비슷해 오매칭 유발 → 완전 제거.
        """
        pp = [_piece("A", "32", 100.0), _piece("B", "32", 50.0)]
        main = [_piece("X", "32", 52.0), _piece("Y", "32", 104.0)]
        r = compare_pp_vs_main(pp, main, "32")
        methods = {m["match_method"] for m in r["matched_pairs"]}
        self.assertNotIn("size_order", methods)
        self.assertEqual(len(r["matched_pairs"]), 0)
        self.assertEqual(len(r["unmatched_pp"]), 2)
        self.assertEqual(len(r["unmatched_main"]), 2)

    def test_mixed_block_then_shape(self):
        """FB 는 이름 매칭, 이름 다른 나머지는 도형 매칭."""
        pp = [_piece("FB", "32", 100.0), _piece("A", "32", 60.0, coords_cm=PIECE_COORDS)]
        main = [_piece("FB", "32", 101.0),
                _piece("Z", "32", 63.0, coords_cm=_scaled(PIECE_COORDS, 1.02))]
        r = compare_pp_vs_main(pp, main, "32")
        by_method = {m["match_method"] for m in r["matched_pairs"]}
        self.assertEqual(by_method, {"block_name", "shape"})

    def test_threshold_is_system_constant(self):
        """임계값 = 시스템 표준 고정 (사장님 확정 2026-07-15 — 사용자 조정 X).

        UI 슬라이더 폐기 → compare_pp_vs_main 은 임계값 파라미터를 받지 않고
        SHAPE_MATCH_THRESHOLD 를 직접 참조. 결과에 적용값이 박혀 UI 가 표시 가능.
        """
        self.assertEqual(SHAPE_MATCH_THRESHOLD, 0.85)
        pp = [_piece("A", "32", 100.0, coords_cm=PIECE_COORDS)]
        main = [_piece("Z", "32", 104.0, coords_cm=SQUARE_COORDS)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertEqual(r["shape_threshold"], SHAPE_MATCH_THRESHOLD)
        # 앞판 vs 정사각형 실측 0.5064 < 0.85 → 매칭 X.
        self.assertEqual(len(r["matched_pairs"]), 0)

    def test_shape_threshold_param_removed(self):
        """shape_threshold 파라미터 완전 제거 확인 (임계값 우회 경로 차단)."""
        pp = [_piece("A", "32", 100.0, coords_cm=PIECE_COORDS)]
        main = [_piece("Z", "32", 104.0, coords_cm=SQUARE_COORDS)]
        with self.assertRaises(TypeError):
            compare_pp_vs_main(pp, main, "32", shape_threshold=0.50)

    def test_square_vs_circle_blocked(self):
        """사각 vs 원 극단 케이스 (실측 0.830) → 임계값 0.85 로 차단 (확정 근거 회귀 가드).

        임계값 0.85 의 확정 근거 자체를 박음 — 이 케이스가 매칭되면 근거 붕괴.
        """
        circle = [
            (20 + 20 * math.cos(2 * math.pi * i / 64),
             20 + 20 * math.sin(2 * math.pi * i / 64))
            for i in range(64)
        ]
        pp = [_piece("SQ", "32", 1600.0, coords_cm=SQUARE_COORDS)]
        main = [_piece("CIR", "32", 1256.0, coords_cm=circle)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertEqual(len(r["matched_pairs"]), 0)
        self.assertEqual(len(r["unmatched_pp"]), 1)
        self.assertEqual(len(r["unmatched_main"]), 1)

    def test_shape_greedy_best_first(self):
        """greedy — 유사도 큰 쌍부터 확정 (면적 순서 무관)."""
        pp = [
            _piece("P1", "32", 100.0, coords_cm=PIECE_COORDS),
            _piece("P2", "32", 99.0, coords_cm=SQUARE_COORDS),
        ]
        main = [
            _piece("M1", "32", 101.0, coords_cm=SQUARE_COORDS),
            _piece("M2", "32", 98.0, coords_cm=_scaled(PIECE_COORDS, 1.01)),
        ]
        r = compare_pp_vs_main(pp, main, "32")
        pairs = {(m["block_name_pp"], m["block_name_main"]) for m in r["matched_pairs"]}
        # 도형 기준: P1(앞판)↔M2(앞판), P2(사각)↔M1(사각).
        self.assertEqual(pairs, {("P1", "M2"), ("P2", "M1")})


class TestSizeMismatch(unittest.TestCase):

    def test_size_not_common(self):
        # PP 는 32, 메인은 33 → target 32 로 비교 시 메인 조각 0
        pp = [_piece("FB", "32", 100.0)]
        main = [_piece("FB", "33", 100.0)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertEqual(len(r["matched_pairs"]), 0)
        self.assertEqual(len(r["unmatched_pp"]), 1)
        self.assertEqual(len(r["unmatched_main"]), 0)
        self.assertEqual(r["main_total_area_cm2"], 0.0)
        # pp_total=100 > 0 이므로 확대율 계산됨: (0-100)/100 = -100%
        self.assertAlmostEqual(r["total_expansion_pct"], -100.0)


class TestExclusion(unittest.TestCase):

    def test_marker_excluded_non(self):
        pp = [
            _piece("FB", "32", 100.0),
            _piece("SCALE_BOX", "32", 2500.0, material_inferred="마카제외", material_raw="NON"),
        ]
        main = [_piece("FB", "32", 103.0)]
        r = compare_pp_vs_main(pp, main, "32")
        # 스케일 박스 제외 → PP 총면적 100 (2500 제외)
        self.assertAlmostEqual(r["pp_total_area_cm2"], 100.0)
        self.assertEqual(len(r["matched_pairs"]), 1)

    def test_excess_unmatched(self):
        pp = [_piece("A", "32", 100.0), _piece("B", "32", 90.0), _piece("C", "32", 80.0)]
        main = [_piece("A", "32", 101.0)]
        r = compare_pp_vs_main(pp, main, "32")
        # A 이름 매칭 1개, PP 초과분 2개 unmatched
        self.assertEqual(len(r["matched_pairs"]), 1)
        self.assertEqual(len(r["unmatched_pp"]), 2)


def _rect(w, h):
    """(w × h) 직사각형 좌표 — bbox 확대율 검증용."""
    return [(0, 0), (w, 0), (w, h), (0, h)]


class TestBBoxExpansion(unittest.TestCase):
    """bbox 가로/세로 확대율 (사장님 확정 2026-07-15 — Task #36)."""

    def test_bbox_fields_returned(self):
        pp = [_piece("FB", "32", 1800.0, coords_cm=_rect(30, 60))]
        main = [_piece("FB", "32", 1984.5, coords_cm=_rect(31.5, 63))]
        m = compare_pp_vs_main(pp, main, "32")["matched_pairs"][0]
        self.assertAlmostEqual(m["pp_width_cm"], 30.0)
        self.assertAlmostEqual(m["pp_height_cm"], 60.0)
        self.assertAlmostEqual(m["main_width_cm"], 31.5)
        self.assertAlmostEqual(m["main_height_cm"], 63.0)

    def test_width_height_expansion_pct(self):
        """가로 +5%, 세로 +5% (31.5/30, 63/60)."""
        pp = [_piece("FB", "32", 1800.0, coords_cm=_rect(30, 60))]
        main = [_piece("FB", "32", 1984.5, coords_cm=_rect(31.5, 63))]
        m = compare_pp_vs_main(pp, main, "32")["matched_pairs"][0]
        self.assertAlmostEqual(m["width_expansion_pct"], 5.0)
        self.assertAlmostEqual(m["height_expansion_pct"], 5.0)

    def test_asymmetric_expansion(self):
        """가로만 확대 (세로 동일) → 방향 분리 확인."""
        pp = [_piece("FB", "32", 1800.0, coords_cm=_rect(30, 60))]
        main = [_piece("FB", "32", 1836.0, coords_cm=_rect(30.6, 60))]
        m = compare_pp_vs_main(pp, main, "32")["matched_pairs"][0]
        self.assertAlmostEqual(m["width_expansion_pct"], 2.0)
        self.assertAlmostEqual(m["height_expansion_pct"], 0.0)

    def test_no_coords_expansion_none(self):
        """좌표 없는 조각 → bbox 0 → 방향 확대율 None (계산 불가 — 추측 X)."""
        pp = [_piece("FB", "32", 100.0)]  # coords_cm=None
        main = [_piece("FB", "32", 103.0)]
        m = compare_pp_vs_main(pp, main, "32")["matched_pairs"][0]
        self.assertIsNone(m["width_expansion_pct"])
        self.assertIsNone(m["height_expansion_pct"])


class TestMaterialFilter(unittest.TestCase):
    """원단 필터 (사장님 확정 2026-07-15 — 원단별 검증)."""

    def test_pair_material_code(self):
        pp = [_piece("FB", "32", 100.0, material_inferred="주원단")]
        main = [_piece("FB", "32", 103.0, material_inferred="주원단")]
        m = compare_pp_vs_main(pp, main, "32")["matched_pairs"][0]
        self.assertEqual(pair_material_code(m), "SELF")

    def test_filter_keeps_only_selected(self):
        pp = [_piece("FB", "32", 100.0, material_inferred="주원단"),
              _piece("LN", "32", 50.0, material_inferred="안감")]
        main = [_piece("FB", "32", 103.0, material_inferred="주원단"),
                _piece("LN", "32", 51.0, material_inferred="안감")]
        pairs = compare_pp_vs_main(pp, main, "32")["matched_pairs"]
        only_self = filter_pairs_by_material(pairs, "SELF")
        self.assertEqual(len(only_self), 1)
        self.assertEqual(only_self[0]["block_name_pp"], "FB")

    def test_filter_all_returns_everything(self):
        pp = [_piece("FB", "32", 100.0, material_inferred="주원단"),
              _piece("LN", "32", 50.0, material_inferred="안감")]
        main = [_piece("FB", "32", 103.0, material_inferred="주원단"),
                _piece("LN", "32", 51.0, material_inferred="안감")]
        pairs = compare_pp_vs_main(pp, main, "32")["matched_pairs"]
        self.assertEqual(len(filter_pairs_by_material(pairs, "전체")), 2)
        self.assertEqual(len(filter_pairs_by_material(pairs, "")), 2)


class TestEdgeCases(unittest.TestCase):

    def test_pp_area_zero_expansion_none(self):
        pp = [_piece("FB", "32", 0.0)]
        main = [_piece("FB", "32", 100.0)]
        r = compare_pp_vs_main(pp, main, "32")
        self.assertIsNone(r["matched_pairs"][0]["expansion_pct"])
        self.assertIsNone(r["total_expansion_pct"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
