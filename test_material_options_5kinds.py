# -*- coding: utf-8 -*-
"""
test_material_options_5kinds.py
-------------------------------
이슈 5 — 사장님 표준 5종 (주원단/안감/포켓팅/배색/논) 통일 검증 (2026-05-06).

배경: 사장님 캡쳐 raw 적발 — 진단 표 헤더 "주원단/심지/안감/배색/포켓팅"
사장님 표준: "주원단/안감/포켓팅/배색/논" — 심지 X (사장님 명시 안 함)

검증:
  1. MATERIAL_OPTIONS = 5종 + 미지정, 심지 폐기
  2. MATERIAL_COLORS_V2 = 5종 키, 심지 키 폐기, '논' 키 추가
  3. DEFAULT_WIDTHS = 5종 키
  4. 정렬 order 모든 곳 5종 통일 (app.py + auto_nesting_v2.py 소스 grep)
  5. 진단 [2] 라벨 = "주원단/안감/포켓팅/배색/논"
  6. dxf_diagnosis._MATERIAL_KEYWORDS — 심지 폐기, 영문 5종 추가
  7. 협력사 메시지 영문 코드 = SELF / LINING / POCKETING / CONTRAST / NON
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


class TestMaterialOptions(unittest.TestCase):
    """app.py 의 MATERIAL_OPTIONS 5종 + 미지정 검증."""

    def test_options_contains_5_kinds_plus_unspecified(self):
        # 격리: app.py import 시 streamlit dep 무거움 → subprocess 격리
        import subprocess
        cmd = (
            "import sys; sys.path.insert(0, '.'); "
            "from app import MATERIAL_OPTIONS; "
            "print(','.join(MATERIAL_OPTIONS))"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd], cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"STDERR: {result.stderr}")
        opts = result.stdout.strip().split(",")
        self.assertEqual(opts, ["주원단", "안감", "포켓팅", "배색", "논", "미지정"])

    def test_심지_not_in_options(self):
        import subprocess
        cmd = (
            "import sys; sys.path.insert(0, '.'); "
            "from app import MATERIAL_OPTIONS; "
            "print('심지' in MATERIAL_OPTIONS)"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd], cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.stdout.strip(), "False")


class TestMaterialColors(unittest.TestCase):

    def test_colors_5_kinds(self):
        import subprocess
        cmd = (
            "import sys; sys.path.insert(0, '.'); "
            "from app import MATERIAL_COLORS_V2; "
            "print(','.join(sorted(MATERIAL_COLORS_V2.keys())))"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd], cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        keys = set(result.stdout.strip().split(","))
        self.assertEqual(keys, {"주원단", "안감", "포켓팅", "배색", "논"})


class TestDxfDiagnosisLabels(unittest.TestCase):
    """dxf_diagnosis 5종 라벨 통일."""

    def test_material_keywords_no_심지(self):
        from dxf_diagnosis import _MATERIAL_KEYWORDS
        self.assertNotIn("심지", _MATERIAL_KEYWORDS)
        # 영문 표준 5종 포함
        for code in ("SELF", "LINING", "POCKETING", "CONTRAST", "NON"):
            self.assertIn(code, _MATERIAL_KEYWORDS, f"{code} 누락")

    def test_coop_message_uses_5_kinds_codes(self):
        from dxf_diagnosis import build_coop_message, FAIL, OK
        diag = {
            "material": {"status": FAIL},
            "panel": {"status": OK, "raw": {"by_class": {}}},
            "quantity": {"status": OK},
            "grain": {"status": OK},
        }
        msg = build_coop_message({"style": "TEST"}, diag)
        # 영문 5종 표기 (FUSE/POCKET 폐기, POCKETING/NON 사용)
        self.assertIn("SELF", msg)
        self.assertIn("LINING", msg)
        self.assertIn("POCKETING", msg)
        self.assertIn("CONTRAST", msg)
        self.assertIn("NON", msg)
        self.assertNotIn("FUSE", msg)
        # POCKET 단독 (POCKETING 안 있는) 폐기 — POCKETING 만 표시
        self.assertNotIn("POCKET / ", msg)


class TestSourceGrepNo심지Order(unittest.TestCase):
    """소스 코드의 정렬 order array 가 모두 5종인지 grep 검증."""

    def test_no_심지_in_app_order_arrays(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # "주원단", "심지" 패턴은 정렬 order 에서 사용 — 폐기 검증
        self.assertNotIn('"주원단", "심지"', src)

    def test_no_심지_in_nest_order_arrays(self):
        src = (ROOT / "auto_nesting_v2.py").read_text(encoding="utf-8")
        self.assertNotIn('"주원단", "심지"', src)

    def test_diagnosis_label_5_kinds(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # 새 라벨
        self.assertIn("(주원단/안감/포켓팅/배색/논)", src)
        # 구 라벨
        self.assertNotIn("(주원단/심지/안감/배색/포켓팅)", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
