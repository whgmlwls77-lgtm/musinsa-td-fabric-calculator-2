# -*- coding: utf-8 -*-
"""
visualize_pieces.py
-------------------
추출한 패턴 피스들을 matplotlib 으로 한 장의 2D 도면으로 그려
output/pattern_preview.png 로 저장한다.

그림에는:
  - 피스별 외곽선을 색으로 채워 표시 (재질별 색상)
  - 피스 중앙에 piece_id (P001 …) 와 피스명 라벨
  - 재질 범례(legend)
  - X/Y 축(cm), 그리드
를 포함한다.

주의:
  matplotlib.patches.Polygon 과 shapely.geometry.Polygon 은 이름이 같아
  그대로 import 하면 충돌한다. 여기서는 alias 로 MplPolygon 을 쓴다.
"""

# ── 표준 라이브러리 ────────────────────────────────────────────
from pathlib import Path

# ── matplotlib ────────────────────────────────────────────────
import matplotlib.pyplot as plt
# 도형(외곽선 채우기) 클래스. shapely 와 충돌 피하려고 alias 부여.
from matplotlib.patches import Polygon as MplPolygon
# 범례에서 "색상 네모 박스 + 라벨" 만들기 위한 패치.
from matplotlib.patches import Patch

# ── 같은 폴더 모듈에서 재사용 (DRY) ───────────────────────────
# 파일 경로·여는 함수는 explore_dxf.py 에서,
# 외곽선 찾기/좌표 뽑기/메타 파싱은 extract_pieces.py 에서 가져온다.
# → 동일 로직을 중복 정의하지 않아 유지보수가 쉬워진다.
from explore_dxf import open_dxf, DXF_FILE
from extract_pieces import (
    find_outline,
    polyline_to_coords,
    parse_piece_metadata,
    MM_TO_CM,
    OUTPUT_DIR,
)


# ╔════════════════════════════════════════════════════════════╗
# ║ 상수 — 재질 색상 맵 / 출력 경로                            ║
# ╚════════════════════════════════════════════════════════════╝
# 재질 코드 → (HEX 색상, 한글 라벨) 맵.
# Optitex 가 쓰는 코드:
#   "1"   주 원단
#   "FN"  Fusing(접착심)
#   "IL"  Inner Lining(안단)
#   ""    미지정(메타정보 없음)
MATERIAL_COLOR_MAP: dict[str, tuple[str, str]] = {
    "1":  ("#d0d0d0", "주원단"),
    "FN": ("#a0c0e0", "접착심(Fusing)"),
    "IL": ("#f0e090", "안단(Lining)"),
    "":   ("#f0c0c0", "미지정"),
}

# 최종 PNG 저장 경로.
PREVIEW_PATH: Path = OUTPUT_DIR / "pattern_preview.png"


