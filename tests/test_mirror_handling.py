# -*- coding: utf-8 -*-
"""
test_mirror_handling.py
-----------------------
Mirror 처리 옵션 A 단위 테스트 (사장님 결정 2026-05-04).

검증 대상:
  1. parse_mirror_value / parse_mirror_value_v3 — 입력값 정규화
  2. mirror_grain_angle — (180 - θ) mod 180 수학적 정확성
  3. _mirror_piece_horizontal — coords_cm 미러 + grain 각도 미러 + piece_id "_M"
  4. _split_mirrored_pieces — 짝수/홀수/q<2 quantity 처리 정책
  5. 식서 LINE 미러 + grain.kind 재분류 일관성

사용자 명시 5 케이스:
  (1) ㄴ자 비대칭 + Mirror=True + Quantity=2  → 원본+미러 두 polygon 분리 배치
  (2) 정사각형 (대칭) + Mirror=True + Quantity=2 → 미러해도 모양 같음
  (3) Mirror=False + Quantity=5 → 동일 polygon 5개 (기존 동작)
  (4) Mirror=True + Quantity=3 (홀수) → ⚠️ 경고 + 미러 skip
  (5) 식서 LINE 30° → 150° / 90° → 90° / 45° → 135° 등 변환 검증
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shapely.geometry import Polygon
from shapely.affinity import scale as shp_scale

from extract_pieces import parse_mirror_value
from auto_nesting_v2 import (
    mirror_grain_angle,
    _reclassify_grain_kind,
    _mirror_piece_horizontal,
    _split_mirrored_pieces,
)


# ╔════════════════════════════════════════════════════════════╗
# ║ 1. parse_mirror_value — 입력값 정규화                        ║
# ╚════════════════════════════════════════════════════════════╝
class TestParseMirrorValue(unittest.TestCase):
    """절대 원칙: 인식 불능 값은 None — 자동 추측 X."""

    def test_true_tokens(self):
        for token in ["True", "true", "TRUE", "1", "Y", "yes", "Yes", "YES"]:
            self.assertIs(parse_mirror_value(token), True, f"입력={token!r}")

    def test_false_tokens(self):
        for token in ["False", "false", "FALSE", "0", "N", "no", "No", "NO", ""]:
            self.assertIs(parse_mirror_value(token), False, f"입력={token!r}")

    def test_unknown_returns_none(self):
        for token in ["maybe", "T", "F", "예", "아니오", "??"]:
            self.assertIsNone(parse_mirror_value(token), f"입력={token!r}")

    def test_none_input(self):
        self.assertIsNone(parse_mirror_value(None))

    def test_whitespace_handling(self):
        self.assertIs(parse_mirror_value("  true  "), True)
        self.assertIs(parse_mirror_value("\tFalse\n"), False)


# ╔════════════════════════════════════════════════════════════╗
# ║ 2. mirror_grain_angle — 수학 공식 (180 - θ) mod 180          ║
# ╚════════════════════════════════════════════════════════════╝
class TestMirrorGrainAngle(unittest.TestCase):
    """X 반사 각도 변환의 수학적 정확성 검증."""

    def test_x_axis_unchanged(self):
        """0° / 180° → 0° (X축 식서는 미러해도 X축)"""
        self.assertAlmostEqual(mirror_grain_angle(0.0), 0.0, places=4)
        self.assertAlmostEqual(mirror_grain_angle(180.0) % 180.0, 0.0, places=4)

    def test_y_axis_unchanged(self):
        """90° → 90° (Y축 식서 = 의류 표준 — X 반사로 변하지 않음)"""
        self.assertAlmostEqual(mirror_grain_angle(90.0), 90.0, places=4)

    def test_bias_swaps(self):
        """45° ↔ 135° (BIAS 두 방향 교환)"""
        self.assertAlmostEqual(mirror_grain_angle(45.0), 135.0, places=4)
        self.assertAlmostEqual(mirror_grain_angle(135.0), 45.0, places=4)

    def test_diagonal_swaps(self):
        """30° ↔ 150°, 60° ↔ 120°, 170° ↔ 10°"""
        self.assertAlmostEqual(mirror_grain_angle(30.0), 150.0, places=4)
        self.assertAlmostEqual(mirror_grain_angle(150.0), 30.0, places=4)
        self.assertAlmostEqual(mirror_grain_angle(60.0), 120.0, places=4)
        self.assertAlmostEqual(mirror_grain_angle(170.0), 10.0, places=4)
        self.assertAlmostEqual(mirror_grain_angle(10.0), 170.0, places=4)

    def test_involution(self):
        """미러를 두 번 적용하면 원래 각도로 돌아옴 (mod 180)"""
        for ang in [0.0, 15.0, 30.0, 45.0, 67.5, 89.0, 90.0, 100.0, 135.0, 170.0]:
            twice = mirror_grain_angle(mirror_grain_angle(ang)) % 180.0
            self.assertAlmostEqual(twice, ang % 180.0, places=4,
                                   msg=f"이중 미러 실패: {ang}")


# ╔════════════════════════════════════════════════════════════╗
# ║ 3. grain kind 재분류 — extract_grain 와 일관                 ║
# ╚════════════════════════════════════════════════════════════╝
class TestReclassifyGrainKind(unittest.TestCase):

    def test_x_grain(self):
        self.assertEqual(_reclassify_grain_kind(0.0), "STRAIGHT_GRAIN_X")
        self.assertEqual(_reclassify_grain_kind(5.0), "STRAIGHT_GRAIN_X")
        self.assertEqual(_reclassify_grain_kind(175.0), "STRAIGHT_GRAIN_X")

    def test_y_grain(self):
        self.assertEqual(_reclassify_grain_kind(90.0), "STRAIGHT_GRAIN_Y")
        self.assertEqual(_reclassify_grain_kind(85.0), "STRAIGHT_GRAIN_Y")
        self.assertEqual(_reclassify_grain_kind(95.0), "STRAIGHT_GRAIN_Y")

    def test_bias(self):
        self.assertEqual(_reclassify_grain_kind(45.0), "BIAS")
        self.assertEqual(_reclassify_grain_kind(135.0), "BIAS")
        self.assertEqual(_reclassify_grain_kind(40.0), "BIAS")
        self.assertEqual(_reclassify_grain_kind(140.0), "BIAS")

    def test_nonstandard(self):
        self.assertEqual(_reclassify_grain_kind(30.0), "NONSTANDARD")
        self.assertEqual(_reclassify_grain_kind(60.0), "NONSTANDARD")
        self.assertEqual(_reclassify_grain_kind(150.0), "NONSTANDARD")


# ╔════════════════════════════════════════════════════════════╗
# ║ 4. _mirror_piece_horizontal — piece dict 미러                ║
# ╚════════════════════════════════════════════════════════════╝
class TestMirrorPieceHorizontal(unittest.TestCase):

    def _l_shape_piece(self) -> dict:
        """ㄴ자 비대칭 polygon (10x10 cm 의 좌하단을 5x5 잘라냄)
            ┌─────┐
            │     │
            │  ┌──┘
            │  │
            └──┘
        """
        coords = [(0, 0), (5, 0), (5, 5), (10, 5), (10, 10), (0, 10), (0, 0)]
        return {
            "piece_id": "P001",
            "piece_name": "L_SHAPE",
            "size": "L",
            "quantity": 2,
            "mirror": True,
            "coords_cm": coords[:-1],  # 마지막 닫힘점 제외
            "width_cm": 10.0,
            "height_cm": 10.0,
            "grain": {
                "angle_deg": 90.0,
                "length_mm": 100.0,
                "kind": "STRAIGHT_GRAIN_Y",
                "raw_layer": "7",
            },
        }

    def test_piece_id_suffix(self):
        p = self._l_shape_piece()
        mp = _mirror_piece_horizontal(p)
        self.assertEqual(mp["piece_id"], "P001_M")
        self.assertEqual(mp["mirrored_from"], "P001")

    def test_coords_mirrored_x(self):
        """X 반사 후 (min_x=0, min_y=0) normalize 결과 확인."""
        p = self._l_shape_piece()
        mp = _mirror_piece_horizontal(p)
        coords_orig = p["coords_cm"]
        coords_mir = mp["coords_cm"]
        # 원본 ≠ 미러 (비대칭 polygon)
        self.assertNotEqual(coords_orig, coords_mir)
        # min_x, min_y 모두 0
        self.assertAlmostEqual(min(c[0] for c in coords_mir), 0.0, places=4)
        self.assertAlmostEqual(min(c[1] for c in coords_mir), 0.0, places=4)
        # bbox 폭/높이 보존 (X 반사는 폭/높이 안 바뀜)
        w_orig = max(c[0] for c in coords_orig) - min(c[0] for c in coords_orig)
        w_mir = max(c[0] for c in coords_mir) - min(c[0] for c in coords_mir)
        self.assertAlmostEqual(w_orig, w_mir, places=4)

    def test_coords_mirror_is_involution(self):
        """미러를 두 번 적용하면 원본과 동일한 polygon."""
        p = self._l_shape_piece()
        mp = _mirror_piece_horizontal(p)
        # 두 번째 미러
        mp2 = _mirror_piece_horizontal({**mp, "piece_id": "P001"})
        # 원본과 같은 polygon (Shapely Polygon 면적 비교)
        poly_orig = Polygon(p["coords_cm"])
        poly_mir2 = Polygon(mp2["coords_cm"])
        self.assertAlmostEqual(poly_orig.area, poly_mir2.area, places=4)
        # exterior coords 도 (정렬 후) 동일
        # — Shapely 가 좌표 순서를 정규화할 수 있으므로 면적+bbox 일치만 검증
        self.assertAlmostEqual(poly_orig.bounds[2] - poly_orig.bounds[0],
                               poly_mir2.bounds[2] - poly_mir2.bounds[0], places=4)

    def test_grain_angle_mirrored(self):
        """grain.angle_deg = (180 - θ) mod 180, kind 재분류"""
        p = self._l_shape_piece()
        # 케이스 (5): 90° → 90° (불변)
        mp = _mirror_piece_horizontal(p)
        self.assertAlmostEqual(mp["grain"]["angle_deg"], 90.0, places=2)
        self.assertEqual(mp["grain"]["kind"], "STRAIGHT_GRAIN_Y")
        self.assertTrue(mp["grain"]["mirrored"])

        # 케이스 (5): 30° → 150°, kind NONSTANDARD ↔ NONSTANDARD
        p2 = self._l_shape_piece()
        p2["grain"]["angle_deg"] = 30.0
        p2["grain"]["kind"] = "NONSTANDARD"
        mp2 = _mirror_piece_horizontal(p2)
        self.assertAlmostEqual(mp2["grain"]["angle_deg"], 150.0, places=2)
        self.assertEqual(mp2["grain"]["kind"], "NONSTANDARD")

        # 케이스 (5): 45° BIAS → 135° BIAS
        p3 = self._l_shape_piece()
        p3["grain"]["angle_deg"] = 45.0
        p3["grain"]["kind"] = "BIAS"
        mp3 = _mirror_piece_horizontal(p3)
        self.assertAlmostEqual(mp3["grain"]["angle_deg"], 135.0, places=2)
        self.assertEqual(mp3["grain"]["kind"], "BIAS")

        # 케이스 (5): 0° X-grain → 0° X-grain
        p4 = self._l_shape_piece()
        p4["grain"]["angle_deg"] = 0.0
        p4["grain"]["kind"] = "STRAIGHT_GRAIN_X"
        mp4 = _mirror_piece_horizontal(p4)
        self.assertAlmostEqual(mp4["grain"]["angle_deg"], 0.0, places=2)
        self.assertEqual(mp4["grain"]["kind"], "STRAIGHT_GRAIN_X")


# ╔════════════════════════════════════════════════════════════╗
# ║ 5. _split_mirrored_pieces — quantity 정책                   ║
# ╚════════════════════════════════════════════════════════════╝
class TestSplitMirroredPieces(unittest.TestCase):

    def _piece(self, pid: str, q: int, mirror=None, coords=None) -> dict:
        return {
            "piece_id": pid,
            "piece_name": pid,
            "size": "L",
            "quantity": q,
            "mirror": mirror,
            "coords_cm": coords or [(0, 0), (10, 0), (10, 10), (0, 10)],
            "width_cm": 10.0,
            "height_cm": 10.0,
            "grain": {
                "angle_deg": 90.0,
                "length_mm": 100.0,
                "kind": "STRAIGHT_GRAIN_Y",
                "raw_layer": "7",
            },
        }

    def test_case_1_l_shape_mirror_quantity_2(self):
        """ㄴ자 + Mirror=True + Quantity=2 → 원본 + 미러 두 piece, 각 quantity=1."""
        l_coords = [(0, 0), (5, 0), (5, 5), (10, 5), (10, 10), (0, 10)]
        p = self._piece("L1", q=2, mirror=True, coords=l_coords)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["piece_id"], "L1_orig")
        self.assertEqual(out[0]["quantity"], 1)
        self.assertEqual(out[1]["piece_id"], "L1_M")
        self.assertEqual(out[1]["quantity"], 1)
        self.assertEqual(warns, [])
        # ㄴ자 미러된 polygon 은 원본과 모양 다름 (비대칭 입증)
        self.assertNotEqual(out[0]["coords_cm"], out[1]["coords_cm"])

    def test_case_2_square_mirror_quantity_2(self):
        """정사각형 (대칭) + Mirror=True + Quantity=2 → 분리는 되지만
           미러 polygon ≡ 원본 polygon (면적·bbox 동일)"""
        sq_coords = [(0, 0), (10, 0), (10, 10), (0, 10)]
        p = self._piece("SQ", q=2, mirror=True, coords=sq_coords)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 2)
        self.assertEqual(warns, [])

        poly_orig = Polygon(out[0]["coords_cm"])
        poly_mir = Polygon(out[1]["coords_cm"])
        self.assertAlmostEqual(poly_orig.area, poly_mir.area, places=4)
        self.assertAlmostEqual(
            poly_orig.bounds[2] - poly_orig.bounds[0],
            poly_mir.bounds[2] - poly_mir.bounds[0],
            places=4,
        )

    def test_case_3_no_mirror_quantity_5(self):
        """Mirror=False + Quantity=5 → 분리 X, 원본 그대로 (기존 동작)"""
        p = self._piece("P5", q=5, mirror=False)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["piece_id"], "P5")  # 접미사 X
        self.assertEqual(out[0]["quantity"], 5)
        self.assertEqual(warns, [])

    def test_case_3b_mirror_none_quantity_5(self):
        """Mirror=None (불명) + Quantity=5 → 미러 적용 X (절대 원칙: 추측 X)"""
        p = self._piece("PN", q=5, mirror=None)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["piece_id"], "PN")
        self.assertEqual(out[0]["quantity"], 5)
        self.assertEqual(warns, [])

    def test_case_4_mirror_quantity_3_odd(self):
        """Mirror=True + Quantity=3 (홀수) → ⚠️ 경고 + 미러 skip"""
        p = self._piece("P3", q=3, mirror=True)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 1)  # 분리 X
        self.assertEqual(out[0]["piece_id"], "P3")
        self.assertEqual(out[0]["quantity"], 3)
        self.assertEqual(len(warns), 1)
        self.assertIn("홀수", warns[0])

    def test_case_4b_mirror_quantity_1(self):
        """Mirror=True + Quantity=1 → "1 pair" (orig:1 + mirror:1)
           정책 갱신 2026-05-05: PAIRED:DOUBLE + Quantity:1 (StyleCAD 표기) 지원."""
        p = self._piece("P1", q=1, mirror=True)
        out, _, warns = _split_mirrored_pieces([p], polygons=None)

        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["piece_id"], "P1_orig")
        self.assertEqual(out[0]["quantity"], 1)
        self.assertEqual(out[1]["piece_id"], "P1_M")
        self.assertEqual(out[1]["quantity"], 1)
        self.assertEqual(warns, [])

    def test_polygons_dict_mirror(self):
        """polygons (mm shapely Polygon) 도 미러 사본 생성됨."""
        l_coords = [(0, 0), (50, 0), (50, 50), (100, 50), (100, 100), (0, 100)]
        p = self._piece("LP", q=2, mirror=True, coords=l_coords)
        poly_in = Polygon(l_coords)
        polygons = {"LP": poly_in}

        out, out_polys, warns = _split_mirrored_pieces([p], polygons=polygons)

        self.assertIn("LP_orig", out_polys)
        self.assertIn("LP_M", out_polys)
        # 미러는 X 축 반사 (centroid 기준) — 면적은 보존
        self.assertAlmostEqual(out_polys["LP_orig"].area, out_polys["LP_M"].area, places=4)
        # 비대칭 polygon → 원본과 미러 좌표 다름
        coords_orig = list(out_polys["LP_orig"].exterior.coords)
        coords_mir = list(out_polys["LP_M"].exterior.coords)
        self.assertNotEqual(coords_orig, coords_mir)

    def test_quantity_total_preserved(self):
        """Mirror=True + Quantity=N (짝수): 분리 후 총 quantity 합이 N 으로 보존."""
        for q in [2, 4, 6, 8, 10]:
            p = self._piece(f"PE{q}", q=q, mirror=True)
            out, _, warns = _split_mirrored_pieces([p], polygons=None)
            total = sum(int(o["quantity"]) for o in out)
            self.assertEqual(total, q, f"quantity={q} 분리 후 합 다름")
            self.assertEqual(warns, [])


# ╔════════════════════════════════════════════════════════════╗
# ║ 회귀 안전 — 28 DXF 모두 mirror=None 시나리오 보장             ║
# ╚════════════════════════════════════════════════════════════╝
class TestRegressionSafety(unittest.TestCase):
    """기존 28(실제 29) DXF 는 모두 mirror 메타 부재 → mirror=None.
       이 경우 _split_mirrored_pieces 는 입력을 그대로 반환해야 함."""

    def test_all_none_mirror_passthrough(self):
        pieces = [
            {"piece_id": f"P{i:03d}", "quantity": q, "mirror": None,
             "coords_cm": [(0, 0), (10, 0), (10, 10), (0, 10)],
             "grain": {"angle_deg": 90.0, "kind": "STRAIGHT_GRAIN_Y",
                       "length_mm": 100.0, "raw_layer": "7"}}
            for i, q in enumerate([1, 1, 2, 2, 4, 5, 6])
        ]
        out, _, warns = _split_mirrored_pieces(pieces, polygons=None)
        self.assertEqual(len(out), len(pieces))
        for orig, new in zip(pieces, out):
            self.assertEqual(orig["piece_id"], new["piece_id"])
            self.assertEqual(orig["quantity"], new["quantity"])
        self.assertEqual(warns, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
