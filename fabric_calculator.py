# -*- coding: utf-8 -*-
"""
fabric_calculator.py
--------------------
패턴 DXF 에서 피스 면적을 합산하고, 사용자가 입력한 원단 폭을 이용해
1벌당 필요한 원단 길이를 재질별로 산출한다. (미터/야드)

[핵심 설계]
- 안단(IL) 은 관례상 주원단에서 같이 재단 → 기본적으로 MAIN 그룹에 합산.
  이를 끄려면 MERGE_IL_INTO_MAIN = False 로 두면 별도 원단 폭을 입력받음.
- 효율(마커 effectiveness) 과 손실률(LOSS_FACTOR) 을 적용해
  실무에 근접한 숫자를 낸다.

[공식]
  net_area_m2     = Σ(area_cm² × qty) / 10000
  gross_area_m2   = net_area_m2 / efficiency
  adjusted_m2     = gross_area_m2 × (1 + LOSS_FACTOR)
  length_m        = adjusted_m2 × 100 / fabric_width_cm
  length_yd       = length_m × 1.0936
"""

# ── 표준 라이브러리 ────────────────────────────────────────────
from pathlib import Path
from datetime import datetime
import unicodedata   # 한글 표시 폭 계산 (정렬용)

# ── 같은 폴더 모듈 재사용 (DRY) ───────────────────────────────
# 파일 열기 / 경로 / 외곽선 / 메타 파싱 로직을 새로 짜지 않는다.
from explore_dxf import open_dxf, DXF_FILE
from extract_pieces import (
    find_outline,
    polyline_to_shapely,
    parse_piece_metadata,
    OUTPUT_DIR,
)


# ╔════════════════════════════════════════════════════════════╗
# ║ === 조정 가능 설정 ===                                     ║
# ╚════════════════════════════════════════════════════════════╝
# 안단(IL) 을 주원단(MAIN) 에 합쳐서 계산할지 여부.
#   True  : 실무 일반 (같은 원단으로 재단)
#   False : 콘트라스트 안단 등 별도 원단 사용 시, 안단 폭을 따로 입력받음
MERGE_IL_INTO_MAIN: bool = True

# 재질 그룹별 기본 원단 폭 (cm). 사용자 입력으로 덮어씀.
DEFAULT_FABRIC_WIDTH_CM: dict[str, float] = {
    "MAIN": 150.0,  # 주원단 — 한국 셔츠 패턴 일반 기준
    "FN":   110.0,  # 접착심 — 일반 기준
    "IL":   150.0,  # 안단 분리 계산 시에만 사용 (MERGE_IL_INTO_MAIN = False)
}

# 마커 효율 (피스 면적 / 전체 마커 면적).
# 1.0 이면 손실 없음(비현실). 일반 셔츠 기준 0.75~0.85 가 현실적.
MARKER_EFFICIENCY: dict[str, float] = {
    "MAIN": 0.80,
    "FN":   0.70,   # 접착심은 조각이 작고 작은 폭이라 효율이 낮은 편
    "IL":   0.75,
}

# 공통 손실 여유율 (원단 셰이딩·불량·테스트 커팅 등 예비분).
LOSS_FACTOR: float = 0.05   # 5%

# 수량이 DXF 에 기록돼 있지 않은 피스의 가정 수량.
DEFAULT_QUANTITY: int = 1

# 미터 → 야드 환산 계수 (정확: 1 m = 1.0936 yd)
M_TO_YD: float = 1.0936

# 재질 그룹 코드 → 한글 라벨
MATERIAL_LABELS: dict[str, str] = {
    "MAIN": "주원단",
    "FN":   "접착심(Fusing)",
    "IL":   "안단(시다)",
    "UNKNOWN": "미지정(주원단에 포함)",
}

# 단위 환산
MM2_TO_CM2: float = 0.01        # 1 mm² = 0.01 cm²
CM2_TO_M2: float = 1.0 / 10000  # 1 cm² = 0.0001 m²

