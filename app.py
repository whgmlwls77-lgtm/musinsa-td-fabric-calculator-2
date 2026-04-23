# -*- coding: utf-8 -*-
"""
app.py (V3) — 원단 요척 산출 시스템 · 풀 그레이딩 지원
------------------------------------------------------
V2 → V3 주요 변경:
  1) CP949 인코딩 깨짐 자동 복원 (SuperALPHA_Plus · Gerber 계열)
  2) 사이즈 자동 감지 (BLK_X_Y 패턴 + SIZE: 메타)
  3) 가장 큰 닫힌 POLYLINE 을 외곽선으로 선택 (완성선/재단선 혼재 시 재단선 채택)
  4) ANNOTATION 기반 재질 분류 ("안감패턴" 등 한글 주석 인식)
  5) 사이즈 선택 UI (단일/복수/전체)
  6) 사이즈별 계산 + 표 형태 결과
  7) PDF/Excel 에 사이즈 차원 추가
"""

# ── 표준 ───────────────────────────────────────────────────────
import io
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── 외부 ──────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
import ezdxf
from ezdxf import recover as ezrecover
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Patch
from shapely.geometry import Polygon as ShapelyPolygon

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Excel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ── 기존 스크립트(V3 에서 저수준만 재사용) ────────────────────
from extract_pieces import (
    polyline_to_shapely,
    polyline_to_coords,
    is_closed_poly,
    MM_TO_CM,
    MM2_TO_CM2,
)


# ╔════════════════════════════════════════════════════════════╗
# ║ 상수                                                       ║
# ╚════════════════════════════════════════════════════════════╝
st.set_page_config(
    page_title="원단 요척 산출 시스템",
    page_icon="📐",
    layout="wide",
)

