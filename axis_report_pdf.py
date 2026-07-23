"""축율 검증 PDF 리포트 생성 (Task #38 — 사장님 확정 2026-07-16).

요척 산출 PDF 스택(reportlab)을 재사용하되, streamlit 의존성 없이 독립 동작
(단위 테스트 가능 · app.py 무손상). 순수 함수 build_axis_pdf(context) -> bytes.

라벨/판정 값은 app.py 가 Task #36 verdict_pair 로 계산해 context 로 전달 —
이 모듈은 렌더링만 담당 (판정 로직 중복 X, 사장님 원칙 준수).
"""
from __future__ import annotations

import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# 요척 PDF 와 동일한 폰트 후보 (app.py _FONT_CANDIDATES 미러 — import 회피용).
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "NotoSansKR-Regular.ttf"),
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
]

_KR_FONT: str | None = None


def _register_korean_font() -> str:
    """한글 폰트 1회 등록 (TTF / TTC). 실패 시 Helvetica."""
    global _KR_FONT
    if _KR_FONT is not None:
        return _KR_FONT
    for path in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            if path.endswith(".ttc"):
                pdfmetrics.registerFont(TTFont("AxisKRFont", path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont("AxisKRFont", path))
            _KR_FONT = "AxisKRFont"
            return _KR_FONT
        except Exception:
            continue
    _KR_FONT = "Helvetica"
    return _KR_FONT


# 판정 심각도 → (표시어, 배경색). 이모지 대신 한글어 + 색 (PDF 폰트 tofu 방지).
_SEV_DISP = {
    "ok": ("정상", colors.HexColor("#dcfce7")),
    "warning": ("신고초과", colors.HexColor("#fef9c3")),
    "critical": ("상한초과", colors.HexColor("#fee2e2")),
}


def _pct(v) -> str:
    return f"{v:+.1f}%" if v is not None else "—"


def _area(v) -> str:
    return f"{v:,.1f}" if v is not None else "—"


def _polygon_thumb_png(coords, box_px: int = 90) -> bytes | None:
    """조각 외곽선 좌표 → 작은 썸네일 PNG (matplotlib — 신규 의존성 X).

    좌표 부재/폴리곤 미성립 시 None (추측 이미지 X — 사장님 원칙 #1).
    """
    if not coords or len(coords) < 3:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon

        xs = [float(p[0]) for p in coords]
        ys = [float(p[1]) for p in coords]
        fig, ax = plt.subplots(figsize=(1.0, 1.0), dpi=90)
        ax.add_patch(MplPolygon(list(zip(xs, ys)), closed=True,
                                facecolor="#cbd5e1", edgecolor="#334155", linewidth=0.8))
        ax.set_xlim(min(xs), max(xs))
        ax.set_ylim(min(ys), max(ys))
        ax.set_aspect("equal")
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.02, transparent=True)
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None


def _thumb_cell(coords, font):
    """썸네일 RLImage 또는 '—' 텍스트 (표 셀용)."""
    png = _polygon_thumb_png(coords)
    if png is None:
        return Paragraph("—", ParagraphStyle("thmb", fontName=font, fontSize=8))
    w, h = ImageReader(io.BytesIO(png)).getSize()
    ratio = min(40.0 / w, 40.0 / h, 1.0)
    return RLImage(io.BytesIO(png), width=w * ratio, height=h * ratio)


