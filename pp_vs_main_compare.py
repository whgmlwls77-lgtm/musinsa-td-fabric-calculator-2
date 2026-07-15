"""
PP vs 메인 패턴 면적 비교 (사장님 원문 2026-07-09).

배경:
  일부 협력사가 메인 패턴을 "축율분"이라 치고 키워서 요척을 뻥튀기함.
  PP 패턴과 메인 그레이딩 패턴의 기준 사이즈 면적을 대조해
  메인이 몇 % 커졌는지 계산 → 뻥튀기 적발.

사장님 확정 사양 (2026-07-14):
  - 판정 임계 없음 (경고 X, 계산 값만 표시 — 사장님 판정)
  - 양쪽 모두 시접 포함 PP-그레이딩 패턴 (가이드 §1 조건 동일)

매칭 로직 재설계 (사장님 확정 2026-07-15):
  - 1차: 이름 완전 매칭 (block_name.strip() dict lookup)
  - 2차: 도형 유사도 매칭 (shape_similarity — raw 좌표 기반)
  - 크기(면적) 순 fallback 완전 폐기 — 모양이 완전 다른데 면적만 비슷하다고
    짝지어지는 오매칭을 유발했음 (사장님 실증 2026-07-15).
  - 둘 다 실패 → unmatched (임의 짝짓기 X — 원칙 #1 추측 금지).

이 모듈은 순수 계산만 담당 (streamlit 의존성 없음 — 단위 테스트 가능).
"""
from __future__ import annotations

from shape_similarity import shape_similarity

SHAPE_MATCH_THRESHOLD = 0.85  # 사장님 확정 2026-07-15
                              # 근거: 사각 vs 원 극단 케이스 (0.830) 차단 최소값
                              # 사용자 조정 X (사장님 원칙 — 시스템 표준)


def _is_marker_excluded(p: dict) -> bool:
    """스케일 박스 / Material:NON 마카제외 piece 판별.

    스케일 박스는 parse_dxf_v3 가 excluded 로 이미 분리하지만,
    Material:NON(마카제외) piece 는 pieces 에 잔존하므로 면적 비교에서 제외.
    """
    inferred = (p.get("material_inferred") or "").strip()
    raw = (p.get("material_raw") or p.get("material") or "").strip().upper()
    return inferred == "마카제외" or raw in {"NON", "NONE"}


def _piece_area(p: dict) -> float:
    """piece 면적 (cm²). parse_dxf_v3 의 area_cm2 (shapely polygon.area × 단위보정)."""
    a = p.get("area_cm2")
    return float(a) if a is not None else 0.0


def _thumb_ref(p: dict) -> dict:
    """썸네일 렌더용 slim piece 참조 (coords/material/이름).

    계산 로직(면적/매칭/확대율)과 무관 — UI 가 조각 모양을 그리도록 원본 좌표만 첨부.
    사장님 지시 2026-07-15 (조각별 상세 썸네일).
    """
    return {
        "coords_cm": p.get("coords_cm") or [],
        "material_inferred": p.get("material_inferred"),
        "piece_name": p.get("piece_name") or "",
        "block_name": (p.get("block_name") or "").strip(),
    }


def _expansion_pct(pp_area: float, main_area: float) -> float | None:
    """확대율 (%) = (메인 - PP) / PP × 100. PP 면적 0 이면 None (계산 불가)."""
    if pp_area <= 0:
        return None
    return (main_area - pp_area) / pp_area * 100.0


def _filter_pieces(pieces: list[dict], target_size: str) -> list[dict]:
    """target_size 조각만 + 스케일 박스/Material:NON 제외."""
    return [
        p for p in pieces
        if p.get("size") == target_size and not _is_marker_excluded(p)
    ]


