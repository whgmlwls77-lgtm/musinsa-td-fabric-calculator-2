# -*- coding: utf-8 -*-
"""
test_fit_svg_to_container.py
----------------------------
이슈 3 — 마카 SVG viewBox 자동 + 가로 스크롤 X 검증 (사장님 본질 2026-05-06).

검증:
  1. fit_svg_to_container 가 width/height 100% + preserveAspectRatio 강제
  2. 기존 width="200" height="60" 같은 cm 좌표계 raw 값을 100% 로 교체
  3. preserveAspectRatio 이미 있으면 갱신 (중복 X)
  4. idempotent — 두 번 호출해도 결과 동일
  5. 빈 SVG / <svg 태그 없는 입력 → 그대로
  6. annotate_marker_svg 통합 결과: 본사 컨벤션 후처리 + 컨테이너 fit
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from auto_nesting_v2 import (
    annotate_marker_svg,
    fit_svg_to_container,
)


SAMPLE_SVG_RAW = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 0 200 60" width="200" height="60">'
    '<rect x="0" y="0" width="50" height="20" fill="blue"/>'
    '</svg>'
)

SAMPLE_SVG_NO_DIMS = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60">'
    '<rect/></svg>'
)


class TestFitSvgToContainer(unittest.TestCase):

    def test_sets_width_height_100_pct(self):
        out = fit_svg_to_container(SAMPLE_SVG_RAW)
        self.assertIn('width="100%"', out)
        self.assertIn('height="100%"', out)

    def test_preserves_viewbox(self):
        """viewBox 는 그대로 보존 — 비율 계산용."""
        out = fit_svg_to_container(SAMPLE_SVG_RAW)
        self.assertIn('viewBox="0 0 200 60"', out)

    def test_replaces_raw_pixel_widths(self):
        """sparrow 의 cm raw width="200" 이 "100%" 로 교체 — iframe 스크롤 방지."""
        out = fit_svg_to_container(SAMPLE_SVG_RAW)
        self.assertNotIn('width="200"', out)
        self.assertNotIn('height="60"', out)

    def test_adds_preserve_aspect_ratio(self):
        """사장님 이슈 B (2026-05-07): xMinYMin → xMidYMid meet (잘림 방지 중앙 정렬)."""
        out = fit_svg_to_container(SAMPLE_SVG_RAW)
        self.assertIn('preserveAspectRatio="xMidYMid meet"', out)

    def test_adds_overflow_visible(self):
        """잘림 방지 — overflow=visible (사장님 이슈 B 본질 2026-05-07)."""
        out = fit_svg_to_container(SAMPLE_SVG_RAW)
        self.assertIn('overflow="visible"', out)

    def test_idempotent(self):
        once = fit_svg_to_container(SAMPLE_SVG_RAW)
        twice = fit_svg_to_container(once)
        self.assertEqual(once, twice)
        # 속성 중복 X
        self.assertEqual(once.count('width="100%"'), 1)
        self.assertEqual(once.count('height="100%"'), 1)
        self.assertEqual(once.count('preserveAspectRatio'), 1)

    def test_adds_dims_when_missing(self):
        """width/height 속성 자체가 없는 SVG에도 추가."""
        out = fit_svg_to_container(SAMPLE_SVG_NO_DIMS)
        self.assertIn('width="100%"', out)
        self.assertIn('height="100%"', out)

    def test_empty_input(self):
        self.assertEqual(fit_svg_to_container(""), "")

    def test_invalid_input_passthrough(self):
        """<svg 태그 없는 입력 → 변경 없이 그대로."""
        invalid = "<div>no svg here</div>"
        self.assertEqual(fit_svg_to_container(invalid), invalid)

    def test_only_first_svg_tag_modified(self):
        """nested SVG (rare) 의 경우 outer 만 수정, inner 보존."""
        nested = (
            '<svg width="100" height="50" viewBox="0 0 100 50">'
            '<svg width="20" height="10" viewBox="0 0 20 10"></svg>'
            '</svg>'
        )
        out = fit_svg_to_container(nested)
        # 첫 svg 만 100% 적용
        first_svg = re.search(r"<svg\b[^>]*>", out).group(0)
        self.assertIn('width="100%"', first_svg)
        # 두 번째 svg(inner) 는 그대로
        self.assertIn('width="20"', out)


class TestAnnotateMarkerIntegrationFit(unittest.TestCase):
    """annotate_marker_svg 통합 결과: fit_svg_to_container 가 마지막에 호출되어
    width/height 100% 강제 — 가로 스크롤 X."""

    def test_full_pipeline_applies_fit(self):
        placements = [{
            "piece_id": "P1", "x_cm": 0, "y_cm": 0,
            "bbox_w_cm": 50, "bbox_h_cm": 20,
            "kind": "STRAIGHT_GRAIN_Y", "rotation_applied_deg": 0,
        }]
        out = annotate_marker_svg(
            SAMPLE_SVG_RAW, placements=placements,
            fabric_width_cm=60.0, marker_length_cm=200.0,
        )
        # fit 적용 검증
        self.assertIn('width="100%"', out)
        self.assertIn('height="100%"', out)
        self.assertIn('preserveAspectRatio="xMidYMid meet"', out)
        # raw width/height 흔적 X
        first_svg = re.search(r"<svg\b[^>]*>", out).group(0)
        self.assertNotIn('width="200"', first_svg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
