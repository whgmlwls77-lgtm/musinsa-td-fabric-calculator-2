# -*- coding: utf-8 -*-
"""
piece_name_normalize.py
-----------------------
패턴 부위명(piece_name) 표준 정규화 (사장님 결정 2026-05-05).

사장님 본질:
  "우리가 표준 정립 → 가이드 박제 → 시스템은 표준만 인식 → 표준 외 위반 알림"

기능:
  1. data/panel_mapping.json 의 standard_names 사전 로드
  2. raw piece_name 정규화:
     - 대소문자 통합 (대문자)
     - 하이픈/공백 → 언더스코어
     - 표준 풀네임 + 약자 매칭
  3. 매칭 시 → (정식 풀네임, True)
  4. 미매칭 시 → (raw 그대로, False) — 위반 알림용
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_MAPPING_PATH: Path = Path(__file__).parent / "data" / "panel_mapping.json"

# 캐시 — 같은 프로세스 내 반복 로드 방지
_CACHE_LOOKUP: dict[str, str] | None = None


def _load_lookup() -> dict[str, str]:
    """모든 카테고리의 standard_names + 약자 → 표준 풀네임 lookup dict.

    키는 모두 대문자/언더스코어 정규화된 토큰. 값은 정식 표준명.
    """
    global _CACHE_LOOKUP
    if _CACHE_LOOKUP is not None:
        return _CACHE_LOOKUP

    lookup: dict[str, str] = {}
    if not _MAPPING_PATH.exists():
        _CACHE_LOOKUP = lookup
        return lookup

    try:
        data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _CACHE_LOOKUP = lookup
        return lookup

    for cat_name, cat in (data.get("categories") or {}).items():
        std = cat.get("standard_names") or {}
        for full_name, info in std.items():
            full_norm = _norm_token(full_name)
            lookup[full_norm] = full_name
            for alias in info.get("약자", []) or []:
                alias_norm = _norm_token(alias)
                lookup[alias_norm] = full_name

    _CACHE_LOOKUP = lookup
    return lookup


def _norm_token(s: str) -> str:
    """대소문자/공백/하이픈 정규화 — 비교용 키.
       대문자 + 언더스코어. 다중 공백/하이픈 압축."""
    if not s:
        return ""
    t = s.strip().upper()
    # 공백 / 하이픈 / 점 → 언더스코어
    t = re.sub(r"[\s\-\.]+", "_", t)
    # 다중 언더스코어 압축
    t = re.sub(r"_+", "_", t)
    # 양 끝 언더스코어 제거
    t = t.strip("_")
    return t


def normalize_piece_name(raw: str) -> tuple[str, bool]:
    """raw piece_name → (정규화된 표준명, 표준 매칭 여부).

    Returns:
      (standard_name, True)  : 표준 어휘집 (또는 약자) 매칭 — 표준 풀네임으로 통일
      (raw_normalized, False): 미매칭 — 정규화만 한 raw (위반 알림용)
      ("", False)            : 빈 입력

    예:
      "FRONT_BODY"           → ("FRONT_BODY", True)
      "front body"           → ("FRONT_BODY", True)  # 대소문자/공백
      "Front-Body"           → ("FRONT_BODY", True)  # 하이픈
      "FB"                   → ("FRONT_BODY", True)  # 약자
      "fb"                   → ("FRONT_BODY", True)
      "Bodice"               → ("BODICE", False)     # 표준 외
      ""                     → ("", False)
    """
    if not raw:
        return "", False

    norm = _norm_token(raw)
    if not norm:
        return "", False

    lookup = _load_lookup()
    if norm in lookup:
        return lookup[norm], True

    # 미매칭 — 정규화된 형태로 반환 (위반 알림 시 가독성)
    return norm, False


def reload_mapping() -> None:
    """data/panel_mapping.json 변경 후 캐시 재로드 (테스트용)."""
    global _CACHE_LOOKUP
    _CACHE_LOOKUP = None


if __name__ == "__main__":
    # 자체 점검 — 표준 어휘집 출력
    lookup = _load_lookup()
    print(f"표준 어휘집 entries: {len(lookup)}")
    print(f"\n샘플 매칭:")
    for raw in ["FRONT_BODY", "front body", "Front-Body", "FB",
                "BACK_BODY", "BB", "WAISTBAND_FRONT", "WBF",
                "BODICE", "UNKNOWN_PIECE"]:
        std, ok = normalize_piece_name(raw)
        emoji = "✅" if ok else "⚠️"
        print(f"  {emoji} {raw!r:30} → {std!r:30} (표준={ok})")
