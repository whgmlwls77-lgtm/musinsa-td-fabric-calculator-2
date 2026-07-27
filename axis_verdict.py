"""축율 대조 판정 (사장님 확정 2026-07-15 — Task #36).

협력사 신고 축율(원단별 세로/가로 %) 대비 시스템 실측 확대율(bbox 기반)을
대조해 판정한다. 순수 계산만 담당 (streamlit 의존성 없음 — 단위 테스트 가능).

판정 규칙 (소수 첫째자리 반올림 비교 — 화면 표시(:+.1f)와 판정 일치):
  - ✅ ok       : round(실측,1) ≤ round(신고,1)   (정상)
  - ⚠️ warning  : round(실측,1) > round(신고,1)    (신고 초과 — 협력사 신고 대비 큼)
  - 🚨 critical : round(실측,1) > 5% (INDUSTRY_MAX) (실무 물리적 상한 초과 — 신고 무관)

우선순위: 5% 상한(critical) > 신고 초과(warning) > 정상(ok).

Task #38-f (사장님 확정 2026-07-23): 표시/판정 정밀도 불일치 버그 수정.
  실측 0.05% 미만은 화면에 "+0.0%"로 표시되는데 기존 strict > 는 신고초과(0.0)로
  오판했음 → 반올림 비교로 화면과 일치. 사장님 지시 "실측 0%면 정상" 부합.
경고 사유(reason) 함께 반환 — 사장님 확정 (2026-07-15): 사장님이 왜 위반인지 확인.
"""
from __future__ import annotations

INDUSTRY_MAX_AXIS_PCT = 5.0  # 사장님 확정 상한 (실무 물리적 한계 — 변경 X)

# 심각도 순위 (통합 판정 시 최악값 선정용).
_SEVERITY_RANK = {"ok": 0, "warning": 1, "critical": 2}


def verdict_single(actual_pct: float, declared_pct: float, direction: str) -> dict:
    """가로 또는 세로 한 방향의 축율 판정.

    Args:
      actual_pct   : 실측 확대율 (%) — bbox 기반, 부호 있음 (음수 = 축소)
      declared_pct : 협력사 신고 축율 (%)
      direction    : "가로" | "세로" (사유 문구용)

    Returns:
      {
        "label": "🚨" | "⚠️" | "✅",
        "reason": str,                              # 사용자 표시용 사유
        "severity": "critical" | "warning" | "ok",
        "actual_pct": float,
        "declared_pct": float,
        "direction": str,
      }
    """
    # Task #38-f (사장님 확정 2026-07-23): 화면 표시(:+.1f)와 판정 정밀도 일치 →
    # 소수 첫째자리로 반올림해 비교 (실측 0.05% 미만 = "+0.0%" 표시 → 정상 처리).
    # 예: 실측 0.03%(표시 +0.0%) vs 신고 0.0% → 기존 strict > 는 신고초과(버그) →
    #     round(0.0,1) > round(0.0,1) = False → 정상.
    actual_r = round(actual_pct, 1)
    declared_r = round(declared_pct, 1)
    if actual_r > round(INDUSTRY_MAX_AXIS_PCT, 1):
        label, severity = "🚨", "critical"
        reason = (
            f"{direction} 축율 {actual_pct:.1f}% 초과 — 실무 물리적 상한 "
            f"{INDUSTRY_MAX_AXIS_PCT:.0f}% 넘음. 패턴에서 반영 불가."
        )
    elif actual_r > declared_r:
        label, severity = "⚠️", "warning"
        reason = (
            f"{direction} 축율 {actual_pct:.1f}% > 신고 {declared_pct:.1f}% "
            f"({actual_pct - declared_pct:.1f}%p 초과) — 협력사 신고 대비 확대율 큼."
        )
    else:
        label, severity = "✅", "ok"
        reason = f"{direction} 축율 {actual_pct:.1f}% ≤ 신고 {declared_pct:.1f}% — 정상."

    return {
        "label": label,
        "reason": reason,
        "severity": severity,
        "actual_pct": actual_pct,
        "declared_pct": declared_pct,
        "direction": direction,
    }


