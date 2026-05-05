# -*- coding: utf-8 -*-
"""
partner_message.py
------------------
협력사 메시지 평이화 (사장님 결정 2026-05-05).

사장님 본질:
  "협력사는 프로그래머 / AI 네이티브 아님. 기술 용어 일절 X."

원칙:
  - "메타", "DXF", "Quantity", "Material", "DOUBLE" 등 기술 용어 X
  - "패턴 조각 갯수", "원단 종류 표기", "좌우 대칭 설정", "식서 표시", "패턴 가이드 ◯페이지" 등 평이한 한국어
  - 누구나 (60대 패턴사 포함) 알아들을 수 있게
"""
from __future__ import annotations


# 가이드 페이지 번호 — 시스템에서 PATTERN_PREP_GUIDE.md 섹션 번호 매핑
GUIDE_REF: dict[str, str] = {
    "pattern_name_invalid": "5번 ‘부위명 표기’",
    "quantity_missing": "7번 ‘수량’",
    "material_missing": "6번 ‘재질 구분’",
    "grain_missing": "(별도 안내) ‘식서 표시’",
    "paired_missing": "7번 ‘수량 — 좌우 대칭 설정’",
    "marker_exclude": "6번 ‘재질 구분 — 마카 제외’",
    "seam_missing": "3번 ‘외곽선은 시접 포함’",
}


def _msg_pattern_name_invalid(piece_name: str) -> str:
    return (
        f"패턴 가이드 {GUIDE_REF['pattern_name_invalid']} 표준 부위명 참고 부탁드립니다.\n"
        f"'{piece_name}' 패턴 명칭을 표준 부위명으로 수정 후 재제출 부탁드립니다."
    )


def _msg_quantity_missing(piece_name: str) -> str:
    return (
        f"패턴 조각 갯수 확인 후 재제출 부탁드립니다.\n"
        f"('{piece_name}' 의 갯수가 표기되지 않았습니다.)"
    )


def _msg_material_missing(piece_name: str) -> str:
    return (
        f"패턴 가이드 {GUIDE_REF['material_missing']} 원단 종류 참고 부탁드립니다.\n"
        f"'{piece_name}' 의 원단 종류 (주원단/안감/포켓팅/배색/논) 표기 후 재제출 부탁드립니다."
    )


def _msg_grain_missing(piece_name: str) -> str:
    return (
        f"식서 (원단 결방향) 표시 추가 후 재제출 부탁드립니다.\n"
        f"('{piece_name}' 의 식서 표시가 없습니다.)"
    )


def _msg_paired_missing(piece_name: str) -> str:
    return (
        f"좌우 대칭 패턴 설정 확인 후 재제출 부탁드립니다.\n"
        f"('{piece_name}' 의 대칭 또는 갯수가 잘못 표기된 것 같습니다.)"
    )


def _msg_marker_exclude() -> str:
    return (
        f"마카 제외할 패턴은 원단 종류를 '논 (NON)' 으로 설정 후 재제출 부탁드립니다."
    )


def _msg_seam_missing(piece_name: str) -> str:
    return (
        f"외곽선에 시접 포함 후 재제출 부탁드립니다.\n"
        f"('{piece_name}' 시접이 빠진 것 같습니다.)"
    )


# 위반 type → 메시지 빌더
_BUILDERS = {
    "pattern_name_invalid": _msg_pattern_name_invalid,
    "quantity_missing": _msg_quantity_missing,
    "material_missing": _msg_material_missing,
    "grain_missing": _msg_grain_missing,
    "paired_missing": _msg_paired_missing,
    "seam_missing": _msg_seam_missing,
}


def build_partner_message(violations: list[dict]) -> str:
    """위반 리스트 → 협력사 전송용 평이한 한국어 메시지.

    Args:
      violations: detect_violations(parsed) 결과 리스트.
                  각 항목: {"type": str, "piece_name": str, "raw_name": str, ...}

    Returns:
      줄바꿈으로 구분된 메시지. 위반 0개면 빈 문자열.
    """
    if not violations:
        return ""

    # 같은 type/piece 조합 중복 제거 + 순서 유지
    seen: set[tuple[str, str]] = set()
    msgs: list[str] = []
    for v in violations:
        vtype = v.get("type", "")
        pn = v.get("raw_name") or v.get("piece_name") or "(이름 없음)"
        key = (vtype, pn)
        if key in seen:
            continue
        seen.add(key)

        builder = _BUILDERS.get(vtype)
        if builder is None:
            continue
        if vtype == "marker_exclude":
            msgs.append(_msg_marker_exclude())
        else:
            msgs.append(builder(pn))

    if not msgs:
        return ""

    intro = "안녕하세요. 패턴 파일 검토 결과 아래 사항 확인 부탁드립니다.\n\n"
    body = "\n\n".join(f"{i+1}. {m}" for i, m in enumerate(msgs))
    return intro + body


# 메시지 자체를 외부에서 직접 호출할 수 있게 노출
build_messages = {
    "pattern_name_invalid": _msg_pattern_name_invalid,
    "quantity_missing": _msg_quantity_missing,
    "material_missing": _msg_material_missing,
    "grain_missing": _msg_grain_missing,
    "paired_missing": _msg_paired_missing,
    "marker_exclude": _msg_marker_exclude,
    "seam_missing": _msg_seam_missing,
}
