# -*- coding: utf-8 -*-
"""
test_material_non_exclusion.py
------------------------------
Material=NON 자동 마카 제외 단위 테스트 (사장님 결정 2026-05-05).

배경:
  StyleCAD "마커 제외 ✅" 시 갯수 0 이 DXF Quantity:1 로 강제 변환되어 직접 인식 불가.
  사장님 결정: Material 값을 "NON" 으로 표기 → infer_material_v3 가 "마카제외" 분류 →
  nest_pieces_sparrow + 변형 4개 가 자동 skip + excluded_pieces 리스트 기록.

검증 (사용자 명시 5 케이스):
  case_1: Material="NON" → infer_material_v3 = "마카제외"
  case_2: 대소문자 무관 (NON/non/Non/NONE/none) → 모두 "마카제외"
  case_3: Material="SELF" → "주원단" (기존 동작 유지)
  case_4: _filter_excluded_materials 가 NON piece skip + excluded_pieces 리스트 기록
  case_5: nest_pieces_sparrow 결과 dict 에 "excluded_pieces" 키 존재 + 정확한 piece_id
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from auto_nesting_v2 import _filter_excluded_materials


# ╔════════════════════════════════════════════════════════════╗
# ║ 1-3. infer_material_v3 NON 분기 (subprocess — streamlit 격리) ║
# ╚════════════════════════════════════════════════════════════╝
def _run_infer_material_v3(piece_name: str, material_raw: str) -> str:
    """app.py 의 infer_material_v3 호출 (streamlit 격리)."""
    cmd = (
        "import sys; sys.path.insert(0, '.'); "
        "from app import infer_material_v3; "
        f"print(infer_material_v3({piece_name!r}, {material_raw!r}, []))"
    )
    result = subprocess.run(
        [sys.executable, "-c", cmd],
        cwd=ROOT,
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"app.py import 실패:\n{result.stderr}")
    return result.stdout.strip()


class TestInferMaterialNON(unittest.TestCase):

    def test_case_1_NON_classifies_as_excluded(self):
        """case_1: Material='NON' → '마카제외'"""
        self.assertEqual(_run_infer_material_v3("DIA30", "NON"), "마카제외")

    def test_case_2_case_insensitive(self):
        """case_2: 'NON'/'non'/'Non'/'NONE'/'none' 모두 '마카제외'"""
        for code in ["NON", "non", "Non", "nOn", "NONE", "none", "None", "NoNe"]:
            self.assertEqual(
                _run_infer_material_v3("DIA30", code),
                "마카제외",
                f"Material 값 {code!r} 분류 실패",
            )

    def test_case_3_SELF_preserved(self):
        """case_3: Material='SELF' 는 기존대로 '주원단' (회귀 안전성)"""
        for code in ["SELF", "Self", "self"]:
            self.assertEqual(
                _run_infer_material_v3("FRONT_BODY", code),
                "주원단",
                f"Material {code!r} 회귀 발생",
            )

    def test_case_3b_Lining_preserved(self):
        """기존 LINING 분류도 영향 없음 (회귀 안전성)"""
        # piece_name 에 lining/안감 키워드 없는 중성 이름 사용
        # — piece_name 키워드가 material_raw 보다 우선이므로
        self.assertEqual(_run_infer_material_v3("FRONT_BODY", "Lining"), "안감")
        self.assertEqual(_run_infer_material_v3("FRONT_BODY", "FUSE"), "심지")
        self.assertEqual(_run_infer_material_v3("FRONT_BODY", "CONTRAST"), "배색")


# ╔════════════════════════════════════════════════════════════╗
# ║ 4. _filter_excluded_materials — 직접 단위 테스트              ║
# ╚════════════════════════════════════════════════════════════╝
class TestFilterExcludedMaterials(unittest.TestCase):
    """헬퍼 함수 — 두 인식 경로 모두 검증.
       (a) material_inferred == "마카제외"
       (b) material_raw / material upper in {NON, NONE}"""

    def test_case_4_filter_skips_inferred_excluded(self):
        """case_4 (a): material_inferred='마카제외' piece 가 skip + excluded_pieces 기록"""
        pieces = [
            {"piece_id": "P1", "material_inferred": "주원단", "material_raw": "SELF"},
            {"piece_id": "DIA30", "material_inferred": "마카제외", "material_raw": "NON"},
            {"piece_id": "P2", "material_inferred": "안감", "material_raw": "Lining"},
        ]
        filtered, excluded = _filter_excluded_materials(pieces)
        self.assertEqual(len(filtered), 2)
        self.assertEqual([p["piece_id"] for p in filtered], ["P1", "P2"])
        self.assertEqual(excluded, ["DIA30"])

    def test_case_4_filter_skips_raw_NON_fallback(self):
        """case_4 (b): material_inferred 비어도 material_raw=NON 만으로 인식 (fallback)"""
        pieces = [
            {"piece_id": "P1", "material_raw": "SELF"},
            {"piece_id": "X", "material_raw": "NON"},
            {"piece_id": "Y", "material_raw": "NONE"},
            {"piece_id": "Z", "material_raw": "non"},
        ]
        filtered, excluded = _filter_excluded_materials(pieces)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["piece_id"], "P1")
        self.assertEqual(set(excluded), {"X", "Y", "Z"})

    def test_case_4_filter_no_exclusion_returns_empty_excluded(self):
        """NON 표기 없는 정상 케이스 — excluded_pieces 빈 리스트, filtered 그대로"""
        pieces = [
            {"piece_id": "P1", "material_inferred": "주원단", "material_raw": "SELF"},
            {"piece_id": "P2", "material_inferred": "안감", "material_raw": "Lining"},
        ]
        filtered, excluded = _filter_excluded_materials(pieces)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(excluded, [])


# ╔════════════════════════════════════════════════════════════╗
# ║ 5. nest_pieces_sparrow 결과 dict 에 excluded_pieces 키 보장    ║
# ╚════════════════════════════════════════════════════════════╝
class TestNestPiecesSparrowExcludedKey(unittest.TestCase):
    """case_5: 4개 nest 함수 모두 결과 dict 에 excluded_pieces 키 포함.

    실제 sparrow 실행 없이 early-return 경로 활용 (sizes_to_nest 매칭 없음 → error 반환):
    error 반환 dict 에도 excluded_pieces 가 들어있어야 함."""

    def _piece(self, pid: str, material_raw: str = "SELF", inferred: str = "주원단", q: int = 1) -> dict:
        return {
            "piece_id": pid,
            "piece_name": pid,
            "size": "L",
            "quantity": q,
            "mirror": None,
            "material_raw": material_raw,
            "material_inferred": inferred,
            "coords_cm": [(0, 0), (10, 0), (10, 10), (0, 10)],
            "width_cm": 10.0, "height_cm": 10.0,
            "grain": {"angle_deg": 90.0, "kind": "STRAIGHT_GRAIN_Y",
                      "length_mm": 100.0, "raw_layer": "7"},
        }

    def test_case_5_excluded_pieces_key_present(self):
        """sizes_to_nest 매칭 없는 early-return 경로에서도 excluded_pieces 포함"""
        from auto_nesting_v2 import nest_pieces_sparrow
        pieces = [
            self._piece("P1", "SELF", "주원단"),
            self._piece("DIA30", "NON", "마카제외"),
        ]
        # sizes_to_nest=["XXX"] → 매칭 없어 early-return (sparrow 안 돌림)
        res = nest_pieces_sparrow(
            pieces=pieces, fabric_width_cm=144.0,
            sizes_to_nest=["XXX"], runtime_seconds=1,
        )
        self.assertIn("excluded_pieces", res)
        self.assertEqual(res["excluded_pieces"], ["DIA30"])

    def test_case_5_excluded_pieces_in_multisize(self):
        """nest_pieces_sparrow_multisize 도 excluded_pieces 포함"""
        from auto_nesting_v2 import nest_pieces_sparrow_multisize
        pieces = [
            self._piece("P1", "SELF", "주원단"),
            self._piece("X", "NON", "마카제외"),
        ]
        # size_ratio 합계 0 → early return
        res = nest_pieces_sparrow_multisize(
            pieces=pieces, fabric_width_cm=144.0,
            size_ratio={"L": 0}, runtime_seconds=1,
        )
        self.assertIn("excluded_pieces", res)
        self.assertEqual(res["excluded_pieces"], ["X"])

    def test_case_5_excluded_pieces_in_by_material(self):
        """nest_by_material 도 excluded_pieces 포함"""
        from auto_nesting_v2 import nest_by_material
        pieces = [
            self._piece("P1", "SELF", "주원단"),
            self._piece("DIA30", "NON", "마카제외"),
        ]
        # 사이즈 매칭 없게 — group_pieces_by_material 결과가 빈 그룹 만 (sparrow 안 돌림)
        res = nest_by_material(
            pieces=pieces, fabric_widths_per_material={"주원단": 144.0},
            sizes_to_nest=["XXX"], runtime_seconds=1,
        )
        self.assertIn("excluded_pieces", res)
        self.assertEqual(res["excluded_pieces"], ["DIA30"])

    def test_case_5_excluded_pieces_in_by_material_multisize(self):
        """nest_by_material_multisize 도 excluded_pieces 포함"""
        from auto_nesting_v2 import nest_by_material_multisize
        pieces = [
            self._piece("P1", "SELF", "주원단"),
            self._piece("DIA30", "NON", "마카제외"),
        ]
        res = nest_by_material_multisize(
            pieces=pieces, fabric_widths_per_material={"주원단": 144.0},
            size_ratio={"L": 0}, runtime_seconds=1,
        )
        self.assertIn("excluded_pieces", res)
        self.assertEqual(res["excluded_pieces"], ["DIA30"])


# ╔════════════════════════════════════════════════════════════╗
# ║ 6. dxf_diagnosis [5] 카테고리 — diagnose_excluded             ║
# ╚════════════════════════════════════════════════════════════╝
class TestDiagnoseExcluded(unittest.TestCase):

    def test_excluded_present(self):
        from dxf_diagnosis import diagnose_excluded
        parsed = {"pieces": [
            {"piece_id": "P1", "piece_name": "FRONT_BODY",
             "material_raw": "SELF", "material_inferred": "주원단"},
            {"piece_id": "DIA30", "piece_name": "DIA30",
             "material_raw": "NON", "material_inferred": "마카제외"},
        ]}
        diag = diagnose_excluded(parsed)
        self.assertEqual(diag["raw"]["excluded_count"], 1)
        self.assertEqual(diag["raw"]["excluded"][0]["piece_id"], "DIA30")
        self.assertIn("DIA30", diag["summary"])

    def test_excluded_absent(self):
        """NON 표기 없으면 OK 상태 + 0개 명시"""
        from dxf_diagnosis import diagnose_excluded
        parsed = {"pieces": [
            {"piece_id": "P1", "material_raw": "SELF", "material_inferred": "주원단"},
        ]}
        diag = diagnose_excluded(parsed)
        self.assertEqual(diag["raw"]["excluded_count"], 0)
        self.assertEqual(diag["status"], "OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
