# -*- coding: utf-8 -*-
"""
auto_nesting.py
---------------
Phase 1: rectpack 기반 자동 마카 배치 (직사각형 근사).

[설계 원칙]
  1. 식서 정보로 0° 또는 90° 사전 회전 → bbox 추출 → rectpack(rotation=False)
  2. rectpack 자체 회전 사용 안 함. 식서 정렬은 사전 회전으로만.
  3. BIAS 피스는 회전 0 (사선 그대로 배치) — Phase 1 보수적 접근.
  4. UNKNOWN 피스는 STRAIGHT_GRAIN_Y 로 가정 + 경고 (자켓 정체 파악 후 재검토).

[Phase 1 한계]
  - 진짜 폴리곤 nesting 아님 (bbox 근사) → 곡선 피스에서 효율 손해.
  - BIAS 는 bbox 가 사선 폴리곤보다 큼 → 더 손해. Phase 2 (pynest2d) 에서 개선 예정.
"""
from __future__ import annotations

from pathlib import Path

from rectpack import newPacker

from grain_extractor import get_alignment_rotation, rotate_polygon
from mirror_pieces import mirror_piece_horizontally


# ╔════════════════════════════════════════════════════════════╗
# ║ 헬퍼: 식서 회전 후 axis-aligned bbox dimensions             ║
# ╚════════════════════════════════════════════════════════════╝
def _bbox_after_rotation(piece: dict, rotation_deg: float) -> tuple[float, float]:
    """
    피스의 bbox 가로/세로를 사전 회전 후 dimensions 로 변환.
      0°/180° → (w, h)        (회전 없음)
      90°     → (h, w)        (가로/세로 swap)
      그 외(BIAS 등) → (w, h) (보수적: 폴리곤이 사선이라 bbox 가 실제보다 큼)
    """
    w, h = piece["width_cm"], piece["height_cm"]
    r_mod = abs(rotation_deg) % 180.0
    if r_mod < 1.0 or r_mod > 179.0:
        return (w, h)
    if abs(r_mod - 90.0) < 1.0:
        return (h, w)
    return (w, h)


