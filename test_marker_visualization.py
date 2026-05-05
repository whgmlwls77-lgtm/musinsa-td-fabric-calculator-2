# -*- coding: utf-8 -*-
"""
test_marker_visualization.py
----------------------------
마카 시각화 본사 컨벤션 단위 테스트 (사장님 결정 2026-05-05).

검증:
  1. shrink_piece_labels — 마카 길이 기반 폰트 자동 조정
  2. ensure_aspect_preservation — preserveAspectRatio 추가
  3. add_grain_arrows_to_svg — 식서 화살표 (bbox 40%)
  4. annotate_marker_svg 통합 후처리
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from auto_nesting_v2 import (
    shrink_piece_labels,
    ensure_aspect_preservation,
    annotate_marker_svg,
    add_grain_arrows_to_svg,
)


SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 0 200 60" width="200" height="60">'
    '<rect x="0" y="0" width="50" height="20" fill="blue"/>'
    '<text x="25" y="10" font-size="3.5">PIECE_1</text>'
    '<text x="100" y="30" font-size="5">PIECE_2</text>'
    '</svg>'
)


class TestShrinkPieceLabels(unittest.TestCase):

    def test_short_marker_min_font(self):
        """마카 짧으면 최소 폰트 (0.8) 적용"""
        out = shrink_piece_labels(SAMPLE_SVG, marker_length_cm=50.0)
        # 0.010 × 50 = 0.5 → max(0.8, 0.5) = 0.8
        self.assertIn('font-size="0.80"', out)

    def test_long_marker_proportional_font(self):
        """마카 200cm → 2.00 폰트"""
        out = shrink_piece_labels(SAMPLE_SVG, marker_length_cm=200.0)
        self.assertIn('font-size="2.00"', out)

    def test_all_text_font_sizes_shrunk(self):
        """모든 <text> 의 font-size 통일"""
        out = shrink_piece_labels(SAMPLE_SVG, marker_length_cm=100.0)
        # 모든 font-size 동일 (1.00)
        sizes = set(re.findall(r'font-size="([\d.]+)"', out))
        self.assertEqual(sizes, {"1.00"})

    def test_empty_svg(self):
        self.assertEqual(shrink_piece_labels("", 100.0), "")


class TestAspectPreservation(unittest.TestCase):

    def test_adds_attribute_when_missing(self):
        out = ensure_aspect_preservation(SAMPLE_SVG)
        self.assertIn('preserveAspectRatio="xMinYMin meet"', out)

    def test_idempotent(self):
        once = ensure_aspect_preservation(SAMPLE_SVG)
        twice = ensure_aspect_preservation(once)
        self.assertEqual(once.count("preserveAspectRatio"), 1)
        self.assertEqual(twice.count("preserveAspectRatio"), 1)

    def test_empty_input(self):
        self.assertEqual(ensure_aspect_preservation(""), "")


class TestGrainArrows(unittest.TestCase):

    def test_arrow_length_40_percent_of_short_bbox(self):
        """식서 화살표 길이 = bbox 짧은 변 × 40% (사장님 컨벤션)"""
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 10, "bbox_h_cm": 20,  # 짧은 변 = 10
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = add_grain_arrows_to_svg(SAMPLE_SVG, placements)
        self.assertIn('id="grain_arrows"', out)
        # 화살표 line 길이 검증 — bbox 짧은변(10) × 40% = 4
        # piece 중심 (5, 10), 식서 Y → (5, 8) → (5, 12), 길이 4 ✓
        self.assertIn('y1="8.000"', out)
        self.assertIn('y2="12.000"', out)


class TestAnnotateMarkerIntegration(unittest.TestCase):

    def test_full_pipeline(self):
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 50, "bbox_h_cm": 20,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = annotate_marker_svg(
            SAMPLE_SVG, placements=placements,
            fabric_width_cm=60.0, marker_length_cm=200.0,
        )
        # 식서 화살표
        self.assertIn('id="grain_arrows"', out)
        # 축 라벨
        self.assertIn("원단 길이방향", out)
        # piece 라벨 폰트 축소
        self.assertIn('font-size="2.00"', out)
        # aspect ratio 보존
        self.assertIn('preserveAspectRatio="xMinYMin meet"', out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
