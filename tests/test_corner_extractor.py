# -*- coding: utf-8 -*-
"""
test_corner_extractor.py
------------------------
조각 유형 감지 + 4코너/원형 지름 치수 추출 검증 (Task #38-g — 사장님 확정 2026-07-24).

검증 (합성 도형 — 사장님 영역 파일 비의존):
  1. 유형 감지: rectangle / curved_rectangle / n_polygon / triangle / circle / unknown
  2. 4코너 변 길이 (사각형/N각형/삼각형)
  3. 원형 중심점 + 식서 축 지름
  4. 식서 정렬 회전 불변성 (회전 + grain 각 동시 부여 → 동일 치수)
  5. 스케일 비례 · 예외(정점 부족) 처리
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import corner_extractor as ce

GRAIN0 = {"angle_deg": 0.0}   # 식서 수평(X) → +90 정렬 시 세로


def _rect(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def _tri():
    return [(0, 0), (12, 0), (6, 9)]


def _circle(r=10.0, n=72, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def _pentagon(r=10.0):
    return [(r * math.cos(2 * math.pi * i / 5 + 0.3), r * math.sin(2 * math.pi * i / 5 + 0.3))
            for i in range(5)]


def _curved_rect():
    """4코너 사각이나 좌·우 장변이 크게 곡선(bow ~1.5cm) → curved_rectangle."""
    pts = [(0.0, 0.0), (4.0, 0.0)]
    for i in range(1, 20):                       # 우 곡선변 (바깥 볼록)
        y = 20.0 * i / 20
        pts.append((4.0 + 1.5 * math.sin(math.pi * i / 20), y))
    pts.append((4.0, 20.0)); pts.append((0.0, 20.0))
    for i in range(19, 0, -1):                   # 좌 곡선변
        y = 20.0 * i / 20
        pts.append((-1.5 * math.sin(math.pi * i / 20), y))
    return pts


def _rotate(pts, deg, ox=0.0, oy=0.0):
    t = math.radians(deg)
    ct, st = math.cos(t), math.sin(t)
    return [((x - ox) * ct - (y - oy) * st + ox, (x - ox) * st + (y - oy) * ct + oy)
            for x, y in pts]


def _scale(pts, s):
    return [(x * s, y * s) for x, y in pts]


# 소매형(곡선 상단) — 커프(0,0)-(20,0), 언더암 코너 y=30, 매끄러운 아크 캡(꼭대기 42).
# 캡은 정점 다수(매끄러움) → 꼭대기가 지배 코너 아님 → 4코너 = 몸판 코너(어깨).
def _sleeve():
    pts = [(0.0, 0.0), (20.0, 0.0), (20.0, 30.0)]
    for i in range(1, 20):                       # 우→좌 아크 캡 (peak 42)
        t = i / 20.0
        pts.append((20.0 - 20.0 * t, 30.0 + 12.0 * math.sin(math.pi * t)))
    pts.append((0.0, 30.0))
    return pts


# grain 90° → get_alignment_rotation = -90, +90 = 0 → 정렬 회전 없음 (raw 그대로 검증).
GRAIN90 = {"angle_deg": 90.0}


class TestPieceType(unittest.TestCase):

    def test_rectangle(self):
        self.assertEqual(ce.detect_piece_type(_rect(10, 20)), ce.TYPE_RECTANGLE)

    def test_curved_rectangle(self):
        self.assertEqual(ce.detect_piece_type(_curved_rect()), ce.TYPE_CURVED_RECTANGLE)

    def test_triangle(self):
        self.assertEqual(ce.detect_piece_type(_tri()), ce.TYPE_TRIANGLE)

    def test_pentagon_is_n_polygon(self):
        self.assertEqual(ce.detect_piece_type(_pentagon()), ce.TYPE_N_POLYGON)

    def test_circle(self):
        self.assertEqual(ce.detect_piece_type(_circle()), ce.TYPE_CIRCLE)

    def test_invalid_unknown(self):
        self.assertEqual(ce.detect_piece_type([(0, 0), (1, 1)]), ce.TYPE_UNKNOWN)
        self.assertEqual(ce.detect_piece_type([]), ce.TYPE_UNKNOWN)


class TestCornerMeasure(unittest.TestCase):

    def test_rectangle_edges(self):
        m = ce.measure_piece(_rect(10, 20), GRAIN0)
        self.assertEqual(m["piece_type"], ce.TYPE_RECTANGLE)
        e = m["edges"]
        # 식서 +90 정렬 → 두 변 ~20, 두 변 ~10 (방향 무관 크기 검증).
        vals = sorted([e["left"], e["right"], e["top"], e["bottom"]])
        self.assertAlmostEqual(vals[0], 10.0, places=3)
        self.assertAlmostEqual(vals[1], 10.0, places=3)
        self.assertAlmostEqual(vals[2], 20.0, places=3)
        self.assertAlmostEqual(vals[3], 20.0, places=3)

    def test_rotation_invariance(self):
        """조각 30° 회전 + grain 각 30 동시 → 정렬 후 동일 변 길이."""
        base = _rect(10, 20)
        m0 = ce.measure_piece(base, {"angle_deg": 0.0})
        rot = _rotate(base, 30.0)
        m30 = ce.measure_piece(rot, {"angle_deg": 30.0})
        for k in ("left", "right", "top", "bottom"):
            self.assertAlmostEqual(m0["edges"][k], m30["edges"][k], places=3)

    def test_scale_proportional(self):
        m1 = ce.measure_piece(_rect(10, 20), GRAIN0)
        m2 = ce.measure_piece(_scale(_rect(10, 20), 1.10), GRAIN0)
        for k in ("left", "right", "top", "bottom"):
            self.assertAlmostEqual(m2["edges"][k] / m1["edges"][k], 1.10, places=4)

    def test_triangle_has_edges(self):
        m = ce.measure_piece(_tri(), GRAIN0)
        self.assertEqual(m["piece_type"], ce.TYPE_TRIANGLE)
        self.assertIsNotNone(m["edges"])
        self.assertIsNone(m["circle"])


class TestCircleMeasure(unittest.TestCase):

    def test_circle_diameters(self):
        m = ce.measure_piece(_circle(r=10.0), GRAIN0)
        self.assertEqual(m["piece_type"], ce.TYPE_CIRCLE)
        self.assertIsNone(m["edges"])
        c = m["circle"]
        self.assertAlmostEqual(c["v_diameter"], 20.0, delta=0.05)
        self.assertAlmostEqual(c["h_diameter"], 20.0, delta=0.05)

    def test_ellipse_diameters_differ(self):
        """타원 (가로 20 × 세로 10) → 지름 축별 차이."""
        ell = [(10 * math.cos(2 * math.pi * i / 72), 5 * math.sin(2 * math.pi * i / 72))
               for i in range(72)]
        m = ce.measure_piece(ell, GRAIN0)
        c = m["circle"]
        # 식서 +90 정렬 → 원래 가로(20)와 세로(10)가 축 교환. 두 지름 20/10 존재.
        dims = sorted([c["v_diameter"], c["h_diameter"]])
        self.assertAlmostEqual(dims[0], 10.0, delta=0.1)
        self.assertAlmostEqual(dims[1], 20.0, delta=0.1)


class TestAngleCornersAndCenter(unittest.TestCase):
    """Task #38-h — 각도 기반 4코너 (재샘플링 무관) + 정중앙 세로/가로 (G-F 폐기 2026-07-27)."""

    def test_find_4_corners_by_angle(self):
        c = ce.find_4_corners_by_angle(_sleeve())
        self.assertIsNotNone(c)
        self.assertEqual(set(c.keys()), {"A", "B", "c", "d"})
        self.assertEqual(len({c["A"], c["B"], c["c"], c["d"]}), 4)  # 4 distinct

    def test_angle_corners_resampling_stable(self):
        """소매를 조밀 재샘플링해도 각도 4코너 좌우변 동일 (28↔5 왜곡 해소 근거)."""
        dense = []
        pts = _sleeve()
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            dense.append(a)
            for t in (0.25, 0.5, 0.75):
                dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        m1 = ce.measure_piece(_sleeve(), GRAIN90)
        m2 = ce.measure_piece(dense, GRAIN90)
        for k in ("left", "right"):
            self.assertAlmostEqual(m1["edges"][k], m2["edges"][k], delta=0.3)

    def test_no_curved_top_field(self):
        """G-F/곡선상단 필드 폐기 확인 (사장님 지시 2026-07-27)."""
        m = ce.measure_piece(_sleeve(), GRAIN90)
        self.assertNotIn("gf", m)
        self.assertNotIn("curved_top", m)

    def test_center_axes_present(self):
        """정중앙 세로/가로 span (모든 조각)."""
        m = ce.measure_piece(_rect(10, 20), GRAIN90)
        ca = m["center_axes"]
        # rect 10×20 (grain90 → 정렬 그대로): 중앙 세로 span 20, 가로 span 10.
        self.assertAlmostEqual(ca["vertical"], 20.0, delta=0.3)
        self.assertAlmostEqual(ca["horizontal"], 10.0, delta=0.3)


class TestExpansionUseCase(unittest.TestCase):
    """4코너 확대율 계산 (axis_verdict Step 2 연동 대비 — 변별 재현)."""

    def test_shrunk_piece_negative_expansion(self):
        pp = ce.measure_piece(_rect(10, 20), GRAIN0)["edges"]
        main = ce.measure_piece(_scale(_rect(10, 20), 0.98), GRAIN0)["edges"]
        for k in ("left", "right", "top", "bottom"):
            exp = (main[k] - pp[k]) / pp[k] * 100
            self.assertAlmostEqual(exp, -2.0, places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
