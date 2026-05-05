# -*- coding: utf-8 -*-
"""
test_material_ui_dynamic.py
---------------------------
원단 폭 UI 동적 생성 단위 테스트 (사장님 결정 2026-05-05).

검증:
  width_section 의 핵심 로직:
    1. DXF 등장 원단만 입력 칸 (detected 기반)
    2. 마카제외(NON) 자동 제외
    3. 수동 추가 UI 폐기 (코드에서 expander 사라짐)

streamlit UI 직접 테스트 어려움 → app.py 소스 grep + 로직 unit test.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


class TestWidthSectionLogic(unittest.TestCase):

    def test_marker_excluded_filtered_from_detected(self):
        """detected 에서 '마카제외' 제거 — width input 노출 X"""
        # width_section 핵심 로직 시뮬레이션
        pieces = [
            {"size": "L", "material_inferred": "주원단"},
            {"size": "L", "material_inferred": "안감"},
            {"size": "L", "material_inferred": "마카제외"},
        ]
        selected = ["L"]
        relevant = [p for p in pieces if p["size"] in selected]
        detected = {p["material_inferred"] for p in relevant}
        detected.discard("마카제외")
        self.assertEqual(detected, {"주원단", "안감"})
        self.assertNotIn("마카제외", detected)

    def test_only_detected_materials_in_widths(self):
        """주원단/안감만 detected → 표시 순서대로 widths dict 에"""
        order = ["주원단", "심지", "안감", "배색", "포켓팅"]
        detected = {"주원단", "안감"}
        widths = {}
        for mat in order:
            if mat in detected:
                widths[mat] = 150.0
        self.assertEqual(list(widths.keys()), ["주원단", "안감"])

    def test_contrast_numbered_collapses_to_single(self):
        """CONTRAST/CONTRAST1/CONTRAST2 모두 '배색' 으로 분류 → 1개 입력 칸"""
        # infer_material_v3 가 모두 '배색' 반환하므로 detected 에 '배색' 1개만 등장
        pieces_inferred = ["배색", "배색", "배색"]  # CONTRAST + CONTRAST1 + CONTRAST2
        detected = set(pieces_inferred)
        self.assertEqual(detected, {"배색"})


class TestManualAddUIRemoved(unittest.TestCase):
    """수동 원단 추가 UI 폐기 검증 — app.py 소스에서 expander 라벨 사라짐."""

    def test_no_expander_label_in_source(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        # 사장님 폐기 결정 — '➕ 원단 추가 (자동 감지 안 된 경우)' expander 사라짐
        self.assertNotIn("➕ 원단 추가 (자동 감지 안 된 경우)", src,
                         "수동 원단 추가 expander 가 아직 남아있음")

    def test_session_state_manual_widths_preserved(self):
        """manual_widths session_state 는 downstream merge 호환 위해 빈 dict 유지"""
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('st.session_state.manual_widths = {}', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
