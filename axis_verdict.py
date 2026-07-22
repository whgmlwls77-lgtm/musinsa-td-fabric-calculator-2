"""축율 대조 판정 (사장님 확정 2026-07-15 — Task #36).

협력사 신고 축율(원단별 세로/가로 %) 대비 시스템 실측 확대율(bbox 기반)을
대조해 판정한다. 순수 계산만 담당 (streamlit 의존성 없음 — 단위 테스트 가능).

판정 규칙 (오차 범위 없음 — 사장님 원칙 #1 추측 금지):
  - ✅ ok       : 실측 ≤ 신고             (정상)
  - ⚠️ warning  : 실측 > 신고             (신고 초과 — 협력사 신고 대비 큼)
  - 🚨 critical : 실측 > 5% (INDUSTRY_MAX) (실무 물리적 상한 초과 — 신고 무관)

우선순위: 5% 상한(critical) > 신고 초과(warning) > 정상(ok).
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
    if actual_pct > INDUSTRY_MAX_AXIS_PCT:
        label, severity = "🚨", "critical"
        reason = (
            f"{direction} 축율 {actual_pct:.1f}% 초과 — 실무 물리적 상한 "
            f"{INDUSTRY_MAX_AXIS_PCT:.0f}% 넘음. 패턴에서 반영 불가."
        )
    elif actual_pct > declared_pct:
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