# 출력 저장 경로
REPORT_PATH: Path = OUTPUT_DIR / "fabric_consumption.txt"


# ╔════════════════════════════════════════════════════════════╗
# ║ 헬퍼: 한글 포함 문자열의 '화면 표시 폭' 기반 패딩           ║
# ╚════════════════════════════════════════════════════════════╝
def _display_width(text: str) -> int:
    """
    터미널에서 차지하는 '칸 수'. 한중일(W,F) 문자는 2칸, 그 외는 1칸.
    (f-string 의 {:<N} 은 '문자 개수' 기준이라 한글 섞이면 어긋난다.)
    """
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in text
    )


def _pad(text: str, width: int) -> str:
    """오른쪽을 공백으로 채워 화면 폭이 width 가 되게 한다."""
    gap = width - _display_width(text)
    return text + " " * max(0, gap)


# ╔════════════════════════════════════════════════════════════╗
# ║ DXF 에서 피스 정보 수집                                    ║
# ╚════════════════════════════════════════════════════════════╝
def extract_piece_simple(doc) -> list[dict]:
    """
    계산에 필요한 최소 필드만 뽑는다.
      { piece_id, block_name, piece_name, material_raw, quantity, area_cm2 }

    닫힌 POLYLINE 이 없거나 폴리곤 변환 실패면 건너뜀.
    """
    user_blocks = [b for b in doc.blocks if not b.name.startswith("*")]
    # 숫자 이름 오름차순 정렬 (P001 부여 순서와 동일하게).
    try:
        user_blocks.sort(key=lambda b: int(b.name))
    except ValueError:
        user_blocks.sort(key=lambda b: b.name)

    pieces: list[dict] = []
    for i, block in enumerate(user_blocks, start=1):
        outline = find_outline(block)
        if outline is None:
            continue

        polygon = polyline_to_shapely(outline)
        if polygon is None:
            continue

        meta = parse_piece_metadata(block)

        pieces.append({
            "piece_id": f"P{i:03d}",
            "block_name": block.name,
            "piece_name": meta["piece_name"],
            "material_raw": meta["material"],     # DXF 원문 코드: "1", "FN", "IL", ""
            "quantity": meta["quantity"],          # int 또는 None
            "area_cm2": polygon.area * MM2_TO_CM2, # shapely area 는 mm² → cm²
        })

    return pieces


def get_style_info(doc) -> tuple[str, str]:
    """
    모델스페이스의 메타 TEXT 에서 (스타일명, 샘플사이즈) 추출.
    찾지 못하면 빈 문자열.
    """
    style = ""
    size = ""
    for text in doc.modelspace().query("TEXT"):
        content = text.dxf.text.strip()
        low = content.lower()
        if low.startswith("style name:"):
            _, _, value = content.partition(":")
            # 긴 스타일명에서 첫 토큰만 (예: "MWESH203 FULL BULK..." → "MWESH203")
            tokens = value.strip().split()
            if tokens:
                style = tokens[0]
        elif low.startswith("sample size:"):
            _, _, value = content.partition(":")
            size = value.strip()
    return style, size


# ╔════════════════════════════════════════════════════════════╗
# ║ 재질 그룹 해석                                             ║
# ╚════════════════════════════════════════════════════════════╝
def resolve_material_group(material_code: str) -> str:
    """
    DXF 원문 재질 코드 → 계산용 그룹 코드.
      "1"   → "MAIN"
      "FN"  → "FN"
      "IL"  → "MAIN" (MERGE_IL_INTO_MAIN=True) 또는 "IL"
      ""    → "UNKNOWN"  (이후 MAIN 으로 흡수하되 경고)
      기타  → 원본 그대로 (예상 밖 코드 — 별도 경고에서 다룸)
    """
    if material_code == "1":
        return "MAIN"
    if material_code == "FN":
        return "FN"
    if material_code == "IL":
        return "MAIN" if MERGE_IL_INTO_MAIN else "IL"
    if material_code == "":
        return "UNKNOWN"
    return material_code


