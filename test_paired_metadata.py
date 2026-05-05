# -*- coding: utf-8 -*-
"""
test_paired_metadata.py
-----------------------
PAIRED 메타 처리 + MATERIAL 대소문자 정규화 단위 테스트 (사장님 결정 2026-05-05).

배경:
  TEST 패턴 파일/MMAPS003-test.dxf 에 사장님이 8 piece 에 'PAIRED: DOUBLE' 박았으나,
  기존 parser 는 'paired' 키를 인식하지 못해 mirror 메타 무시 → 좌우 페어 한쪽만 깔림.
  64 placements (12 piece × 1 + 2 piece × 2 = 16/벌 × 4벌) 만 나오던 것을
  96 placements (24/벌 × 4벌) 로 정상화하기 위함.

검증:
  1. parse_paired_value — 토큰 정규화 (DOUBLE/SINGLE/ 그 외)
  2. parse_piece_metadata — 'PAIRED: DOUBLE' / 'PAIRED: SINGLE' / 부재
  3. PAIRED 우선 — PAIRED + Mirror 둘 다 있으면 PAIRED 가 mirror 결정
  4. _split_mirrored_pieces — Q=1 + mirror=True → "1 pair" (orig:1 + mirror:1)
  5. MATERIAL 대소문자 무시 — 'Lining' / 'LINING' / 'lining' 모두 LINING 분류
  6. MMAPS003-test.dxf 통합 — 14 piece 중 8개 mirror=True
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import ezdxf

from extract_pieces import (
    parse_mirror_value,
    parse_paired_value,
    parse_piece_metadata,
)
from auto_nesting_v2 import _split_mirrored_pieces


# ╔════════════════════════════════════════════════════════════╗
# ║ 1. parse_paired_value — 토큰 정규화                          ║
# ╚════════════════════════════════════════════════════════════╝
class TestParsePairedValue(unittest.TestCase):
    """절대 원칙: 인식 불능 값은 None — 자동 추측 X."""

    def test_double_returns_true(self):
        for tok in ["DOUBLE", "double", "Double", "  DOUBLE  "]:
            self.assertIs(parse_paired_value(tok), True, f"입력={tok!r}")

    def test_pair_yes_aliases(self):
        for tok in ["PAIR", "pair", "YES", "yes", "Y", "y", "TRUE", "1"]:
            self.assertIs(parse_paired_value(tok), True, f"입력={tok!r}")

    def test_single_returns_false(self):
        for tok in ["SINGLE", "single", "Single", " single "]:
            self.assertIs(parse_paired_value(tok), False, f"입력={tok!r}")

    def test_no_aliases(self):
        for tok in ["NO", "no", "N", "n", "FALSE", "0", ""]:
            self.assertIs(parse_paired_value(tok), False, f"입력={tok!r}")

    def test_unknown_returns_none(self):
        # 절대 원칙: 인식 불능 → 추측 X
        for tok in ["TRIPLE", "?", "예", "DOUBLED", "PAIRS", "MAYBE"]:
            self.assertIsNone(parse_paired_value(tok), f"입력={tok!r}")

    def test_none_input(self):
        self.assertIsNone(parse_paired_value(None))


# ╔════════════════════════════════════════════════════════════╗
# ║ 2. parse_piece_metadata — block 단위 PAIRED 인식              ║
# ╚════════════════════════════════════════════════════════════╝
def _mock_text_entity(text: str):
    """ezdxf TEXT 엔티티 모킹."""
    e = MagicMock()
    e.dxftype.return_value = "TEXT"
    e.dxf.text = text
    return e


def _mock_block(texts: list[str]):
    """블록을 iterable 한 mock 으로 — TEXT 엔티티만 포함."""
    return [_mock_text_entity(t) for t in texts]


class TestParsePieceMetadataPaired(unittest.TestCase):

    def test_paired_double_sets_mirror_true(self):
        """사용자 명시 케이스 1: 'PAIRED: DOUBLE' → mirror=True"""
        block = _mock_block([
            "Piece Name: FRONT_BODY",
            "Quantity: 1",
            "MATERIAL: SELF",
            "PAIRED: DOUBLE",
        ])
        meta = parse_piece_metadata(block)
        self.assertIs(meta["mirror"], True)
        self.assertEqual(meta["quantity"], 1)  # quantity 는 그대로 보존

    def test_paired_single_sets_mirror_false(self):
        """사용자 명시 케이스 2: 'PAIRED: SINGLE' → mirror=False"""
        block = _mock_block([
            "Piece Name: COLLAR",
            "Quantity: 1",
            "PAIRED: SINGLE",
        ])
        meta = parse_piece_metadata(block)
        self.assertIs(meta["mirror"], False)

    def test_no_paired_no_mirror_returns_none(self):
        """사용자 명시 케이스 3: PAIRED 부재 + Mirror 부재 → mirror=None"""
        block = _mock_block([
            "Piece Name: FLY",
            "Quantity: 1",
            "MATERIAL: SELF",
        ])
        meta = parse_piece_metadata(block)
        self.assertIsNone(meta["mirror"])

    def test_paired_unknown_value_returns_none(self):
        """절대 원칙: PAIRED 값이 인식 불능 → mirror=None (추측 X)"""
        block = _mock_block([
            "Piece Name: X",
            "PAIRED: TRIPLE",
        ])
        meta = parse_piece_metadata(block)
        self.assertIsNone(meta["mirror"])

    def test_paired_overrides_mirror_when_both_present(self):
        """사용자 명시 케이스 4: PAIRED + Mirror 둘 다 있으면 PAIRED 우선.

        시나리오: 사장님이 PAIRED:DOUBLE 박았고 다른 패턴사가 'Mirror: No' 도 박은 경우
        — PAIRED 가 본 시스템(StyleCAD)의 정식 키이므로 우선.
        """
        # 케이스 (a): PAIRED 가 먼저 등장
        block_a = _mock_block([
            "Piece Name: A",
            "PAIRED: DOUBLE",   # → True
            "Mirror: No",        # → False (덮어쓰면 안 됨)
        ])
        self.assertIs(parse_piece_metadata(block_a)["mirror"], True)

        # 케이스 (b): Mirror 가 먼저, PAIRED 가 나중
        block_b = _mock_block([
            "Piece Name: B",
            "Mirror: Yes",       # → True
            "PAIRED: SINGLE",    # → False (PAIRED 가 우선이므로 결국 False)
        ])
        self.assertIs(parse_piece_metadata(block_b)["mirror"], False)

        # 케이스 (c): Mirror 만 있고 PAIRED 없음 → Mirror 그대로 사용
        block_c = _mock_block([
            "Piece Name: C",
            "Mirror: Yes",
        ])
        self.assertIs(parse_piece_metadata(block_c)["mirror"], True)


# ╔════════════════════════════════════════════════════════════╗
# ║ 3. _split_mirrored_pieces — Q=1 + mirror=True → 1 pair       ║
# ╚════════════════════════════════════════════════════════════╝
class TestSplitMirroredPiecesQ1(unittest.TestCase):
    """사장님 정책 갱신 2026-05-05:
       Q=1 + mirror=True → "1 pair" 의미 → orig:1 + mirror:1 (총 2 piece).
       PAIRED:DOUBLE + Quantity:1 케이스 (StyleCAD 표기 관습)."""

    def _piece(self, pid: str, q: int, mirror=None) -> dict:
        return {
            "piece_id": pid,
            "piece_name": pid,
            "size": "L",
            "quantity": q,
            "mirror": mirror,
            "coords_cm": [(0, 0), (5, 0), (5, 5), (10, 5), (10, 10), (0, 10)],
            "width_cm": 10.0,
            "height_cm": 10.0,
            "grain": {
                "angle_deg": 90.0,
                "length_mm": 100.0,
                "kind": "STRAIGHT_GRAIN_Y",
                "raw_layer": "7",
            },
        }

    def test_q1_mirror_true_expands_to_pair(self):
        """Q=1 + mirror=True → orig:1 + mirror:1, 경고 X (정책 갱신)"""
        p = self._piece("P1", q=1, mirror=True)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["piece_id"], "P1_orig")
        self.assertEqual(out[0]["quantity"], 1)
        self.assertEqual(out[1]["piece_id"], "P1_M")
        self.assertEqual(out[1]["quantity"], 1)
        self.assertEqual(warns, [])

    def test_q2_mirror_true_unchanged(self):
        """Q=2 + mirror=True → orig:1 + mirror:1 (기존 정책 유지)"""
        p = self._piece("P2", q=2, mirror=True)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["quantity"], 1)
        self.assertEqual(out[1]["quantity"], 1)

    def test_q3_mirror_true_warns(self):
        """Q=3 (홀수, 1 제외) + mirror=True → ⚠️ + skip (기존 정책 유지)"""
        p = self._piece("P3", q=3, mirror=True)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["quantity"], 3)
        self.assertEqual(len(warns), 1)


# ╔════════════════════════════════════════════════════════════╗
# ║ 4. MATERIAL 대소문자 정규화 (앱 통합 — subprocess 로 격리)     ║
# ╚════════════════════════════════════════════════════════════╝
class TestMaterialCaseNormalization(unittest.TestCase):
    """app.py 의 infer_material_v3 가 'Lining'/'LINING'/'lining' 모두 '안감' 분류하는지.

    app.py 는 streamlit dep 무거움 → subprocess 로 격리해 import 효과 차단."""

    def test_lining_case_insensitive(self):
        """material_raw 코드가 'Lining'/'LINING'/'lining' 어느 대소문자든 동일 분류.

        주의: infer_material_v3 는 piece_name 키워드 (POCKET 등) 가 material_raw 보다
              우선이므로, 키워드 없는 중성적 piece_name 으로 격리해 검증."""
        import subprocess
        cmd = (
            "import sys; sys.path.insert(0, '.'); "
            "from app import infer_material_v3; "
            "results = [infer_material_v3('FRONT_BODY', code, []) "
            "for code in ['Lining', 'LINING', 'lining', 'LiNiNg']]; "
            "print(','.join(results))"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd],
            cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"STDERR: {result.stderr}")
        labels = result.stdout.strip().split(",")
        self.assertEqual(labels, ["안감", "안감", "안감", "안감"],
                         f"대소문자별 분류 결과 다름: {labels}")

    def test_self_case_insensitive(self):
        """material_raw 'Self'/'SELF'/'self' 동일 분류 (제감/주원단)."""
        import subprocess
        cmd = (
            "import sys; sys.path.insert(0, '.'); "
            "from app import infer_material_v3; "
            "results = [infer_material_v3('FRONT_BODY', code, []) "
            "for code in ['Self', 'SELF', 'self', 'sElF']]; "
            "print(','.join(results))"
        )
        result = subprocess.run(
            [sys.executable, "-c", cmd],
            cwd=ROOT,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"STDERR: {result.stderr}")
        labels = result.stdout.strip().split(",")
        self.assertEqual(labels, ["주원단", "주원단", "주원단", "주원단"],
                         f"대소문자별 분류 결과 다름: {labels}")


# ╔════════════════════════════════════════════════════════════╗
# ║ 5. 실제 DXF 통합 — MMAPS003-test.dxf                          ║
# ╚════════════════════════════════════════════════════════════╝
class TestMMAPS003Integration(unittest.TestCase):
    """raw 검증: TEST 패턴 파일/MMAPS003-test.dxf 에서 PAIRED:DOUBLE 8 piece
       모두 mirror=True 로 파싱되는지 + Quantity 메타 보존되는지."""

    DXF_PATH = ROOT / "TEST 패턴 파일" / "MMAPS003-test.dxf"

    def test_paired_pieces_get_mirror_true(self):
        if not self.DXF_PATH.exists():
            self.skipTest(f"DXF 파일 없음: {self.DXF_PATH}")

        doc = ezdxf.readfile(str(self.DXF_PATH))
        results = []
        for blk in doc.blocks:
            if blk.name.startswith(("*", "$")):
                continue
            meta = parse_piece_metadata(blk)
            if meta["piece_name"]:
                results.append(meta)

        # 사장님 raw 데이터 카운트
        mirror_true_count = sum(1 for m in results if m["mirror"] is True)
        self.assertEqual(
            mirror_true_count, 8,
            f"PAIRED:DOUBLE 8개 중 일부 mirror=True 처리 실패: "
            f"실제 mirror=True {mirror_true_count}개. results={results}"
        )

        # PAIRED:DOUBLE piece 들의 Quantity 는 모두 1 (사장님이 1 pair 의미로 표기)
        # → Quantity 강제 변경 없이 그대로 보존
        paired_pieces = [m for m in results if m["mirror"] is True]
        for m in paired_pieces:
            self.assertEqual(
                m["quantity"], 1,
                f"PAIRED piece quantity 변경됨: {m['piece_name']} q={m['quantity']}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
