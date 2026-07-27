"""축율 검증 Excel 데이터 생성 (Task #38 — 사장님 확정 2026-07-16).

요척 산출 Excel 스택(openpyxl)을 재사용하되 streamlit 의존성 없이 독립 동작
(단위 테스트 가능 · app.py 무손상). 순수 함수 build_axis_xlsx(context) -> bytes.

축적 데이터 재사용(Task #30 확장 학습 재료) 대비 — 스키마 정형화:
  Sheet "요약" / "원단별요약" / "조각별상세".
판정 값은 app.py 가 Task #36 로 계산해 context 로 전달 (판정 로직 중복 X).
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill

_HEADER_FILL = PatternFill("solid", fgColor="F1F5F9")
_HEADER_FONT = Font(bold=True)
_SEV_WORD = {"ok": "정상", "warning": "신고초과", "critical": "상한초과"}
_SEV_FILL = {
    "ok": PatternFill("solid", fgColor="DCFCE7"),
    "warning": PatternFill("solid", fgColor="FEF9C3"),
    "critical": PatternFill("solid", fgColor="FEE2E2"),
}


def _worst(a, b):
    rank = {None: -1, "ok": 0, "warning": 1, "critical": 2}
    return a if rank.get(a, -1) >= rank.get(b, -1) else b


def _num(v):
    """None → 빈칸, 그 외 float 반올림."""
    return "" if v is None else round(float(v), 2)


def _style_header(ws, ncol: int) -> None:
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")


def build_axis_xlsx(context: dict) -> bytes:
    """축율 검증 결과 → Excel bytes (3 시트). context 계약은 axis_report_pdf 와 동일."""
    wb = Workbook()

    # ── Sheet 1: 요약 ──────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "요약"
    material = context.get("material") or "-"
    exp = context.get("scoped_exp")
    rows1 = [
        ["항목", "값"],
        ["스타일", context.get("style") or "-"],
        ["검증 대상 원단", material],
        ["기준 사이즈", context.get("target_size") or "-"],
        ["PP 파일", context.get("file_name_pp") or "-"],
        ["메인 파일", context.get("file_name_main") or "-"],
        ["검증 일자", context.get("generated_at") or "-"],
        ["PP 총면적(cm²)", _num(context.get("scoped_pp_total"))],
        ["메인 총면적(cm²)", _num(context.get("scoped_main_total"))],
        ["면적 확대율(%)", _num(exp)],
        ["신고 세로 축율(%)", _num((context.get("declared") or {}).get("vertical", 0.0))],
        ["신고 가로 축율(%)", _num((context.get("declared") or {}).get("horizontal", 0.0))],
        ["기준 상한(%)", 5.0],
        ["신고 초과(건)", int(context.get("n_warn", 0))],
        ["상한 초과(건)", int(context.get("n_crit", 0))],
    ]
    for r in rows1:
        ws1.append(r)
    _style_header(ws1, 2)
    ws1.column_dimensions["A"].width = 22
    ws1.column_dimensions["B"].width = 30

    # ── Sheet 2: 원단별 요약 ───────────────────────────────────
    ws2 = wb.create_sheet("원단별요약")
    ws2.append(["원단", "조각 수", "신고 초과", "상한 초과", "판정"])
    for r in (context.get("material_summary") or []):
        sev = r.get("worst_sev", "ok")
        ws2.append([
            r.get("material", "-"), int(r.get("n_pieces", 0)),
            int(r.get("n_warn", 0)), int(r.get("n_crit", 0)),
            _SEV_WORD.get(sev, "-"),
        ])
        last = ws2.max_row
        if sev in _SEV_FILL:
            ws2.cell(row=last, column=5).fill = _SEV_FILL[sev]
    _style_header(ws2, 5)
    for col, w in zip("ABCDE", (14, 10, 12, 12, 12)):
        ws2.column_dimensions[col].width = w

    # ── Sheet 3: 조각별 상세 (면적 우선 판정 + 4변 근거 + 정합성 — 재설계 2026-07-26) ──
    ws3 = wb.create_sheet("조각별상세")
    ws3.append(["조각명", "원단", "판정", "PP 면적(mm²)", "메인 면적(mm²)", "면적%",
                "세로%", "가로%", "정합성", "좌변%", "우변%", "상변%", "하변%", "대칭성"])
    for p in (context.get("pairs") or []):
        sev = p.get("verdict_severity")
        edges = p.get("edges") or {}

        def _edge_pct(key):
            tpl = edges.get(key)
            return _num(tpl[2]) if tpl else ""
        ws3.append([
            p.get("block_name") or "(무명)",
            p.get("material") or "-",
            _SEV_WORD.get(sev, "-") if sev else "-",
            _num(p.get("pp_area_mm2")),
            _num(p.get("main_area_mm2")),
            _num(p.get("area_exp")),
            _num(p.get("v_actual")),
            _num(p.get("h_actual")),
            "이상" if p.get("consistency_flag") else "정합",
            _edge_pct("left"), _edge_pct("right"), _edge_pct("top"), _edge_pct("bottom"),
            "; ".join(p.get("symmetry") or []),
        ])
        last = ws3.max_row
        if sev in _SEV_FILL:
            ws3.cell(row=last, column=3).fill = _SEV_FILL[sev]
    _style_header(ws3, 14)
    for col, w in zip("ABCDEFGHIJKLMN",
                      (16, 10, 8, 13, 13, 8, 8, 8, 8, 8, 8, 8, 8, 24)):
        ws3.column_dimensions[col].width = w

    # ── Sheet 4: 오버랩 이미지 (조각별 · 원 방향 — 사장님 지시 2026-07-26) ──
    ws4 = wb.create_sheet("오버랩이미지")
    ws4.append(["조각명", "판정", "QC(파랑) vs PP(빨강) 오버랩"])
    _style_header(ws4, 3)
    ws4.column_dimensions["A"].width = 16
    ws4.column_dimensions["B"].width = 8
    ws4.column_dimensions["C"].width = 40
    anchor_row = 2
    for p in (context.get("pairs") or []):
        png = p.get("overlap_png")
        ws4.cell(row=anchor_row, column=1, value=p.get("block_name") or "(무명)")
        ws4.cell(row=anchor_row, column=2,
                 value=_SEV_WORD.get(p.get("verdict_severity"), "-"))
        if png:
            try:
                img = XLImage(io.BytesIO(png))
                fw, fh = _fit(img.width, img.height, 300.0, 220.0)
                img.width, img.height = fw, fh
                ws4.add_image(img, f"C{anchor_row}")
            except Exception:
                ws4.cell(row=anchor_row, column=3, value="(이미지 생성 실패)")
        else:
            ws4.cell(row=anchor_row, column=3, value="(이미지 없음)")
        anchor_row += 12   # 이미지 높이만큼 행 간격

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fit(w, h, max_w, max_h):
    ratio = min(max_w / w, max_h / h, 1.0)
    return w * ratio, h * ratio
