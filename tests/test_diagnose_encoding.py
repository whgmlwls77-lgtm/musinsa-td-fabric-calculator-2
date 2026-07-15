# -*- coding: utf-8 -*-
"""
test_diagnose_encoding.py
-------------------------
텍스트 인코딩 카테고리 신설 검증 (사장님 확정 결정 2026-07-14).

배경:
  PIECE NAME 부위명 카테고리화 폐기 → 대신 텍스트 인코딩 카테고리 신설.
  "국제표준어 영어로만 쓰면 문제 없음. 중국어 등으로 쓰면 오류 날 수 있음."
  → 영문/숫자만 사용해야 인코딩 오류(CP949/EUC-KR 등) 방지 가능.
  → 비ASCII 문자(ord > 127) 감지 시 위반.

검증:
  1. 전부 영문/숫자 → OK (정상은 침묵 — 본질 #6)
  2. 한글 piece_name → WARN
  3. 중국어 material_raw → WARN
  4. 한글 annotation → WARN (MMDPC513 시나리오)
  5. 비ASCII size → WARN
  6. piece 0개 → FAIL (_empty)
  7. run_full_diagnosis 에 "encoding" 키 존재 + "panel" 키 제거 확인
  8. build_coop_message — encoding WARN 시 영문/숫자 재저장 요청 문구 포함
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_diagnosis import (
    diagnose_text_encoding,
    run_full_diagnosis,
    build_coop_message,
    OK,
    WARN,
    FAIL,
)


def _piece(pid="P1", piece_name="FRONT_BODY", material_raw="SELF",
           size="L", annotations=None, material_inferred="주원단"):
    return {
        "piece_id": pid,
        "piece_name": piece_name,
        "material_raw": material_raw,
        "material_inferred": material_inferred,
        "size": size,
        "annotations": annotations or [],
    }


class TestEncodingOK(unittest.TestCase):
    """전부 영문/숫자 → OK (침묵)."""

    def test_all_ascii_ok(self):
        pieces = [
            _piece("P1", "FRONT_BODY", "SELF", "L"),
            _piece("P2", "BACK_BODY", "LINING", "XL", annotations=["GRAIN", "1cm SA"]),
        ]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], OK)
        self.assertEqual(d["raw"]["violation_count"], 0)
        self.assertEqual(d["raw"]["violations"], [])

    def test_digits_and_symbols_ascii_ok(self):
        # ASCII 기호(_ - / . 숫자)는 위반 아님 (ord <= 127).
        pieces = [_piece("P1", "POCKET_BAG-2", "POCKETING", "M/L", annotations=["A.1"])]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], OK)


class TestEncodingViolations(unittest.TestCase):
    """비ASCII 문자 감지 → WARN."""

    def test_korean_piece_name_warn(self):
        pieces = [_piece("P1", "앞판", "SELF", "L")]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], WARN)
        self.assertEqual(d["raw"]["violation_count"], 1)
        v = d["raw"]["violations"][0]
        self.assertEqual(v["field"], "piece_name")
        self.assertEqual(v["value"], "앞판")
        self.assertIn("앞", v["non_ascii"])

    def test_chinese_material_warn(self):
        pieces = [_piece("P1", "FRONT_BODY", "面料", "L")]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], WARN)
        fields = [v["field"] for v in d["raw"]["violations"]]
        self.assertIn("material_raw", fields)

    def test_korean_annotation_warn(self):
        """MMDPC513 시나리오 — 한글 annotation 감지."""
        pieces = [_piece("P1", "FRONT_BODY", "SELF", "L",
                         annotations=["식서방향", "GRAIN"])]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], WARN)
        annos = [v for v in d["raw"]["violations"] if v["field"] == "annotation"]
        self.assertEqual(len(annos), 1)
        self.assertEqual(annos[0]["value"], "식서방향")

    def test_non_ascii_size_warn(self):
        pieces = [_piece("P1", "FRONT_BODY", "SELF", "라지")]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], WARN)
        fields = [v["field"] for v in d["raw"]["violations"]]
        self.assertIn("size", fields)

    def test_non_ascii_truncated_to_5(self):
        pieces = [_piece("P1", "가나다라마바사", "SELF", "L")]
        d = diagnose_text_encoding({"pieces": pieces})
        v = d["raw"]["violations"][0]
        self.assertEqual(len(v["non_ascii"]), 5)  # 처음 5글자만

    def test_affected_piece_count_in_summary(self):
        pieces = [
            _piece("P1", "앞판", "SELF", "L"),
            _piece("P2", "뒤판", "SELF", "L"),
            _piece("P3", "FRONT_BODY", "SELF", "L"),  # clean
        ]
        d = diagnose_text_encoding({"pieces": pieces})
        self.assertEqual(d["status"], WARN)
        self.assertIn("2개 조각", d["summary"])


class TestEncodingEmpty(unittest.TestCase):

    def test_no_pieces_fail(self):
        d = diagnose_text_encoding({"pieces": []})
        self.assertEqual(d["status"], FAIL)


class TestRunFullDiagnosisIntegration(unittest.TestCase):
    """진단 카테고리 재구성 — encoding 키 존재 + panel 키 제거."""

    def test_encoding_key_present_panel_absent(self):
        parsed = {"pieces": [_piece()], "style": "TEST"}
        diag = run_full_diagnosis(parsed)
        self.assertIn("encoding", diag)
        self.assertNotIn("panel", diag)

    def test_encoding_status_flows_through(self):
        parsed = {"pieces": [_piece("P1", "앞판")], "style": "TEST"}
        diag = run_full_diagnosis(parsed)
        self.assertEqual(diag["encoding"]["status"], WARN)


class TestCoopMessage(unittest.TestCase):
    """build_coop_message — encoding WARN 시 영문/숫자 재저장 요청."""

    def test_coop_message_includes_encoding_remedy(self):
        diag = {
            "material": {"status": OK},
            "encoding": {"status": WARN},
            "quantity": {"status": OK},
            "grain": {"status": OK},
        }
        msg = build_coop_message({"style": "TEST"}, diag)
        self.assertIn("영문", msg)
        self.assertIn("텍스트 표기", msg)

    def test_coop_message_no_panel_keyerror(self):
        """panel 키 없어도 KeyError 없이 동작 (부위명 분기 폐기)."""
        diag = {
            "material": {"status": OK},
            "encoding": {"status": OK},
            "quantity": {"status": OK},
            "grain": {"status": OK},
        }
        # KeyError 없이 완주하면 성공.
        msg = build_coop_message({"style": "TEST"}, diag)
        self.assertIsInstance(msg, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
