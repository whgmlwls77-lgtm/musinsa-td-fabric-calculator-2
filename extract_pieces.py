# -*- coding: utf-8 -*-
"""
extract_pieces.py
-----------------
DXF 파일에서 각 패턴 피스(= 사용자 블록)의 형상 정보와 메타데이터를
추출해 CSV / JSON / 로그 파일로 저장한다.

[사전 확인된 사실]
  - Optitex 출력, 단위는 mm.
  - 모든 INSERT 가 (0,0)·회전 0·스케일 1 → 블록 정의 좌표 = 월드 좌표.
  - 각 블록의 "첫 번째 닫힌 POLYLINE" 이 피스 외곽선.
  - 블록 내부 TEXT 에 "Piece Name: ...", "Size: ...", "Quantity: ...",
    "Material: ...", "Area: ... sq.cm" 형식의 메타정보가 있다고 가정.

[출력]
  output/pieces_info.csv   : 한글 헤더, UTF-8 BOM (Excel 호환)
  output/pieces_info.json  : 들여쓰기 2칸, ensure_ascii=False
  output/analysis_log.txt  : 실행 일시, 입력, 추출/스킵 요약, 오차 검증
"""

# ── 표준 라이브러리 ────────────────────────────────────────────
from pathlib import Path     # 경로 객체
import csv                   # CSV 저장
import json                  # JSON 저장
import datetime              # 로그 타임스탬프

# ── 외부 라이브러리 ────────────────────────────────────────────
# shapely 는 2D 기하 연산 전문 라이브러리.
# Polygon 객체 하나로 둘레/면적/bbox/centroid 를 전부 얻을 수 있다.
from shapely.geometry import Polygon

# ── 같은 폴더 모듈에서 재사용 ──────────────────────────────────
# explore_dxf.py 의 open_dxf 함수와 DXF_FILE 경로 상수를 그대로 쓴다.
# → 파일 열기 로직/에러 처리를 한 곳에서만 관리 (DRY 원칙).
from explore_dxf import open_dxf, DXF_FILE
from grain_extractor import detect_grain_layer, extract_grain, estimate_grain_from_bbox


# ╔════════════════════════════════════════════════════════════╗
# ║ 식서 LAYER 캐시 (doc 당 1회 식별)                          ║
# ╚════════════════════════════════════════════════════════════╝
# extract_piece_info() 가 매 블록마다 doc 전체를 다시 스캔하지 않도록,
# 모듈 전역에 식서 LAYER 를 캐시한다. main() 또는 다른 진입점에서
# init_grain_layer(doc) 를 1회 호출해 세팅.
GRAIN_LAYER: str | None = None


def init_grain_layer(doc) -> str | None:
    """doc 에서 식서 LAYER 를 자동 식별해 모듈 전역에 캐시. 결과 반환."""
    global GRAIN_LAYER
    GRAIN_LAYER = detect_grain_layer(doc)
    return GRAIN_LAYER


# ╔════════════════════════════════════════════════════════════╗
# ║ 상수                                                       ║
# ╚════════════════════════════════════════════════════════════╝
# 단위 환산 (shapely 계산은 원본 좌표 단위(mm)로 나오므로 cm 로 변환).
MM_TO_CM: float = 0.1       # 1 mm  = 0.1 cm  (길이)
MM2_TO_CM2: float = 0.01    # 1 mm² = 0.01 cm² (면적)

# 오차 경고 임계값 (계산 면적과 DXF 기록 면적의 차이).
AREA_ERROR_WARN_PCT: float = 1.0

# 출력 파일 경로 — 모두 output/ 하위.
OUTPUT_DIR: Path = Path.home() / "Desktop" / "Claude" / "fit-prog" / "dxf_test" / "output"
CSV_PATH: Path = OUTPUT_DIR / "pieces_info.csv"
JSON_PATH: Path = OUTPUT_DIR / "pieces_info.json"
LOG_PATH: Path = OUTPUT_DIR / "analysis_log.txt"


