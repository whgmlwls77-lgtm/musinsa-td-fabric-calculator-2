# -*- coding: utf-8 -*-
"""
auto_nesting_v2.py
------------------
Phase 2: jagua-rs / sparrow 기반 polygon nesting (CLI subprocess wrapper).

[설계 원칙]
  1. 외부 sparrow 바이너리 호출 (bin/sparrow-{platform}-{arch}).
  2. JSON in / JSON+SVG out — REST API 불필요.
  3. 반환 dict 는 nest_grading_marker (Phase 1) 와 동일 키 구조 유지 →
     기존 nesting_results_section / visualize_marker 와 호환.
  4. sparrow 가 직접 SVG 도 생성 — svg_content 로 전달, UI 에서 직접 표시 가능.
  5. 시접은 jagua 의 min_item_separation 으로 처리 (Phase 1 의 ±2*seam bbox 확장과 의미 동일).

[Phase 1 대비 개선]
  - 평균 효율: 61.78% → 86.04% (5개 카테고리 평균, 2026-04-29 검증)
  - 본사 평균 효율 능가 (+2.05p)
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from shapely.geometry import Polygon as ShapelyPolygon

from mirror_pieces import mirror_piece_horizontally
from grain_extractor import get_alignment_rotation, rotate_polygon


# ╔════════════════════════════════════════════════════════════╗
# ║ 단위 환산 상수                                              ║
# ╚════════════════════════════════════════════════════════════╝
CM_TO_YD: float = 1.0 / 91.44     # 1 yd = 91.44 cm


# ╔════════════════════════════════════════════════════════════╗
# ║ 바이너리 자동 감지                                          ║
# ╚════════════════════════════════════════════════════════════╝
PROJECT_ROOT = Path(__file__).resolve().parent
BIN_DIR = PROJECT_ROOT / "bin"


def detect_sparrow_binary() -> Path:
    """
    현재 platform/arch 에 맞는 sparrow 바이너리 경로 반환.
    없으면 명확한 에러 메시지로 FileNotFoundError.
    """
    sysname = sys.platform  # "darwin", "linux", "win32"
    machine = platform.machine().lower()  # "arm64", "x86_64", "amd64"

    plat_map = {
        ("darwin", "arm64"):   "sparrow-darwin-arm64",
        ("darwin", "x86_64"):  "sparrow-darwin-x86_64",
        ("linux",  "x86_64"):  "sparrow-linux-x86_64",
        ("linux",  "amd64"):   "sparrow-linux-x86_64",
        ("linux",  "aarch64"): "sparrow-linux-aarch64",
    }
    fname = plat_map.get((sysname, machine))
    if fname is None:
        raise FileNotFoundError(
            f"지원하지 않는 platform/arch: {sysname}/{machine}. "
            f"bin/README.md 의 빌드 안내 참고."
        )

    binpath = BIN_DIR / fname
    if not binpath.exists():
        raise FileNotFoundError(
            f"sparrow 바이너리 없음: {binpath}\n"
            f"bin/README.md 의 빌드 안내 따라 재빌드 필요."
        )
    return binpath


# ╔════════════════════════════════════════════════════════════╗
# ║ pieces → jagua input.json 변환                              ║
# ╚════════════════════════════════════════════════════════════╝
def _normalize_polygon(coords: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], float, float]:
    """polygon 좌표를 (min_x=0, min_y=0) 으로 평행이동. (norm_coords, dx, dy) 반환."""
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    minx, miny = min(xs), min(ys)
    return [(x - minx, y - miny) for x, y in coords], minx, miny


def _align_pieces_to_grain(
    pieces: list[dict],
    polygons: dict | None = None,
) -> tuple[list[dict], dict]:
    """Phase 2 식서 사전 회전 (사장님 결정 2026-05-05).

    각 piece 의 grain.kind 에 따라 polygon 을 회전해 식서를 Y축으로 통일.
    sparrow 는 reflection / 임의 회전 처리하므로, 입력 단계에서 식서 정렬해두면
    grain_mode (1WAY/2WAY) 가 일관되게 적용된다.

    회전:
      STRAIGHT_GRAIN_X → 90°  (식서 X → Y)
      STRAIGHT_GRAIN_Y → 0°   (이미 Y, 회전 없음)
      BIAS / UNKNOWN / NONSTANDARD → 0°  (caller 가 추가 처리)

    Returns: (회전된 pieces, 회전된 polygons)

    근거: "식서 못 읽으면 요척 의미 없음" — 사장님 본질.
    """
    out_pieces: list[dict] = []
    out_polygons: dict = dict(polygons) if polygons else {}

    for p in pieces:
        rot = get_alignment_rotation(p.get("grain"))
        if rot == 0.0:
            out_pieces.append(p)
            continue

        new_p = dict(p)
        coords = p.get("coords_cm") or []
        if coords:
            new_p["coords_cm"] = rotate_polygon(coords, rot)
        # grain 메타 갱신 — 회전 후엔 모두 STRAIGHT_GRAIN_Y, 90°
        old_grain = p.get("grain") or {}
        new_p["grain"] = {**old_grain, "kind": "STRAIGHT_GRAIN_Y", "angle_deg": 90.0,
                          "_rotated_by": rot}

        # polygon (mm shapely) 도 동일 회전 적용
        pid = p.get("piece_id")
        if pid and polygons and pid in polygons:
            from shapely import affinity
            poly = polygons[pid]
            rotated = affinity.rotate(poly, rot, origin='centroid')
            # 양의 사분면으로 평행이동
            minx, miny, _, _ = rotated.bounds
            rotated = affinity.translate(rotated, -minx, -miny)
            out_polygons[pid] = rotated

        out_pieces.append(new_p)

    return out_pieces, out_polygons


def _filter_excluded_materials(pieces: list[dict]) -> tuple[list[dict], list[str]]:
    """Material=NON/NONE piece 를 마카 입력에서 제외 (사장님 결정 2026-05-05).

    StyleCAD "마커 제외 ✅" 시 갯수 0 이 DXF Quantity:1 로 강제 변환되어 직접 인식 불가
    → 우회: Material 값을 "NON" 으로 표기.

    인식 기준 (둘 중 하나):
      - material_inferred == "마카제외"  (infer_material_v3 결과 — 정상 파이프라인)
      - material_raw / material upper in {NON, NONE}  (raw DXF 코드 — fallback)

    Returns:
      (filtered_pieces, excluded_piece_ids)
    """
    filtered: list[dict] = []
    excluded: list[str] = []
    for p in pieces:
        raw_mat = (p.get("material_raw") or p.get("material") or "").strip().upper()
        inferred = (p.get("material_inferred") or "").strip()
        if inferred == "마카제외" or raw_mat in {"NON", "NONE"}:
            excluded.append(p.get("piece_id", ""))
            continue
        filtered.append(p)
    return filtered, excluded


def _expand_with_mirrors(pieces: list[dict], polygons: dict | None, mirror_each: bool) -> tuple[list[dict], dict, dict[str, int]]:
    """
    nest_grading_marker 와 동일한 미러 확장 로직.
    Returns:
      (expanded_pieces, expanded_polygons, mirror_count_per_piece)
    """
    expanded: list[dict] = []
    expanded_polygons: dict = {}
    mirror_count: dict[str, int] = {}

    for p in pieces:
        expanded.append(p)
        if polygons and p["piece_id"] in polygons:
            expanded_polygons[p["piece_id"]] = polygons[p["piece_id"]]

        if not mirror_each:
            mirror_count[p["piece_id"]] = 0
            continue

        kind = (p.get("grain") or {}).get("kind", "UNKNOWN")
        if kind == "BIAS":
            # Phase 1 과 동일 — BIAS 는 미러 안 함 (각도 부호 바뀌어야 정확).
            mirror_count[p["piece_id"]] = 0
            continue

        mp, mpoly = mirror_piece_horizontally(p, polygons.get(p["piece_id"]) if polygons else None)
        expanded.append(mp)
        mirror_count[p["piece_id"]] = 1
        if polygons is not None and mpoly is not None:
            expanded_polygons[mp["piece_id"]] = mpoly

    return expanded, expanded_polygons, mirror_count


_GRAIN_ANGLE_TOL: float = 10.0  # extract_grain 분류 허용 오차와 동일


def _reclassify_grain_kind(angle_deg: float) -> str:
    """미러된 각도를 grain_extractor.extract_grain 와 동일 규칙으로 재분류.

      0~10° / 170~180° → STRAIGHT_GRAIN_X
      80~100°          → STRAIGHT_GRAIN_Y
      35~55° / 125~145°→ BIAS
      그 외            → NONSTANDARD
    """
    a = float(angle_deg) % 180.0
    if a <= _GRAIN_ANGLE_TOL or a >= 180.0 - _GRAIN_ANGLE_TOL:
        return "STRAIGHT_GRAIN_X"
    if abs(a - 90.0) <= _GRAIN_ANGLE_TOL:
        return "STRAIGHT_GRAIN_Y"
    if abs(a - 45.0) <= _GRAIN_ANGLE_TOL or abs(a - 135.0) <= _GRAIN_ANGLE_TOL:
        return "BIAS"
    return "NONSTANDARD"


def mirror_grain_angle(angle_deg: float) -> float:
    """X축 반사 시 식서 각도 변환: (180 - θ) mod 180.

    유도: X 반사로 벡터 (Δx, Δy) → (-Δx, Δy).
        atan2(Δy, Δx) → atan2(Δy, -Δx) = π - θ (라디안) = 180° - θ.
        mod 180 으로 [0, 180) 정규화.

    예:   0 → 0,  30 → 150,  45 → 135,  90 → 90,  135 → 45,  170 → 10.
    """
    return (180.0 - float(angle_deg)) % 180.0


def _mirror_piece_horizontal(piece: dict) -> dict:
    """piece dict 의 X축 반사 사본 생성.

    변경:
      - coords_cm 를 (x, y) → (-x, y) 변환 후 (min_x=0, min_y=0) 으로 평행이동
      - grain.angle_deg = mirror_grain_angle(원본 각도)
      - grain.kind = 새 각도 기반 재분류
      - grain['mirrored'] = True (디버깅용 플래그)
      - piece_id 에 "_M" 접미사
      - mirrored_from = 원본 piece_id (역추적용)
      - bbox_cm / width_cm / height_cm 는 변하지 않음 (X 반사는 폭·높이 보존)
    """
    mirrored = dict(piece)

    coords = piece.get("coords_cm") or []
    if coords:
        rx = [(-x, y) for x, y in coords]
        mnx = min(c[0] for c in rx)
        mny = min(c[1] for c in rx)
        mirrored["coords_cm"] = [(x - mnx, y - mny) for x, y in rx]

    grain = piece.get("grain")
    if grain:
        old_ang = float(grain.get("angle_deg", 0.0) or 0.0)
        new_ang = mirror_grain_angle(old_ang)
        new_grain = dict(grain)
        new_grain["angle_deg"] = round(new_ang, 2)
        new_grain["kind"] = _reclassify_grain_kind(new_ang)
        new_grain["mirrored"] = True
        mirrored["grain"] = new_grain

    orig_pid = piece.get("piece_id", "")
    mirrored["piece_id"] = f"{orig_pid}_M"
    mirrored["mirrored_from"] = orig_pid
    return mirrored


def _split_mirrored_pieces(
    pieces: list[dict],
    polygons: dict | None,
) -> tuple[list[dict], dict, list[str]]:
    """Mirror=True piece 를 원본·미러 별도 piece 로 분리 (옵션 A).

    [정책 — 사장님 결정 2026-05-04, 갱신 2026-05-05]
      - mirror=True + quantity == 1:
          "1 pair" 의미 — 사용자가 1을 적었지만 실제로는 좌우 1쌍.
          원본 piece_id="{pid}_orig" quantity=1,
          미러 piece_id="{pid}_M"   quantity=1
          (StyleCAD PAIRED:DOUBLE + Quantity:1 케이스 — 2026-05-05 MMAPS003-test 검증)
      - mirror=True + quantity 짝수 (≥2):
          원본 piece_id="{pid}_orig" quantity=q/2,
          미러 piece_id="{pid}_M"   quantity=q/2
      - mirror=True + quantity 홀수 (≥3):
          ⚠️ 경고 + 원본 그대로 (미러 적용 skip — quantity 보존)
      - mirror=False / None:
          기존 동작 유지

    polygons (mm 단위 shapely Polygon) 도 미러 사본을 함께 생성:
      shapely.affinity.scale(p, xfact=-1, yfact=1, origin='centroid')

    Returns:
      (out_pieces, out_polygons, warnings)
    """
    from shapely.affinity import scale as _shp_scale

    out_pieces: list[dict] = []
    out_polygons: dict = dict(polygons) if polygons else {}
    warns: list[str] = []

    for p in pieces:
        is_mirror = (p.get("mirror") is True)
        q = int(p.get("quantity") or 1)
        pid = p.get("piece_id", "")

        if not is_mirror:
            out_pieces.append(p)
            continue

        # mirror=True 검증
        if q == 1:
            # "1 pair" 케이스 — 사용자가 1을 적었지만 PAIRED 로 좌우 페어 의미
            half = 1
        elif q < 1:
            warns.append(
                f"⚠️ piece {pid} mirror=True 인데 quantity={q} (잘못된 값). "
                f"미러 적용 skip — 원본 quantity 그대로."
            )
            out_pieces.append(p)
            continue
        elif q % 2 != 0:
            warns.append(
                f"⚠️ piece {pid} mirror=True 인데 quantity={q} (홀수, 1 제외). "
                f"미러 쌍 단위 위반 — 미러 적용 skip, 원본 quantity 그대로."
            )
            out_pieces.append(p)
            continue
        else:
            half = q // 2
        # 원본 사본 (piece_id 에 "_orig" 접미사) — 결과 분석 시 미러 짝과 구분용
        orig = dict(p)
        orig["piece_id"] = f"{pid}_orig"
        orig["quantity"] = half
        out_pieces.append(orig)
        if polygons and pid in polygons:
            out_polygons[orig["piece_id"]] = polygons[pid]

        # 미러 사본
        mp = _mirror_piece_horizontal(p)
        mp["quantity"] = half
        out_pieces.append(mp)
        if polygons and pid in polygons:
            try:
                mirrored_poly = _shp_scale(
                    polygons[pid], xfact=-1, yfact=1, origin='centroid',
                )
                out_polygons[mp["piece_id"]] = mirrored_poly
            except Exception as e:
                warns.append(
                    f"⚠️ piece {pid} polygon 미러 실패 ({e}) — coords_cm 만 미러 적용."
                )

    return out_pieces, out_polygons, warns


def _piece_to_jagua_item(piece: dict, item_id: int, grain_mode: str = "2WAY") -> dict:
    """
    하나의 piece 를 jagua-rs SPP 입력 item dict 로 변환.

    [사장님 정의 — 2026-04-30]
      1WAY = 식서 통일 (모든 piece 같은 방향) → allowed_orientations=[0.0]
      2WAY = 식서 + 식서 반대 교차 (180° 회전 허용) → allowed_orientations=[0.0, 180.0]

    BIAS piece 는 grain_mode 무관하게 [0.0] (사선 각도가 부호 바뀌면 안 됨).

    quantity 메타 그대로 demand 매핑 — DXF 명시값이 정답.
      quantity=1 → sparrow demand=1
      quantity=2 → sparrow demand=2 (같은 polygon 을 2개 배치)
    """
    coords = piece.get("coords_cm")
    if not coords or len(coords) < 3:
        return None

    norm, _dx, _dy = _normalize_polygon(coords)

    kind = (piece.get("grain") or {}).get("kind", "UNKNOWN")
    if kind == "BIAS":
        orientations = [0.0]
    elif grain_mode == "1WAY":
        orientations = [0.0]
    else:  # 2WAY (default)
        orientations = [0.0, 180.0]

    return {
        "id": item_id,
        "demand": int(piece.get("quantity") or 1),
        "allowed_orientations": orientations,
        "shape": {
            "type": "simple_polygon",
            "data": [[round(x, 4), round(y, 4)] for x, y in norm],
        },
    }


def pieces_to_jagua_input(
    pieces: list[dict],
    fabric_width_cm: float,
    name: str = "marker",
    grain_mode: str = "2WAY",
) -> tuple[dict, dict[int, str]]:
    """
    피스 리스트 → jagua-rs SPP input dict + (item_id → piece_id) 매핑 반환.
    grain_mode: 1WAY/2WAY (사장님 정의 — 식서 통일/교차).
    """
    items = []
    id_to_piece: dict[int, str] = {}
    for p in pieces:
        item_id = len(items)
        item = _piece_to_jagua_item(p, item_id, grain_mode=grain_mode)
        if item is None:
            continue
        items.append(item)
        id_to_piece[item_id] = p["piece_id"]

    return {
        "name": name,
        "items": items,
        "strip_height": float(fabric_width_cm),
    }, id_to_piece


# ╔════════════════════════════════════════════════════════════╗
# ║ sparrow 실행 + 결과 파싱                                    ║
# ╚════════════════════════════════════════════════════════════╝
def _run_sparrow(
    input_path: Path,
    work_dir: Path,
    runtime_seconds: int,
    early_termination: bool,
    seed: int | None = None,
) -> tuple[Path, Path, str]:
    """
    sparrow 바이너리 실행. (sol_json_path, sol_svg_path, stderr_text) 반환.
    sparrow 는 cwd/output/ 에 결과를 쓰므로 cwd 를 work_dir 로 지정.
    """
    sparrow = detect_sparrow_binary()

    cmd = [str(sparrow), "-i", str(input_path), "-t", str(int(runtime_seconds))]
    if early_termination:
        cmd.append("-x")
    if seed is not None:
        cmd.extend(["-s", str(int(seed))])

    # sparrow 출력 경로: cwd/output/final_{name}.json/.svg
    (work_dir / "output").mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=runtime_seconds + 30,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"sparrow timeout (>{runtime_seconds + 30}s): {e}")

    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").strip().split("\n")[-10:])
        raise RuntimeError(f"sparrow exit {result.returncode}\n--- stderr ---\n{tail}")

    # sparrow 가 만든 JSON / SVG 찾기 (output/final_*.json)
    out_dir = work_dir / "output"
    json_files = sorted(out_dir.glob("final_*.json"))
    svg_files = sorted(out_dir.glob("final_*.svg"))
    if not json_files:
        raise RuntimeError(f"sparrow 결과 JSON 없음 in {out_dir}")
    return json_files[0], (svg_files[0] if svg_files else None), result.stderr or ""


def _parse_sparrow_solution(
    sol_path: Path,
    id_to_piece: dict[int, str],
    pieces_by_id: dict[str, dict],
) -> dict:
    """
    sparrow 출력 JSON 파싱.
    Returns dict with placements (Phase 1 호환 키) + sparrow 고유 키.
    """
    sol = json.loads(sol_path.read_text())
    s = sol["solution"]
    layout = s["layout"]

    placements: list[dict] = []
    for it in layout["placed_items"]:
        item_id = it["item_id"]
        piece_id = id_to_piece.get(item_id)
        if piece_id is None:
            continue
        piece = pieces_by_id.get(piece_id, {})
        tr = it["transformation"]
        rot_deg = float(tr["rotation"])
        tx, ty = float(tr["translation"][0]), float(tr["translation"][1])
        kind = (piece.get("grain") or {}).get("kind", "UNKNOWN")

        # Phase 1 placements 와 호환: bbox_w_cm / bbox_h_cm 도 채워둠
        # 회전이 ±90/270이면 가로/세로 swap, 그 외(0/180/BIAS)는 그대로.
        w = float(piece.get("width_cm", 0.0))
        h = float(piece.get("height_cm", 0.0))
        r_mod = abs(rot_deg) % 180.0
        if abs(r_mod - 90.0) < 1.0:
            bw, bh = h, w
        else:
            bw, bh = w, h

        placements.append({
            "piece_id": piece_id,
            "piece_name": piece.get("piece_name", ""),
            "kind": kind,
            "x_cm": tx,
            "y_cm": ty,
            "bbox_w_cm": bw,
            "bbox_h_cm": bh,
            "rotation_applied_deg": rot_deg,
        })

    return {
        "placements": placements,
        "marker_length_cm": float(s["strip_width"]),  # SPP 에서 strip_width = 마카 길이
        "efficiency": float(s["density"]),
        "runtime_actual_sec": float(s.get("run_time_sec", 0.0)),
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ 공개 API: nest_pieces_sparrow                              ║
# ╚════════════════════════════════════════════════════════════╝
def nest_pieces_sparrow(
    pieces: list[dict],
    fabric_width_cm: float,
    runtime_seconds: int = 30,
    mirror_each: bool = False,  # DEPRECATED — 2026-04-30 절대 원칙: 좌우 자동 미러 폐기
    sizes_to_nest: list[str] | None = None,
    polygons: dict | None = None,
    seam_allowance_cm: float = 0.0,
    marker_mode: str = "2WAY",  # = grain_mode (1WAY/2WAY)
    grain_mode: str | None = None,  # 명시적 1WAY/2WAY (None 이면 marker_mode 사용)
    n_lay: int = 1,  # 사장님 정의 — 마카 벌수 (옷의 갯수)
    early_termination: bool = True,
    seed: int | None = None,
) -> dict:
    """
    Phase 2 자동 마카 배치 (sparrow CLI wrapper).

    [사장님 절대 원칙 — 2026-04-30]
      1) 좌우 자동 미러 폐기 — DXF Quantity 메타 그대로 사용
      2) 1WAY = 식서 통일, 2WAY = 식서 + 식서 반대 교차
      3) 마카 갯수 = Σ(piece.quantity) × n_lay

    Args:
      pieces: parse_dxf_v3 결과. coords_cm 필드 필수.
      fabric_width_cm: 원단 폭 (cm).
      runtime_seconds: sparrow 실행 시간 (10-120 권장, 기본 30).
      n_lay: 마카 벌수 (default 1).
      grain_mode: "1WAY" 또는 "2WAY" (default 2WAY).
      mirror_each: DEPRECATED. 무시됨. 호출자 호환을 위해 매개변수 유지.
      sizes_to_nest: 사이즈 필터. None 이면 모든 사이즈.
      polygons: {piece_id: shapely.Polygon} (mm 단위). 시각화용. 미러 폴리곤 자동 생성.
      seam_allowance_cm: 시접 (cm). polygon buffer 대신 jagua 의 min_item_separation 으로 처리.
      marker_mode: 메타 정보로만 보존 (sparrow 는 allowed_orientations 로 자동 처리).
      early_termination: -x 옵션 (수렴 시 조기 종료).
      seed: 재현용 RNG 시드.

    Returns:
      Phase 1 nest_grading_marker 와 동일 키 + 추가 sparrow 키:
        engine                    : "sparrow"
        placements                : Phase 1 호환 (piece_id, x_cm, y_cm, bbox_w/h_cm, kind, rotation_applied_deg)
        marker_length_cm          : float
        efficiency                : float (0~1)
        unplaced                  : list[piece_id]
        warnings                  : list[str]
        fabric_width_cm           : float
        marker_mode               : str
        sizes_included            : list[str]
        mirror_count_per_piece    : {piece_id: 0|1}
        pieces_used               : 확장된 piece dict list
        polygons                  : 확장된 polygon dict (입력 polygons 있을 때)
        # 추가:
        runtime_seconds_requested : int  (요청한 -t 값)
        runtime_actual_sec        : float (실제 종료 시각)
        svg_content               : str  (sparrow 생성 SVG, 그대로 표시 가능)
    """
    warnings: list[str] = []

    # grain_mode 결정 (명시 우선)
    effective_grain_mode = (grain_mode or marker_mode or "2WAY").upper()
    if effective_grain_mode not in ("1WAY", "2WAY"):
        effective_grain_mode = "2WAY"

    # 0) Material=NON 마카 제외 필터 (사장님 결정 2026-05-05)
    pieces, excluded_pieces = _filter_excluded_materials(pieces)

    # 0.5) Phase 2 식서 사전 회전 (사장님 결정 2026-05-05)
    #      "식서 못 읽으면 요척 의미 없음"
    pieces, polygons_aligned = _align_pieces_to_grain(pieces, polygons)
    polygons = polygons_aligned if polygons is not None else None

    # 1) 사이즈 필터
    filtered = pieces
    if sizes_to_nest is not None:
        filtered = [p for p in pieces if p.get("size") in sizes_to_nest]
        if not filtered:
            return {
                "engine": "sparrow",
                "error": f"sizes_to_nest={sizes_to_nest} 매칭 피스 없음",
                "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
                "unplaced": [], "warnings": warnings,
                "fabric_width_cm": fabric_width_cm, "marker_mode": effective_grain_mode,
                "sizes_included": list(sizes_to_nest), "mirror_count_per_piece": {},
                "pieces_used": [], "polygons": {} if polygons is not None else None,
                "runtime_seconds_requested": runtime_seconds,
                "runtime_actual_sec": 0.0, "svg_content": "",
                "excluded_pieces": excluded_pieces,
            }

    # 2) [폐기됨] 좌우 자동 미러 — quantity 메타 그대로 사용 (절대 원칙).
    #    backwards compat: mirror_each=True 호출자에게는 무시됨 + 경고만.
    if mirror_each:
        warnings.append(
            "⚠️ mirror_each=True 호출됨. 2026-04-30 절대 원칙으로 좌우 자동 미러는 폐기 — "
            "DXF Quantity 메타 그대로 사용. mirror_each 매개변수는 무시됩니다."
        )
    expanded_pieces = list(filtered)
    expanded_polygons = {p["piece_id"]: polygons[p["piece_id"]]
                        for p in filtered if polygons and p["piece_id"] in polygons} if polygons else {}
    mirror_count: dict[str, int] = {p["piece_id"]: 0 for p in expanded_pieces}
    pieces_by_id = {p["piece_id"]: p for p in expanded_pieces}

    # 2.5) Mirror 처리 (옵션 A — 사장님 결정 2026-05-04, 순서 갱신 2026-05-05)
    #      mirror=True piece 를 원본·미러 별도 piece 로 분리해 sparrow 에 전달.
    #      sparrow 는 reflection 미지원이므로 우리 코드가 미러 polygon 생성.
    #      n_lay 곱셈 BEFORE mirror split 이면 Q=1 paired 가 Q=N 으로 부풀려진 뒤
    #      "Q/2 + Q/2" 짝수 정책 잘못 적용 → 실제 placements 가 절반으로 떨어짐.
    #      → mirror split 먼저, n_lay 곱셈 나중 (사장님 raw 92 일치 검증).
    expanded_pieces, expanded_polygons, mirror_warns = _split_mirrored_pieces(
        expanded_pieces,
        expanded_polygons if polygons is not None else None,
    )
    if mirror_warns:
        warnings.extend(mirror_warns)
    pieces_by_id = {p["piece_id"]: p for p in expanded_pieces}
    # mirror_count_per_piece 갱신 — "_M" 접미사 가진 piece 가 미러 사본
    mirror_count = {
        p["piece_id"]: (1 if p["piece_id"].endswith("_M") else 0)
        for p in expanded_pieces
    }

    # n_lay 적용 — quantity × n_lay = 실제 마카 demand (mirror split 이후)
    if n_lay > 1:
        # 새 piece dict 만들어 quantity 곱셈
        nlay_pieces = []
        for p in expanded_pieces:
            q = int(p.get("quantity") or 1)
            new_p = dict(p)
            new_p["quantity"] = q * n_lay
            nlay_pieces.append(new_p)
        expanded_pieces = nlay_pieces
        pieces_by_id = {p["piece_id"]: p for p in expanded_pieces}

    # 3) jagua input 변환 + 매핑 (grain_mode 적용)
    inp, id_to_piece = pieces_to_jagua_input(
        expanded_pieces, fabric_width_cm, name="marker",
        grain_mode=effective_grain_mode,
    )
    if not inp["items"]:
        return {
            "engine": "sparrow",
            "error": "변환 가능한 polygon 피스 없음 (coords_cm 누락)",
            "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
            "unplaced": [], "warnings": warnings,
            "fabric_width_cm": fabric_width_cm, "marker_mode": effective_grain_mode,
            "sizes_included": list(sizes_to_nest) if sizes_to_nest else [],
            "mirror_count_per_piece": mirror_count,
            "pieces_used": expanded_pieces,
            "polygons": expanded_polygons if polygons is not None else None,
            "runtime_seconds_requested": runtime_seconds,
            "runtime_actual_sec": 0.0, "svg_content": "",
            "excluded_pieces": excluded_pieces,
        }

    # 4) tempfile 작업 디렉토리
    with tempfile.TemporaryDirectory(prefix="sparrow_run_") as tmp_str:
        work_dir = Path(tmp_str)
        input_path = work_dir / "input.json"
        input_path.write_text(json.dumps(inp))

        # config — 시접을 min_item_separation 으로 처리 (cm 단위)
        if seam_allowance_cm and seam_allowance_cm > 0:
            config = {
                "cde_config": {
                    "quadtree_depth": 5,
                    "cd_threshold": 16,
                    "item_surrogate_config": {
                        "n_pole_limits": [[100, 0.0], [20, 0.75], [10, 0.90]],
                        "n_ff_poles": 2,
                        "n_ff_piers": 0,
                    },
                },
                "poly_simpl_tolerance": 0.001,
                "min_item_separation": float(seam_allowance_cm) * 2.0,
                "prng_seed": None,
                "n_samples": 5000,
                "ls_frac": 0.2,
            }
            config_path = work_dir / "config.json"
            config_path.write_text(json.dumps(config))
            # NOTE: sparrow 는 jagua-rs config 와 다른 옵션을 가질 수 있음.
            # min_item_separation 미반영 시 polygon buffer fallback 추가 가능 (TODO).
        # else: sparrow 기본 config 사용

        # 5) sparrow 실행
        try:
            sol_path, svg_path, stderr_text = _run_sparrow(
                input_path, work_dir, runtime_seconds, early_termination, seed,
            )
        except (FileNotFoundError, RuntimeError) as e:
            return {
                "engine": "sparrow",
                "error": f"sparrow 실행 실패: {e}",
                "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
                "unplaced": [p["piece_id"] for p in expanded_pieces],
                "warnings": warnings,
                "fabric_width_cm": fabric_width_cm, "marker_mode": effective_grain_mode,
                "sizes_included": list(sizes_to_nest) if sizes_to_nest else [],
                "mirror_count_per_piece": mirror_count,
                "pieces_used": expanded_pieces,
                "polygons": expanded_polygons if polygons is not None else None,
                "runtime_seconds_requested": runtime_seconds,
                "runtime_actual_sec": 0.0, "svg_content": "",
                "excluded_pieces": excluded_pieces,
            }

        # 6) 결과 파싱 + SVG 읽기
        parsed = _parse_sparrow_solution(sol_path, id_to_piece, pieces_by_id)
        svg_content = svg_path.read_text() if svg_path and svg_path.exists() else ""

    # 7) 미배치 피스 = 입력 piece_id 중 placements 에 안 나타난 것
    placed_pids = {pl["piece_id"] for pl in parsed["placements"]}
    unplaced = [p["piece_id"] for p in expanded_pieces if p["piece_id"] not in placed_pids]
    if unplaced:
        warnings.append(f"sparrow 배치 실패 피스 {len(unplaced)}개: {', '.join(unplaced[:5])}{'...' if len(unplaced) > 5 else ''}")

    return {
        "engine": "sparrow",
        "placements": parsed["placements"],
        "marker_length_cm": parsed["marker_length_cm"],
        "efficiency": parsed["efficiency"],
        "unplaced": unplaced,
        "warnings": warnings,
        "fabric_width_cm": fabric_width_cm,
        "marker_mode": effective_grain_mode,
        "sizes_included": list(sizes_to_nest) if sizes_to_nest else sorted({p.get("size", "") for p in expanded_pieces}),
        "mirror_count_per_piece": mirror_count,
        "pieces_used": expanded_pieces,
        "polygons": expanded_polygons if polygons is not None else None,
        "runtime_seconds_requested": runtime_seconds,
        "runtime_actual_sec": parsed["runtime_actual_sec"],
        "svg_content": svg_content,
        "excluded_pieces": excluded_pieces,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ 그레이딩 호환 별칭 (Phase 1 nest_grading_marker 와 동일 시그니처) ║
# ╚════════════════════════════════════════════════════════════╝
def nest_grading_marker_sparrow(
    pieces: list[dict],
    sizes_to_nest: list[str],
    fabric_width_cm: float,
    polygons: dict | None = None,
    mirror_each: bool = True,
    marker_mode: str = "2WAY",
    seam_allowance_cm: float = 0.0,
    runtime_seconds: int = 30,
    early_termination: bool = True,
    seed: int | None = None,
) -> dict:
    """Phase 1 nest_grading_marker 와 동일 시그니처 — drop-in 대체용."""
    return nest_pieces_sparrow(
        pieces=pieces,
        fabric_width_cm=fabric_width_cm,
        runtime_seconds=runtime_seconds,
        mirror_each=mirror_each,
        sizes_to_nest=sizes_to_nest,
        polygons=polygons,
        seam_allowance_cm=seam_allowance_cm,
        marker_mode=marker_mode,
        early_termination=early_termination,
        seed=seed,
    )


# ╔════════════════════════════════════════════════════════════╗
# ║ SVG 라벨 한글화                                             ║
# ╚════════════════════════════════════════════════════════════╝
# sparrow 의 SVG 라벨은 한 줄 monospace:
#   "h: 144.780 | w: 140.695 | d: 88.411% | final_<name>"
# 의류 소싱 사용자에겐 의미 불명 → 한글로 치환.

# 정규식: "h: 숫자 | w: 숫자 | d: 숫자% | final_..."
_SVG_LABEL_RE = re.compile(
    r"h:\s*([\d.]+)\s*\|\s*w:\s*([\d.]+)\s*\|\s*d:\s*([\d.]+)%\s*\|\s*final_[^\s<]+"
)


def humanize_svg_labels(svg_content: str) -> str:
    """sparrow SVG 의 영문 라벨을 한글 + 의류 단위(yd) 로 치환.

    h(strip_height) = 원단 폭, w(strip_width) = 마카 길이, d = 효율.
    final_<name> 부분 제거.
    """
    if not svg_content:
        return svg_content

    def _replace(m: re.Match) -> str:
        h = float(m.group(1))
        w = float(m.group(2))
        d = float(m.group(3))
        w_yd = w * CM_TO_YD
        return (
            f"원단 폭: {h:.1f} cm   |   "
            f"마카 길이: {w:.1f} cm ({w_yd:.2f} yd)   |   "
            f"효율: {d:.1f}%"
        )

    return _SVG_LABEL_RE.sub(_replace, svg_content)


# ╔════════════════════════════════════════════════════════════╗
# ║ SVG 후처리: 식서 화살표 + 축 라벨 (Bug 2/4 — 2026-05-01)    ║
# ║                                                              ║
# ║ sparrow SVG 좌표계:                                           ║
# ║   X축 (가로) = strip_width   = 마카 길이 (= 원단 길이방향)    ║
# ║   Y축 (세로) = strip_height  = 원단 폭                        ║
# ║                                                              ║
# ║ 식서 컨벤션 (DXF 기준):                                       ║
# ║   STRAIGHT_GRAIN_X → piece 의 X축 = 식서 (회전 0°/180°)       ║
# ║   STRAIGHT_GRAIN_Y → piece 의 Y축 = 식서 (회전 0°/180°)       ║
# ║   BIAS              → 사선 식서 (45°/135°, 회전 0° 만)        ║
# ║                                                              ║
# ║ 마카 위에 그릴 화살표 방향:                                   ║
# ║   piece grain.kind + rotation_applied_deg 조합으로 결정.     ║
# ║   본사 마카와 직접 비교 가능하도록 piece 위에 화살표 표시.    ║
# ╚════════════════════════════════════════════════════════════╝
_SVG_VIEWBOX_RE = re.compile(r'viewBox="([\-0-9.]+)\s+([\-0-9.]+)\s+([\-0-9.]+)\s+([\-0-9.]+)"')


def _piece_grain_arrow_direction(grain_kind: str, rotation_deg: float) -> tuple[float, float] | None:
    """
    piece 의 grain.kind 와 sparrow 가 적용한 회전을 보고 식서 화살표 단위벡터(dx, dy) 반환.

    SVG 좌표계 (Y축이 sparrow 와 동일하게 위→아래로 증가하는 SVG 표준).

    원본 piece 좌표계에서:
      STRAIGHT_GRAIN_X → 식서 = (1, 0)  (피스 X축 양의 방향)
      STRAIGHT_GRAIN_Y → 식서 = (0, 1)
      BIAS             → 식서 = (1, 1)/sqrt(2) (45°)

    sparrow 회전(0°/180°)이 적용되면 단위벡터를 같이 회전.
    식서는 양방향 — 부호 반전(180°)도 같은 식서 방향으로 간주.
    """
    import math
    base = {
        "STRAIGHT_GRAIN_X": (1.0, 0.0),
        "STRAIGHT_GRAIN_Y": (0.0, 1.0),
        "BIAS":             (math.cos(math.radians(45)), math.sin(math.radians(45))),
    }.get(grain_kind)
    if base is None:
        return None
    bx, by = base
    rad = math.radians(rotation_deg)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    return (bx * cos_r - by * sin_r, bx * sin_r + by * cos_r)


def _svg_arrow_marker_def() -> str:
    """SVG defs 에 들어갈 화살촉 marker 정의."""
    return (
        '<defs>'
        '<marker id="grain_arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerUnits="userSpaceOnUse" markerWidth="3" markerHeight="3" orient="auto">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#cc0000"/>'
        '</marker>'
        '</defs>'
    )


def add_grain_arrows_to_svg(
    svg_content: str,
    placements: list[dict],
    arrow_color: str = "#cc0000",
    arrow_width: float = 0.4,
) -> str:
    """
    sparrow SVG 에 piece 별 식서 화살표 추가.

    placements 의 각 항목에서:
      - x_cm, y_cm           : piece 좌하단 (sparrow translation)
      - bbox_w_cm, bbox_h_cm : 회전 후 bbox
      - kind                 : grain.kind (STRAIGHT_GRAIN_X/Y, BIAS, ...)
      - rotation_applied_deg : sparrow 가 적용한 회전 (0/180)

    각 piece 중심(cx, cy)에 식서 방향 단위벡터로 길이 = bbox 짧은변의 40% 짜리
    화살표를 그림. SVG </svg> 직전에 <g id="grain_arrows"> 삽입.

    절대 원칙: piece grain 정보가 없으면 화살표 X (추측 X). UNKNOWN/None 은 skip.
    """
    if not svg_content or not placements:
        return svg_content

    arrow_lines: list[str] = []
    arrow_lines.append('<g id="grain_arrows" style="pointer-events:none">')

    for pl in placements:
        kind = pl.get("kind", "UNKNOWN")
        if kind in ("UNKNOWN", "NONSTANDARD", None, ""):
            continue
        x = float(pl.get("x_cm", 0.0))
        y = float(pl.get("y_cm", 0.0))
        bw = float(pl.get("bbox_w_cm", 0.0))
        bh = float(pl.get("bbox_h_cm", 0.0))
        rot = float(pl.get("rotation_applied_deg", 0.0))

        if bw <= 0 or bh <= 0:
            continue

        cx = x + bw / 2.0
        cy = y + bh / 2.0

        direction = _piece_grain_arrow_direction(kind, rot)
        if direction is None:
            continue
        dx, dy = direction

        # 화살표 길이 = bbox 짧은변의 40% (피스 안에 들어가도록)
        arrow_len = min(bw, bh) * 0.4
        if arrow_len < 0.5:  # 너무 짧으면 스킵 (가독성)
            continue

        # 화살표 양 끝
        x1 = cx - dx * arrow_len / 2.0
        y1 = cy - dy * arrow_len / 2.0
        x2 = cx + dx * arrow_len / 2.0
        y2 = cy + dy * arrow_len / 2.0

        arrow_lines.append(
            f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
            f'stroke="{arrow_color}" stroke-width="{arrow_width}" '
            f'marker-end="url(#grain_arrow)" stroke-linecap="round"/>'
        )

    arrow_lines.append('</g>')
    arrows_block = "\n".join(arrow_lines)

    # 화살촉 marker 정의를 svg 시작 직후에 한 번만 삽입.
    if "id=\"grain_arrow\"" not in svg_content:
        marker_def = _svg_arrow_marker_def()
        # 첫 <svg ...> 태그 닫힘 직후 삽입.
        svg_content = re.sub(
            r"(<svg[^>]*>)",
            r"\1\n" + marker_def,
            svg_content,
            count=1,
        )

    # </svg> 직전 화살표 그룹 삽입.
    return svg_content.replace("</svg>", arrows_block + "\n</svg>")


def add_axis_labels_to_svg(
    svg_content: str,
    fabric_width_cm: float,
    marker_length_cm: float,
) -> str:
    """
    SVG 컨테이너 외곽에 축 라벨 + 화살표 추가.

    sparrow 좌표계 기준:
      가로축 (X)  = 마카 길이 = 원단 길이방향 (= 식서 방향)
      세로축 (Y)  = 원단 폭

    사장님 명시 (2026-05-01 Bug 4):
      - 가로축 라벨: "원단 길이방향 (식서) {marker_length}cm" + 화살표
      - 세로축 라벨: "원단 폭 {fabric_width}cm" + 화살표

    viewBox 를 확장해 라벨 영역 확보.
    """
    if not svg_content:
        return svg_content

    m = _SVG_VIEWBOX_RE.search(svg_content)
    if not m:
        return svg_content

    vb_x, vb_y, vb_w, vb_h = map(float, m.groups())

    # 폰트 크기 — viewBox 비율 기반 (마카 길이의 3% 정도가 적당).
    fs = max(2.5, marker_length_cm * 0.025)
    pad = fs * 1.6  # 라벨 영역 padding

    # 새 viewBox: 좌측·하단·상단 확장
    new_x = vb_x - pad * 1.5
    new_y = vb_y - pad * 1.2
    new_w = vb_w + pad * 1.5 + pad * 0.5
    new_h = vb_h + pad * 1.2 + pad * 1.6

    new_viewbox = f'viewBox="{new_x:.3f} {new_y:.3f} {new_w:.3f} {new_h:.3f}"'
    svg_content = _SVG_VIEWBOX_RE.sub(new_viewbox, svg_content, count=1)

    # 가로축 라벨 (마카 아래) — 컨테이너 0~marker_length_cm
    # 세로축 라벨 (마카 왼쪽) — 컨테이너 0~fabric_width_cm
    width_yd = marker_length_cm * CM_TO_YD

    axis_color = "#0f172a"
    arrow_color = "#0f172a"
    arrow_w = max(0.15, fs * 0.06)

    # 가로 화살표: 마카 아래 위치
    h_arrow_y = vb_y + vb_h + pad * 0.4
    h_arrow_x_start = 0.0
    h_arrow_x_end = marker_length_cm
    # 세로 화살표: 마카 왼쪽
    v_arrow_x = vb_x - pad * 0.4
    v_arrow_y_start = 0.0
    v_arrow_y_end = fabric_width_cm

    # 라벨 텍스트
    label_h = (
        f"← 원단 길이방향 (식서) → "
        f"{marker_length_cm:.1f} cm  ({width_yd:.2f} yd)"
    )
    label_v = f"← 원단 폭 → {fabric_width_cm:.1f} cm"

    # 화살촉 marker (검정) - id 충돌 방지.
    if "id=\"axis_arrow\"" not in svg_content:
        axis_marker = (
            '<defs>'
            '<marker id="axis_arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerUnits="userSpaceOnUse" markerWidth="3" markerHeight="3" orient="auto">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{arrow_color}"/>'
            '</marker>'
            '<marker id="axis_arrow_back" viewBox="0 0 10 10" refX="1" refY="5" '
            'markerUnits="userSpaceOnUse" markerWidth="3" markerHeight="3" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{arrow_color}"/>'
            '</marker>'
            '</defs>'
        )
        svg_content = re.sub(
            r"(<svg[^>]*>)",
            r"\1\n" + axis_marker,
            svg_content,
            count=1,
        )

    axis_block = (
        f'<g id="axis_labels" style="pointer-events:none">'
        # 가로 (X) 화살표 + 라벨
        f'<line x1="{h_arrow_x_start:.3f}" y1="{h_arrow_y:.3f}" '
        f'x2="{h_arrow_x_end:.3f}" y2="{h_arrow_y:.3f}" '
        f'stroke="{arrow_color}" stroke-width="{arrow_w}" '
        f'marker-end="url(#axis_arrow)" marker-start="url(#axis_arrow_back)"/>'
        f'<text x="{(h_arrow_x_start + h_arrow_x_end) / 2:.3f}" '
        f'y="{h_arrow_y + fs * 1.1:.3f}" '
        f'fill="{axis_color}" font-size="{fs:.2f}" '
        f'text-anchor="middle" font-family="sans-serif">{label_h}</text>'
        # 세로 (Y) 화살표 + 라벨 (90° 회전 텍스트)
        f'<line x1="{v_arrow_x:.3f}" y1="{v_arrow_y_start:.3f}" '
        f'x2="{v_arrow_x:.3f}" y2="{v_arrow_y_end:.3f}" '
        f'stroke="{arrow_color}" stroke-width="{arrow_w}" '
        f'marker-end="url(#axis_arrow)" marker-start="url(#axis_arrow_back)"/>'
        f'<text x="{v_arrow_x - fs * 0.3:.3f}" '
        f'y="{(v_arrow_y_start + v_arrow_y_end) / 2:.3f}" '
        f'fill="{axis_color}" font-size="{fs:.2f}" '
        f'text-anchor="middle" font-family="sans-serif" '
        f'transform="rotate(-90 {v_arrow_x - fs * 0.3:.3f} {(v_arrow_y_start + v_arrow_y_end) / 2:.3f})">'
        f'{label_v}</text>'
        f'</g>'
    )

    return svg_content.replace("</svg>", axis_block + "\n</svg>")


def annotate_marker_svg(
    svg_content: str,
    placements: list[dict] | None = None,
    fabric_width_cm: float | None = None,
    marker_length_cm: float | None = None,
) -> str:
    """
    sparrow SVG 에 식서 화살표 + 축 라벨 일괄 추가 (Bug 2/4 통합 후처리).
    각 인자 None 이면 해당 후처리 skip.
    """
    if not svg_content:
        return svg_content
    if placements:
        svg_content = add_grain_arrows_to_svg(svg_content, placements)
    if fabric_width_cm is not None and marker_length_cm is not None:
        svg_content = add_axis_labels_to_svg(
            svg_content, fabric_width_cm, marker_length_cm,
        )
    return svg_content


# ╔════════════════════════════════════════════════════════════╗
# ║ 재질별 nesting (소싱팀용 일직선 흐름)                       ║
# ╚════════════════════════════════════════════════════════════╝
def _piece_pretty_name(p: dict) -> str:
    """피스명 안전 추출 — 비어있으면 piece_id 로 fallback."""
    return (p.get("piece_name") or p.get("piece_id") or "?").strip()


def group_pieces_by_material(pieces: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """
    pieces 를 material_inferred 기준으로 그룹핑.
    Returns:
      (groups, unclassified_warnings)
        groups               : {재질명: [piece dict, ...]}  (입력 순서 보존)
        unclassified_warnings : [{piece_id, piece_name, raw_material}] — material_inferred 가 비었거나 알 수 없는 경우
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    unclassified: list[dict] = []
    for p in pieces:
        mat = (p.get("material_inferred") or "").strip()
        if not mat:
            unclassified.append({
                "piece_id": p.get("piece_id", "?"),
                "piece_name": _piece_pretty_name(p),
                "raw_material": p.get("material_raw", ""),
            })
            # 미분류라도 "주원단" 으로 폴백해 nesting 은 진행 (사용자 결정 보류).
            groups["주원단"].append(p)
            continue
        groups[mat].append(p)
    return dict(groups), unclassified