# ╔════════════════════════════════════════════════════════════╗
# ║ 데이터 수집                                                ║
# ╚════════════════════════════════════════════════════════════╝
def gather_pieces(doc) -> list[dict]:
    """
    DXF 사용자 블록을 순회하며 시각화에 필요한 정보만 dict 로 모은다.

    각 피스 dict 구조:
      {
        "piece_id":   "P001",
        "piece_name": "SLV",
        "material":   "1",
        "coords_cm":  [(x1, y1), (x2, y2), ...],   # cm 단위
        "centroid_cm": (cx, cy),                    # cm 단위
      }

    외곽선(닫힌 POLYLINE)이 없거나 좌표가 3개 미만이면
    경고를 찍고 그 블록은 건너뛴다.
    """
    # 시스템 블록(*Model_Space 등) 제외 후 숫자 이름 오름차순 정렬.
    user_blocks = [b for b in doc.blocks if not b.name.startswith("*")]
    try:
        user_blocks.sort(key=lambda b: int(b.name))
    except ValueError:
        user_blocks.sort(key=lambda b: b.name)

    pieces: list[dict] = []

    for i, block in enumerate(user_blocks, start=1):
        piece_id = f"P{i:03d}"

        # ① 외곽선(첫 번째 닫힌 POLYLINE) 찾기.
        outline = find_outline(block)
        if outline is None:
            print(f"[경고] 블록 '{block.name}' → 닫힌 POLYLINE 없음, 스킵")
            continue

        # ② 좌표를 mm → cm 로 변환.
        coords_mm = polyline_to_coords(outline)
        if len(coords_mm) < 3:
            print(f"[경고] 블록 '{block.name}' → 좌표 수 부족({len(coords_mm)}), 스킵")
            continue
        coords_cm = [(x * MM_TO_CM, y * MM_TO_CM) for x, y in coords_mm]

        # ③ centroid 는 '꼭짓점들의 단순 평균' 으로 근사.
        #    (라벨 배치용이라 대략 중심이면 충분 — shapely 를 쓸 필요 없음)
        cx = sum(x for x, _ in coords_cm) / len(coords_cm)
        cy = sum(y for _, y in coords_cm) / len(coords_cm)

        # ④ TEXT 메타에서 피스명·재질 추출.
        meta = parse_piece_metadata(block)

        pieces.append(
            {
                "piece_id": piece_id,
                "piece_name": meta["piece_name"],
                "material": meta["material"],
                "coords_cm": coords_cm,
                "centroid_cm": (cx, cy),
            }
        )

    return pieces


# ╔════════════════════════════════════════════════════════════╗
# ║ 색상 룩업                                                  ║
# ╚════════════════════════════════════════════════════════════╝
def get_material_color(material: str) -> tuple[str, str]:
    """
    재질 코드를 (HEX 색상, 한글 라벨) 튜플로 변환.
    맵에 없는 코드는 회색 + "기타(코드)" 로 대체.
    """
    if material in MATERIAL_COLOR_MAP:
        return MATERIAL_COLOR_MAP[material]
    return ("#c0c0c0", f"기타({material})")


# ╔════════════════════════════════════════════════════════════╗
# ║ 그리기 함수                                                ║
# ╚════════════════════════════════════════════════════════════╝
def draw_piece(ax, piece: dict) -> None:
    """
    피스 하나를 현재 축(ax) 에 그린다.
      - 외곽선 채우기 (재질 색, 반투명)
      - 테두리(진한 회색)
      - 중심에 piece_id 와 피스명 라벨
    """
    color, _ = get_material_color(piece["material"])

    # matplotlib 의 Polygon 패치.
    # closed=True 면 마지막 점에서 첫 점으로 자동으로 닫는다.
    poly = MplPolygon(
        piece["coords_cm"],
        closed=True,
        facecolor=color,
        edgecolor="#555555",
        linewidth=1.2,
        alpha=0.6,          # 반투명 → 겹침/배경 가독성 개선
    )
    ax.add_patch(poly)

    cx, cy = piece["centroid_cm"]

    # 상단 라벨: piece_id (굵게)
    # y 에 작은 양수 오프셋을 더해 '중심 위쪽' 에 얹는다.
    ax.text(
        cx, cy + 1.2,
        piece["piece_id"],
        ha="center", va="center",
        fontsize=9, fontweight="bold",
    )

    # 하단 라벨: 피스명 (회색, 작게)
    # 피스명이 비어 있으면 아예 출력하지 않아 깔끔하게.
    if piece["piece_name"]:
        ax.text(
            cx, cy - 1.2,
            piece["piece_name"],
            ha="center", va="center",
            fontsize=7, color="#555555",
        )


def add_legend(ax, used_materials: set[str]) -> None:
    """
    실제 도면에 등장한 재질만 모아 범례를 오른쪽 위에 표시.
    (사용되지 않은 재질까지 보여주면 정보 노이즈가 커진다.)
    """
    patches = []
    # 보기 좋은 고정 순서 — 빈 문자열은 마지막에.
    order = ["1", "FN", "IL", ""]
    seen_others = sorted(m for m in used_materials if m not in order)

    for mat in order + seen_others:
        if mat not in used_materials:
            continue
        color, label = get_material_color(mat)
        patches.append(
            Patch(facecolor=color, edgecolor="#555555", alpha=0.6, label=label)
        )

    if patches:
        ax.legend(
            handles=patches,
            loc="upper right",
            title="재질",
            framealpha=0.9,
            fontsize=9,
        )