# ───────────────────────────────────────────────────────────────
# 커스텀 CSS — 미니멀 모노 + 라이트그레이 + 빨강 강조
# ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: "Pretendard", "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
    color: #0f172a;
    -webkit-font-smoothing: antialiased;
}
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1100px;
}
header[data-testid="stHeader"] { background: transparent; }
h1 {
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.02em;
    margin-bottom: 0.3rem;
}
h2, h3, h4 {
    font-weight: 600;
    color: #1e293b;
    margin-top: 2rem !important;
    letter-spacing: -0.01em;
}
hr {
    margin: 1.5rem 0;
    border: none;
    border-top: 1px solid #e2e8f0;
}
[data-testid="stMetric"] {
    background: #f8fafc;
    padding: 1.25rem 1.5rem;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
}
[data-testid="stMetricLabel"] {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    color: #0f172a;
    font-weight: 700;
    font-size: 1.75rem;
}
.stButton button[kind="primary"] {
    background: #dc2626;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.6rem 1.5rem;
    font-weight: 600;
    transition: background 0.15s;
}
.stButton button[kind="primary"]:hover {
    background: #b91c1c;
}
.stButton button:not([kind="primary"]) {
    border: 1px solid #cbd5e0;
    color: #334155;
    border-radius: 6px;
    background: white;
    font-weight: 500;
}
[data-testid="stDownloadButton"] button {
    background: white;
    color: #0f172a;
    border: 1px solid #cbd5e0;
    border-radius: 6px;
    font-weight: 500;
}
[data-testid="stFileUploader"] section {
    border: 2px dashed #cbd5e0;
    border-radius: 10px;
    padding: 1.5rem;
    background: #f8fafc;
}
.stNumberInput input, .stTextInput input {
    border-radius: 6px;
    border: 1px solid #cbd5e0;
}
.stAlert {
    border-radius: 8px;
    border-left-width: 3px;
}
.stDataFrame {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

plt.rcParams["font.family"] = ["Noto Sans KR", "AppleGothic", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

MATERIAL_COLORS_V2: dict[str, str] = {
    "주원단":   "#d0d0d0",
    "심지":     "#a0c0e0",
    "안감":     "#f0e090",
    "배색":     "#f4b0c0",
    "주머니감": "#c0e0a0",
}
DEFAULT_FABRIC_COLOR = "#c0c0c0"

DEFAULT_WIDTHS: dict[str, int] = {
    "주원단":   150,
    "심지":     110,
    "안감":     150,
    "배색":     150,
    "주머니감": 110,
}

# 사이즈 정렬용 (표준 의류 사이즈).
SIZE_ORDER: dict[str, int] = {
    "XXS": 0, "XS": 1, "S": 2, "M": 3, "L": 4,
    "XL": 5, "XXL": 6, "XXXL": 7,
}

M_TO_YD = 1.0936
CM_TO_INCH = 1.0 / 2.54

# BLK_X_Y 패턴 — SuperALPHA_Plus / Gerber 등이 쓰는 블록 명명 규칙.
BLK_PATTERN = re.compile(r"^BLK_(\d+)_(\d+)$", re.IGNORECASE)

# 한글 유니코드 범위.
_HANGUL_RE = re.compile(r"[가-힣]")


# ╔════════════════════════════════════════════════════════════╗
# ║ 한글 폰트 등록 (PDF 용) — 세션당 1회                       ║
# ╚════════════════════════════════════════════════════════════╝
_FONT_CANDIDATES = [
    # 1) 프로젝트 동봉 폰트 (있으면 우선) — 로컬/배포 어디든
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "NotoSansKR-Regular.ttf"),
    # 2) Linux — Streamlit Cloud 에서 packages.txt 로 설치
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # 3) macOS 시스템 폰트 (로컬 개발용 폴백)
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
]


@st.cache_resource(show_spinner=False)
def register_korean_font() -> str:
    """한글 폰트 등록 (TTF / TTC / OTF 지원)."""
    for path in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            if path.endswith(".ttc"):
                # TrueType Collection — subfontIndex=0 로 첫 서브폰트 사용
                pdfmetrics.registerFont(TTFont("KRFont", path, subfontIndex=0))
            else:
                # .ttf / .otf
                pdfmetrics.registerFont(TTFont("KRFont", path))
            return "KRFont"
        except Exception:
            continue
    return "Helvetica"


KR_FONT = register_korean_font()


# ╔════════════════════════════════════════════════════════════╗
# ║ CP949 복원 유틸                                            ║
# ╚════════════════════════════════════════════════════════════╝
def restore_korean_encoding(text: str) -> str:
    """
    ezdxf 가 CP949 DXF 를 UTF-8 로 잘못 디코드했을 때 원복 시도.
    latin1 로 다시 인코딩 후 cp949 로 디코드하면 복원된다.
    실패하면 원본 그대로 반환.
    """
    try:
        return text.encode("latin1").decode("cp949")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _has_korean(text: str) -> bool:
    return bool(_HANGUL_RE.search(text))


def maybe_restore_korean(text: str) -> str:
    """
    텍스트가 이미 한글을 포함하면 그대로,
    아니면 CP949 복원을 시도해 한글이 나오면 복원본 반환.
    """
    if not text:
        return text
    if _has_korean(text):
        return text
    try:
        restored = text.encode("latin1").decode("cp949")
        if _has_korean(restored):
            return restored
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return text


# ╔════════════════════════════════════════════════════════════╗
# ║ 외곽선 선택 — 가장 큰 닫힌 POLYLINE                        ║
# ╚════════════════════════════════════════════════════════════╝
def find_outline_largest(block):
    """
    블록 내부의 닫힌 POLYLINE / LWPOLYLINE 중 면적이 가장 큰 것 반환.
    없으면 None. (한 피스에 완성선·재단선 두 개가 그려져 있을 때
    요척 계산은 더 큰 쪽인 재단선이 맞다.)
    """
    candidates = []
    for entity in block:
        if entity.dxftype() not in ("POLYLINE", "LWPOLYLINE"):
            continue
        if not is_closed_poly(entity):
            continue
        poly = polyline_to_shapely(entity)
        if poly is None or poly.is_empty or not poly.is_valid:
            continue
        candidates.append((poly.area, entity))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


# ╔════════════════════════════════════════════════════════════╗
# ║ 블록 메타 파싱 (V3)                                        ║
# ╚════════════════════════════════════════════════════════════╝
def parse_block_metadata_v3(block) -> dict:
    """
    블록 내부 TEXT 를 훑어 메타를 dict 로 반환.
    CP949 복원을 모든 텍스트에 시도 + ANNOTATION 리스트 수집.

    반환:
      {
        piece_name, size, quantity, material (원문 코드),
        annotations: [str, ...]
      }
    """
    meta = {
        "piece_name": "",
        "size": "",
        "quantity": None,
        "material": "",
        "annotations": [],
    }

    for entity in block:
        if entity.dxftype() != "TEXT":
            continue
        raw = entity.dxf.text.strip()
        text = maybe_restore_korean(raw)

        if ":" not in text:
            continue
        key_raw, _, value = text.partition(":")
        key = key_raw.strip().lower()
        value = value.strip()

        if key == "piece name":
            meta["piece_name"] = value
        elif key == "size":
            meta["size"] = value
        elif key == "quantity":
            try:
                meta["quantity"] = int(value)
            except ValueError:
                # "2 pcs" 같은 경우 첫 토큰만.
                try:
                    meta["quantity"] = int(value.split()[0])
                except (ValueError, IndexError):
                    pass
        elif key == "material":
            meta["material"] = value
        elif key == "annotation":
            if value:
                meta["annotations"].append(value)

    return meta


# ╔════════════════════════════════════════════════════════════╗
# ║ 재질 분류 (ANNOTATION 파싱 강화)                           ║
# ╚════════════════════════════════════════════════════════════╝
def infer_material_v3(
    piece_name: str,
    material_raw: str,
    annotations: list[str],
) -> str:
    """
    V3 우선순위:
      1. ANNOTATION 에 한글 재질 키워드
         "안감" → 안감, "심지" → 심지, "배색" → 배색, "주머니"/"포켓" → 주머니감
      2. 피스 이름 키워드 (V2 와 동일)
      3. DXF material 코드 (FN/IL/1)
      4. 기본 → 주원단
    """
    # 1) ANNOTATION 검사 (우선순위 최상 — 파일에 명시된 의도).
    ann_joined = " ".join(annotations).lower()
    ann_original = " ".join(annotations)  # 한글 확인용 (원문)

    if "안감" in ann_original:
        return "안감"
    if "심지" in ann_original:
        return "심지"
    if "배색" in ann_original:
        return "배색"
    if "주머니" in ann_original or "포켓" in ann_original or "pocket" in ann_joined:
        return "주머니감"

    # 2) 피스 이름 (V2 로직 유지).
    name = piece_name or ""
    name_lower = name.lower()
    if "심지" in name or name.startswith("심지_"):
        return "심지"
    if "안감" in name or "lining" in name_lower:
        return "안감"
    if "배색" in name:
        return "배색"
    if "주머니" in name or "pocket" in name_lower:
        return "주머니감"

    # 3) DXF 재질 코드.
    code = (material_raw or "").strip()
    if code == "FN":
        return "심지"
    if code == "IL":
        return "안감"
    if code == "1" or code == "":
        return "주원단"

    return "주원단"


# ╔════════════════════════════════════════════════════════════╗
# ║ 스케일 박스 판정 (V2 와 동일)                              ║
# ╚════════════════════════════════════════════════════════════╝
def is_scale_box(bbox_cm, coords_cm) -> bool:
    xmin, ymin, xmax, ymax = bbox_cm
    w = xmax - xmin
    h = ymax - ymin
    if not (49.0 <= w <= 51.0) or not (49.0 <= h <= 51.0):
        return False
    if abs(w - h) > 1.0:
        return False
    try:
        poly = ShapelyPolygon(coords_cm)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return False
        hull = poly.convex_hull
        if hull.area == 0:
            return False
        return (poly.area / hull.area) >= 0.95
    except Exception:
        return False


# ╔════════════════════════════════════════════════════════════╗
# ║ 스타일/샘플사이즈 추출 (모델스페이스 TEXT)                 ║
# ╚════════════════════════════════════════════════════════════╝
def get_style_info_v3(doc) -> tuple[str, str]:
    style = ""
    sample_size = ""
    for text in doc.modelspace().query("TEXT"):
        content = maybe_restore_korean(text.dxf.text.strip())
        low = content.lower()
        if low.startswith("style name:"):
            _, _, value = content.partition(":")
            tokens = value.strip().split()
            if tokens:
                style = tokens[0]
        elif low.startswith("sample size:"):
            _, _, value = content.partition(":")
            sample_size = value.strip()
    return style, sample_size


# ╔════════════════════════════════════════════════════════════╗
# ║ 사이즈 감지                                                ║
# ╚════════════════════════════════════════════════════════════╝
def _size_sort_key(size: str) -> tuple:
    """사이즈 정렬용 — 표준 영문 사이즈 순서 → 숫자 → 알파벳."""
    s = (size or "").upper().strip()
    if s in SIZE_ORDER:
        return (0, SIZE_ORDER[s])
    # 숫자로 된 사이즈(예: "44", "55") 숫자 순.
    try:
        return (1, int(s))
    except ValueError:
        return (2, s)


def detect_sizes(doc) -> dict:
    """
    DXF 에서 고유 사이즈 + 피스-사이즈 매핑 + 샘플사이즈 정보.
    반환:
      {
        'sizes': [사이즈 정렬된 list],
        'piece_groups': { piece_id → { size → block_name } },
        'sample_size': 'S' 또는 None,
        'is_full_grading': bool,
        'detection_method': 'BLK_PATTERN' | 'SIZE_META' | 'SINGLE',
      }
    """
    user_blocks = [b for b in doc.blocks if not b.name.startswith("*")]

    _, sample_size = get_style_info_v3(doc)

    # (1) 블록별 SIZE 메타 읽어두기.
    size_by_block: dict[str, str] = {}
    for b in user_blocks:
        for e in b:
            if e.dxftype() != "TEXT":
                continue
            t = maybe_restore_korean(e.dxf.text.strip())
            if t.lower().startswith("size:"):
                _, _, v = t.partition(":")
                size_by_block[b.name] = v.strip()
                break

    # (2) BLK_X_Y 패턴 매칭.
    pattern_hits: dict[str, tuple[int, int]] = {}
    for b in user_blocks:
        m = BLK_PATTERN.match(b.name)
        if m:
            pattern_hits[b.name] = (int(m.group(1)), int(m.group(2)))

    # 결과 구조 초기화.
    piece_groups: dict[str, dict[str, str]] = defaultdict(dict)
    method = "SINGLE"

    if pattern_hits and len(pattern_hits) == len(user_blocks):
        # 전 블록이 BLK_X_Y — 사이즈 인덱스 → 사이즈명 맵 구축.
        idx_to_size: dict[int, str] = {}
        for bn, (_piece, idx) in pattern_hits.items():
            if bn in size_by_block and idx not in idx_to_size:
                idx_to_size[idx] = size_by_block[bn]

        # 메타에서 못 얻은 인덱스는 "Size{idx}" 로.
        for bn, (piece, idx) in pattern_hits.items():
            size_name = size_by_block.get(bn) or idx_to_size.get(idx) or f"Size{idx}"
            piece_groups[f"piece_{piece}"][size_name] = bn

        method = "BLK_PATTERN"

    elif size_by_block:
        # 패턴 없지만 SIZE: 메타가 블록별로 있음 — piece_name 으로 그룹핑.
        # 같은 piece_name + 다른 size 를 같은 피스의 사이즈 그룹으로.
        piece_name_by_block: dict[str, str] = {}
        for b in user_blocks:
            meta = parse_block_metadata_v3(b)
            piece_name_by_block[b.name] = meta["piece_name"] or b.name

        # piece_name → {size → block_name}
        by_pn: dict[str, dict[str, str]] = defaultdict(dict)
        for bn, pn in piece_name_by_block.items():
            sz = size_by_block.get(bn) or "ALL"
            by_pn[pn][sz] = bn

        for pn, group in by_pn.items():
            piece_groups[pn] = group

        method = "SIZE_META"

    else:
        # 사이즈 정보 없음 — 단일 사이즈(샘플 또는 'ALL') 로 취급.
        sz_fallback = sample_size or "ALL"
        for b in user_blocks:
            piece_groups[b.name] = {sz_fallback: b.name}
        method = "SINGLE"

    # 고유 사이즈 집합 + 정렬.
    all_sizes = set()
    for g in piece_groups.values():
        all_sizes.update(g.keys())
    sizes_sorted = sorted(all_sizes, key=_size_sort_key)

    return {
        "sizes": sizes_sorted,
        "piece_groups": dict(piece_groups),
        "sample_size": sample_size or None,
        "is_full_grading": len(sizes_sorted) > 1,
        "detection_method": method,
    }


# ╔════════════════════════════════════════════════════════════╗
# ║ DXF 파싱 (V3) — 캐시                                        ║
# ╚════════════════════════════════════════════════════════════╝
@st.cache_data(show_spinner=False)
def parse_dxf_v3(file_bytes: bytes, file_name: str) -> dict:
    """
    반환:
      {
        'pieces': [...],     # 각 피스(사이즈별로 별개 엔트리)
        'excluded': [...],   # 스케일 박스
        'style': str,
        'sample_size': str,
        'sizes': [...],      # 전체 사이즈
        'is_full_grading': bool,
        'detection_method': str,
        'error': None | str,
      }

    각 피스 dict:
      piece_id, piece_key, block_name, size, piece_name,
      material_raw, material_inferred, annotations,
      quantity, area_cm2, width_cm, height_cm,
      bbox_cm, centroid_cm, coords_cm
    """
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        try:
            doc = ezdxf.readfile(str(tmp_path))
        except ezdxf.DXFStructureError:
            doc, _ = ezrecover.readfile(str(tmp_path))
        except Exception as e:
            return {"error": f"DXF 파싱 실패: {e}",
                    "pieces": [], "excluded": [], "style": "",
                    "sample_size": "", "sizes": [], "is_full_grading": False,
                    "detection_method": "ERROR"}

        style, sample_size = get_style_info_v3(doc)
        size_info = detect_sizes(doc)

        pieces: list[dict] = []
        excluded: list[dict] = []
        pid_counter = 0

        # piece_key(예: piece_1 혹은 piece_name) 오름차순.
        def _pk_sort(pk: str):
            m = re.match(r"piece_(\d+)", pk)
            if m:
                return (0, int(m.group(1)))
            return (1, pk)

        piece_keys_sorted = sorted(size_info["piece_groups"].keys(), key=_pk_sort)

        for piece_key in piece_keys_sorted:
            size_map = size_info["piece_groups"][piece_key]
            # 사이즈 오름차순.
            for size in sorted(size_map.keys(), key=_size_sort_key):
                block_name = size_map[size]
                try:
                    block = doc.blocks[block_name]
                except Exception:
                    continue

                outline = find_outline_largest(block)
                if outline is None:
                    continue

                polygon = polyline_to_shapely(outline)
                if polygon is None or polygon.is_empty:
                    continue
                if not polygon.is_valid:
                    polygon = polygon.buffer(0)
                    if polygon.is_empty:
                        continue

                meta = parse_block_metadata_v3(block)

                # 좌표(cm).
                coords_mm = list(polygon.exterior.coords)
                coords_cm = [(x * MM_TO_CM, y * MM_TO_CM) for x, y in coords_mm]

                minx, miny, maxx, maxy = polygon.bounds
                bbox_cm = (
                    minx * MM_TO_CM, miny * MM_TO_CM,
                    maxx * MM_TO_CM, maxy * MM_TO_CM,
                )
                w_cm = bbox_cm[2] - bbox_cm[0]
                h_cm = bbox_cm[3] - bbox_cm[1]
                centroid_cm = (
                    polygon.centroid.x * MM_TO_CM,
                    polygon.centroid.y * MM_TO_CM,
                )

                # 스케일 박스 필터.
                if is_scale_box(bbox_cm, coords_cm):
                    excluded.append({
                        "block_name": block_name,
                        "piece_name": meta["piece_name"],
                        "size": size,
                        "bbox_cm": bbox_cm,
                    })
                    continue

                pid_counter += 1
                material_inf = infer_material_v3(
                    meta["piece_name"], meta["material"], meta["annotations"],
                )

                pieces.append({
                    "piece_id": f"P{pid_counter:03d}",
                    "piece_key": piece_key,
                    "block_name": block_name,
                    "size": size,
                    "piece_name": meta["piece_name"] or "",
                    "material_raw": meta["material"] or "",
                    "material_inferred": material_inf,
                    "annotations": meta["annotations"],
                    "quantity": meta["quantity"],
                    "area_cm2": polygon.area * MM2_TO_CM2,
                    "width_cm": w_cm,
                    "height_cm": h_cm,
                    "bbox_cm": bbox_cm,
                    "centroid_cm": centroid_cm,
                    "coords_cm": coords_cm,
                })

        return {
            "pieces": pieces,
            "excluded": excluded,
            "style": style,
            "sample_size": size_info["sample_size"] or "",
            "sizes": size_info["sizes"],
            "is_full_grading": size_info["is_full_grading"],
            "detection_method": size_info["detection_method"],
            "error": None,
        }
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ╔════════════════════════════════════════════════════════════╗
# ║ UI — 업로드 + 자동 분석                                    ║
# ╚════════════════════════════════════════════════════════════╝
def upload_section() -> dict | None:
    st.markdown("#### 파일 업로드")
    uploaded = st.file_uploader("DXF 파일을 선택하세요", type=["dxf"])

    if uploaded is None:
        st.info("👆 DXF 파일을 업로드하면 자동으로 분석이 시작됩니다.")
        return None

    with st.spinner("DXF 파싱 중..."):
        parsed = parse_dxf_v3(uploaded.getvalue(), uploaded.name)

    if parsed.get("error"):
        st.error(f"❌ {parsed['error']}")
        return None
    if not parsed["pieces"]:
        st.warning("⚠️ 계산 가능한 피스가 없습니다.")
        return None

    parsed["file_name"] = uploaded.name

    # 풀 그레이딩 여부 표시.
    if parsed["is_full_grading"]:
        st.success(
            f"✅ **{uploaded.name}**  \n"
            f"📊 **풀 그레이딩 파일** ({len(parsed['sizes'])} 사이즈 감지: "
            f"{', '.join(parsed['sizes'])})  \n"
            f"📌 샘플 사이즈: **{parsed['sample_size'] or '?'}** "
            f"{'(권장 기준)' if parsed['sample_size'] else ''}  \n"
            f"스타일: **{parsed['style'] or '?'}**"
        )
    else:
        sz = parsed["sizes"][0] if parsed["sizes"] else "-"
        st.success(
            f"✅ **{uploaded.name}**  \n"
            f"스타일: **{parsed['style'] or '?'}** / 사이즈: **{sz}**"
        )

    # 자동 분류 집계 (사이즈별 피스 수 + 재질 분포).
    # 피스의 고유 개수 = unique piece_key 수.
    unique_pieces = {p["piece_key"] for p in parsed["pieces"]}
    total_piece_entries = len(parsed["pieces"])

    ex_info = ""
    if parsed["excluded"]:
        ex_info = f" · 스케일박스 {len(parsed['excluded'])}개 자동 제외"

    st.caption(
        f"피스 **{len(unique_pieces)}종** × 사이즈 **{len(parsed['sizes'])}개** = "
        f"총 {total_piece_entries}개 엔트리 추출{ex_info}  \n"
        f"감지 방식: `{parsed['detection_method']}`"
    )

    # 재질 분포 (샘플사이즈 또는 첫 사이즈 기준).
    ref_size = parsed["sample_size"] or (parsed["sizes"][0] if parsed["sizes"] else None)
    if ref_size:
        ref_pieces = [p for p in parsed["pieces"] if p["size"] == ref_size]
        counts: dict[str, int] = {}
        for p in ref_pieces:
            counts[p["material_inferred"]] = counts.get(p["material_inferred"], 0) + 1
        order = ["주원단", "심지", "안감", "배색", "주머니감"]
        parts = [f"{m}: {counts[m]}개" for m in order if m in counts]
        extras = sum(c for m, c in counts.items() if m not in order)
        if extras:
            parts.append(f"기타: {extras}개")
        if parts:
            st.caption(f"자동 분류 (사이즈 {ref_size} 기준) — " + " | ".join(parts))

    return parsed


# ╔════════════════════════════════════════════════════════════╗
# ║ UI — 사이즈 선택 섹션                                      ║
# ╚════════════════════════════════════════════════════════════╝
def size_selection_section(parsed: dict) -> list[str]:
    """
    풀 그레이딩일 때만 UI 표시.
    단일 사이즈 파일이면 그대로 반환 (섹션 숨김).
    """
    sizes = parsed["sizes"]
    if not parsed["is_full_grading"]:
        return sizes  # 단일 사이즈

    st.markdown("#### 계산할 사이즈 선택")

    sample = parsed.get("sample_size")
    default_single = sample if sample in sizes else sizes[0]
    default_multi = [sample] if sample in sizes else [sizes[0]]

    mode = st.radio(
        "모드",
        options=["단일 사이즈", "복수 선택", "전체 사이즈"],
        index=0,
        horizontal=True,
        key="size_mode",
    )

    if mode == "단일 사이즈":
        selected = [st.selectbox(
            "사이즈",
            options=sizes,
            index=sizes.index(default_single),
            key="size_single",
        )]
    elif mode == "복수 선택":
        selected = st.multiselect(
            "사이즈 선택",
            options=sizes,
            default=default_multi,
            key="size_multi",
        )
    else:
        selected = list(sizes)

    if not selected:
        st.warning("⚠️ 최소 한 사이즈는 선택해야 합니다.")
        return [default_single]

    st.caption(f"계산 대상 사이즈: **{', '.join(selected)}** ({len(selected)}개)")
    return selected


# ╔════════════════════════════════════════════════════════════╗
# ║ UI — 원단 폭 입력 + 부속원단 (V2 기반)                     ║
# ╚════════════════════════════════════════════════════════════╝
def width_section(pieces: list[dict], selected_sizes: list[str]) -> dict[str, float]:
    st.markdown("#### 원단 폭")

    # 선택된 사이즈에 등장하는 재질만 입력창 표시.
    relevant = [p for p in pieces if p["size"] in selected_sizes]
    detected = {p["material_inferred"] for p in relevant}
    order = ["주원단", "심지", "안감", "배색", "주머니감"]

    widths: dict[str, float] = {}
    cols = st.columns(2)
    col_idx = 0

    for mat in order:
        if mat not in detected:
            continue
        with cols[col_idx % 2]:
            widths[mat] = float(st.number_input(
                f"{mat} 폭 (cm)",
                min_value=30, max_value=300,
                value=int(DEFAULT_WIDTHS.get(mat, 150)),
                step=1,
                key=f"width_{mat}",
            ))
        col_idx += 1

    for mat in sorted(detected - set(order)):
        with cols[col_idx % 2]:
            widths[mat] = float(st.number_input(
                f"{mat} 폭 (cm)",
                min_value=30, max_value=300, value=150, step=1,
                key=f"width_extra_{mat}",
            ))
        col_idx += 1

    # 부속원단 추가.
    if "accessory_fabrics" not in st.session_state:
        st.session_state.accessory_fabrics = []

    with st.expander("➕ 부속원단 추가", expanded=False):
        st.caption("일부 피스를 별도 원단으로 재단하려면 여기서 추가하세요.")

        c1, c2 = st.columns([2, 1])
        new_name = c1.text_input("부속원단 이름", placeholder="예: 배색 스트라이프",
                                 key="acc_name_input")
        new_width = c2.number_input("폭 (cm)", min_value=30, max_value=300,
                                    value=110, step=1, key="acc_width_input")

        opts = [
            f"{p['piece_id']} — {p['piece_name'] or '(이름 없음)'}  [{p['material_inferred']}] · {p['size']}"
            for p in relevant
        ]
        selected_pieces = st.multiselect(
            "이 원단에 포함할 피스", opts, key="acc_pieces_input",
        )
        if st.button("추가", key="acc_add_btn"):
            if not new_name.strip():
                st.warning("이름을 입력하세요.")
            elif not selected_pieces:
                st.warning("피스를 선택하세요.")
            else:
                ids = [s.split(" — ")[0] for s in selected_pieces]
                st.session_state.accessory_fabrics.append({
                    "name": new_name.strip(),
                    "width": float(new_width),
                    "piece_ids": ids,
                })
                st.rerun()

        if st.session_state.accessory_fabrics:
            st.write("**추가된 부속원단**")
            for i, af in enumerate(st.session_state.accessory_fabrics):
                a1, a2 = st.columns([4, 1])
                a1.write(f"• **{af['name']}** ({af['width']:.0f}cm) — {len(af['piece_ids'])}개")
                if a2.button("🗑️", key=f"del_af_{i}"):
                    st.session_state.accessory_fabrics.pop(i)
                    st.rerun()

    for af in st.session_state.get("accessory_fabrics", []):
        widths[af["name"]] = float(af["width"])

    return widths


def apply_accessory_overrides(pieces, accessories):
    if not accessories:
        return pieces
    override = {}
    for af in accessories:
        for pid in af["piece_ids"]:
            override[pid] = af["name"]
    updated = []
    for p in pieces:
        if p["piece_id"] in override:
            p2 = dict(p)
            p2["material_inferred"] = override[p["piece_id"]]
            updated.append(p2)
        else:
            updated.append(p)
    return updated


# ╔════════════════════════════════════════════════════════════╗
# ║ UI — 효율                                                  ║
# ╚════════════════════════════════════════════════════════════╝
def efficiency_section() -> float:
    st.markdown("#### 마커 효율")
    pct = st.slider("마커 효율 (%)", 60, 95, 80, step=1)
    return pct / 100.0


# ╔════════════════════════════════════════════════════════════╗
# ║ 계산                                                       ║
# ╚════════════════════════════════════════════════════════════╝
def _calc_one_size(pieces_one_size, widths, efficiency) -> list[dict]:
    """한 사이즈에 속한 피스들을 받아 재질별 요척 결과 계산."""
    groups: dict[str, list[dict]] = {}
    for p in pieces_one_size:
        groups.setdefault(p["material_inferred"], []).append(p)

    base_order = ["주원단", "심지", "안감", "배색", "주머니감"]
    mats_sorted = [m for m in base_order if m in groups]
    mats_sorted += sorted(m for m in groups if m not in base_order)

    results = []
    for mat in mats_sorted:
        ps = groups[mat]
        net_cm2 = sum(
            p["area_cm2"] * (p["quantity"] if p["quantity"] is not None else 1)
            for p in ps
        )
        net_m2 = net_cm2 / 10000.0
        gross_m2 = net_m2 / efficiency if efficiency > 0 else 0.0
        width = widths.get(mat, 150.0)
        len_m = gross_m2 * 100.0 / width if width > 0 else 0.0
        len_yd = len_m * M_TO_YD
        results.append({
            "name": mat,
            "net_area_m2": net_m2,
            "gross_area_m2": gross_m2,
            "width_cm": width,
            "length_m": len_m,
            "length_yd": len_yd,
            "piece_count": len(ps),
            "total_qty": sum((p["quantity"] or 1) for p in ps),
            "efficiency": efficiency,
        })
    return results


def calculate_by_sizes(
    pieces_all: list[dict],
    selected_sizes: list[str],
    widths: dict[str, float],
    efficiency: float,
) -> dict[str, list[dict]]:
    """사이즈별로 분리 계산. {size → fabric_results list}."""
    out = {}
    for size in selected_sizes:
        subset = [p for p in pieces_all if p["size"] == size]
        out[size] = _calc_one_size(subset, widths, efficiency)
    return out


# ╔════════════════════════════════════════════════════════════╗
# ║ 결과 표시                                                  ║
# ╚════════════════════════════════════════════════════════════╝
def results_section(results_by_size: dict[str, list[dict]]) -> None:
    st.markdown("#### 원단별 요척")

    if not results_by_size:
        st.warning("결과가 없습니다.")
        return

    # 단일 사이즈: V2 와 동일한 metric 카드.
    if len(results_by_size) == 1:
        size, results = next(iter(results_by_size.items()))
        st.caption(f"사이즈: **{size}**")
        PER_ROW = 3
        for start in range(0, len(results), PER_ROW):
            row = results[start:start + PER_ROW]
            cols = st.columns(PER_ROW)
            for i, r in enumerate(row):
                with cols[i]:
                    st.metric(
                        r["name"],
                        f"{r['length_yd']:.2f} yd",
                        f"{r['length_m']:.2f} m  (폭 {r['width_cm']:.0f}cm)",
                    )
                    st.caption(
                        f"피스 {r['piece_count']}종 / 총 면적 {r['gross_area_m2']:.2f} m² / 효율 {r['efficiency']:.0%}"
                    )
        return

    # 복수 사이즈: 표 형태 + 원단별 컬럼.
    all_materials = []
    for results in results_by_size.values():
        for r in results:
            if r["name"] not in all_materials:
                all_materials.append(r["name"])

    # 행: 사이즈, 열: 재질 → "X.XX yd"
    rows = []
    for size, results in results_by_size.items():
        by_mat = {r["name"]: r for r in results}
        row = {"사이즈": size}
        for m in all_materials:
            r = by_mat.get(m)
            row[m] = f"{r['length_yd']:.2f} yd" if r else "-"
        rows.append(row)
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # 상세(미터+폭) 펼치기.
    with st.expander("📊 상세 — 사이즈별 미터/폭/면적"):
        detail_rows = []
        for size, results in results_by_size.items():
            for r in results:
                detail_rows.append({
                    "사이즈": size,
                    "원단": r["name"],
                    "폭(cm)": int(r["width_cm"]),
                    "길이(yd)": round(r["length_yd"], 2),
                    "길이(m)": round(r["length_m"], 2),
                    "면적(m²)": round(r["gross_area_m2"], 3),
                    "피스종": r["piece_count"],
                    "효율": f"{r['efficiency']:.0%}",
                })
        st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)