# ╔════════════════════════════════════════════════════════════╗
# ║ 저수준 헬퍼: POLYLINE 좌표 추출 / 닫힘 판정                ║
# ╚════════════════════════════════════════════════════════════╝
def polyline_to_coords(pline) -> list[tuple[float, float]]:
    """
    ezdxf 의 POLYLINE / LWPOLYLINE 엔티티에서 (x, y) 튜플 리스트를 뽑는다.
    두 엔티티는 API 가 다르므로 타입별로 분기한다.
    """
    dxftype = pline.dxftype()

    if dxftype == "LWPOLYLINE":
        # LWPOLYLINE: 점 정보가 엔티티 자체에 압축 저장됨.
        # get_points("xy") 는 [(x, y), ...] 형태로 돌려줌.
        return [(pt[0], pt[1]) for pt in pline.get_points("xy")]

    if dxftype == "POLYLINE":
        # 구형 POLYLINE: 각 꼭짓점이 별도의 VERTEX 서브 엔티티.
        # v.dxf.location 은 Vec3 → .x, .y 로 접근.
        return [(v.dxf.location.x, v.dxf.location.y) for v in pline.vertices]

    # 지원하지 않는 타입이면 빈 리스트.
    return []


def is_closed_poly(pline) -> bool:
    """
    POLYLINE / LWPOLYLINE 의 '닫힘(is_closed)' 여부를 통일된 인터페이스로 반환.
    - Polyline      : is_closed 프로퍼티
    - LWPolyline    : closed / is_closed 어트리뷰트
    getattr 로 두 경우 모두 안전하게 처리.
    """
    return bool(
        getattr(pline, "is_closed", False) or getattr(pline, "closed", False)
    )


# ╔════════════════════════════════════════════════════════════╗
# ║ 블록 분석 함수                                             ║
# ╚════════════════════════════════════════════════════════════╝
def find_outline(block):
    """
    블록 안의 '닫힌 POLYLINE/LWPOLYLINE 중 면적이 가장 큰 것' 을 외곽선으로 반환.
    못 찾으면 None.

    이전 버전(첫 번째 닫힘)은 자켓처럼 LAYER 1(시접 포함) + LAYER 14(net) 가
    공존하는 DXF 에서 어느 것이 먼저 나오는지 모호. 도메인 규칙상 요척은
    무조건 시접 포함 외곽선을 써야 하므로 면적 최대를 채택.
    """
    best = None
    best_area = -1.0
    for entity in block:
        if entity.dxftype() not in ("POLYLINE", "LWPOLYLINE"):
            continue
        if not is_closed_poly(entity):
            continue
        polygon = polyline_to_shapely(entity)
        if polygon is None:
            continue
        if polygon.area > best_area:
            best_area = polygon.area
            best = entity
    return best


_MIRROR_TRUE_TOKENS: frozenset = frozenset({"TRUE", "1", "Y", "YES"})
_MIRROR_FALSE_TOKENS: frozenset = frozenset({"FALSE", "0", "N", "NO", ""})

_PAIRED_TRUE_TOKENS: frozenset = frozenset({"DOUBLE", "PAIR", "YES", "Y", "TRUE", "1"})
_PAIRED_FALSE_TOKENS: frozenset = frozenset({"SINGLE", "NO", "N", "FALSE", "0", ""})


def parse_mirror_value(value: str) -> bool | None:
    """
    Mirror 메타 값을 bool 또는 None 으로 정규화.
      True : "True"/"true"/"TRUE"/"1"/"Y"/"yes"/"Yes"
      False: "False"/"false"/"FALSE"/"0"/"N"/"no"/"No"/""
      그 외 → None (불명 → 호출자가 추측 X)

    절대 원칙: 키 자체 부재 또는 인식 불능 값 → 자동 추측 금지 (None 보존).
    """
    if value is None:
        return None
    token = value.strip().upper()
    if token in _MIRROR_TRUE_TOKENS:
        return True
    if token in _MIRROR_FALSE_TOKENS:
        return False
    return None