def compare_pp_vs_main(
    pp_pieces: list[dict],
    main_pieces: list[dict],
    target_size: str,
) -> dict:
    """PP 패턴 vs 메인 패턴 기준 사이즈 면적 비교.

    Args:
      pp_pieces   : PP 파일 parse_dxf_v3 결과의 pieces
      main_pieces : 메인 파일 parse_dxf_v3 결과의 pieces
      target_size : 비교 기준 사이즈 (두 파일 공통)

    도형 매칭 임계값은 시스템 표준 SHAPE_MATCH_THRESHOLD (0.85) 고정 —
    사용자 조정 X (사장님 확정 2026-07-15).

    Returns:
      {
        'target_size': str,
        'shape_threshold': float,      # 적용된 시스템 표준값 (UI 표시용)
        'pp_total_area_cm2': float,
        'main_total_area_cm2': float,
        'total_expansion_pct': float | None,
        'matched_pairs': [
          {'block_name_pp', 'block_name_main', 'pp_area', 'main_area',
           'expansion_pct', 'match_method',        # 'block_name' | 'shape'
           'similarity_score',                     # shape 매칭만 float, 이름 매칭은 None
           'pp_piece', 'main_piece'},              # 썸네일 렌더용 slim 참조 (2026-07-15)
          ...
        ],
        'unmatched_pp': [{'block_name', 'area', 'piece'}, ...],
        'unmatched_main': [{'block_name', 'area', 'piece'}, ...],
      }

    매칭 순서 (사장님 확정 2026-07-15):
      1. 블록 이름(비어있지 않은) 동일 조각 짝짓기 (match_method='block_name')
      2. 남은 조각들 도형 유사도 greedy 매칭 (match_method='shape')
         — 모든 PP × 메인 조합 유사도 계산 → 큰 순으로 짝짓고 제거
         — SHAPE_MATCH_THRESHOLD 미만은 매칭 X
      3. 매칭 안 된 조각 → unmatched (크기 순 fallback 폐기 — 오매칭 유발)
    """
    pp = _filter_pieces(pp_pieces, target_size)
    main = _filter_pieces(main_pieces, target_size)

    pp_total = sum(_piece_area(p) for p in pp)
    main_total = sum(_piece_area(p) for p in main)

    matched: list[dict] = []
    pp_used = [False] * len(pp)
    main_used = [False] * len(main)

    # ── Step 1: 블록 이름 매칭 (비어있지 않은 이름만) ──────────────
    # 같은 이름이 여러 개면 등장 순서대로 1:1 매칭 (남은 것끼리).
    main_by_block: dict[str, list[int]] = {}
    for j, mp in enumerate(main):
        bn = (mp.get("block_name") or "").strip()
        if bn:
            main_by_block.setdefault(bn, []).append(j)

    for i, pp_p in enumerate(pp):
        bn = (pp_p.get("block_name") or "").strip()
        if not bn:
            continue
        candidates = main_by_block.get(bn)
        if not candidates:
            continue
        # 아직 안 쓴 첫 후보 매칭.
        for j in candidates:
            if not main_used[j]:
                pp_used[i] = True
                main_used[j] = True
                pp_a = _piece_area(pp_p)
                main_a = _piece_area(main[j])
                matched.append({
                    "block_name_pp": bn,
                    "block_name_main": (main[j].get("block_name") or "").strip(),
                    "pp_area": pp_a,
                    "main_area": main_a,
                    "expansion_pct": _expansion_pct(pp_a, main_a),
                    "match_method": "block_name",
                    "similarity_score": None,
                    "pp_piece": _thumb_ref(pp_p),
                    "main_piece": _thumb_ref(main[j]),
                })
                break

    # ── Step 2: 남은 조각 도형 유사도 매칭 (사장님 확정 2026-07-15) ──
    # 크기(면적) 순 fallback 폐기 — 모양이 완전 다른데 면적만 비슷하면 오매칭.
    # 모든 PP × 메인 조합 유사도 계산 → 큰 순 greedy (Hungarian 대신).
    pp_left_idx = [i for i in range(len(pp)) if not pp_used[i]]
    main_left_idx = [j for j in range(len(main)) if not main_used[j]]

    similarity_matrix: list[tuple[float, int, int]] = []
    for i in pp_left_idx:
        for j in main_left_idx:
            sim = shape_similarity(pp[i].get("coords_cm"), main[j].get("coords_cm"))
            similarity_matrix.append((sim, i, j))

    similarity_matrix.sort(key=lambda x: -x[0])
    for sim, i, j in similarity_matrix:
        if sim < SHAPE_MATCH_THRESHOLD:
            break   # 정렬돼 있으므로 이후는 전부 임계값 미만.
        if pp_used[i] or main_used[j]:
            continue
        pp_a = _piece_area(pp[i])
        main_a = _piece_area(main[j])
        matched.append({
            "block_name_pp": (pp[i].get("block_name") or "").strip(),
            "block_name_main": (main[j].get("block_name") or "").strip(),
            "pp_area": pp_a,
            "main_area": main_a,
            "expansion_pct": _expansion_pct(pp_a, main_a),
            "match_method": "shape",
            "similarity_score": sim,
            "pp_piece": _thumb_ref(pp[i]),
            "main_piece": _thumb_ref(main[j]),
        })
        pp_used[i] = True
        main_used[j] = True

    # ── Step 3: 매칭 안 된 조각 = unmatched ────────────────────────
    unmatched_pp = [
        {"block_name": (pp[i].get("block_name") or "").strip(), "area": _piece_area(pp[i]),
         "piece": _thumb_ref(pp[i])}
        for i in range(len(pp)) if not pp_used[i]
    ]
    unmatched_main = [
        {"block_name": (main[j].get("block_name") or "").strip(), "area": _piece_area(main[j]),
         "piece": _thumb_ref(main[j])}
        for j in range(len(main)) if not main_used[j]
    ]

    return {
        "target_size": target_size,
        "shape_threshold": SHAPE_MATCH_THRESHOLD,
        "pp_total_area_cm2": pp_total,
        "main_total_area_cm2": main_total,
        "total_expansion_pct": _expansion_pct(pp_total, main_total),
        "matched_pairs": matched,
        "unmatched_pp": unmatched_pp,
        "unmatched_main": unmatched_main,
    }
