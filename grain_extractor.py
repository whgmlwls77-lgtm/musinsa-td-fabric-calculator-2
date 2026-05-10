# -*- coding: utf-8 -*-
"""
grain_extractor.py
------------------
DXF 블록에서 식서/푸서/바이어스(원단 결방향) 정보 추출.

[설계 원칙]
  - LAYER명에 의존하지 않는다 (Optitex 출력은 LAYER가 숫자라 매칭 불가).
  - 점수 기반 자동 식별 — 식서 LAYER의 사회적 컨벤션을 정량화:
      LINE 전용 / 블록당 1~2개 / 0·45·90° 근처 / 이름 휴리스틱.
  - 회전 옵션은 1WAY/2WAY 만. 90도 회전·FREE 같은 의류 외 개념은 도입 금지.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict


# ╔════════════════════════════════════════════════════════════╗
# ║ 상수                                                       ║
# ╚════════════════════════════════════════════════════════════╝
# 각도 분류 허용 오차(°) — 식서/푸서/바이어스 분류 기준.
ANGLE_TOL_GRAIN: float = 10.0    # 0°/90° 식서 허용 오차
ANGLE_TOL_BIAS: float = 10.0     # 45° 바이어스 허용 오차

# detect_grain_layer 점수 가중치.
SCORE_LINE_ONLY: int = 5
SCORE_BLOCK_COVERAGE: int = 3
SCORE_ANGLE_CLUSTERING: int = 2
SCORE_NAME_HEURISTIC: int = 1

# LAYER명 휴리스틱 (정확 일치 또는 대문자 포함).
GRAIN_NAME_KEYWORDS: tuple[str, ...] = ("GRAIN", "STRAIGHT", "GR", "SG", "GL")
GRAIN_NAME_EXACT: tuple[str, ...] = ("7",)


# ╔════════════════════════════════════════════════════════════╗
# ║ 헬퍼                                                       ║
# ╚════════════════════════════════════════════════════════════╝
def _line_angle_mod180(line_entity) -> float:
    """LINE 엔티티의 방향 각도(°)를 0~180 범위로 정규화.
    LINE 시작/끝 어느 쪽이 화살표 머리든 같은 값이 나오게 mod 180."""
    s, e = line_entity.dxf.start, line_entity.dxf.end
    ang = math.degrees(math.atan2(e.y - s.y, e.x - s.x))
    return ang % 180.0


def _near_anchor(angle_mod180: float, anchor: float, tol: float) -> bool:
    """0~180 정규화된 각도가 anchor 와 ±tol 안에 있는지.
    180 ↔ 0 wrap-around 도 처리."""
    d = abs(angle_mod180 - anchor)
    return min(d, 180.0 - d) <= tol


# ╔════════════════════════════════════════════════════════════╗
# ║ 1. 식서 LAYER 자동 식별 (점수 기반)                         ║
# ╚════════════════════════════════════════════════════════════╝
def detect_grain_layer(doc) -> str | None:
    """
    DXF 사용자 블록을 스캔, 각 LAYER 에 점수를 매겨 식서 LAYER 후보 선택.

    점수 룰:
      +5 : LAYER 가 LINE 엔티티만 보유 (POLYLINE/TEXT 없음)
      +3 : 블록 50% 이상 커버 + 블록당 LINE 평균 1~2개
      +2 : 각도가 0°/45°/90°/135° 근처(±10°)에 90% 이상 몰림
      +1 : LAYER명이 "7" 정확 일치 또는 GRAIN/STRAIGHT/GR 등 포함

    동점은 LAYER ID 작은 것 우선. 최고점이 0 이면 None.
    """
    user_blocks = [b for b in doc.blocks if not b.name.startswith("*")]
    if not user_blocks:
        return None

    # 레이어별 entity 타입 분포 + LINE 좌표 수집을 한 번의 순회로.
    layer_types: dict[str, Counter] = defaultdict(Counter)
    layer_lines: dict[str, list] = defaultdict(list)  # [(block_name, line)]
    for block in user_blocks:
        for e in block:
            layer = e.dxf.layer
            layer_types[layer][e.dxftype()] += 1
            if e.dxftype() == "LINE":
                layer_lines[layer].append((block.name, e))

    if not layer_lines:
        return None

    n_blocks = len(user_blocks)
    scores: dict[str, int] = {}

    for layer, lines in layer_lines.items():
        score = 0

        # +5: LINE 외 entity 없음
        non_line = sum(c for t, c in layer_types[layer].items() if t != "LINE")
        if non_line == 0:
            score += SCORE_LINE_ONLY

        # +3: 블록 커버리지 50%+ 및 블록당 평균 1~2개
        block_counts = Counter(b for b, _ in lines)
        coverage = len(block_counts) / n_blocks
        avg_per_block = len(lines) / max(len(block_counts), 1)
        if coverage >= 0.5 and 1.0 <= avg_per_block <= 2.0:
            score += SCORE_BLOCK_COVERAGE

        # +2: 각도가 정통 anchor (0/45/90/135) 에 90% 이상 몰림
        anchors = (0.0, 45.0, 90.0, 135.0)
        good = sum(
            1 for _, ln in lines
            if any(_near_anchor(_line_angle_mod180(ln), a, ANGLE_TOL_GRAIN)
                   for a in anchors)
        )
        if good / len(lines) >= 0.9:
            score += SCORE_ANGLE_CLUSTERING

        # +1: 이름 휴리스틱
        upper = layer.upper()
        if layer in GRAIN_NAME_EXACT or any(kw in upper for kw in GRAIN_NAME_KEYWORDS):
            score += SCORE_NAME_HEURISTIC

        scores[layer] = score

    if not scores or max(scores.values()) == 0:
        return None

    # 정렬: 점수 내림차순, 동점은 LAYER ID 작은 것 (숫자 우선, 비숫자는 뒤로).
    def sort_key(item: tuple[str, int]) -> tuple:
        layer, score = item
        try:
            lid = int(layer)
        except ValueError:
            lid = float("inf")
        return (-score, lid, layer)

    return sorted(scores.items(), key=sort_key)[0][0]


# ╔════════════════════════════════════════════════════════════╗
# ║ 2. 블록 단위 식서 정보 추출                                ║
# ╚════════════════════════════════════════════════════════════╝
def extract_grain(block, grain_layer: str | None) -> dict | None:
    """
    블록 안에서 grain_layer 의 첫 LINE 1개를 찾아 결방향 정보 추출.

    분류 (각도는 mod 180):
      0~10° 또는 170~180° → "STRAIGHT_GRAIN_X"  (X축 방향 식서)
      80~100°             → "STRAIGHT_GRAIN_Y"  (Y축 방향 식서)
      35~55° 또는 125~145° → "BIAS"
      그 외               → "NONSTANDARD"

    grain_layer 가 None 이거나 LINE 을 못 찾으면 None.
    호출자가 None 을 받으면 fallback (보통 {"kind": "UNKNOWN"}) 처리.
    """
    if not grain_layer:
        return None

    for e in block:
        if e.dxftype() != "LINE" or e.dxf.layer != grain_layer:
            continue

        s, ed = e.dxf.start, e.dxf.end
        length_mm = math.hypot(ed.x - s.x, ed.y - s.y)
        ang = _line_angle_mod180(e)

        # 분류 (구간 검사. mod 180 이므로 0/180 wrap 은 별도 처리.)
        if ang <= ANGLE_TOL_GRAIN or ang >= 180.0 - ANGLE_TOL_GRAIN:
            kind = "STRAIGHT_GRAIN_X"
        elif abs(ang - 90.0) <= ANGLE_TOL_GRAIN:
            kind = "STRAIGHT_GRAIN_Y"
        elif abs(ang - 45.0) <= ANGLE_TOL_BIAS or abs(ang - 135.0) <= ANGLE_TOL_BIAS:
            kind = "BIAS"
        else:
            kind = "NONSTANDARD"

        return {
            "angle_deg": round(ang, 2),
            "length_mm": round(length_mm, 2),
            "kind": kind,
            "raw_layer": grain_layer,
        }

    return None


# ╔════════════════════════════════════════════════════════════╗
# ║ 3. 식서 정렬용 회전                                         ║
# ╚════════════════════════════════════════════════════════════╝
def get_alignment_rotation(grain: dict | None) -> float:
    """피스를 식서 가로(X축, sparrow strip 길이방향)로 통일하기 위한 회전 각도(도).
    양수=반시계, 음수=시계.

    사장님 본질 (2026-05-08 정정): 식서 = 원단 길이방향 = 마카 가로 (→).
    sparrow strip 좌표계: X축 = 마카 길이 (무한 성장), Y축 = 원단 폭.
    → STRAIGHT_GRAIN_X 가 정상 식서 — 그대로 배치.

      STRAIGHT_GRAIN_X → 0°    (이미 식서 가로 = 정상)
      STRAIGHT_GRAIN_Y → 90°   (반시계 90° 회전 → 식서 X 통일)
      BIAS             → 0°    (45° 그대로 유지)
      UNKNOWN          → 0°    (caller 가 STRAIGHT_GRAIN_X 가정 + 경고)
      NONSTANDARD      → 0°    (caller 가 경고)

    회전 0° = "DXF 에 그려진 그대로 배치". rectpack 의 rotation 파라미터와
    독립적인 사전처리. 의류에 없는 90° 또는 임의 회전은 절대 반환하지 않는다.
    """
    if not grain:
        return 0.0
    kind = grain.get("kind", "UNKNOWN")
    if kind == "STRAIGHT_GRAIN_Y":
        return 90.0
    # STRAIGHT_GRAIN_X / BIAS / UNKNOWN / NONSTANDARD 모두 0°
    return 0.0


def estimate_grain_from_bbox(width: float, height: float) -> dict:
    """
    식서 마크가 없는 피스의 grain 을 외곽선 bbox 비율로 자동 추정.

    규칙:
      height/width > 1.2  → STRAIGHT_GRAIN_Y (세로 긴 피스)
      width/height > 1.2  → STRAIGHT_GRAIN_X (가로 긴 피스)
      비율 0.83 ~ 1.2     → STRAIGHT_GRAIN_Y (정사각형 근접 — 셔츠 본체로 Y 가정)

    반환 dict 에 estimated=True 표시 → 호출자가 경고 출력 가능.
    실측값(angle_deg/length_mm) 은 없음(0).
    """
    if width <= 0 or height <= 0:
        return {
            "kind": "STRAIGHT_GRAIN_Y",
            "angle_deg": 90.0,
            "length_mm": 0.0,
            "raw_layer": None,
            "estimated": True,
            "reason": f"invalid bbox (w={width}, h={height}) — Y 기본",
        }

    ratio = height / width
    if ratio > 1.2:
        kind = "STRAIGHT_GRAIN_Y"
        ang = 90.0
        reason = f"세로/가로={ratio:.2f} > 1.2 (세로 길음)"
    elif ratio < 1.0 / 1.2:  # ≈ 0.833
        kind = "STRAIGHT_GRAIN_X"
        ang = 0.0
        reason = f"세로/가로={ratio:.2f} < 0.83 (가로 길음)"
    else:
        kind = "STRAIGHT_GRAIN_Y"
        ang = 90.0
        reason = f"세로/가로={ratio:.2f} (정사각형 근접 — Y 기본)"

    return {
        "kind": kind,
        "angle_deg": ang,
        "length_mm": 0.0,
        "raw_layer": None,
        "estimated": True,
        "reason": reason,
    }


def rotate_polygon(
    coords: list,
    angle_deg: float,
    around: tuple[float, float] = (0.0, 0.0),
) -> list:
    """폴리곤 좌표를 around 점 기준으로 회전 후, 양의 1사분면(min_x=0, min_y=0)으로 평행이동.

    회전 0° 이면 회전 단계는 건너뛰고 평행이동만 수행. 빈 입력은 빈 리스트.
    """
    if not coords:
        return []
    # shapely 는 행렬 변환을 안전·정확하게 처리해주므로 직접 행렬 짜는 것보다 robust.
    from shapely.geometry import Polygon
    from shapely import affinity

    poly = Polygon(coords)
    if angle_deg != 0.0:
        poly = affinity.rotate(poly, angle_deg, origin=around)
    minx, miny, _, _ = poly.bounds
    poly = affinity.translate(poly, -minx, -miny)
    # exterior.coords 마지막 점은 첫 점과 동일(닫힘 표현) → 제외.
    return [(x, y) for x, y in poly.exterior.coords[:-1]]
