# -*- coding: utf-8 -*-
"""
test_placements_symmetry.py
---------------------------
회귀 방지: nest_by_material(단일 사이즈 경로) 와 nest_by_material_multisize
(복수 사이즈 경로) 의 summary_rows 스키마 대칭 검증.

버그 (2026-07-13, 사장님 실물 캡처):
  단일 사이즈 산출 시 UI "마카 갯수 0 개" — nest_by_material summary_rows 에
  placements_total 필드가 누락되어 app.py row.get("placements_total", 0) → 0.
  복수 경로(2026-05-10 사장님 본질)에는 있었으나 단일 경로에 미반영.

검증:
  1. nest_by_material summary_rows 각 row 에 placements_total 키 존재
  2. nest_by_material_multisize summary_rows 각 row 에 placements_total 키 존재
  3. 두 함수 summary_rows 스키마(키 집합) 완전 동일
  4. 실제 nesting 성공 시 placements_total >= 1 (마카 깔린 piece 수, 0 아님)

주: 에러 경로도 res["placements"]=[] 로 전체 스키마를 append 하므로
    sparrow 바이너리 성공/실패와 무관하게 키 대칭은 성립 (환경 비의존).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from auto_nesting_v2 import nest_by_material, nest_by_material_multisize


def _piece(pid: str, inferred: str = "주원단", q: int = 1) -> dict:
    return {
        "piece_id": pid,
        "piece_name": pid,
        "size": "L",
        "quantity": q,
        "mirror": None,
        "material_raw": "SELF",
        "material_inferred": inferred,
        "coords_cm": [(0, 0), (10, 0), (10, 10), (0, 10)],
        "width_cm": 10.0, "height_cm": 10.0,
        "grain": {"angle_deg": 90.0, "kind": "STRAIGHT_GRAIN_Y",
                  "length_mm": 100.0, "raw_layer": "7"},
    }


class TestPlacementsSymmetry(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pieces = [_piece("P1"), _piece("P2")]
        widths = {"주원단": 144.0}
        # 단일 사이즈 경로 (벌수 1) — 버그가 노출됐던 경로.
        cls.single = nest_by_material(
            pieces=[dict(p) for p in pieces],
            fabric_widths_per_material=widths,
            sizes_to_nest=["L"], n_lay=1, runtime_seconds=2,
        )
        # 복수 사이즈 경로 (정상 baseline).
        cls.multi = nest_by_material_multisize(
            pieces=[dict(p) for p in pieces],
            fabric_widths_per_material=widths,
            size_ratio={"L": 1}, runtime_seconds=2,
        )

    def test_single_rows_have_placements_total(self):
        rows = self.single["summary_rows"]
        self.assertTrue(rows, "단일 경로 summary_rows 가 비어있음")
        for r in rows:
            self.assertIn("placements_total", r)
            self.assertIn("placements_per_garment", r)

    def test_multi_rows_have_placements_total(self):
        rows = self.multi["summary_rows"]
        self.assertTrue(rows, "복수 경로 summary_rows 가 비어있음")
        for r in rows:
            self.assertIn("placements_total", r)
            self.assertIn("placements_per_garment", r)

    def test_schema_symmetry(self):
        """두 함수 summary_rows 의 키 집합 완전 동일."""
        s_keys = set(self.single["summary_rows"][0].keys())
        m_keys = set(self.multi["summary_rows"][0].keys())
        self.assertEqual(
            s_keys, m_keys,
            f"스키마 불일치 — 단일만: {s_keys - m_keys} / 복수만: {m_keys - s_keys}",
        )

    def test_placements_total_nonzero_when_nested(self):
        """nesting 성공(has_error=False) 시 placements_total >= 1 (마카 갯수 0 버그 재발 방지)."""
        for r in self.single["summary_rows"]:
            if not r.get("has_error"):
                self.assertGreaterEqual(
                    r["placements_total"], 1,
                    "단일 경로 nesting 성공인데 placements_total 이 0 — 회귀 재발",
                )

    def test_single_total_garments_reflects_n_lay(self):
        """단일 경로 total_garments = n_lay (raw 진실값). n_lay=1 → 1."""
        for r in self.single["summary_rows"]:
            self.assertEqual(r["total_garments"], 1)


if __name__ == "__main__":
    unittest.main()
