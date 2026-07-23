# -*- coding: utf-8 -*-
"""
test_axis_report.py
-------------------
축율 검증 다운로드 (PDF/Excel) 생성 검증 (Task #38 — 사장님 확정 2026-07-16).

검증:
  1. build_axis_pdf → 유효한 PDF 바이트 (%PDF- 시작)
  2. build_axis_pdf 조각 썸네일 이미지 임베드 (좌표 있으면 XObject 존재)
  3. build_axis_pdf 빈 조각 목록도 안전 (예외 X)
  4. build_axis_xlsx → 시트 3개 (요약/원단별요약/조각별상세) + 필드
  5. 미매칭 조각(판정 None) 포함 케이스 안전
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook

from axis_report_pdf import build_axis_pdf
from axis_report_xlsx import build_axis_xlsx


def _ctx(pairs=None, material_summary=None):
    return {
        "style": "TESTSTYLE",
        "file_name_pp": "pp.dxf",
        "file_name_main": "main.dxf",
        "target_size": "L",
        "material": "SELF",
        "generated_at": "2026-07-23 10:00",
        "declared": {"vertical": 3.0, "horizontal": 2.0},
        "scoped_pp_total": 1800.0,
        "scoped_main_total": 1890.0,
        "scoped_exp": 5.0,
        "n_warn": 1,
        "n_crit": 0,
        "material_summary": material_summary if material_summary is not None else [
            {"material": "SELF", "n_pieces": 1, "n_warn": 1, "n_crit": 0, "worst_sev": "warning"}
        ],
        "pairs": pairs if pairs is not None else [{
            "block_name": "FB", "material": "SELF",
            "pp_area": 1800.0, "main_area": 1890.0,
            "width_exp": 5.0, "height_exp": 0.0, "area_exp": 5.0,
            "width_sev": "warning", "height_sev": "ok",
            "reasons": ["가로 축율 5.0% > 신고 2.0% (3.0%p 초과)."],
            "pp_coords": [(0, 0), (30, 0), (30, 60), (0, 60)],
            "main_coords": [(0, 0), (31.5, 0), (31.5, 60), (0, 60)],
            "matched": True,
        }],
    }


class TestAxisPdf(unittest.TestCase):

    def test_pdf_valid_bytes(self):
        pdf = build_axis_pdf(_ctx())
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)

    def test_pdf_thumbnail_embedded(self):
        """좌표 있는 조각 → 썸네일 이미지 XObject 임베드 (matplotlib 경로)."""
        pdf = build_axis_pdf(_ctx())
        self.assertIn(b"/XObject", pdf)  # 이미지 flowable 임베드 증거

    def test_pdf_empty_pairs_safe(self):
        pdf = build_axis_pdf(_ctx(pairs=[], material_summary=[]))
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_pdf_unmatched_piece_safe(self):
        """미매칭 조각(판정 None · 좌표 한쪽 None)도 예외 없이 렌더."""
        pairs = [{
            "block_name": "X (PP만)", "material": "SELF",
            "pp_area": 100.0, "main_area": None,
            "width_exp": None, "height_exp": None, "area_exp": None,
            "width_sev": None, "height_sev": None, "reasons": [],
            "pp_coords": [(0, 0), (10, 0), (10, 10), (0, 10)], "main_coords": None,
            "matched": False,
        }]
        pdf = build_axis_pdf(_ctx(pairs=pairs))
        self.assertTrue(pdf.startswith(b"%PDF-"))


class TestAxisXlsx(unittest.TestCase):

    def test_three_sheets(self):
        wb = load_workbook(io.BytesIO(build_axis_xlsx(_ctx())))
        self.assertEqual(wb.sheetnames, ["요약", "원단별요약", "조각별상세"])

    def test_summary_fields(self):
        wb = load_workbook(io.BytesIO(build_axis_xlsx(_ctx())))
        ws = wb["요약"]
        keys = {ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)}
        for expect in ("면적 확대율(%)", "기준 상한(%)", "신고 초과(건)", "상한 초과(건)"):
            self.assertIn(expect, keys)

    def test_detail_sheet_header_and_row(self):
        wb = load_workbook(io.BytesIO(build_axis_xlsx(_ctx())))
        ws = wb["조각별상세"]
        header = [ws.cell(row=1, column=c).value for c in range(1, 10)]
        self.assertEqual(header, ["블록명", "원단", "PP 면적(cm²)", "메인 면적(cm²)",
                                  "가로 확대율(%)", "세로 확대율(%)", "면적 확대율(%)", "판정", "사유"])
        self.assertEqual(ws.cell(row=2, column=1).value, "FB")
        self.assertEqual(ws.cell(row=2, column=8).value, "신고초과")  # worst=warning

    def test_material_summary_sheet(self):
        wb = load_workbook(io.BytesIO(build_axis_xlsx(_ctx())))
        ws = wb["원단별요약"]
        self.assertEqual([ws.cell(row=1, column=c).value for c in range(1, 6)],
                         ["원단", "조각 수", "신고 초과", "상한 초과", "판정"])
        self.assertEqual(ws.cell(row=2, column=1).value, "SELF")


if __name__ == "__main__":
    unittest.main(verbosity=2)