def parse_paired_value(value: str) -> bool | None:
    """
    PAIRED 메타 값을 mirror bool 로 정규화 (StyleCAD 등 좌우 페어 표기).
      True : DOUBLE / PAIR / YES — 좌우 페어 piece (원본 + 미러)
      False: SINGLE / NO — 단일 piece (미러 X)
      그 외 → None (절대 원칙: 추측 X — 호출자가 미러 적용 안 함)
    """
    if value is None:
        return None
    token = value.strip().upper()
    if token in _PAIRED_TRUE_TOKENS:
        return True
    if token in _PAIRED_FALSE_TOKENS:
        return False
    return None


def parse_piece_metadata(block) -> dict:
    """
    블록 내부 TEXT 엔티티를 훑어 메타정보를 dict 로 돌려준다.
    찾지 못한 필드는 빈 문자열 / None 으로 채움.
    """
    meta = {
        "piece_name": "",
        "piece_name_raw": "",        # 원본 그대로 (위반 알림 가독성)
        "is_standard_name": False,   # 표준 어휘집 매칭 여부 (진단 [위반 알림]용)
        "size": "",
        "quantity": None,            # int 또는 None
        "material": "",
        "mirror": None,              # bool 또는 None (불명 — 절대 원칙: 추측 X)
        "recorded_area_cm2": None,   # DXF 자체에 기록된 면적 (검증용)
    }
    paired_seen = False  # PAIRED 키가 이미 mirror 값을 정했는지 — Mirror 키가 덮어쓰지 못하게.

    for entity in block:
        if entity.dxftype() != "TEXT":
            continue

        # TEXT 의 실제 문자열. 앞뒤 공백 제거.
        text = entity.dxf.text.strip()
        if ":" not in text:
            continue  # "key: value" 형식이 아니면 건너뜀.

        # 첫 ':' 하나로만 분리 — 값 안에 콜론이 또 있어도 안전하게 자르기 위함.
        key_raw, _, value = text.partition(":")
        key = key_raw.strip().lower()    # 비교는 소문자로 정규화
        value = value.strip()

        if key == "piece name":
            meta["piece_name_raw"] = value
            try:
                from piece_name_normalize import normalize_piece_name
                std, ok = normalize_piece_name(value)
                meta["piece_name"] = std or value
                meta["is_standard_name"] = ok
            except Exception:
                # 정규화 실패해도 원본은 보존 (절대 원칙: 추측 X)
                meta["piece_name"] = value
                meta["is_standard_name"] = False
        elif key == "size":
            meta["size"] = value
        elif key == "quantity":
            # 숫자 변환 실패(예: "2 pcs") 시 첫 토큰만 시도.
            try:
                meta["quantity"] = int(value)
            except ValueError:
                try:
                    meta["quantity"] = int(value.split()[0])
                except (ValueError, IndexError):
                    pass
        elif key == "material":
            meta["material"] = value
        elif key == "paired":
            # StyleCAD 좌우 페어 메타. PAIRED > Mirror 우선순위 — 한 번 박히면 Mirror 키가 덮어쓰지 않음.
            meta["mirror"] = parse_paired_value(value)
            paired_seen = True
        elif key == "mirror":
            if not paired_seen:
                meta["mirror"] = parse_mirror_value(value)
        elif key == "area":
            # "12.34 sq.cm" → 첫 토큰(숫자) 만 분리 후 float 변환.
            tokens = value.split()
            if tokens:
                try:
                    meta["recorded_area_cm2"] = float(tokens[0])
                except ValueError:
                    pass

    return meta