def build_axis_pdf(context: dict) -> bytes:
    """축율 검증 결과 → PDF bytes.

    context (app.py 가 화면 스코프 그대로 구성):
      style, file_name_pp, file_name_main, target_size, material, generated_at,
      declared {vertical, horizontal},
      scoped_pp_total, scoped_main_total, scoped_exp,
      n_warn, n_crit,
      material_summary [{material, n_pieces, n_warn, n_crit, worst_sev}],
      pairs [{block_name, material, pp_area, main_area,
              width_exp, height_exp, area_exp, width_sev, height_sev,
              reasons, pp_coords, main_coords, matched}]
    """
    font = _register_korean_font()
    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = font

    title_style = ParagraphStyle("AxTitle", parent=styles["Heading1"], fontName=font,
                                 fontSize=18, textColor=colors.HexColor("#0369a1"), spaceAfter=12)
    section = ParagraphStyle("AxSection", parent=styles["Heading2"], fontName=font,
                             fontSize=12, textColor=colors.HexColor("#0f172a"),
                             spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("AxBody", parent=styles["Normal"], fontName=font,
                          fontSize=10, textColor=colors.HexColor("#0f172a"))
    small = ParagraphStyle("AxSmall", parent=styles["Normal"], fontName=font,
                           fontSize=8, textColor=colors.HexColor("#64748b"))
    cell = ParagraphStyle("AxCell", parent=styles["Normal"], fontName=font, fontSize=8)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    el = []

    style_label = context.get("style") or "STYLE"
    material = context.get("material") or "-"
    el.append(Paragraph(f"축율 검증 리포트 — {style_label}", title_style))

    # 헤더 메타
    meta = [
        ["검증 대상 원단", material],
        ["기준 사이즈", context.get("target_size") or "-"],
        ["PP 파일", context.get("file_name_pp") or "-"],
        ["메인 파일", context.get("file_name_main") or "-"],
        ["검증 일자", context.get("generated_at") or "-"],
    ]
    el.append(_kv_table(meta, font))
    el.append(Spacer(1, 8))

    # 상단 요약 (선택 원단 스코프)
    el.append(Paragraph(f"면적 요약 ({material})", section))
    exp = context.get("scoped_exp")
    summ = [
        ["PP 총면적", f"{_area(context.get('scoped_pp_total'))} cm²"],
        ["메인 총면적", f"{_area(context.get('scoped_main_total'))} cm²"],
        ["면적 확대율", _pct(exp) if exp is not None else "계산 불가"],
    ]
    el.append(_kv_table(summ, font))
    el.append(Spacer(1, 8))

    # 협력사 신고 축율
    decl = context.get("declared") or {}
    el.append(Paragraph("협력사 신고 축율", section))
    el.append(_kv_table([
        ["세로 축율 (신고)", f"{decl.get('vertical', 0.0):.1f} %"],
        ["가로 축율 (신고)", f"{decl.get('horizontal', 0.0):.1f} %"],
    ], font))
    el.append(Spacer(1, 6))

    # 판정 요약
    n_warn = int(context.get("n_warn", 0))
    n_crit = int(context.get("n_crit", 0))
    el.append(Paragraph(
        f"<b>판정 요약</b> — 신고 초과 {n_warn}건 / 상한 초과 {n_crit}건", body))
    el.append(Spacer(1, 10))

    # 원단별 요약 표
    msum = context.get("material_summary") or []
    if msum:
        el.append(Paragraph("원단별 요약", section))
        rows = [["원단", "조각 수", "신고 초과", "상한 초과", "판정"]]
        for r in msum:
            word = _SEV_DISP.get(r.get("worst_sev", "ok"), _SEV_DISP["ok"])[0]
            rows.append([r.get("material", "-"), str(r.get("n_pieces", 0)),
                         str(r.get("n_warn", 0)), str(r.get("n_crit", 0)), word])
        t = Table(rows, colWidths=[90, 70, 80, 80, 90])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]))
        el.append(t)
        el.append(Spacer(1, 10))

    # 조각별 상세 표 (썸네일 + 가로/세로/면적 확대율 + 판정)
    pairs = context.get("pairs") or []
    el.append(Paragraph("조각별 상세", section))
    if not pairs:
        el.append(Paragraph("(표시할 조각이 없습니다)", small))
    else:
        header = ["블록 이름", "PP", "메인", "가로", "세로", "면적", "판정"]
        data = [[Paragraph(f"<b>{h}</b>", cell) for h in header]]
        sev_bg = []  # (row_idx, col_idx, color)
        for i, p in enumerate(pairs, start=1):
            w_sev = p.get("width_sev")
            h_sev = p.get("height_sev")
            worst = _worst(w_sev, h_sev)
            verdict_word = _SEV_DISP.get(worst, ("—", colors.white))[0] if worst else "—"
            data.append([
                Paragraph(str(p.get("block_name") or "(무명)"), cell),
                _thumb_cell(p.get("pp_coords"), font),
                _thumb_cell(p.get("main_coords"), font),
                Paragraph(_pct(p.get("width_exp")), cell),
                Paragraph(_pct(p.get("height_exp")), cell),
                Paragraph(_pct(p.get("area_exp")), cell),
                Paragraph(verdict_word, cell),
            ])
            if worst and worst in _SEV_DISP:
                sev_bg.append((i, 6, _SEV_DISP[worst][1]))
        t = Table(data, colWidths=[110, 48, 48, 55, 55, 55, 60])
        style_cmds = [
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        for (ri, ci, col) in sev_bg:
            style_cmds.append(("BACKGROUND", (ci, ri), (ci, ri), col))
        t.setStyle(TableStyle(style_cmds))
        el.append(t)

        # 위반 사유 (있으면)
        reason_lines = []
        for p in pairs:
            for r in (p.get("reasons") or []):
                reason_lines.append(f"· {p.get('block_name') or '(무명)'}: {r}")
        if reason_lines:
            el.append(Spacer(1, 8))
            el.append(Paragraph("위반 사유", section))
            for line in reason_lines:
                el.append(Paragraph(line, body))

    el.append(Spacer(1, 16))
    el.append(Paragraph(
        f"축율 검증 · 기준 상한 5% · 생성일 {context.get('generated_at') or '-'}", small))

    doc.build(el)
    return buf.getvalue()


def _worst(a, b):
    """두 심각도 중 최악 (critical > warning > ok > None)."""
    rank = {None: -1, "ok": 0, "warning": 1, "critical": 2}
    return a if rank.get(a, -1) >= rank.get(b, -1) else b


def _kv_table(data, font, col_widths=(140, 300)) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t
