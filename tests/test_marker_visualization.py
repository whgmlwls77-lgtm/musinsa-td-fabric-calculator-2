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

ROOT = Path(__file__).resolve().parent.parent
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
        """식서 화살표 길이 = bbox 짧은 변 × 40% (사장님 컨벤션 30~40%)"""
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 10, "bbox_h_cm": 20,  # 짧은 변 = 10
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = add_grain_arrows_to_svg(SAMPLE_SVG, placements)
        self.assertIn('id="grain_arrows"', out)
        # 화살표 길이 = 짧은변 10 × 40% = 4
        # 중심 (5, 10), Y 방향 → start=(5, 8), end=(5, 12)
        # head_len = 4 × 18% = 0.72 → line 본체 (8 → 12-0.72=11.28)
        self.assertIn('y1="8.000"', out)
        self.assertIn('y2="11.280"', out)  # line tail (head 영역 빼고)
        # 화살촉 polygon: 첫 vertex = 화살표 끝점 (5, 12)
        self.assertIn('<polygon points="5.000,12.000', out)

    def test_arrow_color_black_konvention(self):
        """본사 컨벤션 (사장님 캡쳐 raw 2026-05-06): 식서 화살표 검정 — 빨강 폐기."""
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 10, "bbox_h_cm": 20,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = add_grain_arrows_to_svg(SAMPLE_SVG, placements)
        self.assertIn('stroke="#000000"', out)
        self.assertIn('fill="#000000"', out)
        self.assertNotIn('#cc0000', out)  # 구 빨강 폐기

    def test_marker_defs_polygon_dynamic(self):
        """markerUnits userSpaceOnUse 거대 화살촉 폐기 — polygon 동적 그리기."""
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 10, "bbox_h_cm": 20,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = add_grain_arrows_to_svg(SAMPLE_SVG, placements)
        # 구 marker 정의 (id="grain_arrow", 단수) 박혀있으면 안됨
        self.assertNotIn('<marker id="grain_arrow"', out)
        self.assertNotIn('marker-end="url(#grain_arrow)"', out)
        # polygon 화살촉 동적 생성
        self.assertIn('<polygon points=', out)

    def test_arrow_direction_unified_under_180_rotation(self):
        """이슈 1 정정 (사장님 캡쳐 raw 2026-05-08): 식서 양방향 본질 — sparrow
        가 piece 를 180° 회전 배치해도 화살표는 마카 좌표계 +Y (↓) 통일.
        본사 컨벤션 "모두 한 방향" 일치 (2WAY 시 ↓↑ 혼재 폐기).

        sparrow native transform 본질 (2026-05-11 정정): rot=180 piece 의
        anchor (x_cm/y_cm) 는 bbox 우상단. 같은 piece bbox 좌하단=(0,0) 표현
        위해 rot=0 → (0,0), rot=180 → (bw, bh) 박음.
        """
        placements_0 = [{
            "piece_id": "P_a", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 10, "bbox_h_cm": 20,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        placements_180 = [{
            "piece_id": "P_b", "x_cm": 10, "y_cm": 20,
            "bbox_w_cm": 10, "bbox_h_cm": 20,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 180,
        }]
        out_0 = add_grain_arrows_to_svg(SAMPLE_SVG, placements_0)
        out_180 = add_grain_arrows_to_svg(SAMPLE_SVG, placements_180)
        # rot=0 → end=(5, 12) ↓ / rot=180 → anchor 보정 후 동일 piece 위치 → (5, 12) ↓
        self.assertIn('<polygon points="5.000,12.000', out_0)
        self.assertIn('<polygon points="5.000,12.000', out_180)
        # 두 화살표 polygon 좌표 일치 (방향 통일 + anchor 보정 본질 입증)
        poly_0 = re.search(r'<polygon points="([^"]+)"', out_0).group(1)
        poly_180 = re.search(r'<polygon points="([^"]+)"', out_180).group(1)
        self.assertEqual(poly_0, poly_180)

    def test_arrow_direction_unified_grain_x_with_rotation(self):
        """STRAIGHT_GRAIN_X (수평 식서) — 회전 0° vs 180° 화살표 방향 동일.

        sparrow native transform 본질 (2026-05-11): rot=180 piece anchor =
        bbox 우상단 → 같은 piece bbox 좌하단=(0,0) 표현 위해 (bw, bh) 박음.
        """
        # GRAIN_X 회전 0° → base (1,0) → dx=1, dy=0, dx>0 (정상)
        # GRAIN_X 회전 180° → (-1, 0) → dx<-eps & dy≈0 → 부호 반전 → (1, 0)
        placements_0 = [{
            "piece_id": "Px_a", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 20, "bbox_h_cm": 10,
            "kind": "STRAIGHT_GRAIN_X", "rotation_applied_deg": 0,
        }]
        placements_180 = [{
            "piece_id": "Px_b", "x_cm": 20, "y_cm": 10,
            "bbox_w_cm": 20, "bbox_h_cm": 10,
            "kind": "STRAIGHT_GRAIN_X", "rotation_applied_deg": 180,
        }]
        out_0 = add_grain_arrows_to_svg(SAMPLE_SVG, placements_0)
        out_180 = add_grain_arrows_to_svg(SAMPLE_SVG, placements_180)
        poly_0 = re.search(r'<polygon points="([^"]+)"', out_0).group(1)
        poly_180 = re.search(r'<polygon points="([^"]+)"', out_180).group(1)
        self.assertEqual(poly_0, poly_180)

    def test_stroke_width_dynamic_to_arrow_length(self):
        """stroke-width 가 화살표 길이의 4% 비례 — piece 크기 무관 가림 X."""
        # 큰 piece (bbox 100cm) → arrow_len 40 → stroke 1.6
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 100, "bbox_h_cm": 200,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = add_grain_arrows_to_svg(SAMPLE_SVG, placements)
        self.assertIn('stroke-width="1.600"', out)


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
        # aspect ratio 보존 — fit_svg_to_container 가 마지막에 xMidYMid meet 적용
        # (사장님 이슈 B 본질 2026-05-07: 잘림 방지 중앙 정렬)
        self.assertIn('preserveAspectRatio="xMidYMid meet"', out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