# ╔════════════════════════════════════════════════════════════╗
# ║ 피스 프리뷰 (기준 사이즈만)                                ║
# ╚════════════════════════════════════════════════════════════╝
def build_grid_figure(pieces: list[dict], cols: int = 4) -> plt.Figure:
    n = len(pieces)
    if n == 0:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "피스 없음", ha="center", va="center")
        ax.axis("off")
        return fig

    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.2, rows * 3.2))

    axes_flat = [axes] if rows == 1 and cols == 1 else (
        axes.flatten() if hasattr(axes, "flatten") else [axes]
    )

    for ax, p in zip(axes_flat, pieces):
        coords = p["coords_cm"]
        cx = sum(x for x, _ in coords) / len(coords)
        cy = sum(y for _, y in coords) / len(coords)
        centered = [(x - cx, y - cy) for x, y in coords]
        color = MATERIAL_COLORS_V2.get(p["material_inferred"], DEFAULT_FABRIC_COLOR)
        ax.add_patch(MplPolygon(
            centered, closed=True,
            facecolor=color, edgecolor="#444444",
            linewidth=1.1, alpha=0.8,
        ))
        parts = [p["piece_id"]]
        if p["piece_name"]:
            parts.append(p["piece_name"])
        ax.set_title(" — ".join(parts), fontsize=9, pad=4)
        ax.set_xlabel(
            f"{p['width_cm']:.0f} × {p['height_cm']:.0f} cm  ·  {p['material_inferred']}",
            fontsize=7, labelpad=2,
        )
        mx = max(p["width_cm"], p["height_cm"], 1.0)
        half = mx / 2.0
        pad = mx * 0.12
        ax.set_xlim(-half - pad, half + pad)
        ax.set_ylim(-half - pad, half + pad)
        ax.set_aspect("equal")
        ax.tick_params(axis="both", which="both", labelsize=6, length=2)
        ax.grid(True, alpha=0.2, linestyle=":")

    for ax in axes_flat[n:]:
        ax.set_visible(False)

    used = sorted({p["material_inferred"] for p in pieces})
    legend_patches = [
        Patch(facecolor=MATERIAL_COLORS_V2.get(m, DEFAULT_FABRIC_COLOR),
              edgecolor="#444444", alpha=0.8, label=m)
        for m in used
    ]
    fig.legend(handles=legend_patches, loc="upper right", fontsize=9,
               title="재질", framealpha=0.9, bbox_to_anchor=(0.995, 0.995))
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def preview_section(pieces_all: list[dict], selected_sizes: list[str],
                    sample_size: str | None) -> tuple[plt.Figure, str]:
    st.markdown("#### 피스 프리뷰")

    # 기준 사이즈: 샘플사이즈 → 선택 리스트 첫 원소.
    ref_size = sample_size if sample_size in selected_sizes else selected_sizes[0]
    ref_pieces = [p for p in pieces_all if p["size"] == ref_size]

    st.caption(f"※ 프리뷰는 **사이즈 {ref_size}** 기준 ({len(ref_pieces)} 피스)")

    fig = build_grid_figure(ref_pieces)
    st.pyplot(fig)
    return fig, ref_size


