# -*- coding: utf-8 -*-
"""
mirror_pieces.py
----------------
의류 패턴 피스의 좌우 미러링.

[설계 원칙]
  - 본사 마카는 좌우 대칭 한 쌍씩 배치 — 이걸 자동화하기 위한 모듈.
  - X 축 기준 반전 (가로 뒤집기) — 폴리곤 좌표 (x, y) → (-x, y).
  - bbox 가로/세로 차원은 동일 (rectpack 입력 동일 → nesting 결과 동일).
  - grain.kind 는 보존 (X/Y 식서는 미러로 안 바뀜).
  - BIAS 는 호출자가 별도 처리 — 이 함수는 BIAS 도 그대로 미러하지만,
    bias 각도는 +45° ↔ -45° 가 돼야 정확하므로 nest_grading_marker 가
    BIAS 는 미러 안 하도록 분기.
"""
from __future__ import annotations

import copy

from shapely.affinity import scale as shp_scale


# ╔════════════════════════════════════════════════════════════╗
# ║ 미러 접미사                                                 ║
# ╚════════════════════════════════════════════════════════════╝
MIRROR_SUFFIX: str = "_mirror"
MIRROR_NAME_SUFFIX: str = "_M"


def mirror_piece_horizontally(
    piece: dict,
    polygon=None,
):
    """
    피스를 X 축 기준으로 미러링한 사본 반환.

    Args:
      piece: extract_piece_info 결과 dict.
      polygon: shapely Polygon (mm 좌표) — 있으면 함께 미러링해서 반환.

    Returns:
      (mirrored_piece_dict, mirrored_polygon_or_None)

    피스 dict 변환:
      piece_id     → 원본 + "_mirror"
      piece_name   → 원본 + "_M"
      width_cm/height_cm/bbox_cm/area_cm2 → 그대로 (미러로 안 변함)
      grain        → 그대로 복사 (X/Y 식서 보존)
      그 외 메타   → 그대로 복사

    폴리곤:
      origin="centroid" 기준으로 X 반전.
      visualize_marker 가 rotate_polygon 으로 (0,0) 정규화하므로 위치는 무관.
    """
    mirrored = copy.deepcopy(piece)
    mirrored["piece_id"] = piece["piece_id"] + MIRROR_SUFFIX
    name = piece.get("piece_name") or ""
    mirrored["piece_name"] = name + MIRROR_NAME_SUFFIX

    mirrored_polygon = None
    if polygon is not None:
        mirrored_polygon = shp_scale(
            polygon, xfact=-1.0, yfact=1.0, origin="centroid"
        )

    return mirrored, mirrored_polygon
