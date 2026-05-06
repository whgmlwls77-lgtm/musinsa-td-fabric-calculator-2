# -*- coding: utf-8 -*-
"""
test_diagnose_quantity_by_material.py
-------------------------------------
이슈 A — 진단 [4] 재질별 piece 수 분리 검증 (사장님 본질 2026-05-07).

배경: 우리 22 = 본사 17 (SELF) + LINING 5. 합계만 표시 → 본사 비교 헷갈림.

검증:
  1. raw['per_garment_by_material'] 키 존재 + 재질별 정확 합산
  2. summary 에 재질별 분해 표시 ("주원단 17개, 안감 5개")
  3. 표준 5종 우선 정렬 (주원단/안감/포켓팅/배색/논)
  4. 마카제외 (NON) 는 by_material 에서 제외
  5. MMAPS003 시나리오: SELF 17 + LINING 5 = 22 (본사 SELF 17 일치)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import diagnose_quantity, OK


def _piece(pid, q=1, mirror=None, mat_inferred="주원단", mat_raw=""):
    return {
        "piece_id": pid,
        "piece_key": pid,
        "piece_name": pid,
        "quantity": q,
        "mirror": mirror,
        "material_inferred": mat_inferred,
        "material_raw": mat_raw,
    }


class TestPerGarmentByMaterial(unittest.TestCase):

    def test_self_only(self):
        pieces = [
            _piece("P1", q=1, mirror=True, mat_inferred="주원단"),  # 2
            _piece("P2", q=2, mirror=False, mat_inferred="주원단"),  # 2
        ]
        d = diagnose_quantity({"pieces": pieces})
        self.assertEqual(d["raw"]["per_garment_by_material"], {"주원단": 4})

    def test_self_plus_lining(self):
        pieces = [
            _piece("P1", q=1, mirror=True, mat_inferred="주원단"),  # 2
            _piece("P2", q=1, mirror=False, mat_inferred="안감"),   # 1
            _piece("P3", q=1, mirror=True, mat_inferred="안감"),   # 2
        ]
        d = diagnose_quantity({"pieces": pieces})
        self.assertEqual(
            d["raw"]["per_garment_by_material"],
            {"주원단": 2, "안감": 3},
        )
        self.assertEqual(d["raw"]["per_garment_marker_pieces"], 5)

    def test_excluded_not_in_by_material(self):
        """Material:NON 은 by_material 에서 제외."""
        pieces = [
            _piece("P1", q=1, mirror=False, mat_inferred="주원단"),
            _piece("P2", q=1, mirror=False, mat_inferred="마카제외", mat_raw="NON"),
        ]
        d = diagnose_quantity({"pieces": pieces})
        by_mat = d["raw"]["per_garment_by_material"]
        self.assertIn("주원단", by_mat)
        self.assertNotIn("마카제외", by_mat)
        self.assertNotIn("논", by_mat)

    def test_summary_contains_material_breakdown(self):
        pieces = [
            _piece("P1", q=1, mirror=True, mat_inferred="주원단"),  # 2
            _piece("P2", q=1, mirror=False, mat_inferred="안감"),   # 1
        ]
        d = diagnose_quantity({"pieces": pieces})
        self.assertIn("주원단 2개", d["summary"])
        self.assertIn("안감 1개", d["summary"])
        self.assertIn("합계 3개", d["summary"])

    def test_standard_order_priority(self):
        """주원단/안감/포켓팅/배색/논 순서 우선."""
        pieces = [
            _piece("P1", mat_inferred="배색"),
            _piece("P2", mat_inferred="안감"),
            _piece("P3", mat_inferred="주원단"),
            _piece("P4", mat_inferred="포켓팅"),
        ]
        d = diagnose_quantity({"pieces": pieces})
        # algo_state 에 표준 순서대로 박혀있는지 검증
        algo = d["algo_state"]
        idx_self = algo.find("주원단")
        idx_lining = algo.find("안감")
        idx_pkt = algo.find("포켓팅")
        idx_contrast = algo.find("배색")
        self.assertLess(idx_self, idx_lining)
        self.assertLess(idx_lining, idx_pkt)
        self.assertLess(idx_pkt, idx_contrast)


class TestMMAPS003WithLining(unittest.TestCase):
    """사장님 raw 시나리오 (2026-05-07): SELF 17 + LINING 5 = 22 합계."""

    def test_mmaps003_breakdown(self):
        # MMAPS003-test.dxf raw 측정 기반 — SELF 10 piece + LINING 3 piece + DIA30/50X50 NON
        pieces = [
            # SELF (주원단) 10 piece — 1벌당 17 합산
            _piece("BACK_BODY",                  q=1, mirror=True,  mat_inferred="주원단"),  # 2
            _piece("BACK_POCKET_FACING_BOTTOM",  q=2, mirror=None,  mat_inferred="주원단"),  # 2
            _piece("BACK_POCKET_FACING_UPPER",   q=2, mirror=None,  mat_inferred="주원단"),  # 2
            _piece("FLY",                        q=1, mirror=None,  mat_inferred="주원단"),  # 1
            _piece("FLY_UNDERLAY",               q=1, mirror=None,  mat_inferred="주원단"),  # 1
            _piece("FRONT_BODY",                 q=1, mirror=True,  mat_inferred="주원단"),  # 2
            _piece("FRONT_POCKET_FACING_BOTTOM", q=1, mirror=True,  mat_inferred="주원단"),  # 2
            _piece("FRONT_POCKET_FACING_UPPER",  q=1, mirror=True,  mat_inferred="주원단"),  # 2
            _piece("WAISTBAND_BACK",             q=1, mirror=None,  mat_inferred="주원단"),  # 1
            _piece("WAISTBAND_FRONT",            q=1, mirror=True,  mat_inferred="주원단"),  # 2
            # LINING (안감) 3 piece — 1벌당 5 합산
            _piece("BACK_POCKET_BAG",  q=1, mirror=True,  mat_inferred="안감"),  # 2
            _piece("FLY_FACING",       q=1, mirror=None,  mat_inferred="안감"),  # 1
            _piece("FRONT_POCKET_BAG", q=1, mirror=True,  mat_inferred="안감"),  # 2
            # NON (마카제외)
            _piece("MMAPS003_DIA30",   q=1, mirror=None,  mat_raw="NON", mat_inferred="마카제외"),
            _piece("50X50",            q=1, mirror=None,  mat_raw="NON", mat_inferred="마카제외"),
        ]
        d = diagnose_quantity({"pieces": pieces})
        by_mat = d["raw"]["per_garment_by_material"]
        # 본사 SELF 17 vs 우리 SELF — ✅ 일치 검증
        self.assertEqual(by_mat["주원단"], 17)
        self.assertEqual(by_mat["안감"], 5)
        self.assertEqual(d["raw"]["per_garment_marker_pieces"], 22)
        self.assertEqual(d["raw"]["n_excluded"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
