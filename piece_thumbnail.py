"""piece 썸네일 SVG 렌더러 (순수 모듈 — streamlit 비의존).

협력사 DXF 에 부위명이 없거나 회사 약자만 있어도 사장님이 각 piece 의 모양을
눈으로 보고 재질을 지정할 수 있게 UI 에 SVG 썸네일을 제공한다.
(근거: 사장님 실증 2026-07-13 — 부위명은 계산에 불필요, UI 재질 판단에는 필요)

사장님 절대 원칙: coords_cm(raw 외곽선)만 사용. 추측/보간 없음.
"""

from __future__ import annotations

import base64


# ── 재질별 테두리 색 (사장님 지정 2026-07-13) ─────────────────────
# 키는 app.py MATERIAL_OPTIONS 와 정합: 주원단/안감/포켓팅/배색/논/미지정
MATERIAL_BORDER_COLOR: dict[str, str] = {
    "주원단":   "#1e40af",   # 진파랑
    "안감":     "#7c3aed",   # 보라
    "포켓팅":   "#059669",   # 초록
    "배색":     "#dc2626",   # 빨강
    "논":       "#6b7280",   # 회색 (마카 제외)
    "미지정":   "#9ca3af",   # 옅은 회색 default
}


def material_border_color(material: str | None) -> str:
    """재질명 → 테두리 색. 미지정/미매칭은 default(옅은 회색)."""
    return MATERIAL_BORDER_COLOR.get(material or "", MATERIAL_BORDER_COLOR["미지정"])


def render_piece_thumbnail_svg(
    piece: dict,
    size_px: int = 150,
    border_color: str = "#333",
) -> str:
    """piece 하나를 SVG 썸네일 문자열로 렌더링.

    - coords_cm: 조각 외곽선 좌표 (cm 단위 (x, y) 리스트)
    - viewBox 는 piece 실제 bbox 비율 그대로 (가로 긴 조각 → 가로 긴 viewBox).
      정사각(size_px) 캔버스 + preserveAspectRatio="xMidYMid meet" 로
      브라우저가 자동 letterbox (가로 긴 조각 → 세로 여백, 세로 긴 → 가로 여백).
    - DXF y-up → SVG y-down 좌표 flip (CAD 방향 그대로 세움).
    - fill: #f5f5f5 (연회색), stroke: border_color (재질별).

    반환: 완결형 SVG 문자열. coords 가 유효하지 않으면 "" (호출자가 placeholder 처리).
    """
    coords = piece.get("coords_cm") or []
    # 폴리곤 성립 최소 3점.
    if len(coords) < 3:
        return ""

    xs = [pt[0] for pt in coords]
    ys = [pt[1] for pt in coords]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = maxx - minx
    h = maxy - miny
    # 폭/높이 0 (직선/점) 이면 썸네일 무의미.
    if w <= 0 or h <= 0:
        return ""

    # DXF y-up → SVG y-down: y' = maxy - y (상하 반전으로 CAD 방향 유지).
    pts = " ".join(f"{(x - minx):.2f},{(maxy - y):.2f}" for x, y in coords)

    # stroke 잘림 방지용 여백 (긴 변의 4%).
    pad = max(w, h) * 0.04
    vb_x = -pad
    vb_y = -pad
    vb_w = w + 2 * pad
    vb_h = h + 2 * pad
    # stroke 두께도 크기에 비례 (viewBox 좌표계 기준).
    stroke_w = max(max(w, h) * 0.012, 0.05)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size_px}" height="{size_px}" '
        f'viewBox="{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="display:block;background:#ffffff;border-radius:6px;">'
        f'<polygon points="{pts}" fill="#f5f5f5" '
        f'stroke="{border_color}" stroke-width="{stroke_w:.3f}" '
        f'stroke-linejoin="round"/>'
        f'</svg>'
    )


def svg_data_uri(svg: str) -> str:
    """SVG 문자열 → base64 data URI (`<img src=...>` 로 안전 임베드용).

    Streamlit st.markdown 의 HTML sanitizer 가 inline <svg> 를 스트립할 수 있어,
    <img> data URI 로 감싸면 버전 무관하게 안정적으로 렌더링된다.
    빈 svg 는 "" 반환.
    """
    if not svg:
        return ""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"
