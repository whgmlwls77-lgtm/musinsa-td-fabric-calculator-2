"""sparrow 원본 SVG → PNG 렌더 (cairosvg). Task #38-b/#38-c (사장님 확정 2026-07-23).

배경:
  요척 PDF 마카 배치도를 matplotlib 로 재렌더링하면 라벨/타이틀이 겹쳐 깨짐.
  UI 화면에 표시되는 sparrow 원본 SVG 는 품질 완벽 → 그대로 PNG 로 래스터해 임베드.
  SVG 자체는 수정하지 않음 (사장님 지시 — 원본 그대로). 렌더 시 폰트만 주입.

Task #38-c 한글 깨짐(tofu □) 수정:
  sparrow SVG 의 <text> 는 font-family="sans-serif" 사용 → cairosvg(fontconfig)가
  한글 글리프 없는 폰트로 대체 → 모든 한글 □. (실측: 8858 → □)
  해결(방법 2.2): 렌더 직전 SVG 복사본의 font-family 를 "시스템에 실재하는 한글 폰트"
  단일 family 로 치환. 콤마 후보 나열은 fontconfig 이 첫 항목을 Verdana 로 치환 후
  멈춰 tofu 가 되므로(실측), fc-match 로 실재 확인된 family 하나만 주입.
    - macOS: Apple SD Gothic Neo (실측 렌더 정상)
    - Linux(Streamlit Cloud): NanumGothic / Noto Sans CJK KR (packages.txt 설치분)
  cairosvg 2.9 는 @font-face(base64 임베드) 미지원 → 임베드 방식(2.1) 불가 (실측 tofu).

macOS Homebrew 의 libcairo 는 표준 dyld 경로에 없어 cairocffi 가 못 찾는 경우가 있어,
import 전에 DYLD_FALLBACK_LIBRARY_PATH 에 homebrew lib 경로를 보강한다.
"""
from __future__ import annotations

import os
import re
import subprocess

# libcairo 후보 경로 (macOS Homebrew). 리눅스는 표준 경로라 불필요.
_CANDIDATE_LIB_DIRS = ["/opt/homebrew/lib", "/usr/local/lib"]

# 한글 폰트 후보 (우선순위). fc-match 로 "실재" 확인된 첫 family 만 사용.
_KR_FONT_CANDIDATES = [
    "Apple SD Gothic Neo",   # macOS 기본
    "NanumGothic",           # Linux/Streamlit Cloud (packages.txt)
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "AppleGothic",
    "Malgun Gothic",
]

_KR_FAMILY: str | None = None
_KR_FAMILY_RESOLVED = False


def _ensure_cairo_dyld_path() -> None:
    """cairosvg import 전에 homebrew lib 경로를 DYLD_FALLBACK_LIBRARY_PATH 에 보강."""
    cur = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = [p for p in cur.split(":") if p]
    changed = False
    for d in _CANDIDATE_LIB_DIRS:
        if os.path.isdir(d) and d not in parts:
            parts.append(d)
            changed = True
    if changed:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


# 모듈 import 시점(= cairosvg 최초 import 이전)에 1회 보강.
_ensure_cairo_dyld_path()


def _font_exists(family: str) -> bool:
    """fc-match 결과가 요청 family 를 그대로 해석했으면 실재 (Verdana 등 치환이면 False)."""
    try:
        out = subprocess.run(
            ["fc-match", "--format", "%{family}", family],
            capture_output=True, text=True, timeout=5,
        ).stdout.lower()
    except Exception:
        return False
    return family.lower() in out


def resolve_korean_family() -> str | None:
    """시스템에 실재하는 한글 폰트 family 1개 (fc-match 확인). 없으면 None (1회 캐시)."""
    global _KR_FAMILY, _KR_FAMILY_RESOLVED
    if _KR_FAMILY_RESOLVED:
        return _KR_FAMILY
    for fam in _KR_FONT_CANDIDATES:
        if _font_exists(fam):
            _KR_FAMILY = fam
            break
    _KR_FAMILY_RESOLVED = True
    return _KR_FAMILY


_FONT_FAMILY_RE = re.compile(r'font-family="[^"]*"')


def _inject_korean_font(svg: str, family: str) -> str:
    """SVG 복사본의 모든 font-family 를 실재 한글 family 로 치환 (원본 미변경).

    sparrow SVG 는 <text> 에만 font-family 를 쓰므로 전량 치환해도 안전.
    """
    return _FONT_FAMILY_RE.sub(f'font-family="{family}"', svg)


def svg_to_png(svg: str, output_width: int = 1400) -> bytes | None:
    """SVG 문자열 → PNG bytes (종횡비 유지). 실패/빈 입력 시 None (추측 이미지 X).

    렌더 직전 font-family 를 실재 한글 폰트로 주입 (원본 SVG 미변경 — 복사본만).
    output_width 만 지정 → cairosvg 가 viewBox 비율대로 높이 자동 계산.
    """
    if not svg:
        return None
    family = resolve_korean_family()
    render_svg = _inject_korean_font(svg, family) if family else svg
    try:
        import cairosvg
        return cairosvg.svg2png(bytestring=render_svg.encode("utf-8"), output_width=output_width)
    except Exception:
        return None