# ╔════════════════════════════════════════════════════════════╗
# ║ 사용자 입력 (원단 폭)                                      ║
# ╚════════════════════════════════════════════════════════════╝
def _prompt_float(label: str, default: float) -> float:
    """
    input() 을 감싸 방어적으로 float 를 읽는다.
    - 빈 입력     → default
    - 숫자 아님   → 경고 + default
    - EOF (비TTY) → default (자동 수락)
    """
    try:
        raw = input(label).strip()
    except EOFError:
        # 비대화형(파이프) 실행 대응.
        print("(입력 없음 — 기본값 사용)")
        return default

    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"  [경고] '{raw}' 는 숫자가 아님 — 기본값 {default} cm 사용")
        return default


def prompt_fabric_widths() -> dict[str, float]:
    """
    재질 그룹별 원단 폭 입력 받기.
    MERGE_IL_INTO_MAIN 이 False 일 때만 IL 폭도 묻는다.
    """
    widths: dict[str, float] = {}

    widths["MAIN"] = _prompt_float(
        f"주원단 폭 (cm, 기본 {DEFAULT_FABRIC_WIDTH_CM['MAIN']:.0f}): ",
        DEFAULT_FABRIC_WIDTH_CM["MAIN"],
    )
    widths["FN"] = _prompt_float(
        f"접착심 폭 (cm, 기본 {DEFAULT_FABRIC_WIDTH_CM['FN']:.0f}): ",
        DEFAULT_FABRIC_WIDTH_CM["FN"],
    )

    if not MERGE_IL_INTO_MAIN:
        widths["IL"] = _prompt_float(
            f"안단 폭 (cm, 기본 {DEFAULT_FABRIC_WIDTH_CM['IL']:.0f}): ",
            DEFAULT_FABRIC_WIDTH_CM["IL"],
        )

    return widths


