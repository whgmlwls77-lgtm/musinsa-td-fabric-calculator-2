# -*- coding: utf-8 -*-
"""
test_piece_thumbnail.py
-----------------------
piece_thumbnail.render_piece_thumbnail_svg 검증 (사장님 지시 2026-07-13).

검증:
  1. 정사각형 조각 → 정사각형 viewBox (w ≈ h)
  2. 가로 긴 조각 → 가로 긴 viewBox (w > h) + 세로 letterbox (정사각 캔버스)
  3. 세로 긴 조각 → 세로 긴 viewBox (h > w) + 가로 letterbox
  4. 빈 coords_cm / 점 부족 / 폭0 → 빈 문자열 (placeholder 는 호출자 처리)
  5. border_color / 재질 색 매핑 정합 (MATERIAL_BORDER_COLOR)
  6. svg_data_uri 왕복 (빈 svg → "")
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from piece_thumbnail import (
    render_piece_thumbnail_svg,
    svg_data_uri,
    material_border_color,
    MATERIAL_BORDER_COLOR,
)

_VIEWBOX_RE = re.compile(
    r'viewBox="\s*([\-0-9.]+)\s+([\-0-9.]+)\s+([\-0-9.]+)\s+([\-0-9.]+)"'
)


def _viewbox_wh(svg: str) -> tuple[float, float]:
    """SVG 문자열에서 viewBox 의 (width, height) 추출."""
    m = _VIEWBOX_RE.search(svg)
    assert m, f"viewBox 없음: {svg[:120]}"
    return float(m.group(3)), float(m.group(4))


def _piece(coords) -> dict:
    return {"coords_cm": coords}


class TestPieceThumbnailViewBox(unittest.TestCase):
    def test_square_piece_square_viewbox(self):
        """정사각형 조각 → viewBox w ≈ h."""
        sq = _piece([(0, 0), (10, 0), (10, 10), (0, 10)])
        svg = render_piece_thumbnail_svg(sq)
        self.assertTrue(svg.startswith("<svg"))
        w, h = _viewbox_wh(svg)
        self.assertAlmostEqual(w, h, delta=0.01)

    def test_wide_piece_wide_viewbox(self):
        """가로 긴 조각 → viewBox w > h (정사각 캔버스 → 세로 letterbox)."""
        wide = _piece([(0, 0), (20, 0), (20, 5), (0, 5)])
        svg = render_piece_thumbnail_svg(wide)
        w, h = _viewbox_wh(svg)
        self.assertGreater(w, h)
        # 캔버스는 정사각 (width=height=size_px) 유지 → letterbox 는 브라우저가 처리.
        self.assertIn('preserveAspectRatio="xMidYMid meet"', svg)
        self.assertIn('width="150" height="150"', svg)

    def test_tall_piece_tall_viewbox(self):
        """세로 긴 조각 → viewBox h > w (정사각 캔버스 → 가로 letterbox)."""
        tall = _piece([(0, 0), (5, 0), (5, 20), (0, 20)])
        svg = render_piece_thumbnail_svg(tall)
        w, h = _viewbox_wh(svg)
        self.assertGreater(h, w)

    def test_size_px_applied(self):
        """size_px 인자가 width/height 에 반영."""
        sq = _piece([(0, 0), (10, 0), (10, 10), (0, 10)])
        svg = render_piece_thumbnail_svg(sq, size_px=80)
        self.assertIn('width="80" height="80"', svg)


class TestPieceThumbnailEmpty(unittest.TestCase):
    def test_empty_coords(self):
        self.assertEqual(render_piece_thumbnail_svg(_piece([])), "")

    def test_missing_coords_key(self):
        self.assertEqual(render_piece_thumbnail_svg({}), "")

    def test_too_few_points(self):
        self.assertEqual(render_piece_thumbnail_svg(_piece([(0, 0), (1, 1)])), "")

    def test_zero_width(self):
        """폭 0 (수직선) → 빈 문자열."""
        line = _piece([(0, 0), (0, 5), (0, 10)])
        self.assertEqual(render_piece_thumbnail_svg(line), "")


class TestBorderColor(unittest.TestCase):
    def test_border_color_in_svg(self):
        sq = _piece([(0, 0), (10, 0), (10, 10), (0, 10)])
        svg = render_piece_thumbnail_svg(sq, border_color="#dc2626")
        self.assertIn('stroke="#dc2626"', svg)
        self.assertIn('fill="#f5f5f5"', svg)

    def test_material_color_mapping(self):
        # MATERIAL_OPTIONS 6종 모두 색 보유.
        for mat in ["주원단", "안감", "포켓팅", "배색", "논", "미지정"]:
            self.assertIn(mat, MATERIAL_BORDER_COLOR)
            self.assertTrue(material_border_color(mat).startswith("#"))

    def test_unknown_material_default(self):
        """미매칭/None → 미지정 default 색."""
        self.assertEqual(material_border_color("표준외원단"),
                         MATERIAL_BORDER_COLOR["미지정"])
        self.assertEqual(material_border_color(None),
                         MATERIAL_BORDER_COLOR["미지정"])


class TestSvgDataUri(unittest.TestCase):
    def test_data_uri_prefix(self):
        sq = _piece([(0, 0), (10, 0), (10, 10), (0, 10)])
        uri = svg_data_uri(render_piece_thumbnail_svg(sq))
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))

    def test_empty_svg_empty_uri(self):
        self.assertEqual(svg_data_uri(""), "")


if __name__ == "__main__":
    unittest.main()
