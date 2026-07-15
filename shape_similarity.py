"""도형 유사도 매칭 (사장님 확정 2026-07-15).

C(간단 특징 필터) + A(정규화 IoU 정밀) 2단계.
raw 좌표 기반 계산 — 사장님 원칙 #1 준수 (추측/보간 없음).

배경:
  PP → 메인 이관 시 약간의 수정은 있어도 조각 모양이 아예 달라지진 않음 (사장님 통찰).
  이름이 다른 조각을 크기(면적) 순으로 짝짓던 기존 fallback 은 모양이 완전 다른
  조각을 오매칭시켰음 → 도형 유사도로 대체.

임계값 확정 근거 (사장님 확정 2026-07-15 — pp_vs_main_compare.SHAPE_MATCH_THRESHOLD):
  임계값 0.85 = 사각 vs 원 극단 케이스 (실측 0.830) 차단 최소값.
  사장님 원칙 #1 (추측 금지) 준수 — 실측 근거.
  사장님 원칙 #2 (결정은 사장님) — 시스템이 확정, 사용자 조정 X.

의존성: shapely + numpy (프로젝트 기존 사용 — 신규 설치 없음).
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Polygon as ShapelyPolygon


# ── 사장님 확정 상수 (하드코딩 금지 — 호출부에서 조정 가능) ──────
SIMPLE_FILTER_THRESHOLD = 0.5   # 이 미만이면 IoU 계산 skip → 0.0
SIMPLE_WEIGHT = 0.3             # 최종 = 0.3 × simple + 0.7 × IoU
IOU_WEIGHT = 0.7
ROTATION_CANDIDATES_DEG = (0, 90, 180, 270)   # × 미러 2 = 8 조합


def _as_array(coords) -> np.ndarray | None:
    """coords_cm → (N, 2) float 배열. 폴리곤 성립 최소 3점."""
    if coords is None:
        return None
    arr = np.asarray([(float(p[0]), float(p[1])) for p in coords], dtype=float) \
        if len(coords) else np.empty((0, 2))
    if arr.shape[0] < 3:
        return None
    return arr


def _polygon(arr: np.ndarray) -> ShapelyPolygon | None:
    """(N, 2) 배열 → shapely 폴리곤. 자기교차는 buffer(0) 로 정리."""
    try:
        poly = ShapelyPolygon(arr)
    except Exception:
        return None
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    return poly


# ╔════════════════════════════════════════════════════════════╗
# ║ [C] 간단 특징 벡터 (빠른 필터)                             ║
# ╚════════════════════════════════════════════════════════════╝
def compute_simple_features(coords_cm) -> dict | None:
    """조각 외곽선 raw 좌표 → 크기 무관 특징 4개.

    반환:
      - aspect_ratio         : bbox 가로/세로 비
      - compactness          : 4πA/P² (완벽 원=1, 길쭉할수록 낮음)
      - convex_hull_vertices : shapely convex_hull 꼭지점 수
      - bbox_area_ratio      : 실제 면적 / bbox 면적

    좌표가 폴리곤을 이루지 못하면 None (호출자가 매칭 불가 처리).
    """
    arr = _as_array(coords_cm)
    if arr is None:
        return None
    poly = _polygon(arr)
    if poly is None:
        return None

    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    h = maxy - miny
    if w <= 0 or h <= 0:
        return None

    area = poly.area
    perim = poly.length
    hull = poly.convex_hull
    # exterior.coords 는 첫 점이 끝에 반복 → -1.
    hull_vertices = max(len(hull.exterior.coords) - 1, 3)

    return {
        "aspect_ratio": w / h,
        "compactness": (4.0 * math.pi * area / (perim * perim)) if perim > 0 else 0.0,
        "convex_hull_vertices": float(hull_vertices),
        "bbox_area_ratio": area / (w * h),
    }


_FEATURE_KEYS = ("aspect_ratio", "compactness", "convex_hull_vertices", "bbox_area_ratio")


def simple_similarity(f1: dict, f2: dict) -> float:
    """4개 특징 벡터 L2 정규화 후 코사인 유사도. 0~1.

    사장님 사양 그대로 (2026-07-15). 특징이 모두 양수라 코사인은 값이 높게 나오며
    (빠른 skip 필터 용도), 실제 변별은 [A] normalized_iou 가 담당한다.
    """
    if not f1 or not f2:
        return 0.0
    v1 = np.array([f1[k] for k in _FEATURE_KEYS], dtype=float)
    v2 = np.array([f2[k] for k in _FEATURE_KEYS], dtype=float)
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 <= 0 or n2 <= 0:
        return 0.0
    cos = float(np.dot(v1, v2) / (n1 * n2))
    return max(0.0, min(1.0, cos))


# ╔════════════════════════════════════════════════════════════╗
# ║ [A] 정규화 IoU (정밀)                                      ║
# ╚════════════════════════════════════════════════════════════╝
def _pca_align(arr: np.ndarray) -> np.ndarray:
    """PCA 주축 정렬 — 무게중심 원점 이동 + 제1 주축을 x축으로 회전.

    numpy np.linalg.eigh 직접 구현 (외부 의존성 없음).
    """
    centered = arr - arr.mean(axis=0)
    cov = np.cov(centered.T)
    if not np.all(np.isfinite(cov)):
        return centered
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]          # 분산 큰 축 먼저
    return centered @ vecs[:, order]


def _normalize_bbox(arr: np.ndarray) -> np.ndarray | None:
    """bbox 크기 통일 — 긴 변 = 1 로 균등 축소 + bbox 중심 원점.

    균등(uniform) 스케일 → 가로/세로 비 보존.
    (bbox 를 정사각으로 늘리는 비균등 정규화는 2:1 직사각형과 정사각형을
     동일 도형으로 만들어 오매칭을 유발하므로 채택 X.)
    """
    mins = arr.min(axis=0)
    maxs = arr.max(axis=0)
    span = maxs - mins
    scale = float(max(span[0], span[1]))
    if scale <= 0:
        return None
    center = (mins + maxs) / 2.0
    return (arr - center) / scale


def _transform(arr: np.ndarray, deg: float, mirror: bool) -> np.ndarray:
    """미러(좌우 반전) 후 회전."""
    out = arr.copy()
    if mirror:
        out[:, 0] = -out[:, 0]
    t = math.radians(deg)
    rot = np.array([[math.cos(t), -math.sin(t)],
                    [math.sin(t), math.cos(t)]], dtype=float)
    return out @ rot.T


def normalized_iou(coords1, coords2, try_mirror: bool = True) -> float:
    """두 폴리곤의 크기/회전/미러 정규화 후 IoU (0~1).

    1. bbox 크기 통일 (긴 변 = 1 균등 스케일 정규화)
    2. PCA 축 정렬 (회전 통일) — shapely + numpy
    3. 미러 시도 (좌우 반전 후 재계산, 최고값 채택)
    4. IoU (intersection.area / union.area) 반환

    회전 후보 4개(0°/90°/180°/270°) × 미러 여부 2 = 8 조합 중 최고 IoU 채택.
    (PCA 주축 부호 모호성 — 축이 뒤집혀 정렬될 수 있어 8 조합 전수 확인.)
    """
    a1 = _as_array(coords1)
    a2 = _as_array(coords2)
    if a1 is None or a2 is None:
        return 0.0

    base1 = _normalize_bbox(_pca_align(a1))
    aligned2 = _pca_align(a2)
    if base1 is None:
        return 0.0
    poly1 = _polygon(base1)
    if poly1 is None:
        return 0.0

    best = 0.0
    mirrors = (False, True) if try_mirror else (False,)
    for mirror in mirrors:
        for deg in ROTATION_CANDIDATES_DEG:
            cand = _normalize_bbox(_transform(aligned2, deg, mirror))
            if cand is None:
                continue
            poly2 = _polygon(cand)
            if poly2 is None:
                continue
            try:
                inter = poly1.intersection(poly2).area
                union = poly1.union(poly2).area
            except Exception:
                continue
            if union > 0:
                best = max(best, inter / union)
    return max(0.0, min(1.0, best))


# ╔════════════════════════════════════════════════════════════╗
# ║ 통합 유사도 (C + A)                                        ║
# ╚════════════════════════════════════════════════════════════╝
def shape_similarity(coords1, coords2) -> float:
    """0~1 도형 유사도.

    1. simple_similarity 로 빠른 필터 (< 0.5 는 IoU 계산 skip → 0.0 반환)
    2. normalized_iou 로 정밀 계산
    3. 최종 = 0.3 × simple + 0.7 × IoU
    """
    f1 = compute_simple_features(coords1)
    f2 = compute_simple_features(coords2)
    if f1 is None or f2 is None:
        return 0.0
    simple = simple_similarity(f1, f2)
    if simple < SIMPLE_FILTER_THRESHOLD:
        return 0.0
    iou = normalized_iou(coords1, coords2)
    return SIMPLE_WEIGHT * simple + IOU_WEIGHT * iou