# ╔════════════════════════════════════════════════════════════╗
# ║ 요척 계산 본체                                             ║
# ╚════════════════════════════════════════════════════════════╝
def calculate_yardage(
    pieces: list[dict],
    fabric_widths: dict[str, float],
) -> tuple[dict, list[str]]:
    """
    피스 리스트를 재질 그룹별로 합산하여 그룹별 결과 dict 를 돌려준다.

    반환:
      result = {
        "MAIN": {"net_area_m2", "gross_area_m2", "adjusted_m2",
                 "width_cm", "length_m", "length_yd",
                 "piece_count", "total_qty"},
        "FN":   {...},
        (IL 분리 모드면 "IL" 도),
      }
      warnings = 경고 문자열 리스트
    """
    # 그룹별로 피스를 묶는다.
    grouped: dict[str, list[dict]] = {}

    warnings: list[str] = []
    qty_missing: list[dict] = []
    unknown_material: list[dict] = []
    il_merged: list[dict] = []
    unexpected_codes: list[dict] = []

    for p in pieces:
        raw_mat = p["material_raw"]
        group = resolve_material_group(raw_mat)

        # 예상 밖 코드 트래킹.
        if group not in ("MAIN", "FN", "IL", "UNKNOWN"):
            unexpected_codes.append(p)

        # 미지정(빈 문자열) 은 경고 + MAIN 에 흡수.
        if group == "UNKNOWN":
            unknown_material.append(p)
            group = "MAIN"

        # IL 합병 정보용 로그.
        if raw_mat == "IL" and MERGE_IL_INTO_MAIN:
            il_merged.append(p)

        # 수량 보정.
        qty = p["quantity"]
        if qty is None:
            qty_missing.append(p)
            qty = DEFAULT_QUANTITY

        grouped.setdefault(group, []).append({"piece": p, "qty_used": qty})

    # 그룹별로 면적·길이 계산.
    result: dict[str, dict] = {}
    for group, entries in grouped.items():
        net_area_cm2 = sum(e["piece"]["area_cm2"] * e["qty_used"] for e in entries)
        net_area_m2 = net_area_cm2 * CM2_TO_M2

        efficiency = MARKER_EFFICIENCY.get(group, 0.75)
        gross_area_m2 = net_area_m2 / efficiency

        adjusted_m2 = gross_area_m2 * (1.0 + LOSS_FACTOR)

        width_cm = fabric_widths.get(group, DEFAULT_FABRIC_WIDTH_CM.get(group, 150.0))
        # 길이(m) = 면적(m²) ÷ 폭(m) = 면적 × 100 / 폭(cm)
        length_m = adjusted_m2 * 100.0 / width_cm
        length_yd = length_m * M_TO_YD

        result[group] = {
            "net_area_m2": net_area_m2,
            "gross_area_m2": gross_area_m2,
            "adjusted_m2": adjusted_m2,
            "width_cm": width_cm,
            "length_m": length_m,
            "length_yd": length_yd,
            "piece_count": len(entries),
            "total_qty": sum(e["qty_used"] for e in entries),
            "efficiency": efficiency,
        }

    # ── 경고 메시지 ────────────────────────────────────────
    if il_merged and MERGE_IL_INTO_MAIN:
        ids = ", ".join(p["piece_id"] for p in il_merged)
        warnings.append(
            f"안단(시다) {len(il_merged)}개 피스 ({ids}) 는 주원단에 포함 계산"
        )
    if qty_missing:
        ids = ", ".join(p["piece_id"] for p in qty_missing)
        warnings.append(
            f"수량 미지정 피스 {len(qty_missing)}개 ({ids}) → {DEFAULT_QUANTITY} 로 가정"
        )
    if unknown_material:
        ids = ", ".join(p["piece_id"] for p in unknown_material)
        warnings.append(
            f"재질 미지정 피스 {len(unknown_material)}개 ({ids}) → 주원단에 포함 계산"
        )
    if unexpected_codes:
        detail = ", ".join(
            f"{p['piece_id']}('{p['material_raw']}')" for p in unexpected_codes
        )
        warnings.append(f"예기치 않은 재질 코드 감지: {detail}")

    warnings.append(
        f"손실률 {LOSS_FACTOR * 100:.0f}%, 효율 기본값(MAIN {MARKER_EFFICIENCY['MAIN']:.0%} / "
        f"FN {MARKER_EFFICIENCY['FN']:.0%}) 사용 — 실측 마커 완성 후 조정 권장"
    )

    return result, warnings