def setup_axes(ax, pieces: list[dict]) -> None:
    """
    축 범위·라벨·그리드·제목을 설정.
    patch 는 ax.add_patch 만으로는 자동 스케일이 안 되므로
    여기서 명시적으로 xlim/ylim 을 지정한다.
    """
    # 모든 피스의 모든 좌표를 펼쳐서 전체 범위 계산.
    all_x = [x for p in pieces for x, _ in p["coords_cm"]]
    all_y = [y for p in pieces for _, y in p["coords_cm"]]

    if not all_x:
        # 방어적: 피스가 하나도 없으면 기본값.
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
    else:
        margin = 5.0  # cm — 피스 경계에 약간의 여백
        ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
        ax.set_ylim(min(all_y) - margin, max(all_y) + margin)

    # 종횡비 1:1 — 패턴 왜곡 방지(실측 시각화에 필수).
    ax.set_aspect("equal")

    # 축 라벨, 그리드.
    ax.set_xlabel("X (cm)")
    ax.set_ylabel("Y (cm)")
    ax.grid(True, alpha=0.3, linestyle="--")

    # 제목 — 파일명이 너무 길면 줄임표로 잘라 보기 좋게.
    title_src = DXF_FILE.name
    title = title_src if len(title_src) <= 60 else title_src[:57] + "..."
    ax.set_title(f"패턴 미리보기 — {title}", fontsize=12)


def save_preview(fig, path: Path) -> None:
    """
    PNG 저장. dpi=150 로 인쇄 품질에 가깝게, bbox_inches='tight' 로 여백 최소화.
    """
    # 저장 디렉터리가 없으면 만든다(방어적).
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")


# ╔════════════════════════════════════════════════════════════╗
# ║ 메인                                                       ║
# ╚════════════════════════════════════════════════════════════╝
def main() -> None:
    # 한글 폰트 설정 — matplotlib 은 기본적으로 한글이 깨진다.
    # macOS 에는 'AppleGothic' 이 기본 설치돼 있다.
    plt.rcParams["font.family"] = "AppleGothic"
    # 마이너스 부호를 유니코드 U+2212 로 쓰면 한글 폰트에서 깨지므로 끔.
    plt.rcParams["axes.unicode_minus"] = False

    print("=" * 70)
    print(f"시각화 시작: {DXF_FILE.name}")
    print("=" * 70)

    # 1) DXF 열기
    doc = open_dxf(DXF_FILE)
    if doc is None:
        print("[중단] DXF 를 열 수 없어 종료.")
        return

    # 2) 피스 데이터 모으기
    pieces = gather_pieces(doc)
    if not pieces:
        print("[중단] 그릴 피스가 없음.")
        return

    # 3) Figure / Axes 준비
    fig, ax = plt.subplots(figsize=(16, 10))

    # 4) 피스 하나씩 그리기
    for piece in pieces:
        draw_piece(ax, piece)

    # 5) 축 설정 (xlim/ylim/aspect/grid/title)
    setup_axes(ax, pieces)

    # 6) 범례 — 실제 등장한 재질만
    used_materials = {p["material"] for p in pieces}
    add_legend(ax, used_materials)

    # 7) 저장 + 닫기(메모리 회수)
    save_preview(fig, PREVIEW_PATH)
    plt.close(fig)

    # 8) 콘솔 요약
    print(f"\n그린 피스 수 : {len(pieces)}")
    print(f"사용된 재질  : {sorted(used_materials)}")
    print(f"저장 위치    : {PREVIEW_PATH}")
    print("\n" + "=" * 70)
    print("시각화 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
