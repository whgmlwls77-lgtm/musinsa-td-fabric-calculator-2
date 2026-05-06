# -*- coding: utf-8 -*-
"""
test_diagnose_quantity_paired.py
--------------------------------
이슈 2 — diagnose_quantity 가 PAIRED 처리 후 1벌당 마카 piece 수를 명시하는지 검증.

사장님 본질 (2026-05-06):
  "DXF unique piece 14개 (raw) → PAIRED 처리 후 1벌당 마카 piece 17개"

옵션 A 정책 (auto_nesting_v2._split_mirrored_pieces 와 동치):
  - mirror=True + q==1       → 2  (PAIRED:DOUBLE, orig+M split)
  - mirror=True + q 짝수(≥2) → q
  - mirror=True + q 홀수(≥3) → q  (split skip)
  - mirror=False/None        → q
  - Material:NON / 마카제외   → 0
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import per_garment_marker_pieces, diagnose_quantity, OK


def _piece(pid: str, q: int | None = 1, mirror=None,
           mat_inferred: str = "주원단", mat_raw: str = "") -> dict:
    return {
        "piece_id": pid,
        "piece_key": pid,
        "piece_name": pid,
        "quantity": q,
        "mirror": mirror,
        "material_inferred": mat_inferred,
        "material_raw": mat_raw,
    }


class TestPerGarmentPolicy(unittest.TestCase):
    """옵션 A 정책별 1벌당 piece 수 계산."""

    def test_q1_mirror_true_returns_2(self):
        """PAIRED:DOUBLE + Q=1 → split orig+M → 2"""
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=1, mirror=True)), 2)

    def test_q2_mirror_true_returns_2(self):
        """Q=2 + mirror=True → split q/2+q/2 = 2"""
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=2, mirror=True)), 2)

    def test_q4_mirror_true_returns_4(self):
        """Q=4 짝수 + mirror=True → split q/2+q/2 = 4"""
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=4, mirror=True)), 4)

    def test_q3_mirror_true_returns_3(self):
        """Q=3 홀수 + mirror=True → split skip → 3"""
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=3, mirror=True)), 3)

    def test_q1_no_mirror_returns_1(self):
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=1, mirror=False)), 1)

    def test_q2_no_mirror_returns_2(self):
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=2, mirror=False)), 2)

    def test_quantity_none_defaults_to_1(self):
        self.assertEqual(per_garment_marker_pieces(_piece("P1", q=None, mirror=False)), 1)

    def test_material_non_excluded(self):
        self.assertEqual(
            per_garment_marker_pieces(_piece("P1", q=1, mirror=False, mat_raw="NON")), 0
        )

    def test_inferred_marker_excluded(self):
        self.assertEqual(
            per_garment_marker_pieces(
                _piece("P1", q=1, mirror=False, mat_inferred="마카제외")
            ),
            0,
        )


class TestDiagnoseQuantityIncludesPerGarment(unittest.TestCase):

    def test_raw_includes_per_garment_marker_pieces(self):
        pieces = [
            _piece("P1", q=1, mirror=True),  # → 2
            _piece("P2", q=1, mirror=False),  # → 1
        ]
        d = diagnose_quantity({"pieces": pieces})
        self.assertIn("per_garment_marker_pieces", d["raw"])
        self.assertEqual(d["raw"]["per_garment_marker_pieces"], 3)
        self.assertEqual(d["raw"]["n_unique_pieces"], 2)
        self.assertEqual(d["raw"]["n_excluded"], 0)
        self.assertIn("PAIRED 처리 후", d["algo_state"])

    def test_summary_contains_paired_count_when_full_coverage(self):
        pieces = [_piece("P1", q=1, mirror=True), _piece("P2", q=2, mirror=False)]
        d = diagnose_quantity({"pieces": pieces})
        self.assertEqual(d["status"], OK)
        self.assertIn("1벌당 마카 piece", d["summary"])
        self.assertIn("4", d["summary"])  # 2+2

    def test_excluded_marker_separated(self):
        pieces = [
            _piece("P1", q=1, mirror=True),  # → 2
            _piece("P2", q=1, mirror=False, mat_inferred="마카제외"),  # → 0
        ]
        d = diagnose_quantity({"pieces": pieces})
        self.assertEqual(d["raw"]["per_garment_marker_pieces"], 2)
        self.assertEqual(d["raw"]["n_excluded"], 1)
        self.assertIn("마카제외 1", d["dxf_state"])


class TestMMAPS003Scenario(unittest.TestCase):
    """사장님 audit md raw: 14 unique → 13 마카 분류 + 1 NON → 1벌당 마카 piece 17."""

    def test_full_mmaps003_layout(self):
        # 사장님 audit md §3.3 표 기반 — 10 piece (3개는 표준 어휘집에 있지만 이 DXF 미사용)
        pieces = [
            _piece("BACK_BODY",                  q=1, mirror=True),   # → 2
            _piece("BACK_POCKET_FACING_BOTTOM",  q=2, mirror=False),  # → 2
            _piece("BACK_POCKET_FACING_UPPER",   q=2, mirror=False),  # → 2
            _piece("FLY",                        q=1, mirror=False),  # → 1
            _piece("FLY_UNDERLAY",               q=1, mirror=False),  # → 1
            _piece("FRONT_BODY",                 q=1, mirror=True),   # → 2
            _piece("FRONT_POCKET_FACING_BOTTOM", q=1, mirror=True),   # → 2
            _piece("FRONT_POCKET_FACING_UPPER",  q=1, mirror=True),   # → 2
            _piece("WAISTBAND_BACK",             q=1, mirror=False),  # → 1
            _piece("WAISTBAND_FRONT",            q=1, mirror=True),   # → 2
            _piece("DIA30", q=1, mirror=False, mat_raw="NON",
                   mat_inferred="마카제외"),                             # → 0
        ]
        d = diagnose_quantity({"pieces": pieces})
        self.assertEqual(d["raw"]["per_garment_marker_pieces"], 17)
        self.assertEqual(d["raw"]["n_unique_pieces"], 11)
        self.assertEqual(d["raw"]["n_excluded"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