# ╔════════════════════════════════════════════════════════════╗
# ║ 출력(콘솔 & 파일 공용 포맷)                                ║
# ╚════════════════════════════════════════════════════════════╝
def _format_report_lines(
    result: dict,
    warnings: list[str],
    fabric_widths: dict[str, float],
    style: str,
    size: str,
    mode_info: str,
    now: datetime,
) -> list[str]:
    """
    콘솔/파일 공용 출력 라인 리스트 생성.
    문자열 리스트로 돌려주어 print / 파일 저장에 공용.
    """
    title = f"원단 요척 산출 ({style or 'Style ?'}, Sample Size {size or '?'}, 1벌 기준)"
    bar = "═" * 60

    lines: list[str] = []
    lines.append(bar)
    lines.append(f"  {title}")
    lines.append(f"  실행: {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  모드: {mode_info}")
    lines.append(bar)
    lines.append("")

    # 표 헤더 — 한글 포함 정렬은 _pad 로.
    # 폭: 재질 20, 폭 9, 필요 길이 나머지
    head = f"  {_pad('재질', 20)} {_pad('폭', 9)} {_pad('필요 길이', 30)}"
    lines.append(head)
    lines.append("  " + "─" * 58)

    # 출력 순서 고정 (MAIN → FN → IL 순서).
    display_order = ["MAIN", "FN", "IL"]
    for group in display_order:
        if group not in result:
            continue
        r = result[group]
        label = MATERIAL_LABELS.get(group, group)
        width_str = f"{r['width_cm']:.0f}cm"
        length_str = f"{r['length_m']:.2f} m (≈ {r['length_yd']:.2f} yd)"
        lines.append(
            f"  {_pad(label, 20)} {_pad(width_str, 9)} {_pad(length_str, 30)}"
        )

    lines.append("  " + "─" * 58)

    # ★ 합계 라인 — 그룹별 최종 야드.
    for group in display_order:
        if group not in result:
            continue
        r = result[group]
        label = MATERIAL_LABELS.get(group, group)
        summary = f"★ 합계 ({label}): {_pad('', 4)}{r['length_yd']:>6.2f} yd"
        lines.append("  " + summary)

    # 상세(투명성) 정보.
    lines.append("")
    lines.append("  [상세]")
    for group in display_order:
        if group not in result:
            continue
        r = result[group]
        label = MATERIAL_LABELS.get(group, group)
        lines.append(
            f"    {_pad(label, 20)} "
            f"net {r['net_area_m2']:.4f} m² / "
            f"효율 {r['efficiency']:.0%} → gross {r['gross_area_m2']:.4f} m² / "
            f"손실 포함 {r['adjusted_m2']:.4f} m²  "
            f"(피스 {r['piece_count']}종, 누적수량 {r['total_qty']})"
        )

    # 주의사항.
    lines.append("")
    lines.append("  [주의]")
    for w in warnings:
        lines.append(f"    - {w}")

    return lines


def print_summary(
    result: dict,
    warnings: list[str],
    fabric_widths: dict[str, float],
    style: str,
    size: str,
    mode_info: str,
    now: datetime,
) -> None:
    lines = _format_report_lines(
        result, warnings, fabric_widths, style, size, mode_info, now
    )
    for line in lines:
        print(line)


def save_report(
    result: dict,
    warnings: list[str],
    fabric_widths: dict[str, float],
    style: str,
    size: str,
    mode_info: str,
    now: datetime,
    path: Path,
) -> None:
    """콘솔과 동일한 내용을 텍스트 파일로 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _format_report_lines(
        result, warnings, fabric_widths, style, size, mode_info, now
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ╔════════════════════════════════════════════════════════════╗
# ║ 메인                                                       ║
# ╚════════════════════════════════════════════════════════════╝
def main() -> None:
    print("=" * 60)
    print(f"원단 요척 계산: {DXF_FILE.name}")
    print("=" * 60)

    doc = open_dxf(DXF_FILE)
    if doc is None:
        print("[중단] DXF 를 열 수 없어 종료.")
        return

    # 스타일명·샘플 사이즈 추출 (없으면 빈 값).
    style, size = get_style_info(doc)

    # 피스 수집.
    pieces = extract_piece_simple(doc)
    if not pieces:
        print("[중단] 계산할 피스가 없음.")
        return
    print(f"피스 {len(pieces)}개 추출 완료.\n")

    # 사용자 원단 폭 입력 (엔터 시 기본값).
    fabric_widths = prompt_fabric_widths()

    # 모드 설명 문자열.
    mode_info = (
        "안단(IL) → 주원단 통합 계산"
        if MERGE_IL_INTO_MAIN
        else "안단(IL) 분리 계산"
    )

    # 계산.
    result, warnings = calculate_yardage(pieces, fabric_widths)

    # 출력 (콘솔 + 파일).
    now = datetime.now()
    print()
    print_summary(result, warnings, fabric_widths, style, size, mode_info, now)

    save_report(
        result, warnings, fabric_widths, style, size, mode_info, now, REPORT_PATH
    )

    print()
    print(f"저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()