def polyline_to_shapely(pline):
    """
    POLYLINE 엔티티 → shapely Polygon 변환.
    좌표가 3개 미만이면 폴리곤을 만들 수 없으므로 None 반환.
    """
    coords = polyline_to_coords(pline)
    if len(coords) < 3:
        return None

    # shapely 는 좌표 리스트를 받아 자동으로 닫힌 polygon 을 만든다
    # (첫 좌표 == 마지막 좌표 가 아니어도 내부적으로 닫힘 처리).
    try:
        polygon = Polygon(coords)
    except Exception:
        return None

    # 자기교차·중복점 등으로 유효하지 않으면 buffer(0) 트릭으로 수리 시도.
    # (실무에서 의류 패턴은 깨끗한 경우가 대부분이지만 안전장치로 추가.)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        return None
    return polygon


def compute_geometry(polygon: Polygon) -> dict:
    """
    shapely Polygon 에서 둘레/면적/bbox/centroid 를 cm 단위로 계산.
    모든 숫자는 소수 2자리로 반올림해 가독성 향상.
    """
    minx, miny, maxx, maxy = polygon.bounds
    cx, cy = polygon.centroid.x, polygon.centroid.y

    return {
        "perimeter_cm": round(polygon.length * MM_TO_CM, 2),
        "area_cm2": round(polygon.area * MM2_TO_CM2, 2),
        "bbox_cm": [
            round(minx * MM_TO_CM, 2),
            round(miny * MM_TO_CM, 2),
            round(maxx * MM_TO_CM, 2),
            round(maxy * MM_TO_CM, 2),
        ],
        "width_cm": round((maxx - minx) * MM_TO_CM, 2),
        "height_cm": round((maxy - miny) * MM_TO_CM, 2),
        "centroid_cm": [round(cx * MM_TO_CM, 2), round(cy * MM_TO_CM, 2)],
    }