def verdict_pair(
    width_actual: float,
    width_declared: float,
    height_actual: float,
    height_declared: float,
) -> dict:
    """가로 + 세로 각각 판정 후 통합.

    Returns:
      {
        "width":  {label, reason, severity, ...},   # verdict_single 반환
        "height": {label, reason, severity, ...},
        "worst_severity": "critical" | "warning" | "ok",   # 조각 전체 최악 상태
        "worst_label": "🚨" | "⚠️" | "✅",
        "reasons": [str, ...],   # 경고/상한 초과 사유만 (정상 제외) — UI 알림용
      }
    """
    w = verdict_single(width_actual, width_declared, "가로")
    h = verdict_single(height_actual, height_declared, "세로")

    worst = w if _SEVERITY_RANK[w["severity"]] >= _SEVERITY_RANK[h["severity"]] else h
    reasons = [v["reason"] for v in (w, h) if v["severity"] != "ok"]

    return {
        "width": w,
        "height": h,
        "worst_severity": worst["severity"],
        "worst_label": worst["label"],
        "reasons": reasons,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ Task #38-g: 조각 유형별 축율 계산 + 대칭성 진단             ║
# ╚════════════════════════════════════════════════════════════╝
AXIS_SYMMETRY_TOL_PCT = 0.5   # 좌/우·상/하 확대율 차 이 값(%p) 이상이면 비대칭 알림


def _dim_pct(pp_dim, main_dim):
    """(main - pp) / pp × 100. pp ≤ 0 or None 이면 None (계산 불가)."""
    if pp_dim is None or main_dim is None or pp_dim <= 0:
        return None
    return (main_dim - pp_dim) / pp_dim * 100.0


def _symmetry_diagnosis(left, right, top, bottom) -> list:
    """좌/우(세로 축)·상/하(가로 축) 확대율 편차가 임계 이상이면 비대칭 알림.

    사각형/N각형/삼각형 전용 (원형은 호출 안 함). 값이 None 이면 해당 축 건너뜀.
    """
    msgs = []
    if left is not None and right is not None and abs(left - right) >= AXIS_SYMMETRY_TOL_PCT:
        msgs.append(
            f"세로 축 비대칭 — 좌변 {left:+.1f}% vs 우변 {right:+.1f}% "
            f"(차 {abs(left - right):.1f}%p)"
        )
    if top is not None and bottom is not None and abs(top - bottom) >= AXIS_SYMMETRY_TOL_PCT:
        msgs.append(
            f"가로 축 비대칭 — 상변 {top:+.1f}% vs 하변 {bottom:+.1f}% "
            f"(차 {abs(top - bottom):.1f}%p)"
        )
    return msgs


def _avg(a, b):
    vals = [v for v in (a, b) if v is not None]
    return sum(vals) / len(vals) if vals else None


# 정합성 임계 — 이론 면적(세로·가로 종합) vs 실제 면적 차 이 값(%p) 이상이면 이상 신호.
AXIS_CONSISTENCY_TOL_PCT = 2.0


def _theoretical_area_pct(v_pct, h_pct):
    """세로·가로 축율(%) → 이론 면적 확대율(%) = (1+v)(1+h)-1. None 이면 None."""
    if v_pct is None or h_pct is None:
        return None
    return ((1.0 + v_pct / 100.0) * (1.0 + h_pct / 100.0) - 1.0) * 100.0


def verdict_area(area_pct: float, declared_pct: float) -> dict:
    """면적 확대율 기반 판정 (사장님 재설계 2026-07-26 — 판정 = 면적만).

    - 🚨 critical : |면적 확대율| > 5% (INDUSTRY_MAX · 양방향 상한)
    - ⚠️ warning  : 면적 확대율 > 신고 (declared · 확대 방향만 · round tolerance)
    - ✅ ok        : 그 외
    기존 verdict_single (축별 판정) 은 무손상 — 별도 함수.
    """
    ar = round(area_pct, 1)
    dr = round(declared_pct, 1)
    if round(abs(area_pct), 1) > INDUSTRY_MAX_AXIS_PCT:
        label, severity = "🚨", "critical"
        reason = f"면적 확대율 {area_pct:.1f}% — 실무 상한 ±{INDUSTRY_MAX_AXIS_PCT:.0f}% 초과."
    elif ar > dr:
        label, severity = "⚠️", "warning"
        reason = f"면적 확대율 {area_pct:.1f}% > 신고 {declared_pct:.1f}% — 신고 대비 큼."
    else:
        label, severity = "✅", "ok"
        reason = f"면적 확대율 {area_pct:.1f}% ≤ 신고 {declared_pct:.1f}% — 정상."
    return {"label": label, "severity": severity, "reason": reason,
            "area_pct": area_pct, "declared_pct": declared_pct}


def verdict_from_measures(
    pp_measure: dict,
    main_measure: dict,
    width_declared: float,
    height_declared: float,
    area_exp: float | None = None,
    bbox_width_exp: float | None = None,
    bbox_height_exp: float | None = None,
) -> dict:
    """PP·메인 측정 결과 + 면적 확대율 → 판정(면적 기준) + 근거(세로/가로/4변) + 정합성.

    사장님 재설계 (2026-07-26):
      - 판정 = 면적 확대율만 (verdict_area · round tolerance · ±5% 상한).
      - 세로/가로/4변 축율 = 판정 X · 근거 정보로만.
      - 대칭성 = 근거 정보로만.
      - 정합성: 이론 면적(1+세로)(1+가로)-1 vs 실제 면적, 차 > 2%p → 이상 신호.

    측정 (좌변/우변=식서 세로, 상변/하변=식서 가로):
      - 사각형류: 세로=(좌+우)/2, 가로=(상+하)/2 / 원형: 세로·가로 지름
      - 측정 불가 → bbox 세로/가로 참고 (근거만 · 판정은 여전히 면적).

    Returns:
      {
        "piece_type", "method": "corner"|"circle"|"fallback_bbox",
        "edges_expansion": {left,right,top,bottom} | None,
        "diameter_expansion": {"vertical","horizontal"} | None,
        "width_actual" (가로 근거), "height_actual" (세로 근거),
        "area_exp": float | None,
        "verdict": verdict_area(...) | None,   # 면적 기준 판정
        "symmetry": [str, ...],
        "consistency": {"theoretical","actual","diff","flag","msg"},
        "warnings": [str, ...],
      }
    """
    ptype = (main_measure or {}).get("piece_type") or (pp_measure or {}).get("piece_type") or "unknown"
    warnings = list((pp_measure or {}).get("warnings") or [])
    warnings += list((main_measure or {}).get("warnings") or [])

    pp_edges = (pp_measure or {}).get("edges")
    main_edges = (main_measure or {}).get("edges")
    pp_circle = (pp_measure or {}).get("circle")
    main_circle = (main_measure or {}).get("circle")

    method = "fallback_bbox"
    edges_expansion = None
    diameter_expansion = None
    symmetry: list = []

    # 정중앙 세로/가로 확대율 (근거 — 판정 무영향, 사장님 지시 2026-07-27).
    pp_ctr = (pp_measure or {}).get("center_axes") or {}
    main_ctr = (main_measure or {}).get("center_axes") or {}
    center_v_exp = _dim_pct(pp_ctr.get("vertical"), main_ctr.get("vertical"))
    center_h_exp = _dim_pct(pp_ctr.get("horizontal"), main_ctr.get("horizontal"))

    if pp_circle and main_circle:
        method = "circle"
        v_actual = _dim_pct(pp_circle.get("v_diameter"), main_circle.get("v_diameter"))
        h_actual = _dim_pct(pp_circle.get("h_diameter"), main_circle.get("h_diameter"))
        diameter_expansion = {"vertical": v_actual, "horizontal": h_actual}
    elif pp_edges and main_edges:
        method = "corner"
        le = _dim_pct(pp_edges.get("left"), main_edges.get("left"))
        re = _dim_pct(pp_edges.get("right"), main_edges.get("right"))
        te = _dim_pct(pp_edges.get("top"), main_edges.get("top"))
        be = _dim_pct(pp_edges.get("bottom"), main_edges.get("bottom"))
        edges_expansion = {"left": le, "right": re, "top": te, "bottom": be}
        h_actual = _avg(te, be)   # 가로 = 상+하 (기존 유지)
        v_actual = _avg(le, re)   # 세로 = 좌+우 (각도 4코너로 왜곡 없음 · G-F 폐기 2026-07-27)
        symmetry = _symmetry_diagnosis(le, re, te, be)
    else:
        v_actual = bbox_height_exp   # 근거 없음 → bbox 참고
        h_actual = bbox_width_exp
        warnings.append("조각 4코너/원형 측정 불가 — 세로/가로는 bbox 참고값 (판정은 면적 기준).")

    # ── 판정 = 면적 확대율만 ──
    declared_area = _theoretical_area_pct(height_declared, width_declared) or 0.0
    verdict = verdict_area(area_exp, declared_area) if area_exp is not None else None

    # ── 정합성: 이론 면적(세로·가로) vs 실제 면적 ──
    theo = _theoretical_area_pct(v_actual, h_actual)
    if theo is not None and area_exp is not None:
        diff = abs(theo - area_exp)
        flag = diff > AXIS_CONSISTENCY_TOL_PCT
        msg = (f"이상 신호 — 이론 면적 {theo:+.1f}% vs 실제 {area_exp:+.1f}% (차 {diff:.1f}%p)"
               if flag else f"정합 — 이론 {theo:+.1f}% ≈ 실제 {area_exp:+.1f}% (차 {diff:.1f}%p)")
        consistency = {"theoretical": theo, "actual": area_exp, "diff": diff,
                       "flag": flag, "msg": msg}
    else:
        consistency = {"theoretical": theo, "actual": area_exp, "diff": None,
                       "flag": False, "msg": "정합성 계산 불가 (측정/면적 부재)"}

    return {
        "piece_type": ptype, "method": method,
        "edges_expansion": edges_expansion, "diameter_expansion": diameter_expansion,
        "width_actual": h_actual, "height_actual": v_actual,
        "center_v_expansion": center_v_exp,   # 정중앙 세로 (근거 · Task 2026-07-27)
        "center_h_expansion": center_h_exp,   # 정중앙 가로 (근거)
        "area_exp": area_exp, "verdict": verdict,
        "symmetry": symmetry, "consistency": consistency, "warnings": warnings,
    }