def nest_by_material(
    pieces: list[dict],
    fabric_widths_per_material: dict[str, float],
    sizes_to_nest: list[str] | None = None,
    polygons: dict | None = None,
    mirror_each: bool = False,  # DEPRECATED — 2026-04-30 폐기
    grain_mode: str = "2WAY",
    n_lay: int = 1,
    runtime_seconds: int = 30,
    early_termination: bool = True,
    seed: int | None = None,
    progress_callback=None,
) -> dict:
    """
    재질별로 별도 마카를 만들어 sparrow 로 nesting.

    Args:
      pieces                    : parse_dxf_v3 결과 (material_inferred 필수).
      fabric_widths_per_material : {재질명: cm} — 각 재질의 원단 폭.
      sizes_to_nest             : 사이즈 필터 (None=전부).
      polygons                  : {piece_id: shapely.Polygon} (시각화용).
      mirror_each               : 좌우 미러 자동.
      runtime_seconds           : 재질당 sparrow 실행 시간.
      progress_callback         : (current_index, total, material_name) -> None
                                  streamlit st.progress 같이 진행 표시용.

    Returns:
      {
        "by_material": {
          재질명: nest_pieces_sparrow 결과 dict (humanize 된 svg_content_humanized 포함),
          ...
        },
        "unclassified_warnings": [...],
        "summary_rows": [
          {material, fabric_width_cm, marker_length_cm, marker_length_yd,
           pieces_count, mirror_count, efficiency_pct, runtime_actual_sec}, ...
        ],
        "total_runtime_sec": float,
      }
    """
    # 0) Material=NON 마카 제외 필터 (사장님 결정 2026-05-05)
    pieces, excluded_pieces = _filter_excluded_materials(pieces)

    # 1) 사이즈 필터
    filtered = pieces
    if sizes_to_nest is not None:
        filtered = [p for p in pieces if p.get("size") in sizes_to_nest]

    # 2) 재질별 그룹핑
    groups, unclassified = group_pieces_by_material(filtered)

    # 3) 각 재질별 sparrow 호출
    by_material: dict[str, dict] = {}
    summary_rows: list[dict] = []
    total_rt = 0.0

    # 표시 순서: 표준 재질 우선
    standard_order = ["주원단", "심지", "안감", "배색", "포켓팅"]
    materials_ordered = [m for m in standard_order if m in groups]
    materials_ordered += sorted(m for m in groups if m not in standard_order)

    total = len(materials_ordered)
    for idx, mat in enumerate(materials_ordered, start=1):
        if progress_callback:
            try: progress_callback(idx, total, mat)
            except Exception: pass

        mat_pieces = groups[mat]
        width = float(fabric_widths_per_material.get(mat, 144.0))

        # polygons 도 이 재질 피스만 슬라이스
        mat_polygons = None
        if polygons is not None:
            mat_polygons = {
                p["piece_id"]: polygons[p["piece_id"]]
                for p in mat_pieces
                if p["piece_id"] in polygons
            }

        try:
            res = nest_pieces_sparrow(
                pieces=mat_pieces,
                fabric_width_cm=width,
                runtime_seconds=runtime_seconds,
                mirror_each=False,  # 폐기됨
                grain_mode=grain_mode,
                n_lay=n_lay,
                sizes_to_nest=None,  # 위에서 이미 필터됨
                polygons=mat_polygons,
                seam_allowance_cm=0.0,
                marker_mode=grain_mode,  # backwards compat
                early_termination=early_termination,
                seed=seed,
            )
        except Exception as e:
            res = {
                "engine": "sparrow",
                "error": f"sparrow 호출 실패: {e}",
                "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
                "unplaced": [p["piece_id"] for p in mat_pieces],
                "warnings": [], "fabric_width_cm": width,
                "marker_mode": "2WAY",
                "sizes_included": list(sizes_to_nest) if sizes_to_nest else [],
                "mirror_count_per_piece": {}, "pieces_used": mat_pieces,
                "polygons": mat_polygons or {},
                "runtime_seconds_requested": runtime_seconds,
                "runtime_actual_sec": 0.0, "svg_content": "",
            }

        # SVG 한글화 + 식서 화살표 + 축 라벨 (Bug 2/4 — 2026-05-01)
        humanized = humanize_svg_labels(res.get("svg_content", ""))
        res["svg_content_humanized"] = annotate_marker_svg(
            humanized,
            placements=res.get("placements"),
            fabric_width_cm=res.get("fabric_width_cm"),
            marker_length_cm=res.get("marker_length_cm"),
        )

        by_material[mat] = res
        total_rt += res.get("runtime_actual_sec", 0.0)

        marker_cm = res.get("marker_length_cm", 0.0)
        n_mirror = sum(1 for v in res.get("mirror_count_per_piece", {}).values() if v == 1)
        summary_rows.append({
            "material": mat,
            "fabric_width_cm": width,
            "marker_length_cm": marker_cm,
            "marker_length_yd": marker_cm * CM_TO_YD,
            "pieces_count": len(mat_pieces),
            "mirror_count": n_mirror,
            "efficiency_pct": res.get("efficiency", 0.0) * 100,
            "runtime_actual_sec": res.get("runtime_actual_sec", 0.0),
            "has_error": bool(res.get("error")),
        })

    return {
        "by_material": by_material,
        "unclassified_warnings": unclassified,
        "summary_rows": summary_rows,
        "total_runtime_sec": total_rt,
        "materials_ordered": materials_ordered,
        "excluded_pieces": excluded_pieces,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ Multi-size 그레이딩 마카 (본사 표준 — 사이즈비율)            ║
# ╚════════════════════════════════════════════════════════════╝
def _expand_pieces_by_ratio(
    pieces: list[dict],
    size_ratio: dict[str, int],
    polygons: dict | None,
    mirror_each: bool,
) -> tuple[list[dict], dict, dict[str, int]]:
    """
    각 사이즈별로 ratio 회수만큼 piece 복제 + (옵션) 좌우 미러.
    Returns: (expanded, expanded_polygons, mirror_count_per_origin)
    """
    expanded: list[dict] = []
    expanded_polygons: dict = {}
    mirror_count: dict[str, int] = {}

    for p in pieces:
        sz = p.get("size")
        if sz not in size_ratio:
            continue
        n = int(size_ratio[sz])
        if n <= 0:
            continue
        for k in range(n):
            # 복제 — piece_id 충돌 회피
            new_pid = f"{p['piece_id']}__{sz}_{k}"
            clone = dict(p)
            clone["piece_id"] = new_pid
            expanded.append(clone)
            mirror_count[new_pid] = 0
            if polygons and p["piece_id"] in polygons:
                expanded_polygons[new_pid] = polygons[p["piece_id"]]

            if mirror_each:
                kind = (p.get("grain") or {}).get("kind", "UNKNOWN")
                if kind != "BIAS":
                    mp, mpoly = mirror_piece_horizontally(
                        clone,
                        polygons.get(p["piece_id"]) if polygons else None,
                    )
                    expanded.append(mp)
                    mirror_count[new_pid] = 1
                    if expanded_polygons is not None and mpoly is not None:
                        expanded_polygons[mp["piece_id"]] = mpoly
    return expanded, expanded_polygons, mirror_count


def nest_pieces_sparrow_multisize(
    pieces: list[dict],
    fabric_width_cm: float,
    size_ratio: dict[str, int],
    runtime_seconds: int = 30,
    mirror_each: bool = False,  # DEPRECATED — 좌우 자동 미러 폐기
    grain_mode: str = "2WAY",
    polygons: dict | None = None,
    seam_allowance_cm: float = 0.0,
    early_termination: bool = True,
    seed: int | None = None,
) -> dict:
    """
    본사 표준 다중사이즈 마카.

    Args:
      pieces       : parse_dxf_v3 결과 (모든 사이즈 포함).
      size_ratio   : {"S": 1, "M": 2, "L": 2, "XL": 1, "XXL": 1} 같은 사이즈→벌수 dict
      polygons     : {piece_id: shapely.Polygon} (시각화용)

    Returns nest_pieces_sparrow 와 동일 키 + 추가:
      total_garments       : Σ size_ratio.values()
      yards_per_garment    : 1벌당 요척 (yd)
      cm_per_garment       : 1벌당 마카 길이 (cm)
      size_ratio           : 입력 그대로
    """
    total_garments = sum(int(v) for v in size_ratio.values() if v)

    # 0) Material=NON 마카 제외 필터 (사장님 결정 2026-05-05)
    pieces, excluded_pieces = _filter_excluded_materials(pieces)

    if total_garments <= 0:
        return {
            "engine": "sparrow",
            "error": f"size_ratio 합계가 0: {size_ratio}",
            "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
            "unplaced": [], "warnings": [], "fabric_width_cm": fabric_width_cm,
            "marker_mode": "2WAY",
            "size_ratio": size_ratio, "total_garments": 0,
            "yards_per_garment": 0.0, "cm_per_garment": 0.0,
            "sizes_included": list(size_ratio.keys()),
            "mirror_count_per_piece": {}, "pieces_used": [],
            "polygons": {} if polygons is not None else None,
            "runtime_seconds_requested": runtime_seconds,
            "runtime_actual_sec": 0.0, "svg_content": "",
            "svg_content_humanized": "",
            "excluded_pieces": excluded_pieces,
        }

    # 사이즈별 비율로 expansion — quantity 메타 사용 (좌우 자동 미러 폐기)
    expanded, expanded_polygons, mirror_count = _expand_pieces_by_ratio(
        pieces, size_ratio, polygons, mirror_each=False,  # 폐기됨
    )
    if not expanded:
        return {
            "engine": "sparrow",
            "error": f"size_ratio={size_ratio} 매칭 피스 없음",
            "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
            "unplaced": [], "warnings": [], "fabric_width_cm": fabric_width_cm,
            "marker_mode": "2WAY",
            "size_ratio": size_ratio, "total_garments": total_garments,
            "yards_per_garment": 0.0, "cm_per_garment": 0.0,
            "sizes_included": list(size_ratio.keys()),
            "mirror_count_per_piece": {}, "pieces_used": [],
            "polygons": {} if polygons is not None else None,
            "runtime_seconds_requested": runtime_seconds,
            "runtime_actual_sec": 0.0, "svg_content": "",
            "svg_content_humanized": "",
            "excluded_pieces": excluded_pieces,
        }

    # quantity 메타 그대로 + grain_mode 로 1WAY/2WAY 적용
    res = nest_pieces_sparrow(
        pieces=expanded,
        fabric_width_cm=fabric_width_cm,
        runtime_seconds=runtime_seconds,
        mirror_each=False,
        grain_mode=grain_mode,
        sizes_to_nest=None,
        polygons=expanded_polygons if polygons is not None else None,
        seam_allowance_cm=seam_allowance_cm,
        marker_mode=grain_mode,
        early_termination=early_termination,
        seed=seed,
    )

    # 1벌당 환산
    cm_total = res.get("marker_length_cm", 0.0)
    cm_per = cm_total / total_garments if total_garments > 0 else 0.0
    yd_per = cm_per * CM_TO_YD

    res["size_ratio"] = size_ratio
    res["total_garments"] = total_garments
    res["yards_per_garment"] = yd_per
    res["cm_per_garment"] = cm_per
    res["mirror_count_per_piece"] = mirror_count
    res["sizes_included"] = sorted(size_ratio.keys())
    # multisize 진입 단계에서 제외된 piece + nest_pieces_sparrow 안에서 제외된 piece 합집합 (중복 제거)
    res["excluded_pieces"] = sorted(set(res.get("excluded_pieces", []) + excluded_pieces))
    # SVG humanize + 식서 화살표 + 축 라벨 (Bug 2/4 — 2026-05-01)
    humanized = humanize_svg_labels(res.get("svg_content", ""))
    res["svg_content_humanized"] = annotate_marker_svg(
        humanized,
        placements=res.get("placements"),
        fabric_width_cm=res.get("fabric_width_cm"),
        marker_length_cm=res.get("marker_length_cm"),
    )

    return res


def nest_by_material_multisize(
    pieces: list[dict],
    fabric_widths_per_material: dict[str, float],
    size_ratio: dict[str, int],
    polygons: dict | None = None,
    mirror_each: bool = False,  # DEPRECATED
    grain_mode: str = "2WAY",
    runtime_seconds: int = 30,
    early_termination: bool = True,
    seed: int | None = None,
    progress_callback=None,
) -> dict:
    """
    재질별 multi-size 마카.
    nest_by_material 과 동일 시그니처에 size_ratio 추가.
    """
    # 0) Material=NON 마카 제외 필터 (사장님 결정 2026-05-05)
    pieces, excluded_pieces = _filter_excluded_materials(pieces)

    groups, unclassified = group_pieces_by_material(pieces)

    by_material: dict[str, dict] = {}
    summary_rows: list[dict] = []
    total_rt = 0.0
    standard_order = ["주원단", "심지", "안감", "배색", "포켓팅"]
    materials_ordered = [m for m in standard_order if m in groups]
    materials_ordered += sorted(m for m in groups if m not in standard_order)

    total = len(materials_ordered)
    for idx, mat in enumerate(materials_ordered, start=1):
        if progress_callback:
            try: progress_callback(idx, total, mat)
            except Exception: pass

        mat_pieces = groups[mat]
        width = float(fabric_widths_per_material.get(mat, 144.0))
        mat_polygons = None
        if polygons is not None:
            mat_polygons = {p["piece_id"]: polygons[p["piece_id"]]
                            for p in mat_pieces if p["piece_id"] in polygons}

        try:
            res = nest_pieces_sparrow_multisize(
                pieces=mat_pieces,
                fabric_width_cm=width,
                size_ratio=size_ratio,
                runtime_seconds=runtime_seconds,
                mirror_each=False,  # 폐기됨
                grain_mode=grain_mode,
                polygons=mat_polygons,
                seam_allowance_cm=0.0,
                early_termination=early_termination,
                seed=seed,
            )
        except Exception as e:
            res = {
                "engine": "sparrow", "error": f"multisize 호출 실패: {e}",
                "placements": [], "marker_length_cm": 0.0, "efficiency": 0.0,
                "unplaced": [p["piece_id"] for p in mat_pieces], "warnings": [],
                "fabric_width_cm": width, "marker_mode": "2WAY",
                "size_ratio": size_ratio,
                "total_garments": sum(size_ratio.values()),
                "yards_per_garment": 0.0, "cm_per_garment": 0.0,
                "sizes_included": list(size_ratio.keys()),
                "mirror_count_per_piece": {}, "pieces_used": mat_pieces,
                "polygons": mat_polygons or {},
                "runtime_seconds_requested": runtime_seconds,
                "runtime_actual_sec": 0.0,
                "svg_content": "", "svg_content_humanized": "",
            }
        # SVG humanize + 식서 화살표 + 축 라벨 (Bug 2/4 — 2026-05-01)
        humanized = humanize_svg_labels(res.get("svg_content", ""))
        res["svg_content_humanized"] = annotate_marker_svg(
            humanized,
            placements=res.get("placements"),
            fabric_width_cm=res.get("fabric_width_cm"),
            marker_length_cm=res.get("marker_length_cm"),
        )
        by_material[mat] = res
        total_rt += res.get("runtime_actual_sec", 0.0)

        marker_cm = res.get("marker_length_cm", 0.0)
        n_mirror = sum(1 for v in res.get("mirror_count_per_piece", {}).values() if v == 1)
        summary_rows.append({
            "material": mat,
            "fabric_width_cm": width,
            "marker_length_cm": marker_cm,
            "marker_length_yd": marker_cm * CM_TO_YD,
            "pieces_count": len(mat_pieces),  # 1벌당 unique 패턴
            "mirror_count": n_mirror,
            "efficiency_pct": res.get("efficiency", 0.0) * 100,
            "runtime_actual_sec": res.get("runtime_actual_sec", 0.0),
            "has_error": bool(res.get("error")),
            # multi-size 추가 키
            "total_garments": res.get("total_garments", 0),
            "yards_per_garment": res.get("yards_per_garment", 0.0),
            "cm_per_garment": res.get("cm_per_garment", 0.0),
        })

    return {
        "by_material": by_material,
        "unclassified_warnings": unclassified,
        "summary_rows": summary_rows,
        "total_runtime_sec": total_rt,
        "materials_ordered": materials_ordered,
        "size_ratio": size_ratio,
        "total_garments": sum(int(v) for v in size_ratio.values() if v),
        "excluded_pieces": excluded_pieces,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ 본사 검증 데이터 매칭 + 사이즈비율 파싱                       ║
# ╚════════════════════════════════════════════════════════════╝
import re as _re
import json as _json

_HQ_VALIDATION_JSON = PROJECT_ROOT / "요척자료데이터" / "요척_검증데이터.json"

# 사이즈비율 표기 정규식 (본사 데이터 분석 결과 두 형식 발견)
#   "X:Y"     예: "18:35", "10:57"   — X=사이즈 종류 수 (추정), Y=총벌수 또는 비율
#   "X:Y-Z"   예: "4:32-4", "4:26-4" — X=사이즈 종류 수, Y=기준 사이즈, Z=기준 사이즈 벌수
_SIZE_RATIO_PATTERN_XYZ = _re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*-\s*(\d+)\s*$")
_SIZE_RATIO_PATTERN_XY = _re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")


def parse_hq_size_ratio(ratio_str: str, available_sizes: list[str] | None = None) -> dict | None:
    """
    본사 사이즈비율 문자열 → {size: count} dict 추정.

    본사 표기 의미가 모호하므로 보수적 추정:
      - "X:Y-Z" → X 사이즈 종류, 기준 사이즈 Y에 Z벌 + 다른 사이즈 1벌씩 (추정)
      - "X:Y"   → X 사이즈 종류 모두 1벌씩 (균등 분배 추정)

    available_sizes 가 주어지면 그 안에서만 매핑.
    의미 모호로 정확한 본사 비율 재현은 보장 X — UI 에서 "본사 추정" 으로 표시 권장.

    Returns None 이면 파싱 실패 (사용자 수동 입력 권장).
    """
    if not ratio_str or not ratio_str.strip():
        return None

    available_sorted = sorted(available_sizes) if available_sizes else None

    # X:Y-Z 형식
    m = _SIZE_RATIO_PATTERN_XYZ.match(ratio_str)
    if m:
        n_sizes = int(m.group(1))
        ref_size_num = m.group(2)
        ref_count = int(m.group(3))
        if not available_sorted:
            return None
        # 기준 사이즈 매칭 시도 (숫자 사이즈 기준)
        ref_size = None
        for s in available_sorted:
            if s == ref_size_num or s.lstrip("0") == ref_size_num.lstrip("0"):
                ref_size = s
                break
        # 가장 가까운 사이즈 N개 선택 (기준 사이즈 중심)
        if ref_size and ref_size in available_sorted:
            idx = available_sorted.index(ref_size)
        else:
            idx = len(available_sorted) // 2
        # idx 중심으로 ±N개 사이즈 선택
        half = n_sizes // 2
        start = max(0, idx - half)
        end = min(len(available_sorted), start + n_sizes)
        start = max(0, end - n_sizes)
        chosen_sizes = available_sorted[start:end]
        if not chosen_sizes:
            return None
        ratio = {sz: 1 for sz in chosen_sizes}
        # 기준 사이즈에 ref_count 적용
        if ref_size in ratio and ref_count > 0:
            ratio[ref_size] = max(1, ref_count if ref_count <= 10 else 1)
        return ratio

    # X:Y 형식 (단순) — X 사이즈 종류 균등 분배
    m = _SIZE_RATIO_PATTERN_XY.match(ratio_str)
    if m:
        n_sizes = int(m.group(1))
        if not available_sorted:
            return None
        # available 중 N 사이즈 선택 (균등 분포)
        if n_sizes >= len(available_sorted):
            return {sz: 1 for sz in available_sorted}
        # 가운데 N개 선택
        idx_mid = len(available_sorted) // 2
        half = n_sizes // 2
        start = max(0, idx_mid - half)
        end = min(len(available_sorted), start + n_sizes)
        start = max(0, end - n_sizes)
        return {sz: 1 for sz in available_sorted[start:end]}

    return None


def extract_style_code(filename: str) -> str | None:
    """
    DXF 파일명에서 무신사 품번(스타일 코드) 추출.

    품번 패턴: M[성별][시즌][카테고리][숫자] 형식 (예: MWDPS901, MMAPS006)
    파일명 안의 첫 매칭만 반환.

    예:
      "MWDPS901.dxf"                            → "MWDPS901"
      "MMCPS120-AAMA (최종).dxf"                → "MMCPS120"
      "MWFSL6A03(J26-V017) MARKER FILE_JAO.dxf" → "MWFSL6A03"
      "MMFPK3E04_더블 니트 ... .dxf"             → "MMFPK3E04"
    """
    if not filename:
        return None
    # 파일명을 _ . - 공백 ( ) 등으로 분리한 토큰에서 매칭 (\b 는 _ 옆에서 깨짐)
    tokens = _re.split(r"[\s_().\-]+", filename.upper())
    pattern = _re.compile(r"^M[A-Z][A-Z0-9]{2,8}\d[A-Z0-9]{0,3}$")
    for tok in tokens:
        if pattern.match(tok):
            return tok
    # 확장: 토큰 앞부분에 품번이 prefix 로 박혀 있는 케이스 (예: MMCPS120 + 한글)
    for tok in tokens:
        m = _re.match(r"^(M[A-Z][A-Z0-9]{2,8}\d[A-Z0-9]{0,3})", tok)
        if m:
            return m.group(1)
    return None


def load_hq_validation_data() -> list[dict]:
    """검증 데이터 JSON 로드 (한 번만 읽고 캐시)."""
    if not _HQ_VALIDATION_JSON.exists():
        return []
    try:
        return _json.loads(_HQ_VALIDATION_JSON.read_text())
    except Exception:
        return []


def find_hq_match(style_code: str | None) -> dict | None:
    """
    품번에 해당하는 본사 검증 데이터 entry 반환.
    여러 entry 매칭 시 효율 비어있지 않은 첫 항목 반환.
    """
    if not style_code:
        return None
    code_upper = style_code.upper()
    matches = []
    for d in load_hq_validation_data():
        c = (d.get("품번") or "").strip().upper()
        if c == code_upper or (c and code_upper in c) or (c and c in code_upper):
            matches.append(d)
    if not matches:
        return None
    # 효율 비어있지 않은 것 우선
    valid = [m for m in matches if m.get("효율_pct") not in (None, "", "0", 0)]
    if valid:
        return valid[0]
    return matches[0]
