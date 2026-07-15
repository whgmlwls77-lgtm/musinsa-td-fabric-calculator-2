# -*- coding: utf-8 -*-
"""
test_shape_similarity.py
------------------------
도형 유사도 매칭 검증 (사장님 확정 사양 2026-07-15).

배경:
  PP → 메인 이관 시 약간의 수정은 있어도 조각 모양이 아예 달라지진 않음 (사장님 통찰).
  이름 매칭 실패 조각을 크기(면적) 순으로 짝짓던 기존 fallback = 오매칭 유발 → 도형 유사도로 대체.

검증 (실측 기준 — 2026-07-15 측정):
  1. identity (자기 자신)   → 1.0        (실측 1.0000)
  2. 90° 회전               → >= 0.95    (실측 0.9682)
  3. 미러                   → >= 0.95    (실측 1.0000)
  4. 10% 확대 (축율)        → >= 0.90    (실측 1.0000)
  5. 완전 다른 조각 (사각형 vs 원) → 임계값 0.85 로 차단 (실측 0.830 — 아래 주석 참조)

임계값 0.85 확정 경위 (사장님 확정 2026-07-15):
  원사양 [4] 는 "사각형 vs 원 → 유사도 < 0.5" 를 요구했으나, 사양 공식
  `0.3 × simple + 0.7 × IoU` 로는 구조적으로 불가능 (클로드 실측 보고).
    - 사각형 vs 원 정규화 IoU = 0.784 (두 도형이 실제로 78% 겹침 — 원 면적 = bbox × π/4)
    - simple(코사인) = 0.936 (특징 4개 전부 양수 → 코사인은 0.5 밑으로 안 내려감)
    - 최종 = 0.3 × 0.936 + 0.7 × 0.784 = 0.830
  공식 최솟값 = 0.15 + 0.7 × IoU → < 0.5 는 simple 필터(< 0.5)가 걸려야 가능한데
  코사인은 그 밑으로 갈 수 없음 → 공식과 원 기준 상호 배타.
  → 사장님 결정: 공식 유지 + 임계값을 0.85 (사각 vs 원 0.830 차단 최소값) 로 확정.
    가중치 임의 조정은 추측(원칙 #1 위반)이라 채택 X — 실측 근거로 임계값만 확정.
  차단 자체의 회귀 가드는 tests/test_pp_vs_main_compare.py::test_square_vs_circle_blocked.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shape_similarity import (
    compute_simple_features,
    normalized_iou,
    shape_similarity,
    simple_similarity,
)


# ── 테스트 도형 (raw 좌표 — 추측/보간 없음) ────────────────────────
# 의류 앞판 유사 도형 (어깨 사선 있는 L 자형).
PIECE = [(0, 0), (30, 0), (30, 60), (18, 90), (0, 90)]
SQUARE = [(0, 0), (40, 0), (40, 40), (0, 40)]


def _circle(r=20.0, n=64, cx=20.0, cy=20.0):
    """원 근사 (정 n 각형)."""
    return [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def _rot90(pts):
    """90° 회전 (x, y) → (-y, x)."""
    return [(-y, x) for x, y in pts]


def _mirror(pts):
    """좌우 미러 (x, y) → (-x, y)."""
    return [(-x, y) for x, y in pts]


def _scale(pts, s):
    """균등 확대 (축율 모사)."""
    return [(x * s, y * s) for x, y in pts]


class TestShapeSimilarityBoss(unittest.TestCase):
    """사장님 확정 5 케이스 중 유사도 값 자체를 검증하는 4 케이스.

    5번(사각형 vs 원)은 유사도 값이 아니라 "매칭 차단" 이 본질 →
    tests/test_pp_vs_main_compare.py::test_square_vs_circle_blocked 에서 가드.
    """

    def test_identity(self):
        """자기 자신 → 유사도 1.0 (실측 1.0000)."""
        self.assertAlmostEqual(shape_similarity(PIECE, PIECE), 1.0, places=6)

    def test_rotation_90(self):
        """90° 회전 → >= 0.95 (실측 0.9682 — PCA 정렬 + 4 회전 후보)."""
        self.assertGreaterEqual(shape_similarity(PIECE, _rot90(PIECE)), 0.95)

    def test_mirror(self):
        """미러 (좌우 페어 조각) → >= 0.95 (실측 1.0000 — 8 조합 중 미러 채택)."""
        self.assertGreaterEqual(shape_similarity(PIECE, _mirror(PIECE)), 0.95)

    def test_scale_10pct(self):
        """10% 확대 (축율) → >= 0.90 (실측 1.0000 — bbox 균등 정규화로 크기 무관)."""
        self.assertGreaterEqual(shape_similarity(PIECE, _scale(PIECE, 1.10)), 0.90)


class TestNormalizedIoU(unittest.TestCase):
    """[A] 정규화 IoU — 회전/미러/스케일 불변 확인."""

    def test_iou_identity(self):
        self.assertAlmostEqual(normalized_iou(PIECE, PIECE), 1.0, places=6)

    def test_iou_rotation_invariant(self):
        self.assertGreaterEqual(normalized_iou(PIECE, _rot90(PIECE)), 0.95)

    def test_iou_scale_invariant(self):
        self.assertGreaterEqual(normalized_iou(PIECE, _scale(PIECE, 1.10)), 0.95)

    def test_iou_aspect_discriminates(self):
        """정사각형 vs 2:1 직사각형 → IoU 0.5 (균등 스케일 정규화로 가로세로 비 보존).

        bbox 를 정사각으로 늘리는 비균등 정규화였다면 두 도형이 동일(IoU 1.0)해져
        오매칭 → 균등 스케일 채택 근거 회귀 가드.
        """
        rect_2x1 = [(0, 0), (80, 0), (80, 40), (0, 40)]
        self.assertAlmostEqual(normalized_iou(SQUARE, rect_2x1), 0.5, places=2)

    def test_iou_invalid_coords_zero(self):
        """폴리곤 미성립 (점 2개) → 0.0 (추측 X)."""
        self.assertEqual(normalized_iou([(0, 0), (1, 1)], PIECE), 0.0)


class TestSimpleFeatures(unittest.TestCase):
    """[C] 간단 특징 — raw 좌표 기반 계산 확인."""

    def test_square_features(self):
        f = compute_simple_features(SQUARE)
        self.assertAlmostEqual(f["aspect_ratio"], 1.0, places=6)
        # 정사각형 compactness = 4πA/P² = 4π(1600)/(160²) = 0.7854
        self.assertAlmostEqual(f["compactness"], math.pi / 4.0, places=4)
        self.assertEqual(f["convex_hull_vertices"], 4.0)
        self.assertAlmostEqual(f["bbox_area_ratio"], 1.0, places=6)

    def test_invalid_coords_none(self):
        """폴리곤 미성립 → None (호출자가 매칭 불가 처리)."""
        self.assertIsNone(compute_simple_features([(0, 0), (1, 1)]))
        self.assertIsNone(compute_simple_features([]))

    def test_simple_similarity_identity(self):
        f = compute_simple_features(PIECE)
        self.assertAlmostEqual(simple_similarity(f, f), 1.0, places=6)

    def test_simple_similarity_none_zero(self):
        self.assertEqual(simple_similarity(None, None), 0.0)


class TestShapeDiscrimination(unittest.TestCase):
    """다른 조각 변별력 — 시스템 표준 임계값 0.85 기준."""

    def test_square_vs_circle_below_threshold(self):
        """사각형 vs 원 → 임계값 0.85 미만 (실측 0.830 — 0.85 확정의 근거값).

        이 값이 0.85 이상으로 올라가면 임계값 확정 근거가 붕괴 → 회귀 가드.
        """
        self.assertLess(shape_similarity(SQUARE, _circle()), 0.85)

    def test_different_pieces_below_threshold(self):
        """앞판 vs 사각형 → 시스템 표준 임계값 0.85 미만 → 매칭 X (실측 0.5064)."""
        self.assertLess(shape_similarity(PIECE, SQUARE), 0.85)

    def test_different_pieces_circle_below_threshold(self):
        """앞판 vs 원 → 시스템 표준 임계값 0.85 미만 → 매칭 X (실측 0.5612)."""
        self.assertLess(shape_similarity(PIECE, _circle()), 0.85)

    def test_invalid_coords_zero(self):
        """좌표 없는 조각 → 0.0 (임의 짝짓기 X — 원칙 #1)."""
        self.assertEqual(shape_similarity([], PIECE), 0.0)
        self.assertEqual(shape_similarity(None, PIECE), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
