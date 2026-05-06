# -*- coding: utf-8 -*-
"""
test_results_section_scale_hq.py
--------------------------------
이슈 C — material_results_section 시그니처 + 본사/스케일 안내 (사장님 본질 2026-05-07).

검증:
  1. material_results_section 가 scale_diag keyword 인자 받음 (None default)
  2. 호출자 (run_v3_3 흐름) 가 parsed["_diagnosis"]["scale"] 전달
  3. 본사 비교 expander 안내 + 효율 metric delta 표시 코드 grep

UI 함수의 Streamlit 의존성 때문에 직접 렌더 불가 — 시그니처 + 소스 grep 으로 검증.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestSignature(unittest.TestCase):

    def test_scale_diag_keyword_arg(self):
        """material_results_section 시그니처에 scale_diag keyword 인자 존재."""
        import subprocess
        cmd = (
            "import sys, inspect; sys.path.insert(0, '.'); "
            "from app import material_results_section; "
            "sig = inspect.signature(material_results_section); "
            "print(','.join(sig.parameters.keys()))"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd], cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"STDERR: {result.stderr}")
        params = result.stdout.strip().split(",")
        self.assertIn("scale_diag", params)
        # default 값이 None
        cmd2 = (
            "import sys, inspect; sys.path.insert(0, '.'); "
            "from app import material_results_section; "
            "sig = inspect.signature(material_results_section); "
            "print(sig.parameters['scale_diag'].default)"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd2], cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.stdout.strip(), "None")


class TestSourceGrep(unittest.TestCase):
    """소스 코드의 본사 비교 + 스케일 안내 코드 존재 검증."""

    def test_hq_efficiency_delta_in_metric(self):
        """효율 metric 카드에 본사 비교 delta 표시 — 이슈 C 본질."""
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # 본사 효율 비교 — '본사 N.NN% 대비' 형식
        self.assertIn("본사 ", src)
        self.assertIn("대비", src)
        # delta_color 분기 (gap 양수→normal / 음수→inverse)
        self.assertIn("delta_color", src)

    def test_scale_diag_quoted_in_hq_box(self):
        """본사 비교 expander 안에 스케일 안내 박스 — 이슈 C 본질.

        사장님 본질 정정 (2026-05-07): 사용자 노출 메시지에서 raw 수치/비율/단위 명시 X.
        새 메시지 = "50cm × 50cm 박스 인식 완료" / "박스 비정상".
        """
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # 새 메시지 (사장님 본질 정정)
        self.assertIn("50cm × 50cm 박스 인식", src)
        self.assertIn("50cm × 50cm 박스 비정상", src)
        # raw 수치 사용자 노출 X — 옛 패턴이 사라졌는지 검증
        self.assertNotIn("DXF 스케일 미스매치", src)
        self.assertNotIn("단위 의심:", src)
        self.assertNotIn("보정 비율 ×{", src)

    def test_caller_passes_scale_diag(self):
        """호출자가 parsed['_diagnosis']['scale'] 을 전달하는지."""
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # parsed.get("_diagnosis") 후 .get("scale") 추출 패턴
        self.assertIn('_diagnosis', src)
        self.assertIn('scale_diag=', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