# ╔════════════════════════════════════════════════════════════╗
# ║ PDF 리포트                                                 ║
# ╚════════════════════════════════════════════════════════════╝
def figure_to_png_bytes(fig: plt.Figure, dpi: int = 120) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    return buf.getvalue()


def _pdf_kv_table(data, font_name, col_widths=(110, 330)) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def generate_pdf_report_v3(context: dict) -> bytes:
    """
    context:
      style, sample_size, file_name, generated_at,
      selected_sizes,             # 선택된 사이즈 리스트
      results_by_size,            # {size: [fabric_results]}
      piece_count_by_size,        # {size: int}
      total_piece_entries,        # 전체 피스 엔트리 수 (전 사이즈 합)
      efficiency_pct,
      preview_png_bytes, ref_size (프리뷰 기준).
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = KR_FONT

    title_style = ParagraphStyle(
        "TitleRed", parent=styles["Heading1"], fontName=KR_FONT,
        fontSize=18, textColor=colors.HexColor("#dc2626"), spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontName=KR_FONT,
        fontSize=12, textColor=colors.HexColor("#0f172a"),
        spaceBefore=10, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName=KR_FONT,
        fontSize=10, textColor=colors.HexColor("#0f172a"),
    )

    elements = []

    # 타이틀.
    label = f"{context.get('style') or 'STYLE'} (SELF)"
    elements.append(Paragraph(label, title_style))

    # 스타일 요약.
    elements.append(Paragraph("스타일 요약", section_style))
    summary = [
        ["스타일", context.get("style") or "-"],
        ["샘플사이즈", context.get("sample_size") or "-"],
        ["계산 사이즈", ", ".join(context["selected_sizes"])],
        ["파일", context.get("file_name") or "-"],
        ["작성일", context.get("generated_at") or "-"],
    ]
    elements.append(_pdf_kv_table(summary, KR_FONT))

    # 사이즈별 요척 표.
    elements.append(Paragraph("사이즈별 · 원단별 요척", section_style))
    # 모든 재질 수집.
    all_mats: list[str] = []
    for rs in context["results_by_size"].values():
        for r in rs:
            if r["name"] not in all_mats:
                all_mats.append(r["name"])

    header = ["사이즈"] + all_mats
    rows = [header]
    for size, results in context["results_by_size"].items():
        by_mat = {r["name"]: r for r in results}
        row = [size]
        for m in all_mats:
            r = by_mat.get(m)
            row.append(f"{r['length_yd']:.2f} yd" if r else "-")
        rows.append(row)
    col_widths = [60] + [80] * len(all_mats)
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), KR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f8fafc")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))

    # 사이즈별 상세 (미터·폭·면적).
    elements.append(Paragraph("상세 (미터/폭/면적)", section_style))
    detail_hdr = ["사이즈", "원단", "폭(cm)", "길이(yd)", "길이(m)", "면적(m²)", "효율"]
    detail_rows = [detail_hdr]
    for size, results in context["results_by_size"].items():
        for r in results:
            detail_rows.append([
                size, r["name"],
                f"{r['width_cm']:.0f}",
                f"{r['length_yd']:.2f}",
                f"{r['length_m']:.2f}",
                f"{r['gross_area_m2']:.3f}",
                f"{r['efficiency']:.0%}",
            ])
    t = Table(detail_rows, colWidths=[55, 80, 60, 70, 70, 70, 55])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), KR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 14))

    # 프리뷰 이미지.
    preview = context.get("preview_png_bytes")
    if preview:
        ref_size = context.get("ref_size", "")
        elements.append(Paragraph(f"패턴 프리뷰 (사이즈 {ref_size} 기준)", section_style))
        try:
            from PIL import Image as PILImage
            pil = PILImage.open(io.BytesIO(preview))
            w_px, h_px = pil.size
            target_w = 520
            target_h = target_w * (h_px / w_px)
            max_h = 700
            if target_h > max_h:
                target_h = max_h
                target_w = target_h * (w_px / h_px)
            elements.append(RLImage(io.BytesIO(preview),
                                    width=target_w, height=target_h))
        except Exception:
            elements.append(RLImage(io.BytesIO(preview), width=520, height=320))

    doc.build(elements)
    return buf.getvalue()


# ╔════════════════════════════════════════════════════════════╗
# ║ Excel 생성                                                 ║
# ╚════════════════════════════════════════════════════════════╝
def generate_excel_v3(
    results_by_size: dict[str, list[dict]],
    pieces_all: list[dict],
    context: dict,
    selected_sizes: list[str],
) -> bytes:
    wb = Workbook()

    # 요척요약.
    ws1 = wb.active
    ws1.title = "요척요약"
    ws1.append(["스타일", context.get("style") or "-"])
    ws1.append(["샘플사이즈", context.get("sample_size") or "-"])
    ws1.append(["계산 사이즈", ", ".join(selected_sizes)])
    ws1.append(["파일", context.get("file_name") or "-"])
    ws1.append(["작성일", context.get("generated_at") or "-"])
    ws1.append([])

    headers = ["사이즈", "원단명", "폭(cm)", "길이(yd)", "길이(m)",
               "면적(m²)", "효율(%)", "피스종"]
    ws1.append(headers)
    header_row = ws1.max_row
    for size, results in results_by_size.items():
        for r in results:
            ws1.append([
                size, r["name"], round(r["width_cm"], 0),
                round(r["length_yd"], 2), round(r["length_m"], 2),
                round(r["gross_area_m2"], 4),
                round(r["efficiency"] * 100, 0),
                r["piece_count"],
            ])

    # 피스목록 (선택된 사이즈에 해당하는 피스만).
    ws2 = wb.create_sheet("피스목록")
    p_hdr = ["피스ID", "사이즈", "피스명", "재질", "가로(cm)", "세로(cm)",
             "면적(cm²)", "수량", "주석(ANN)"]
    ws2.append(p_hdr)
    for p in pieces_all:
        if p["size"] not in selected_sizes:
            continue
        qty = p["quantity"] if p["quantity"] is not None else 1
        ws2.append([
            p["piece_id"], p["size"], p["piece_name"] or "",
            p["material_inferred"],
            round(p["width_cm"], 1), round(p["height_cm"], 1),
            round(p["area_cm2"], 1), qty,
            " | ".join(p.get("annotations", []))[:80],
        ])

    # 스타일.
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="DDDDDD")
    thin = Side(style="thin", color="AAAAAA")
    border = Border(top=thin, bottom=thin, left=thin, right=thin)

    for cell in ws1[header_row]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
    for cell in ws2[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center")

    # 열 너비 자동.
    for ws in (ws1, ws2):
        for col in ws.columns:
            col_letter = col[0].column_letter
            maxw = 0
            for cell in col:
                v = "" if cell.value is None else str(cell.value)
                disp = sum(2 if ord(c) > 127 else 1 for c in v)
                if disp > maxw:
                    maxw = disp
            ws.column_dimensions[col_letter].width = min(maxw + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ╔════════════════════════════════════════════════════════════╗
# ║ 다운로드 섹션                                              ║
# ╚════════════════════════════════════════════════════════════╝
def download_section(
    pieces_all: list[dict],
    results_by_size: dict[str, list[dict]],
    selected_sizes: list[str],
    preview_fig: plt.Figure,
    ref_size: str,
    parsed: dict,
    efficiency: float,
) -> None:
    st.markdown("#### 다운로드")

    try:
        png = figure_to_png_bytes(preview_fig, dpi=110)
    except Exception as e:
        st.warning(f"프리뷰 이미지 생성 실패: {e}")
        png = b""

    piece_count_by_size = {
        size: sum(1 for p in pieces_all if p["size"] == size)
        for size in selected_sizes
    }

    context = {
        "style": parsed.get("style") or "",
        "sample_size": parsed.get("sample_size") or "",
        "file_name": parsed.get("file_name") or "",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "selected_sizes": selected_sizes,
        "results_by_size": results_by_size,
        "piece_count_by_size": piece_count_by_size,
        "total_piece_entries": sum(piece_count_by_size.values()),
        "efficiency_pct": efficiency * 100,
        "preview_png_bytes": png,
        "ref_size": ref_size,
    }

    base = (parsed.get("style") or "style").replace(" ", "_")
    date_str = datetime.now().strftime("%Y%m%d")

    c1, c2 = st.columns(2)
    try:
        pdf_bytes = generate_pdf_report_v3(context)
        c1.download_button(
            "⬇️ PDF 리포트",
            data=pdf_bytes,
            file_name=f"yocheok_{base}_{date_str}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as e:
        c1.error(f"PDF 생성 실패: {e}")

    try:
        xlsx_bytes = generate_excel_v3(
            results_by_size, pieces_all, context, selected_sizes,
        )
        c2.download_button(
            "⬇️ Excel",
            data=xlsx_bytes,
            file_name=f"yocheok_{base}_{date_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as e:
        c2.error(f"Excel 생성 실패: {e}")


# ╔════════════════════════════════════════════════════════════╗
# ║ 메인                                                       ║
# ╚════════════════════════════════════════════════════════════╝
def main() -> None:
    # 상단 헤더 — 이모지 제거, 깔끔한 타이틀 + 서브타이틀
    st.markdown("""
    <div style="padding-top: 0.5rem; padding-bottom: 1rem;">
        <h1 style="margin-bottom: 0.3rem;">원단 요척 산출 시스템</h1>
        <p style="color: #64748b; margin: 0; font-size: 0.95rem;">
            패턴 DXF 파일로 원단 소요량을 자동 계산합니다
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    parsed = upload_section()
    if parsed is None:
        return

    # 파일 변경 시 세션 초기화.
    if st.session_state.get("last_file") != parsed["file_name"]:
        st.session_state.pop("calc_v3", None)
        st.session_state["accessory_fabrics"] = []
        st.session_state["last_file"] = parsed["file_name"]

    pieces_all = parsed["pieces"]

    st.divider()
    selected_sizes = size_selection_section(parsed)

    st.divider()
    widths = width_section(pieces_all, selected_sizes)

    st.divider()
    efficiency = efficiency_section()

    st.divider()
    if st.button("▶️ 요척 계산하기", type="primary"):
        pieces_calc = apply_accessory_overrides(
            pieces_all, st.session_state.get("accessory_fabrics", []),
        )
        with st.spinner("계산 중..."):
            results_by_size = calculate_by_sizes(
                pieces_calc, selected_sizes, widths, efficiency,
            )
        st.session_state["calc_v3"] = {
            "results_by_size": results_by_size,
            "pieces": pieces_calc,
            "widths": widths,
            "efficiency": efficiency,
            "selected_sizes": selected_sizes,
            "timestamp": datetime.now(),
        }

    if "calc_v3" in st.session_state:
        calc = st.session_state["calc_v3"]
        st.divider()
        results_section(calc["results_by_size"])
        st.divider()
        fig, ref_size = preview_section(
            calc["pieces"], calc["selected_sizes"],
            parsed.get("sample_size"),
        )
        st.divider()
        download_section(
            calc["pieces"], calc["results_by_size"],
            calc["selected_sizes"], fig, ref_size,
            parsed, calc["efficiency"],
        )
        plt.close(fig)

    # 푸터
    st.markdown("""
    <div style="margin-top: 4rem; padding-top: 2rem; border-top: 1px solid #e2e8f0; text-align: center;">
        <p style="color: #94a3b8; font-size: 0.8rem; margin: 0;">
            원단 요척 산출 시스템 · v3.1
        </p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
