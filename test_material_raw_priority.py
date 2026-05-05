# -*- coding: utf-8 -*-
"""
test_material_raw_priority.py
-----------------------------
infer_material_v3 V4 (사장님 결정 2026-05-05) — raw 코드 우선, piece_name 재분류 폐기.

검증:
  1. raw 코드 5종 표준 인식 (SELF/LINING/POCKETING/CONTRAST/FUSE)
  2. CONTRAST + 숫자 매김 (CONTRAST1/CONTRAST2/...) → 배색
  3. 대소문자 무시 (Self/SELF/self 모두 동일)
  4. raw 코드 명시 시 piece_name 키워드 무시 (재분류 폐기 검증)
  5. raw 코드 부재 + annotations 만 있으면 annotations fallback
  6. raw 코드 부재 + piece_name 만 있으면 piece_name fallback
  7. 모두 부재 → FALLBACK "주원단" (경고)
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _infer(piece_name: str, material_raw: str, annotations=None) -> str:
    if annotations is None:
        annotations = []
    cmd = (
        "import sys; sys.path.insert(0, '.'); "
        "from app import infer_material_v3; "
        f"print(infer_material_v3({piece_name!r}, {material_raw!r}, {annotations!r}))"
    )
    r = subprocess.run([sys.executable, "-c", cmd], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


class TestRawCodeStandard(unittest.TestCase):
    """1순위: raw 코드 5종 표준."""

    def test_self_variants(self):
        for c in ["SELF", "Self", "self", "sElF", "1", "MAIN"]:
            self.assertEqual(_infer("FRONT_BODY", c), "주원단", f"{c!r}")

    def test_lining_variants(self):
        for c in ["LINING", "Lining", "lining", "IL", "LIN"]:
            self.assertEqual(_infer("FRONT_BODY", c), "안감", f"{c!r}")

    def test_pocketing_variants(self):
        for c in ["POCKETING", "Pocketing", "pocketing", "POCKET", "PK", "PKT"]:
            self.assertEqual(_infer("FRONT_BODY", c), "포켓팅", f"{c!r}")

    def test_contrast_basic(self):
        for c in ["CONTRAST", "Contrast", "contrast", "CT", "CONT"]:
            self.assertEqual(_infer("FRONT_BODY", c), "배색", f"{c!r}")

    def test_contrast_numbered(self):
        """CONTRAST1, CONTRAST2, ... 모두 배색 (사장님 숫자 매김 표준)"""
        for n in [1, 2, 3, 9, 10, 99]:
            self.assertEqual(_infer("FRONT_BODY", f"CONTRAST{n}"), "배색", f"CONTRAST{n}")
            # 대소문자 무관
            self.assertEqual(_infer("FRONT_BODY", f"contrast{n}"), "배색", f"contrast{n}")

    def test_fuse_variants(self):
        for c in ["FUSE", "FN", "FUSING", "INTERFACING", "INTERLINING"]:
            self.assertEqual(_infer("FRONT_BODY", c), "심지", f"{c!r}")

    def test_non_excluded(self):
        for c in ["NON", "Non", "non", "NONE", "None", "none"]:
            self.assertEqual(_infer("DIA30", c), "마카제외", f"{c!r}")


class TestPieceNameReclassificationDeprecated(unittest.TestCase):
    """piece_name 재분류 분기 폐기 검증 — raw 코드 명시 시 piece_name 무시."""

    def test_pocket_bag_with_lining_keeps_lining(self):
        """FRONT_POCKET_BAG (POCKET 키워드 함유) + Material:Lining → 안감 (재분류 X)
        이전 V3.3 동작 (piece_name POCKET 키워드 우선) → 포켓팅 으로 재분류했음.
        V4 (사장님 본질 2026-05-05): raw 코드 그대로 안감."""
        self.assertEqual(_infer("FRONT_POCKET_BAG", "Lining"), "안감")
        self.assertEqual(_infer("BACK_POCKET_BAG", "LINING"), "안감")

    def test_collar_with_self_keeps_self(self):
        """COLLAR (이전엔 piece_name 키워드 매칭 없음) + Material:SELF → 주원단"""
        self.assertEqual(_infer("COLLAR", "SELF"), "주원단")

    def test_lining_keyword_in_name_with_self_keeps_self(self):
        """name 에 lining 들어있어도 raw=SELF → 주원단 (raw 우선)"""
        self.assertEqual(_infer("LINING_PIECE", "SELF"), "주원단")


class TestAnnotationsFallback(unittest.TestCase):
    """raw 코드 부재 시 annotations 인식."""

    def test_annotations_lining(self):
        self.assertEqual(_infer("X", "", ["안감"]), "안감")
        self.assertEqual(_infer("X", "", ["lining"]), "안감")

    def test_annotations_fuse(self):
        self.assertEqual(_infer("X", "", ["심지"]), "심지")
        self.assertEqual(_infer("X", "", ["fusing"]), "심지")

    def test_annotations_contrast(self):
        self.assertEqual(_infer("X", "", ["배색"]), "배색")

    def test_annotations_pocketing(self):
        self.assertEqual(_infer("X", "", ["포켓팅"]), "포켓팅")
        self.assertEqual(_infer("X", "", ["pocketing"]), "포켓팅")


class TestPieceNameFallbackOnlyWhenAllAbsent(unittest.TestCase):
    """raw + annotations 모두 부재 시만 piece_name fallback."""

    def test_piece_name_lining_fallback(self):
        self.assertEqual(_infer("LINING_PIECE", "", []), "안감")

    def test_piece_name_self_default(self):
        """piece_name 에 키워드 없으면 → 주원단 fallback (경고용)"""
        self.assertEqual(_infer("FRONT_BODY", "", []), "주원단")


class TestFallbackWarning(unittest.TestCase):
    """모든 입력 부재 → 주원단 fallback (경고)"""

    def test_all_empty(self):
        self.assertEqual(_infer("", "", []), "주원단")


if __name__ == "__main__":
    unittest.main(verbosity=2)