# ╔════════════════════════════════════════════════════════════╗
# ║ 메인: nest_pieces                                          ║
# ╚════════════════════════════════════════════════════════════╝
def nest_pieces(
    pieces: list[dict],
    fabric_width_cm: float,
    marker_mode: str = "1WAY",
    seam_allowance_cm: float = 0.0,
) -> dict:
    """
    Phase 1 자동 마카 배치.

    Args:
      pieces: extract_piece_info 결과 리스트.
              필요 필드: piece_id, width_cm, height_cm, area_cm2, grain.
              quantity 는 None 이면 1 로 가정.
      fabric_width_cm: 원단 폭 (cm)
      marker_mode: "1WAY" | "2WAY" — Phase 1 에선 메타 정보로만 보존.
      seam_allowance_cm: 시접(cm). bbox 가로/세로에 ±2*seam 적용.

    Returns:
      {
        "placements": [{"piece_id", "piece_name", "kind",
                        "x_cm", "y_cm",
                        "bbox_w_cm", "bbox_h_cm",
                        "rotation_applied_deg"}, ...],
        "marker_length_cm": float,
        "efficiency": float,        # 폴리곤 실면적 / (마카 길이 × 폭)
        "unplaced": [piece_id, ...],
        "warnings": [str, ...],
        "fabric_width_cm": float,
        "marker_mode": str,
      }
    """
    if marker_mode not in ("1WAY", "2WAY"):
        raise ValueError(f"marker_mode 는 '1WAY' 또는 '2WAY' 만 지원: {marker_mode!r}")

    warnings: list[str] = []

    # ── 1. 회전 결정 + 회전 후 bbox + 시접 적용 ──────────────────
    prepared: list[dict] = []
    for p in pieces:
        grain = p.get("grain") or {"kind": "UNKNOWN"}
        kind = grain.get("kind", "UNKNOWN")
        rotation = get_alignment_rotation(grain)

        if kind == "UNKNOWN":
            warnings.append(
                f"{p['piece_id']} ({p.get('piece_name', '?')}): "
                "grain UNKNOWN — STRAIGHT_GRAIN_Y 가정 (회전 0°)"
            )
        elif grain.get("estimated"):
            # bbox 기반 자동 추정 — 검토 필요
            warnings.append(
                f"{p['piece_id']} ({p.get('piece_name', '?')}): "
                f"식서 마크 없음 — bbox 비율로 {kind} 추정 — 검토 필요 "
                f"({grain.get('reason', '')})"
            )
        elif kind == "NONSTANDARD":
            warnings.append(
                f"{p['piece_id']} ({p.get('piece_name', '?')}): "
                f"grain NONSTANDARD ({grain.get('angle_deg')}°) — 회전 0°"
            )

        bw, bh = _bbox_after_rotation(p, rotation)
        if seam_allowance_cm > 0:
            bw += 2.0 * seam_allowance_cm
            bh += 2.0 * seam_allowance_cm

        if bw > fabric_width_cm:
            warnings.append(
                f"{p['piece_id']}: bbox 가로 {bw:.1f}cm > 원단 폭 "
                f"{fabric_width_cm:.1f}cm → 배치 불가"
            )

        qty = p.get("quantity") or 1

        prepared.append({
            "piece_id": p["piece_id"],
            "piece_name": p.get("piece_name", ""),
            "kind": kind,
            "rotation_applied_deg": rotation,
            "bbox_w_cm": bw,
            "bbox_h_cm": bh,
            "area_cm2": p.get("area_cm2", 0.0),
            "qty": qty,
        })

    # ── 2. rectpack packing ────────────────────────────────────
    # 빈 길이는 모든 피스 세로 합 + 100cm 여유 (반드시 들어가도록 보수적).
    bin_length = sum(pp["bbox_h_cm"] * pp["qty"] for pp in prepared) + 100.0

    # ★ rotation=False — 식서 통일은 사전 회전으로 끝났으므로 추가 회전 금지.
    packer = newPacker(rotation=False)
    for pp in prepared:
        for q in range(pp["qty"]):
            rid = f"{pp['piece_id']}__{q}"
            packer.add_rect(pp["bbox_w_cm"], pp["bbox_h_cm"], rid=rid)

    packer.add_bin(fabric_width_cm, bin_length, count=1)
    packer.pack()

    # ── 3. 결과 추출 ──────────────────────────────────────────
    placements: list[dict] = []
    placed_rids: set[str] = set()
    max_y = 0.0
    prepared_by_id = {pp["piece_id"]: pp for pp in prepared}

    for rect in packer.rect_list():
        # rect_list() 반환: (bin_index, x, y, w, h, rid)
        _, x, y, w, h, rid = rect
        placed_rids.add(rid)
        pid = rid.rsplit("__", 1)[0]
        meta = prepared_by_id[pid]
        placements.append({
            "piece_id": pid,
            "piece_name": meta["piece_name"],
            "kind": meta["kind"],
            "x_cm": float(x),
            "y_cm": float(y),
            "bbox_w_cm": float(w),
            "bbox_h_cm": float(h),
            "rotation_applied_deg": meta["rotation_applied_deg"],
        })
        max_y = max(max_y, y + h)

    all_rids = {f"{pp['piece_id']}__{q}" for pp in prepared for q in range(pp["qty"])}
    unplaced_pids = sorted(
        {rid.rsplit("__", 1)[0] for rid in (all_rids - placed_rids)}
    )
    if unplaced_pids:
        warnings.append(
            f"배치 실패 피스 {len(unplaced_pids)}개: {', '.join(unplaced_pids)}"
        )

    # ── 4. 효율 계산 ─────────────────────────────────────────
    marker_length_cm = float(max_y)
    if marker_length_cm > 0 and fabric_width_cm > 0:
        total_polygon_area = sum(pp["area_cm2"] * pp["qty"] for pp in prepared)
        efficiency = total_polygon_area / (marker_length_cm * fabric_width_cm)
    else:
        efficiency = 0.0

    return {
        "placements": placements,
        "marker_length_cm": marker_length_cm,
        "efficiency": efficiency,
        "unplaced": unplaced_pids,
        "warnings": warnings,
        "fabric_width_cm": fabric_width_cm,
        "marker_mode": marker_mode,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ 그레이딩 마카 (다중 사이즈 + 좌우 미러)                     ║
# ╚════════════════════════════════════════════════════════════╝
def nest_grading_marker(
    pieces: list[dict],
    sizes_to_nest: list[str],
    fabric_width_cm: float,
    polygons: dict | None = None,
    mirror_each: bool = True,
    marker_mode: str = "1WAY",
    seam_allowance_cm: float = 0.0,
) -> dict:
    """
    여러 사이즈 + 좌우 미러를 한 마카에 묶어 nesting (본사 관행 자동화).

    Args:
      pieces: extract_piece_info 결과 (전 사이즈 포함).
      sizes_to_nest: 마카에 넣을 사이즈 라벨 ["S", "L"] 등.
      fabric_width_cm: 원단 폭 (cm).
      polygons: {piece_id: shapely.Polygon} (mm) — 있으면 미러 폴리곤도 생성해서 반환.
      mirror_each: True 면 각 피스의 좌우 미러 추가 (BIAS 제외).
      marker_mode: "1WAY" | "2WAY" — 메타 정보로만 보존.
      seam_allowance_cm: 시접 (cm).

    Returns:
      nest_pieces 결과 + 추가:
        sizes_included         : 사용된 사이즈 라벨 리스트
        mirror_count_per_piece : {원본 piece_id: 1 or 0} — 미러 생성 여부
        pieces_used            : nest 에 들어간 확장된 피스 리스트 (시각화용)
        polygons               : 확장된 폴리곤 dict (입력에 polygons 가 있을 때만)
    """
    # 1. 사이즈 필터
    filtered = [p for p in pieces if p.get("size") in sizes_to_nest]
    if not filtered:
        return {
            "error": f"sizes_to_nest={sizes_to_nest} 에 매치되는 피스 없음",
            "placements": [],
            "marker_length_cm": 0.0,
            "efficiency": 0.0,
            "unplaced": [],
            "warnings": [],
            "fabric_width_cm": fabric_width_cm,
            "marker_mode": marker_mode,
            "sizes_included": sizes_to_nest,
            "mirror_count_per_piece": {},
            "pieces_used": [],
        }

    # 2. 미러 확장
    expanded_pieces: list[dict] = []
    expanded_polygons: dict | None = {} if polygons is not None else None
    mirror_count: dict[str, int] = {}

    for p in filtered:
        # 원본 추가
        expanded_pieces.append(p)
        if expanded_polygons is not None and p["piece_id"] in polygons:
            expanded_polygons[p["piece_id"]] = polygons[p["piece_id"]]

        if not mirror_each:
            mirror_count[p["piece_id"]] = 0
            continue

        # BIAS 는 미러 안 함 — 사선 각도가 +45° ↔ -45° 로 바뀌어야 정확하므로
        # Phase 1.5 에서 별도 처리. 일단 그대로 두기.
        kind = p.get("grain", {}).get("kind", "UNKNOWN")
        if kind == "BIAS":
            mirror_count[p["piece_id"]] = 0
            continue

        # 미러 생성
        mirror_piece, mirror_polygon = mirror_piece_horizontally(
            p, polygons.get(p["piece_id"]) if polygons else None
        )
        expanded_pieces.append(mirror_piece)
        mirror_count[p["piece_id"]] = 1
        if expanded_polygons is not None and mirror_polygon is not None:
            expanded_polygons[mirror_piece["piece_id"]] = mirror_polygon

    # 3. nest_pieces 호출 — Phase 1 알고리즘 그대로
    result = nest_pieces(
        expanded_pieces,
        fabric_width_cm=fabric_width_cm,
        marker_mode=marker_mode,
        seam_allowance_cm=seam_allowance_cm,
    )

    # 4. 메타 정보 추가
    result["sizes_included"] = list(sizes_to_nest)
    result["mirror_count_per_piece"] = mirror_count
    result["pieces_used"] = expanded_pieces
    if expanded_polygons is not None:
        result["polygons"] = expanded_polygons

    return result


# ╔════════════════════════════════════════════════════════════╗
# ║ 마카 시각화                                                ║
# ╚════════════════════════════════════════════════════════════╝
# DXF 원문 재질 코드 → 한글 라벨 매핑 (app.py MATERIAL_COLORS_V2 와 호환).
_MATERIAL_RAW_TO_LABEL: dict[str, str] = {
    "1":  "주원단",
    "":   "주원단",   # 미지정도 주원단으로 표시
    "FN": "심지",
    "IL": "안감",
}
# app.py 의 MATERIAL_COLORS_V2 와 동일 팔레트.
_COLORS_BY_LABEL: dict[str, str] = {
    "주원단":   "#d0d0d0",
    "심지":     "#a0c0e0",
    "안감":     "#f0e090",
    "배색":     "#f4b0c0",
    "주머니감": "#c0e0a0",
}
_DEFAULT_COLOR: str = "#c0c0c0"
_BIAS_COLOR: str = "#dc2626"   # ★ BIAS 강조 — 빨강
_BBOX_LINE: str = "#94a3b8"
_FABRIC_BG: str = "#fffaf0"


def _setup_korean_font() -> None:
    """matplotlib 한글 폰트 설정. 동봉 NotoSansKR 우선.
    addfont() 만으론 family name 매칭이 불안정 — FontProperties.get_name() 으로
    실제 family name 을 추출해 rcParams 에 직접 지정."""
    import matplotlib as mpl
    import matplotlib.font_manager as fm

    here = Path(__file__).parent
    bundled = here / "fonts" / "NotoSansKR-Regular.ttf"
    family_chain: list[str] = []
    if bundled.exists():
        try:
            fm.fontManager.addfont(str(bundled))
            actual_name = fm.FontProperties(fname=str(bundled)).get_name()
            family_chain.append(actual_name)
        except Exception:
            pass
    family_chain.extend(["AppleGothic", "NanumGothic", "sans-serif"])

    mpl.rcParams["font.family"] = family_chain
    mpl.rcParams["axes.unicode_minus"] = False


def _piece_color(material_raw: str, is_bias: bool) -> str:
    """피스 색상 결정. BIAS 면 빨강, 그 외엔 재질별 팔레트."""
    if is_bias:
        return _BIAS_COLOR
    label = _MATERIAL_RAW_TO_LABEL.get(material_raw, material_raw)
    return _COLORS_BY_LABEL.get(label, _DEFAULT_COLOR)


def visualize_marker(
    pieces: list[dict],
    nest_result: dict,
    fabric_width_cm: float,
    polygons: dict | None = None,
    save_path=None,
    polygon_unit: str = "mm",
):
    """
    마카 배치 시각화. matplotlib Figure 반환.

    Args:
      polygons: {piece_id: shapely.Polygon}.
                제공되면 회전·평행이동 후 실선 폴리곤으로 그려 곡선 손실 시각화.
                None 이면 bbox 영역만 색칠.
      polygon_unit: "mm" (기본) 또는 "cm". app.py 의 coords_cm 같이 cm 좌표를
                    그대로 넘길 때 "cm" 지정 (스케일링 안 함).
      save_path: 지정되면 PNG 저장.

    그림 요소:
      - 원단 영역 (배경)
      - bbox 점선  ← rectpack 이 본 직사각형
      - 실제 폴리곤 실선 + 반투명 색칠
      - BIAS 는 빨강 강조
      - 피스명 + grain 방향 화살표 라벨
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon as MplPolygon

    _setup_korean_font()

    piece_by_id = {p["piece_id"]: p for p in pieces}
    marker_length = nest_result["marker_length_cm"]
    eff = nest_result["efficiency"]
    fabric_w = fabric_width_cm

    fig_h = max(6.0, 8.0 * marker_length / fabric_w + 1.0)
    fig, ax = plt.subplots(figsize=(8.0, fig_h))

    # 원단 배경
    ax.add_patch(Rectangle(
        (0, 0), fabric_w, marker_length,
        facecolor=_FABRIC_BG, edgecolor="black",
        linewidth=1.5, zorder=1,
    ))

    for pl in nest_result["placements"]:
        pid = pl["piece_id"]
        x, y = pl["x_cm"], pl["y_cm"]
        bw, bh = pl["bbox_w_cm"], pl["bbox_h_cm"]
        kind = pl["kind"]
        is_bias = (kind == "BIAS")

        meta = piece_by_id.get(pid, {})
        material = meta.get("material", "")
        color = _piece_color(material, is_bias)

        # bbox 점선 — rectpack 이 본 직사각형
        ax.add_patch(Rectangle(
            (x, y), bw, bh,
            facecolor="none", edgecolor=_BBOX_LINE,
            linestyle=":", linewidth=1.0, zorder=2,
        ))

        # 실제 폴리곤 (제공됐을 때) — 곡선 손실 시각화
        if polygons and pid in polygons:
            poly = polygons[pid]
            # 단위 변환: mm → cm (÷10) 또는 cm → cm (그대로)
            scale = 0.1 if polygon_unit == "mm" else 1.0
            cm_coords = [(cx * scale, cy * scale)
                         for cx, cy in poly.exterior.coords[:-1]]
            rotated = rotate_polygon(
                cm_coords, pl["rotation_applied_deg"], around=(0.0, 0.0)
            )
            offset = [(cx + x, cy + y) for cx, cy in rotated]
            ax.add_patch(MplPolygon(
                offset, closed=True,
                facecolor=color, edgecolor="black",
                linewidth=0.8, alpha=0.7, zorder=3,
            ))
        else:
            ax.add_patch(Rectangle(
                (x, y), bw, bh,
                facecolor=color, edgecolor="black",
                linewidth=0.6, alpha=0.5, zorder=3,
            ))

        # 라벨 (grain 방향 화살표 + 피스명)
        arrow_map = {
            "STRAIGHT_GRAIN_X": "↔",
            "STRAIGHT_GRAIN_Y": "↕",
            "BIAS": "★BIAS",
            "UNKNOWN": "?",
            "NONSTANDARD": "!",
        }
        arrow = arrow_map.get(kind, "")
        text_color = "white" if is_bias else "#1f2937"
        if bw >= 4 and bh >= 3:  # 너무 좁으면 텍스트 생략
            ax.text(
                x + bw / 2, y + bh / 2,
                f"{meta.get('piece_name', '')}\n{arrow}",
                ha="center", va="center",
                fontsize=6.5, color=text_color, zorder=4,
            )

    ax.set_xlim(-2, fabric_w + 2)
    ax.set_ylim(-2, marker_length + 4)
    ax.set_aspect("equal")
    ax.set_xlabel("원단 폭 (cm)")
    ax.set_ylabel("원단 길이 (cm)")
    ax.grid(True, linestyle=":", alpha=0.3, zorder=0)

    title = (
        f"마카 길이 {marker_length:.1f} cm × 폭 {fabric_w:.0f} cm   "
        f"|   효율 {eff:.1%}"
    )
    ax.set_title(title, fontsize=11, pad=10)
    fig.tight_layout()

    if save_path is not None:
        sp = Path(save_path)
        sp.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(sp), dpi=120, bbox_inches="tight")

    return fig
