# -*- coding: utf-8 -*-
"""
test_svg_font_fixed.py
----------------------
회귀 방지: 마카 SVG 라벨 폰트 크기가 마카 길이/원단 폭과 무관하게 고정.

사장님 지적 (2026-07-13):
  "폰트는 원단폭과 무관하게 고정하는게 맞아 화면에서 글씨가 잘안보여
   원단폭과 무관하게 폰트 크기는 픽스"

이전 버그: annotate_marker_svg 축 라벨 + shrink_piece_labels piece 라벨이
  모두 marker_length_cm 비례 → 큰 마카에서 글씨가 화면 밖으로 벗어남.

검증:
  1. shrink_piece_labels — 마카 100/300/500/700 모두 동일 고정 폰트 (3.0)
  2. annotate_marker_svg 축 라벨 — 마카 100/300/500/700 모두 동일 고정 (5.5)
  3. 축 라벨(5.5) > piece 라벨(3.0) — 둘 다 고정, 축이 더 큼
  4. 원단 폭 달라도 폰트 동일 (폭 무관)
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from auto_nesting_v2 import shrink_piece_labels, annotate_marker_svg


SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 0 400 150" width="400" height="150">'
    '<polygon points="0,0 400,0 400,150 0,150" fill="none"/>'
    '<text x="10" y="20" font-size="8.00">PIECE_A</text>'
    '</svg>'
)

MARKERS = [100.0, 300.0, 500.0, 700.0]


def _font_sizes(svg: str) -> list[float]:
    return [float(x) for x in re.findall(r'font-size="([\d.]+)"', svg)]


class TestPieceLabelFontFixed(unittest.TestCase):

    def test_shrink_font_identical_across_marker_lengths(self):
        """마카 길이 100/300/500/700 → piece 라벨 폰트 모두 동일."""
        vals = []
        for mlen in MARKERS:
            out = shrink_piece_labels(SAMPLE_SVG, marker_length_cm=mlen)
            vals.append(set(_font_sizes(out)))
        # 전부 {3.0}
        self.assertEqual(vals[0], {3.0})
        self.assertTrue(all(v == vals[0] for v in vals),
                        f"마카 길이별 piece 폰트 불일치: {vals}")

    def test_shrink_not_proportional(self):
        """이전 비례(marker×0.010) 재발 방지 — 700cm 여도 7.0 아님."""
        out = shrink_piece_labels(SAMPLE_SVG, marker_length_cm=700.0)
        self.assertNotIn(7.0, _font_sizes(out))


class TestAxisLabelFontFixed(unittest.TestCase):

    def test_axis_font_identical_across_marker_lengths(self):
        """마카 길이 무관 축 라벨 폰트 고정 (5.5)."""
        axis_vals = []
        for mlen in MARKERS:
            out = annotate_marker_svg(
                SAMPLE_SVG, placements=None,
                fabric_width_cm=150.0, marker_length_cm=mlen,
            )
            fss = _font_sizes(out)
            # 축 라벨 = 최댓값(5.5), piece = 최솟값(3.0)
            axis_vals.append(max(fss))
        self.assertTrue(all(abs(v - 5.5) < 1e-6 for v in axis_vals),
                        f"축 라벨 폰트 마카길이 비례 잔존: {axis_vals}")

    def test_axis_bigger_than_piece_both_fixed(self):
        """축 라벨(5.5) > piece 라벨(3.0), 둘 다 고정."""
        out = annotate_marker_svg(
            SAMPLE_SVG, placements=None,
            fabric_width_cm=150.0, marker_length_cm=400.0,
        )
        fss = set(_font_sizes(out))
        self.assertIn(3.0, fss)   # piece 라벨
        self.assertIn(5.5, fss)   # 축 라벨
        self.assertEqual(fss, {3.0, 5.5})

    def test_font_independent_of_fabric_width(self):
        """원단 폭 달라도(150 vs 300) 폰트 동일 — 사장님 '원단폭 무관' 본질."""
        out_narrow = annotate_marker_svg(
            SAMPLE_SVG, placements=None,
            fabric_width_cm=150.0, marker_length_cm=400.0,
        )
        out_wide = annotate_marker_svg(
            SAMPLE_SVG, placements=None,
            fabric_width_cm=300.0, marker_length_cm=400.0,
        )
        self.assertEqual(set(_font_sizes(out_narrow)),
                         set(_font_sizes(out_wide)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