def extract_piece_info(block, piece_id: str) -> dict | None:
    """
    블록 하나에서 정보를 통합 추출.
    외곽선이 없거나 폴리곤 변환 실패 시 None → 호출자가 스킵 처리.
    """
    outline = find_outline(block)
    if outline is None:
        return None

    polygon = polyline_to_shapely(outline)
    if polygon is None:
        return None

    geometry = compute_geometry(polygon)
    metadata = parse_piece_metadata(block)
    # 식서 추출: 1) DXF LINE 마크 우선, 2) 없으면 bbox 비율로 자동 추정.
    grain = extract_grain(block, GRAIN_LAYER)
    if grain is None:
        grain = estimate_grain_from_bbox(geometry["width_cm"], geometry["height_cm"])

    # DXF 기록 면적과 우리가 계산한 면적의 오차(%) 산출.
    area_error_pct = None
    recorded = metadata["recorded_area_cm2"]
    if recorded is not None and recorded > 0:
        diff = geometry["area_cm2"] - recorded
        area_error_pct = round(abs(diff) / recorded * 100, 3)

    return {
        "piece_id": piece_id,
        "block_name": block.name,
        "piece_name": metadata["piece_name"],
        "size": metadata["size"],
        "quantity": metadata["quantity"],
        "material": metadata["material"],
        "perimeter_cm": geometry["perimeter_cm"],
        "area_cm2": geometry["area_cm2"],
        "bbox_cm": geometry["bbox_cm"],
        "width_cm": geometry["width_cm"],
        "height_cm": geometry["height_cm"],
        "centroid_cm": geometry["centroid_cm"],
        "recorded_area_cm2": recorded,
        "area_error_pct": area_error_pct,
        "grain": grain,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ 저장 함수                                                  ║
# ╚════════════════════════════════════════════════════════════╝
def save_csv(pieces: list[dict], path: Path) -> None:
    """
    CSV 저장. UTF-8 BOM(utf-8-sig) 으로 저장해 Windows 엑셀에서
    한글 헤더가 깨지지 않게 한다.
    """
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        # 한글 헤더 (TD 가 엑셀에서 바로 이해하기 쉽게).
        writer.writerow([
            "피스ID", "블록명", "피스명", "사이즈", "수량", "재질",
            "둘레_cm", "면적_cm2",
            "Xmin_cm", "Ymin_cm", "Xmax_cm", "Ymax_cm",
            "가로_cm", "세로_cm",
            "중심X_cm", "중심Y_cm",
            "기록면적_cm2", "면적오차_pct",
        ])

        for p in pieces:
            bb = p["bbox_cm"]
            cen = p["centroid_cm"]
            writer.writerow([
                p["piece_id"],
                p["block_name"],
                p["piece_name"],
                p["size"],
                "" if p["quantity"] is None else p["quantity"],
                p["material"],
                p["perimeter_cm"],
                p["area_cm2"],
                bb[0], bb[1], bb[2], bb[3],
                p["width_cm"], p["height_cm"],
                cen[0], cen[1],
                "" if p["recorded_area_cm2"] is None else p["recorded_area_cm2"],
                "" if p["area_error_pct"] is None else p["area_error_pct"],
            ])


def save_json(pieces: list[dict], path: Path) -> None:
    """
    JSON 저장. ensure_ascii=False 로 한글을 그대로 보존.
    들여쓰기 2칸 → 사람이 읽기 쉽게.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pieces, f, indent=2, ensure_ascii=False)


def save_log(summary_text: str, path: Path) -> None:
    """분석 로그 파일 저장 (단순 텍스트)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(summary_text)


# ╔════════════════════════════════════════════════════════════╗
# ║ 콘솔 출력                                                  ║
# ╚════════════════════════════════════════════════════════════╝
def _display_id(piece: dict) -> str:
    """piece_id 와 피스명을 합친 표시용 라벨. 피스명이 없으면 piece_id 만."""
    if piece["piece_name"]:
        return f"{piece['piece_id']} — {piece['piece_name']}"
    return piece["piece_id"]


def print_console_table(pieces: list[dict]) -> None:
    """요구된 컬럼으로 표 출력."""
    print("\n── 추출된 피스 정보 ──")
    header = (
        f"  {'피스ID':<28} | {'사이즈':>6} | {'수량':>4} | "
        f"{'둘레(cm)':>9} | {'면적(cm²)':>10} | "
        f"{'가로×세로(cm)':<18} | {'오차%':>7}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for p in pieces:
        label = _display_id(p)
        size = p["size"] if p["size"] else "-"
        qty = str(p["quantity"]) if p["quantity"] is not None else "-"
        err_str = f"{p['area_error_pct']:.3f}" if p["area_error_pct"] is not None else "  -"
        size_str = f"{p['width_cm']:.1f} × {p['height_cm']:.1f}"
        print(
            f"  {label:<28} | {size:>6} | {qty:>4} | "
            f"{p['perimeter_cm']:>9.1f} | {p['area_cm2']:>10.1f} | "
            f"{size_str:<18} | {err_str:>7}"
        )


# ╔════════════════════════════════════════════════════════════╗
# ║ 로그 본문 생성                                             ║
# ╚════════════════════════════════════════════════════════════╝
def build_log_text(pieces: list[dict], skipped: list[str], total_blocks: int) -> str:
    """analysis_log.txt 본문을 문자열로 만들어 반환."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append("DXF 피스 추출 분석 로그")
    lines.append("=" * 60)
    lines.append(f"실행 일시    : {now}")
    lines.append(f"입력 파일    : {DXF_FILE}")
    lines.append(f"사용자 블록  : {total_blocks} 개")
    lines.append(f"추출 성공    : {len(pieces)} 개")
    lines.append(f"스킵         : {len(skipped)} 개")
    if skipped:
        lines.append(f"스킵된 블록  : {', '.join(skipped)}")
    lines.append("")

    # 오차 검증 요약
    lines.append("── 오차 검증 ──")
    has_rec = [p for p in pieces if p["recorded_area_cm2"] is not None]
    lines.append(f"기록된 면적 보유 피스 : {len(has_rec)} / {len(pieces)}")

    if has_rec:
        errs = [p["area_error_pct"] for p in has_rec]
        lines.append(f"평균 오차율           : {sum(errs) / len(errs):.4f} %")
        lines.append(f"최대 오차율           : {max(errs):.4f} %")
        over = [p for p in has_rec if p["area_error_pct"] >= AREA_ERROR_WARN_PCT]
        lines.append(f"{AREA_ERROR_WARN_PCT}% 이상 오차 피스 수   : {len(over)}")
        if over:
            lines.append("  해당 피스:")
            for p in over:
                lines.append(
                    f"    - {p['piece_id']} ({p['block_name']}) : "
                    f"계산 {p['area_cm2']} vs 기록 {p['recorded_area_cm2']} "
                    f"→ 오차 {p['area_error_pct']:.3f}%"
                )
    else:
        lines.append("(DXF 내부에 Area 기록이 없어 오차 검증을 수행하지 못함)")
    lines.append("")

    # 피스별 상세
    lines.append("── 피스별 오차율 ──")
    for p in pieces:
        err = f"{p['area_error_pct']:.3f}%" if p["area_error_pct"] is not None else "(기록 없음)"
        label = _display_id(p)
        lines.append(f"  {label:<24} (블록 {p['block_name']:<3}) → {err}")

    return "\n".join(lines) + "\n"


# ╔════════════════════════════════════════════════════════════╗
# ║ 메인                                                       ║
# ╚════════════════════════════════════════════════════════════╝
def main() -> None:
    # output 폴더를 (없으면) 생성. parents=True, exist_ok=True → 안전.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"피스 정보 추출 시작: {DXF_FILE.name}")
    print("=" * 70)

    doc = open_dxf(DXF_FILE)
    if doc is None:
        print("[중단] DXF 를 열 수 없어 종료.")
        return

    # 식서 LAYER 1회 식별 → 모듈 전역 GRAIN_LAYER 캐시.
    detected = init_grain_layer(doc)
    print(f"[식서 LAYER] 자동 식별 결과: {detected!r}")

    # 사용자 블록만 (시스템 블록 * 시작 제외).
    user_blocks = [b for b in doc.blocks if not b.name.startswith("*")]

    # piece_id 를 "숫자 이름 오름차순" 으로 부여하려고 블록을 정렬.
    try:
        user_blocks.sort(key=lambda b: int(b.name))
    except ValueError:
        # 숫자 아닌 블록명(예: "SLV_01")이 섞이면 문자열 정렬로 대체.
        user_blocks.sort(key=lambda b: b.name)

    pieces: list[dict] = []
    skipped: list[str] = []

    for i, block in enumerate(user_blocks, start=1):
        piece_id = f"P{i:03d}"   # P001, P002, ...
        info = extract_piece_info(block, piece_id)

        if info is None:
            print(f"[경고] 블록 '{block.name}' → 닫힌 POLYLINE 없음, 스킵")
            skipped.append(block.name)
            continue

        pieces.append(info)

        # 면적 오차가 임계치 이상이면 즉시 경고.
        if (info["area_error_pct"] is not None
                and info["area_error_pct"] >= AREA_ERROR_WARN_PCT):
            print(
                f"[경고] {piece_id} ({block.name}) 면적 오차 "
                f"{info['area_error_pct']:.3f}% "
                f"(계산 {info['area_cm2']} cm² vs 기록 {info['recorded_area_cm2']} cm²)"
            )

    # 콘솔 표
    print_console_table(pieces)

    # 파일 저장
    save_csv(pieces, CSV_PATH)
    save_json(pieces, JSON_PATH)
    log_text = build_log_text(pieces, skipped, len(user_blocks))
    save_log(log_text, LOG_PATH)

    print("\n── 저장 결과 ──")
    print(f"  CSV  : {CSV_PATH}")
    print(f"  JSON : {JSON_PATH}")
    print(f"  LOG  : {LOG_PATH}")

    print("\n" + "=" * 70)
    print("추출 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
