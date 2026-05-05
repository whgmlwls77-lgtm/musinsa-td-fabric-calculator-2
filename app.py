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
import json
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
from grain_extractor import (
    detect_grain_layer,
    extract_grain,
    estimate_grain_from_bbox,
)
from dxf_diagnosis import (
    run_full_diagnosis,
    build_coop_message,
    STATUS_LABEL,
    STATUS_EMOJI,
    OK as DIAG_OK,
    WARN as DIAG_WARN,
    FAIL as DIAG_FAIL,
)
from auto_nesting import nest_grading_marker, visualize_marker
from auto_nesting_v2 import (
    nest_grading_marker_sparrow,
    nest_by_material,
    nest_by_material_multisize,
    humanize_svg_labels,
    extract_style_code,
    find_hq_match,
    parse_hq_size_ratio,
)


# ╔════════════════════════════════════════════════════════════╗
# ║ 본사 검증 데이터 안전 변환 헬퍼                              ║
# ╚════════════════════════════════════════════════════════════╝
def safe_float(value, default: float = 0.0) -> float:
    """본사 데이터의 숫자 필드(문자열일 수 있음)를 안전하게 float 변환.
    빈 문자열, None, 변환 실패 시 default 반환.
    검증 데이터 CSV/JSON 일부 entry 가 효율/원단폭/요척 등을 빈 문자열로 가지는 경우 대응.
    """
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _hq_has_value(value) -> bool:
    """hq_match 의 필드가 표시 가능한 값인지 (None/""/0 이 아닌지)."""
    if value is None or value == "":
        return False
    try:
        return float(value) > 0
    except (ValueError, TypeError):
        return bool(str(value).strip())


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
_MIRROR_TRUE_TOKENS_V3: frozenset = frozenset({"TRUE", "1", "Y", "YES"})
_MIRROR_FALSE_TOKENS_V3: frozenset = frozenset({"FALSE", "0", "N", "NO", ""})

_PAIRED_TRUE_TOKENS_V3: frozenset = frozenset({"DOUBLE", "PAIR", "YES", "Y", "TRUE", "1"})
_PAIRED_FALSE_TOKENS_V3: frozenset = frozenset({"SINGLE", "NO", "N", "FALSE", "0", ""})


def parse_mirror_value_v3(value: str) -> bool | None:
    """
    Mirror 메타 값을 bool / None 으로 정규화.
      True : "True"/"true"/"TRUE"/"1"/"Y"/"yes"/"Yes"
      False: "False"/"false"/"FALSE"/"0"/"N"/"no"/"No"/""
      그 외 → None (절대 원칙: 추측 X — 호출자가 미러 적용 안 함)
    """
    if value is None:
        return None
    token = value.strip().upper()
    if token in _MIRROR_TRUE_TOKENS_V3:
        return True
    if token in _MIRROR_FALSE_TOKENS_V3:
        return False
    return None


def parse_paired_value_v3(value: str) -> bool | None:
    """
    PAIRED 메타 값을 mirror bool 로 정규화 (StyleCAD 등 좌우 페어 표기).
      True : DOUBLE / PAIR / YES — 좌우 페어 piece (원본 + 미러)
      False: SINGLE / NO — 단일 piece (미러 X)
      그 외 → None (절대 원칙: 추측 X — 호출자가 미러 적용 안 함)

    근거: TEST 패턴 파일/MMAPS003-test.dxf 에서 사장님이 8 piece 에 PAIRED:DOUBLE 박음.
          StyleCAD 좌우 페어 메타 — Yuka의 'Mirror:' 와 동일 의미.
    """
    if value is None:
        return None
    token = value.strip().upper()
    if token in _PAIRED_TRUE_TOKENS_V3:
        return True
    if token in _PAIRED_FALSE_TOKENS_V3:
        return False
    return None


def parse_block_metadata_v3(block) -> dict:
    """
    블록 내부 TEXT 를 훑어 메타를 dict 로 반환.
    CP949 복원을 모든 텍스트에 시도 + ANNOTATION 리스트 수집.

    반환:
      {
        piece_name, size, quantity, material (원문 코드),
        mirror (bool|None — 불명일 때 None),
        annotations: [str, ...]
      }
    """
    meta = {
        "piece_name": "",
        "size": "",
        "quantity": None,
        "material": "",
        "mirror": None,           # bool|None — 키 부재 시 None (절대 원칙: 추측 X)
        "annotations": [],
    }
    paired_seen = False  # PAIRED 키가 이미 mirror 를 정했는지 — Mirror 키가 덮어쓰지 못하게.

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
        elif key == "paired":
            # StyleCAD 좌우 페어 메타. PAIRED > Mirror 우선순위.
            meta["mirror"] = parse_paired_value_v3(value)
            paired_seen = True
        elif key == "mirror":
            if not paired_seen:
                meta["mirror"] = parse_mirror_value_v3(value)
        elif key == "annotation":
            if value:
                meta["annotations"].append(value)

    return meta


# ╔════════════════════════════════════════════════════════════╗
# ║ 재질 분류 (ANNOTATION 파싱 강화)                           ║
# ╚════════════════════════════════════════════════════════════╝
_MATERIAL_TOKEN_RE = re.compile(r"[가-힣A-Za-z]+")


def _strip_parens(text: str) -> str:
    """괄호와 그 안의 내용 제거 — 본체 piece에 '(심지)' 같은 부착 메모를 무시.
    예: '카라(심지)' → '카라', '심지부착(2겹)' → '심지부착'.
    """
    if not text:
        return text
    return re.sub(r"\([^)]*\)", " ", text)


def _has_token(text: str, token: str) -> bool:
    """text 에서 token 이 단어 단위(한글/영문 연속체)로 등장하는지.
    괄호 내용은 무시. 'FUSED' / '심지부착' 같이 한 단어 안에 박혀있으면 매칭 X.
    """
    if not text:
        return False
    cleaned = _strip_parens(text)
    return token in _MATERIAL_TOKEN_RE.findall(cleaned)


def _has_token_in_list(items: list[str], token: str) -> bool:
    return any(_has_token(item, token) for item in items)


def _has_lower_token_in_list(items: list[str], token: str) -> bool:
    return any(_has_token(item.lower() if item else "", token) for item in items)


def infer_material_v3(
    piece_name: str,
    material_raw: str,
    annotations: list[str],
) -> str:
    """
    V3.3 (재질 분류 fix):
      0. material_raw 가 SELF/1/MAIN 등 명시면 무조건 주원단 (annotations 메모 무시)
      1. ANNOTATION 키워드 — **단어 단위**, 괄호 내용 제외
         (예: '심지부착', '(심지)', 'FUSED' 같은 메모/파생 단어는 매칭 X)
      2. 피스 이름 키워드 — 동일 토큰 매칭
      3. DXF material 코드 — 영문(SELF/FUSE/LINING/CONTRAST/POCKET) + 레거시(1/FN/IL)
      4. 기본 → 주원단
    """
    # 0) material_raw 가 SELF / 주원단 명시면 annotations 메모와 무관하게 주원단
    code = (material_raw or "").strip().upper()
    if code in ("SELF", "1", "MAIN", "FABRIC", "주원단"):
        return "주원단"

    # 1) ANNOTATION 검사 — 단어 단위, 괄호 제외
    if _has_token_in_list(annotations, "안감") or _has_lower_token_in_list(annotations, "lining"):
        return "안감"
    if (_has_token_in_list(annotations, "심지")
            or _has_lower_token_in_list(annotations, "fuse")
            or _has_lower_token_in_list(annotations, "fusing")
            or _has_lower_token_in_list(annotations, "interfacing")):
        return "심지"
    if _has_token_in_list(annotations, "배색") or _has_lower_token_in_list(annotations, "contrast"):
        return "배색"
    if (_has_token_in_list(annotations, "주머니")
            or _has_token_in_list(annotations, "포켓")
            or _has_lower_token_in_list(annotations, "pocket")):
        return "주머니감"

    # 2) 피스 이름 키워드 — 동일 토큰 매칭 (괄호 제외)
    name = piece_name or ""
    name_lower = name.lower()
    if (_has_token(name, "심지") or _has_token(name_lower, "fuse")
            or _has_token(name_lower, "fusing") or _has_token(name_lower, "interfacing")
            or _has_token(name, "FN") or _has_token(name.upper(), "FN")):
        return "심지"
    if _has_token(name, "안감") or _has_token(name_lower, "lining"):
        return "안감"
    if _has_token(name, "배색") or _has_token(name_lower, "contrast"):
        return "배색"
    if (_has_token(name, "주머니") or _has_token(name, "포켓")
            or _has_token(name_lower, "pocket")):
        return "주머니감"

    # 3) DXF 재질 코드 — 영문 표준 + 레거시 숫자/약어 모두 지원.
    code = (material_raw or "").strip().upper()

    # 심지 (Fusing / Interfacing)
    if code in ("FUSE", "FN", "FUSING", "INTERFACING", "INTERLINING"):
        return "심지"
    # 안감 (Lining)
    if code in ("LINING", "IL", "INNER LINING", "LIN"):
        return "안감"
    # 배색 (Contrast)
    if code in ("CONTRAST", "CT", "CONT"):
        return "배색"
    # 주머니감 (Pocket fabric — 재질 코드로 쓰였을 때)
    if code in ("POCKET", "PK", "PKT"):
        return "주머니감"
    # 주원단/제감 (Self / Main)
    if code in ("SELF", "1", "MAIN", "FABRIC", ""):
        return "주원단"

    # 알려지지 않은 코드 → 기본값
    return "주원단"


# ╔════════════════════════════════════════════════════════════╗
# ║ 재질 매핑 사전 (data/material_mapping.json)                ║
# ║ 사장님 절대 원칙: DXF Material 0% 시 사용자 입력만 신뢰     ║
# ╚════════════════════════════════════════════════════════════╝
MATERIAL_MAPPING_PATH: Path = Path(__file__).parent / "data" / "material_mapping.json"
MATERIAL_OPTIONS: list[str] = ["주원단", "심지", "안감", "배색", "주머니감", "미지정"]


def load_material_mapping() -> dict:
    """매핑 사전 로드. 파일 없거나 깨졌으면 기본 구조 반환."""
    default = {"by_style": {}, "global": {}}
    if not MATERIAL_MAPPING_PATH.exists():
        return default
    try:
        data = json.loads(MATERIAL_MAPPING_PATH.read_text(encoding="utf-8"))
        # 형식 검증 — 두 키 보장.
        if not isinstance(data, dict):
            return default
        data.setdefault("by_style", {})
        data.setdefault("global", {})
        return data
    except (json.JSONDecodeError, OSError):
        return default


def save_material_mapping(mapping: dict) -> None:
    """매핑 사전 저장. data/ 폴더 자동 생성."""
    MATERIAL_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    MATERIAL_MAPPING_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_piece_token(piece_name: str, style: str) -> str:
    """piece_name 에서 스타일 코드 접두어 제거 → 부위 약자 토큰만.

    예: piece_name='MMAPS003 CAPS', style='MMAPS003' → 'CAPS'
        piece_name='MMAPS003-FRONT', style='MMAPS003' → 'FRONT'
        piece_name='', style='X' → '(이름 없음)'

    절대 원칙: 토큰 추출 실패 시 piece_name 원본 그대로 그룹키로 사용
              (절대 임의 분류 X — 사용자가 알아볼 수 있는 키로 보존)
    """
    if not piece_name:
        return "(이름 없음)"
    name = piece_name.strip()
    if not name:
        return "(이름 없음)"
    if style:
        # 스타일 prefix 제거 (대소문자 무시, 구분자 - _ 공백 허용).
        sty_norm = style.strip().upper()
        upper = name.upper()
        if upper.startswith(sty_norm):
            rest = name[len(sty_norm):].lstrip(" -_")
            if rest:
                return rest
    return name


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
# ║ 단위 자동 감지 (DXF 좌표 → cm 변환 스케일)                 ║
# ╚════════════════════════════════════════════════════════════╝
from ezdxf import bbox as _ezbbox

# $INSUNITS → (scale_to_cm, 단위명)
_INSUNITS_MAP = {
    1: (2.54, "inch"),
    4: (0.1,  "mm"),
    5: (1.0,  "cm"),
    6: (100.0, "m"),
}


def detect_unit_scale_to_cm(doc) -> tuple[float, str]:
    """
    DXF 도면의 단위를 감지하여 'cm' 로 환산할 스케일을 반환한다.

    전략:
      1. $INSUNITS 헤더값 확인 (mm/cm/inch/m)
      2. 도면 전체 bbox 크기로 교차 검증 (의류 패턴 현실 스케일과 비교)
      3. 헤더와 좌표가 불일치하면 **좌표 기반 추정을 우선** (헤더가 거짓말 하는 경우 많음)

    반환: (scale_to_cm, 감지 정보 문자열)
    """
    # 1) 헤더 힌트
    insunits = doc.header.get("$INSUNITS", 0)
    header_hint = _INSUNITS_MAP.get(insunits)  # None 또는 (scale, name)

    # 2) 좌표 스케일 추정
    longest = 0.0
    try:
        all_entities = list(doc.modelspace())
        extents = _ezbbox.extents(all_entities)
        if extents.has_data:
            longest = max(
                extents.extmax.x - extents.extmin.x,
                extents.extmax.y - extents.extmin.y,
            )
    except Exception:
        pass

    # 의류 패턴 전체 bbox 현실 범위 (가장 긴 변 기준):
    #   mm → 500~5000 (예: 1500mm = 150cm)
    #   cm → 30~500   (예: 150cm)
    #   m  → 0.3~5    (예: 1.5m)
    #   inch → 20~200 (드묾)
    if longest >= 500:
        coord_guess = (0.1, "mm")
    elif longest >= 30:
        coord_guess = (1.0, "cm")
    elif longest >= 0.3:
        coord_guess = (100.0, "m")
    else:
        coord_guess = None

    # 3) 결정
    if header_hint and coord_guess:
        if abs(header_hint[0] - coord_guess[0]) < 0.01:
            return header_hint[0], f"{header_hint[1]} (헤더+좌표 일치)"
        # 불일치 → 좌표 신뢰
        return coord_guess[0], f"{coord_guess[1]} (좌표 기준; 헤더 '{header_hint[1]}'는 무시)"
    if coord_guess:
        return coord_guess[0], f"{coord_guess[1]} (좌표 기반 추정)"
    if header_hint:
        return header_hint[0], f"{header_hint[1]} (헤더 기반)"
    # 최후 fallback
    return 0.1, "mm (기본값)"


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

        # ── 단위 자동 감지 (mm/cm/inch/m → cm) ──
        unit_scale, unit_info = detect_unit_scale_to_cm(doc)
        unit_scale2 = unit_scale * unit_scale  # 면적용 (제곱)

        # ── 식서 LAYER 자동 감지 (1회) ──
        grain_layer = detect_grain_layer(doc)

        # ── 진단 raw 메트릭 (Bug A — DXF 진단 리포트) ──
        # 식서 LAYER 의 LINE 갯수 (모든 블록 합산) — diagnose_grain 에서 사용.
        total_grain_lines = 0
        for blk in doc.blocks:
            for e in blk:
                if e.dxftype() == "LINE":
                    if grain_layer is None or e.dxf.layer == grain_layer:
                        total_grain_lines += 1

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

                # 좌표(cm) — 감지된 단위 스케일 적용.
                coords_raw = list(polygon.exterior.coords)
                coords_cm = [(x * unit_scale, y * unit_scale) for x, y in coords_raw]

                minx, miny, maxx, maxy = polygon.bounds
                bbox_cm = (
                    minx * unit_scale, miny * unit_scale,
                    maxx * unit_scale, maxy * unit_scale,
                )
                w_cm = bbox_cm[2] - bbox_cm[0]
                h_cm = bbox_cm[3] - bbox_cm[1]
                centroid_cm = (
                    polygon.centroid.x * unit_scale,
                    polygon.centroid.y * unit_scale,
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

                # 식서 추출: 1) DXF LINE 마크 우선, 2) 없으면 bbox 비율로 추정.
                grain = extract_grain(block, grain_layer)
                if grain is None:
                    grain = estimate_grain_from_bbox(w_cm, h_cm)

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
                    "mirror": meta.get("mirror"),  # bool|None — 옵션 A 미러 처리
                    "area_cm2": polygon.area * unit_scale2,
                    "width_cm": w_cm,
                    "height_cm": h_cm,
                    "bbox_cm": bbox_cm,
                    "centroid_cm": centroid_cm,
                    "coords_cm": coords_cm,
                    "grain": grain,
                })

        return {
            "pieces": pieces,
            "excluded": excluded,
            "style": style,
            "sample_size": size_info["sample_size"] or "",
            "sizes": size_info["sizes"],
            "is_full_grading": size_info["is_full_grading"],
            "detection_method": size_info["detection_method"],
            "unit_info": unit_info,
            "unit_scale": unit_scale,
            # 진단 raw 메트릭 — diagnose_grain 등이 doc 없이 사용 가능.
            "diagnosis_raw": {
                "grain_layer": grain_layer,
                "total_grain_lines": total_grain_lines,
            },
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
        f"감지 방식: `{parsed['detection_method']}` · 단위: `{parsed.get('unit_info', '?')}` → cm 기준 계산"
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

    # ── DXF 진단 리포트 (사장님 명시 — 알고리즘 읽기 실패 vs 협력사 정보 누락 구분) ──
    diagnosis_section(parsed)

    return parsed


# ╔════════════════════════════════════════════════════════════╗
# ║ UI — DXF 진단 리포트 (4대 카테고리 + 협력사 메시지)         ║
# ║ 사장님 절대 원칙: 알고리즘 읽기 실패 vs 협력사 정보 누락 구분 ║
# ╚════════════════════════════════════════════════════════════╝
def diagnosis_section(parsed: dict) -> None:
    """업로드 직후 자동 분석 박스 — 4대 카테고리 진단 + 협력사 피드백 메시지."""
    diag = run_full_diagnosis(parsed)
    parsed["_diagnosis"] = diag  # 다른 섹션에서도 참조 가능하도록 저장

    style = parsed.get("style") or "(미지정)"

    n_fail = sum(1 for d in diag.values() if d["status"] == DIAG_FAIL)
    n_warn = sum(1 for d in diag.values() if d["status"] == DIAG_WARN)
    n_ok = sum(1 for d in diag.values() if d["status"] == DIAG_OK)

    # 헤더 — 한눈 요약.
    if n_fail == 0 and n_warn == 0:
        head_msg = f"📋 **DXF 진단 리포트** — `{style}`  ✅ 4/4 정상"
        st.success(head_msg)
    elif n_fail > 0:
        head_msg = f"📋 **DXF 진단 리포트** — `{style}`  ❌ 누락 {n_fail} · ⚠️ 부족 {n_warn} · ✅ 정상 {n_ok}"
        st.error(head_msg)
    else:
        head_msg = f"📋 **DXF 진단 리포트** — `{style}`  ⚠️ 부족 {n_warn} · ✅ 정상 {n_ok}"
        st.warning(head_msg)

    # 4가지 진단 항목 — expander 로 상세 라인.
    labels = [
        ("grain",    "[1] 결방향 (식서/푸서/바이어스)"),
        ("material", "[2] 원단 표기 (주원단/심지/안감/배색/주머니감)"),
        ("panel",    "[3] 패널 정보 (앞판/뒤판/사이바 등)"),
        ("quantity", "[4] 수량 / 좌우 대칭"),
    ]
    with st.expander("상세 진단 보기", expanded=(n_fail + n_warn > 0)):
        for key, label in labels:
            d = diag[key]
            emoji = STATUS_EMOJI[d["status"]]
            st.markdown(
                f"{emoji} **{label}** — {STATUS_LABEL[d['status']]}  \n"
                f"&nbsp;&nbsp;&nbsp;&nbsp;ㄴ 요약: {d['summary']}  \n"
                f"&nbsp;&nbsp;&nbsp;&nbsp;ㄴ DXF 상태: {d['dxf_state']}  \n"
                f"&nbsp;&nbsp;&nbsp;&nbsp;ㄴ 알고리즘: {d['algo_state']}",
                unsafe_allow_html=True,
            )

    # ── 협력사 피드백 메시지 자동 생성 ──
    if n_fail > 0 or n_warn > 0:
        coop_msg = build_coop_message(parsed, diag)
        with st.expander("📨 협력사 요청 메시지 (자동 생성)", expanded=False):
            st.caption(
                "아래 메시지를 협력사 / 패턴사에게 전달하면 다음 패턴 파일의 정확도가 향상됩니다."
            )
            st.code(coop_msg, language="markdown")
            st.download_button(
                "📥 메시지 텍스트 다운로드",
                data=coop_msg.encode("utf-8"),
                file_name=f"coop_request_{style}.txt",
                mime="text/plain",
                key=f"coop_msg_dl__{style}",
            )


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
# ║ UI — 수동 재질 분류 섹션 (사장님 절대 원칙)                 ║
# ║ DXF Material 코드 누락 시 사용자 입력 + 매핑 사전 저장      ║
# ╚════════════════════════════════════════════════════════════╝
def material_mapping_section(parsed: dict) -> dict:
    """
    수동 재질 분류 UI. DXF Material 메타 보유율 검사 → 누락 시 사용자 입력.

    동작:
      1. parsed["pieces"] 의 piece_name 을 부위 약자로 토큰화
      2. 같은 약자 = 같은 그룹 (사이즈만 다른 동일 부위)
      3. 매핑 사전(data/material_mapping.json) 추천값 표시 (있으면 default, 없으면 "주원단")
      4. 사용자 selectbox 선택 → 모든 사이즈에 자동 전파 (그룹 단위)
      5. 예외 처리 expander — piece 단위 override (특정 사이즈/piece 만 다른 재질)
      6. parsed["pieces"][*]["material_inferred"] 직접 override
      7. 매핑 사전 자동 저장 (다음 DXF 부터 추천값 재사용)

    사장님 절대 원칙:
      - default 는 매핑 사전 또는 "주원단" 만 (자동 분류 결과는 default 로 신뢰 X)
      - 토큰 추출 실패 시 piece_name 원본 그대로 그룹키 (임의 분류 X)

    반환: { 토큰: 선택된_재질 } dict (UI 미리보기/디버깅용).
    """
    pieces = parsed["pieces"]
    style = parsed.get("style", "") or ""

    # ── Material 보유율 검사 ───────────────────────────────────────
    n = len(pieces)
    n_with_mat = sum(1 for p in pieces if (p.get("material_raw") or "").strip())
    coverage = n_with_mat / n if n else 0.0

    # ── 부위 토큰 그룹핑 (같은 약자 = 같은 그룹) ───────────────────
    token_groups: dict[str, list[dict]] = {}
    for p in pieces:
        tok = normalize_piece_token(p.get("piece_name") or "", style)
        token_groups.setdefault(tok, []).append(p)

    # ── 모든 piece에 Material 메타 있으면 자동 분류만 보여주고 끝 ──
    if coverage >= 1.0:
        st.markdown("#### 🧵 재질 분류")
        st.success(
            f"✅ 모든 piece에 Material 메타 표기됨 ({n_with_mat}/{n}) — DXF 자동 분류 사용."
        )
        # 자동 분류 결과 한 줄 요약.
        mat_counts: dict[str, int] = {}
        for p in pieces:
            mat_counts[p["material_inferred"]] = mat_counts.get(p["material_inferred"], 0) + 1
        order = ["주원단", "심지", "안감", "배색", "주머니감"]
        parts = [f"{m}: {mat_counts[m]}" for m in order if m in mat_counts]
        if parts:
            st.caption(" · ".join(parts))
        return {tok: grp[0]["material_inferred"] for tok, grp in token_groups.items()}

    # ── 매핑 사전 로드 ────────────────────────────────────────────
    mapping_db = load_material_mapping()
    style_map: dict[str, str] = mapping_db.get("by_style", {}).get(style, {})
    global_map: dict[str, str] = mapping_db.get("global", {})

    st.markdown("#### 🧵 재질 분류 — 수동 입력 필요")

    if coverage == 0.0:
        st.warning(
            f"⚠️ **DXF에 `Material:` 코드 없음** ({n_with_mat}/{n} piece)  \n"
            f"각 부위 약자의 재질을 직접 선택해주세요. "
            f"**알고리즘은 추측하지 않습니다** — 사장님 절대 원칙."
        )
    else:
        st.warning(
            f"⚠️ **Material 코드 부분 누락** — {n_with_mat}/{n} piece만 표기됨. "
            f"누락분 직접 선택."
        )

    n_tokens = len(token_groups)
    st.caption(
        f"📦 **{n_tokens}개 부위 그룹** × 사이즈별 = 총 {n} piece — "
        f"부위별로 한 번만 선택하면 같은 부위 모든 사이즈에 자동 적용."
    )

    if style_map or global_map:
        recs = []
        if style_map:
            recs.append(f"이 스타일({style}) 이전 매핑 {len(style_map)}개")
        if global_map:
            recs.append(f"전역 표준 약자 {len(global_map)}개")
        st.caption("💡 매핑 사전 사용: " + " · ".join(recs))

    # ── 부위별 selectbox (그리드 배치) ───────────────────────────
    # default 우선순위 (사장님 절대 원칙: 알고리즘 추정 신뢰 X):
    #   1) 스타일별 사전 (이전 사용자 입력 — 신뢰 가능)
    #   2) 전역 사전 (전역 표준 약자 — 신뢰 가능)
    #   3) "주원단" (명시적 fallback — 자동 분류 결과는 default 로 채택하지 않음)
    user_mapping: dict[str, str] = {}
    cols_per_row = min(3, max(1, n_tokens))
    cols = st.columns(cols_per_row)

    sorted_tokens = sorted(token_groups.keys())
    for i, tok in enumerate(sorted_tokens):
        grp = token_groups[tok]
        col = cols[i % cols_per_row]
        with col:
            default = (
                style_map.get(tok)
                or global_map.get(tok)
                or "주원단"
            )
            # MATERIAL_OPTIONS에 없는 값 보호.
            try:
                idx = MATERIAL_OPTIONS.index(default)
            except ValueError:
                idx = 0
            sample_name = grp[0].get("piece_name") or ""
            from_dict = (tok in style_map) or (tok in global_map)
            label_suffix = " 💡" if from_dict else ""
            choice = st.selectbox(
                f"**{tok}** — {len(grp)}개 사이즈{label_suffix}",
                MATERIAL_OPTIONS,
                index=idx,
                key=f"mat_map__{style}__{tok}",
                help=(
                    f"piece_name 예: {sample_name}"
                    + ("\n💡 매핑 사전 추천값" if from_dict else "")
                ) if sample_name else None,
            )
            user_mapping[tok] = choice

    # ── 사용자 선택 → pieces 직접 override (그룹 단위) ───────────
    # "미지정" 은 그대로 유지 (자동 분류 결과를 보존하지 않고 명시적 선택만 적용).
    overridden = 0
    for p in pieces:
        tok = normalize_piece_token(p.get("piece_name") or "", style)
        chosen = user_mapping.get(tok)
        if chosen and chosen != "미지정":
            if p.get("material_inferred") != chosen:
                overridden += 1
            p["material_inferred"] = chosen

    # ── 예외 처리 expander (piece 단위 override) ─────────────────
    # 같은 약자 그룹이지만 특정 사이즈/piece 만 재질이 다른 경우 사용.
    # 예: 같은 PKT 약자에 안감용·주머니감용 혼재 / 특정 사이즈만 다른 재질.
    with st.expander("🔧 예외 처리 — 특정 piece 만 다른 재질로 (선택)", expanded=False):
        st.caption(
            "그룹 단위로 일괄 분류된 후 **특정 piece 만** 다른 재질로 override 합니다. "
            "사용 사례: 같은 약자에 두 재질 혼재(안감용 PKT vs 주머니감용 PKT) / "
            "특정 사이즈만 다른 처리."
        )
        # piece 단위 표 형태 — 그룹 정렬 → piece_name 정렬.
        for tok in sorted_tokens:
            grp = token_groups[tok]
            group_choice = user_mapping.get(tok, "주원단")
            with st.container():
                st.markdown(f"**{tok}** — 그룹 분류: `{group_choice}` ({len(grp)}개)")
                cols_e = st.columns(min(3, max(1, len(grp))))
                for j, p in enumerate(sorted(grp, key=lambda x: (x.get("size") or "", x.get("piece_name") or ""))):
                    with cols_e[j % len(cols_e)]:
                        size_lbl = p.get("size") or "?"
                        pname = p.get("piece_name") or ""
                        # piece 고유키 (size + piece_name 조합).
                        piece_key = f"{size_lbl}__{pname}"
                        # 현재 material (그룹 적용 후 값) 을 default 로.
                        cur = p.get("material_inferred") or group_choice
                        try:
                            idx_e = MATERIAL_OPTIONS.index(cur)
                        except ValueError:
                            idx_e = 0
                        ex_choice = st.selectbox(
                            f"size {size_lbl}",
                            MATERIAL_OPTIONS,
                            index=idx_e,
                            key=f"mat_exc__{style}__{tok}__{piece_key}",
                            help=pname,
                        )
                        # 그룹값과 다르면 override (이미 그룹 단위에서 설정된 값을 piece 단위로 덮어씀).
                        if ex_choice != "미지정" and ex_choice != p.get("material_inferred"):
                            p["material_inferred"] = ex_choice
                            overridden += 1

    # ── 매핑 사전 저장 (스타일 키 있을 때만) ─────────────────────
    if style:
        # 사용자가 "미지정"으로 둔 토큰은 사전에 저장하지 않음 (오염 방지).
        clean_map = {k: v for k, v in user_mapping.items() if v != "미지정"}
        if clean_map:
            mapping_db.setdefault("by_style", {})[style] = clean_map
            try:
                save_material_mapping(mapping_db)
            except OSError as e:
                st.warning(f"매핑 사전 저장 실패 (계속 진행): {e}")

    # ── 분류 결과 미리보기 ────────────────────────────────────────
    rev: dict[str, list[str]] = {}
    for tok, mat in user_mapping.items():
        rev.setdefault(mat, []).append(tok)

    summary_parts = []
    for mat in ["주원단", "심지", "안감", "배색", "주머니감", "미지정"]:
        if mat in rev:
            summary_parts.append(f"**{mat}** ({len(rev[mat])}개 부위)")
    if summary_parts:
        st.caption("분류 결과: " + " · ".join(summary_parts))

    # 미지정이 남으면 경고
    if "미지정" in rev:
        st.warning(
            f"⚠️ **{len(rev['미지정'])}개 부위가 미지정 상태** — "
            f"마카 배치 시 임시로 '주원단'으로 처리됩니다. "
            f"정확한 요척을 위해 분류해주세요."
        )

    with st.expander("📋 부위별 상세 (확인용)"):
        for mat in ["주원단", "심지", "안감", "배색", "주머니감", "미지정"]:
            toks = rev.get(mat)
            if toks:
                st.markdown(f"- **{mat}** ({len(toks)}개): {', '.join(sorted(toks))}")

    # 미지정으로 남은 piece 의 material_inferred 는 자동 분류값 ("주원단")이 그대로 유지.
    # (해당 piece 들이 마카에 들어가야 누락이 없음 — 단, 사용자에게 경고로 알려줌.)
    return user_mapping


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

    # v3.3: accessory_fabrics 위젯 영구 제거. 함수(apply_accessory_overrides)는 보존.
    # 사용자가 피스명을 모르므로 피스 단위 선택은 UX 적합하지 않음.
    # session_state["accessory_fabrics"] 는 빈 리스트로 유지 (apply_accessory_overrides 호환).
    if "accessory_fabrics" not in st.session_state:
        st.session_state.accessory_fabrics = []

    # ── 작업 2: "+ 원단 추가" 버튼 — 자동 감지 못 한 원단 종류 수동 추가 ──
    # 피스 선택 없이 종류 + 폭만 입력. 해당 종류 코드의 피스가 DXF 에 있어야 사용됨.
    if "manual_widths" not in st.session_state:
        st.session_state.manual_widths = {}  # {재질명: 폭}

    standard = ["배색", "안감", "주머니감", "심지", "기타"]
    not_yet = [m for m in standard if m not in detected and m not in st.session_state.manual_widths]

    with st.expander("➕ 원단 추가 (자동 감지 안 된 경우)", expanded=False):
        st.caption(
            "패턴에 재질 표기(`Material:` 또는 `Annotation:`)가 빠진 원단을 직접 추가합니다. "
            "추가 후 해당 종류의 피스가 DXF 에 없으면 무시됩니다."
        )
        if not_yet:
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                pick = st.selectbox("원단 종류", options=not_yet, key="add_fabric_kind")
            with c2:
                new_w = st.number_input(
                    "원단 폭 (cm)",
                    min_value=30, max_value=300,
                    value=int(DEFAULT_WIDTHS.get(pick, 110)),
                    step=1, key="add_fabric_width",
                )
            with c3:
                st.write("")  # vertical alignment
                if st.button("추가", key="add_fabric_btn", type="primary"):
                    st.session_state.manual_widths[pick] = float(new_w)
                    st.rerun()
        else:
            st.caption("추가 가능한 표준 종류가 없습니다 (모두 자동 감지됨).")

        # 수동 추가 목록
        if st.session_state.manual_widths:
            st.write("**수동 추가된 원단**")
            for mat, w in list(st.session_state.manual_widths.items()):
                cm1, cm2 = st.columns([4, 1])
                # DXF 에 해당 종류 피스가 있는지 검증 (소싱팀 안내용)
                has_pieces = any(p.get("material_inferred") == mat for p in relevant)
                status = f"✓ DXF 에 피스 있음" if has_pieces else "⚠️ DXF 에 해당 종류 피스 없음 — 무시됨"
                cm1.write(f"• **{mat}** ({w:.0f}cm) — {status}")
                if cm2.button("🗑️", key=f"del_manual_{mat}"):
                    del st.session_state.manual_widths[mat]
                    st.rerun()

    # 수동 추가 폭을 widths 에 병합 (자동 감지 폭이 우선, 수동은 미감지 종류만 채움)
    for mat, w in st.session_state.manual_widths.items():
        if mat not in widths:
            widths[mat] = w

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
# ║ UI — 자동 마카 배치 (베타)                                  ║
# ╚════════════════════════════════════════════════════════════╝
def _pick_default_base_size(available: list[str]) -> str:
    """기준사이즈 default 추천 — 영문은 가운데(S/M/L 중 L 우선), 인치는 중간값."""
    if not available:
        return ""
    order = ["XS", "S", "M", "L", "XL", "XXL"]
    in_order = [s for s in available if s in order]
    if in_order:
        # L 우선, 없으면 가운데
        if "L" in in_order:
            return "L"
        return in_order[len(in_order) // 2]
    # 인치 사이즈 (정수)
    try:
        nums = sorted([(int(s), s) for s in available])
        return nums[len(nums) // 2][1]
    except (ValueError, TypeError):
        return sorted(available)[len(available) // 2]


def nesting_section(available_sizes: list[str], hq_match: dict | None = None) -> dict:
    """v3.3 (Phase 2-B-5 redesign 2): 벌수 + 결방향 자유 입력.

    사장님 정의:
      - 벌수 = 마카에 들어가는 옷 갯수 (자유 입력, min=1)
      - 결방향 = 1WAY / 2WAY
      - 조합 자유 (제약 X)

    UI:
      단일 사이즈: 벌수 + 결방향 두 가지만
      그레이딩: 사이즈별 표 (선택 + 벌수 + 결방향)
    """
    runtime = 30
    n_sizes_avail = len(available_sizes)

    # ── 감지된 사이즈 표시 ──
    if available_sizes:
        suffix = "(단일)" if n_sizes_avail == 1 else f"(그레이딩 {n_sizes_avail}종)"
        st.markdown(f"📐 **감지된 사이즈**: " + " · ".join(f"`{s}`" for s in available_sizes) + f"  {suffix}")
    else:
        st.warning("⚠️ DXF에서 사이즈를 감지하지 못했습니다.")
        return {
            "mirror": True, "runtime_seconds": 30,
            "size_ratio": None, "base_size": "",
            "marker_mode_label": "2WAY", "config_id": "empty",
            "total_garments": 0, "summary_text": "",
        }

    default_base = _pick_default_base_size(available_sizes)

    st.markdown("**마카 구성**")

    # ── 단일 사이즈 모드 ──
    if n_sizes_avail == 1:
        only_size = available_sizes[0]
        c1, c2 = st.columns([1, 2])
        with c1:
            n_garments = st.number_input(
                "벌수",
                min_value=1, max_value=20, value=1, step=1,
                help="마카에 들어가는 옷 갯수 (자유 입력).",
            )
        with c2:
            direction = st.radio(
                "결방향",
                options=["1WAY", "2WAY"],
                index=1,  # 2WAY default
                horizontal=True,
                help="1WAY: 단방향(결 통일) · 2WAY: 양방향(좌우 페어/180° 플립 허용).",
            )
        # 알고리즘 매핑
        n_garments = int(n_garments)
        mirror = (direction == "2WAY")
        # 단일사이즈 + 벌수 N → size_ratio 로 매핑 (벌수 1 일 때는 size_ratio=None 단일 nest)
        if n_garments == 1:
            size_ratio = None  # 단일사이즈 단일벌 → nest_by_material 단순 호출
            total_garments = 1
        else:
            size_ratio = {only_size: n_garments}
            total_garments = n_garments
        summary_text = f"{only_size} {n_garments}벌 ({direction})"
        config_id = f"single_{n_garments}_{direction.lower()}"
        marker_mode_label = direction
        base_size = only_size

    # ── 그레이딩 모드 ──
    else:
        st.caption("사이즈별로 벌수와 결방향을 입력하세요. 빈 사이즈는 마카에서 제외됩니다.")

        # 표 헤더
        hc1, hc2, hc3, hc4 = st.columns([1, 2, 2, 2])
        with hc1: st.markdown("**선택**")
        with hc2: st.markdown("**사이즈**")
        with hc3: st.markdown("**벌수**")
        with hc4: st.markdown("**결방향**")

        size_configs: list[tuple[str, int, str]] = []
        for sz in available_sizes:
            is_default = (sz == default_base)
            c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
            with c1:
                selected = st.checkbox(
                    f"sel_{sz}",
                    value=is_default,
                    key=f"size_sel_{sz}",
                    label_visibility="collapsed",
                )
            with c2:
                st.write(f"`{sz}`")
            with c3:
                n_v = st.number_input(
                    f"n_{sz}",
                    min_value=0, max_value=20,
                    value=(1 if is_default else 0),
                    step=1,
                    key=f"size_n_{sz}",
                    disabled=not selected,
                    label_visibility="collapsed",
                )
            with c4:
                dir_v = st.selectbox(
                    f"dir_{sz}",
                    options=["1WAY", "2WAY"],
                    index=1,  # 2WAY default
                    key=f"size_dir_{sz}",
                    disabled=not selected,
                    label_visibility="collapsed",
                )
            if selected and int(n_v) > 0:
                size_configs.append((sz, int(n_v), dir_v))

        # 선택된 게 없으면 default 강제
        if not size_configs:
            st.warning(f"⚠️ 최소 1개 사이즈를 선택하고 벌수 ≥ 1을 입력하세요. "
                       f"기본값으로 `{default_base}` 1벌 (2WAY) 적용.")
            size_configs = [(default_base, 1, "2WAY")]

        # 알고리즘 매핑 — 결방향 통일 (단순화: 하나라도 2WAY 있으면 2WAY, 다르면 경고)
        directions = set(d for _, _, d in size_configs)
        mixed_dirs = len(directions) > 1
        if mixed_dirs:
            mirror = True  # 혼합이면 2WAY로 통일
            marker_mode_label = "2WAY (혼합)"
            st.warning(
                f"⚠️ 사이즈별 결방향이 다릅니다 ({', '.join(directions)}). "
                f"전체 마카는 **2WAY**로 통일 처리됩니다."
            )
        else:
            sole_dir = next(iter(directions))
            mirror = (sole_dir == "2WAY")
            marker_mode_label = sole_dir

        size_ratio = {sz: n for sz, n, _ in size_configs}
        total_garments = sum(n for _, n, _ in size_configs)
        if len(size_configs) == 1 and total_garments == 1:
            # 단일사이즈 1벌 → 단순 nest 호출 (size_ratio 없음)
            size_ratio = None

        # 요약 텍스트
        if len(size_configs) == 1:
            sz, n, d = size_configs[0]
            summary_text = f"{sz} {n}벌 ({d})"
        else:
            summary_text = " + ".join(f"{sz} {n}벌 ({d})" for sz, n, d in size_configs)
            summary_text += f" · 총 {total_garments}벌"

        base_size = size_configs[0][0]
        config_id = f"grading_{len(size_configs)}sizes_{total_garments}garments"

    # ── 라이브 미리보기 (Bug 3 — 2026-05-01) ──
    # 사장님 명시: 사용자 입력 벌수 = 알고리즘 처리 벌수 라이브 표시.
    est_runtime = 30 if total_garments <= 2 else (45 if total_garments <= 4 else 60)
    st.success(
        f"✓ **현재 마카 구성: {summary_text}**  \n"
        f"📦 총 {total_garments}벌 · 알고리즘 처리 마카 갯수 = "
        f"Σ(piece.quantity) × {total_garments}벌  \n"
        f"⏱️ 예상 처리시간 약 {est_runtime}초"
    )

    # ── 고급 옵션 ──
    with st.expander("⚙️ 고급 옵션 (기본값 권장)", expanded=False):
        runtime = st.slider(
            "최적화 시간 (초)",
            min_value=10, max_value=120, value=est_runtime, step=5,
            help="길수록 효율 향상. 수렴 시 조기 종료됨.",
        )

    return {
        "mirror": mirror,
        "runtime_seconds": runtime,
        "size_ratio": size_ratio,
        "base_size": base_size,
        "marker_mode_label": marker_mode_label,
        "config_id": config_id,
        "total_garments": total_garments,
        "summary_text": summary_text,
    }


# 회귀/하위호환 보존: rectpack 옵션 받는 구버전 — 외부 호출자/regression 용.
def nesting_section_legacy(available_sizes: list[str]) -> dict:
    """[보존] v3.2 베타 옵션 dict — 직접 호출되지 않음. 회귀 안전 위해 함수만 남김."""
    return {
        "use_nesting": False,
        "sizes_to_nest": [],
        "mirror": True,
        "marker_mode": "2WAY",
        "seam_allowance_cm": 0.0,
        "engine": "sparrow",
        "sparrow_runtime": 30,
    }


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
# ║ 결과 표시 — 자동 마카 배치(nesting) 전용                   ║
# ╚════════════════════════════════════════════════════════════╝
def nesting_results_section(
    nest_result: dict,
    fabric_width_cm: float,
) -> None:
    """nest_grading_marker 결과를 화면에 표시. (기존 results_section 과 별개)"""
    st.markdown("#### 자동 마카 배치 결과")

    if nest_result.get("error"):
        st.error(nest_result["error"])
        return

    eff_pct = nest_result["efficiency"] * 100
    marker_cm = nest_result["marker_length_cm"]
    marker_yd = marker_cm / 91.44
    marker_m = marker_cm / 100.0

    # 핵심 메트릭 3개
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("효율", f"{eff_pct:.1f} %")
    with c2:
        st.metric("마카 길이", f"{marker_yd:.2f} yd",
                  f"{marker_m:.2f} m / {marker_cm:.1f} cm")
    with c3:
        st.metric("원단 폭", f"{fabric_width_cm:.0f} cm",
                  f"≈ {fabric_width_cm / 2.54:.1f} in")

    # 메타 정보
    sizes_str = ", ".join(nest_result.get("sizes_included", []))
    n_pieces = len(nest_result.get("pieces_used", []))
    n_mirrored = sum(1 for v in nest_result.get("mirror_count_per_piece", {}).values() if v == 1)
    n_unplaced = len(nest_result.get("unplaced", []))
    engine = nest_result.get("engine", "rectpack")
    engine_label = "sparrow (Phase 2, polygon nesting)" if engine == "sparrow" else "rectpack (Phase 1, bbox)"
    runtime_info = ""
    if engine == "sparrow":
        rt = nest_result.get("runtime_actual_sec")
        rt_req = nest_result.get("runtime_seconds_requested")
        if rt is not None:
            runtime_info = f"  ·  엔진: {engine_label}  ·  실행 {rt:.1f}s / 요청 {rt_req}s"
        else:
            runtime_info = f"  ·  엔진: {engine_label}"
    else:
        runtime_info = f"  ·  엔진: {engine_label}"
    st.caption(
        f"사이즈: **{sizes_str}**  ·  "
        f"피스 수: {n_pieces} (미러 생성 {n_mirrored})  ·  "
        f"배치 실패: {n_unplaced}  ·  "
        f"결방향: {nest_result.get('marker_mode', '—')}"
        f"{runtime_info}"
    )

    # 시각화 — sparrow 는 자체 생성 SVG 가 가장 정확. 없으면 matplotlib fallback.
    svg_content = nest_result.get("svg_content", "")
    if engine == "sparrow" and svg_content:
        # SVG 직접 표시 — sparrow 의 placement 좌표가 정확히 반영됨
        st.markdown("##### 마카 시각화 (sparrow native SVG)")
        st.components.v1.html(svg_content, height=600, scrolling=True)

        # SVG 다운로드
        st.download_button(
            "마카 SVG 다운로드 (벡터)",
            data=svg_content.encode("utf-8"),
            file_name="marker_phase2_sparrow.svg",
            mime="image/svg+xml",
        )
        # matplotlib bbox preview 도 같이 보여줌 (기존 익숙한 시각)
        with st.expander("📐 bbox 기반 matplotlib 미리보기 (참고)"):
            try:
                fig = visualize_marker(
                    nest_result["pieces_used"], nest_result, fabric_width_cm,
                    polygons=nest_result.get("polygons"), polygon_unit="cm",
                )
                st.pyplot(fig)
                plt.close(fig)
            except Exception as viz_err:
                st.caption(f"(matplotlib 미리보기 실패: {viz_err})")
    else:
        # rectpack — 기존 matplotlib 시각화
        fig = visualize_marker(
            nest_result["pieces_used"],
            nest_result,
            fabric_width_cm,
            polygons=nest_result.get("polygons"),
            polygon_unit="cm",
        )
        st.pyplot(fig)
        png_bytes = figure_to_png_bytes(fig)
        st.download_button(
            "마카 PNG 다운로드",
            data=png_bytes,
            file_name="marker_phase1.png",
            mime="image/png",
        )
        plt.close(fig)

    # 경고 (추정/배치 실패 등)
    if nest_result.get("warnings"):
        with st.expander(f"⚠️ 경고 {len(nest_result['warnings'])}건 (추정/배치)"):
            for w in nest_result["warnings"]:
                st.write(f"- {w}")


# ╔════════════════════════════════════════════════════════════╗
# ║ v3.3: 재질별 결과 표시 (소싱팀용)                           ║
# ╚════════════════════════════════════════════════════════════╝
def material_results_section(nest_all: dict, pdf_context: dict | None = None,
                             hq_match: dict | None = None,
                             marker_config: dict | None = None) -> None:
    """nest_by_material 결과를 재질별 카드 + 총합 표로 표시.
    - 재질당 1개 마카 (한글 라벨 SVG)
    - 미분류 피스 경고
    - pdf_context 가 있으면 상단에 PDF/Excel 다운로드 버튼 표시
    - hq_match + marker_config 있으면 본사 효율/요척 비교 + 마카 구성 차이 안내
    """
    by_material = nest_all.get("by_material", {})
    summary_rows = nest_all.get("summary_rows", [])
    unclassified = nest_all.get("unclassified_warnings", [])
    materials_ordered = nest_all.get("materials_ordered", [])

    if not by_material:
        st.warning("계산된 재질이 없습니다.")
        return

    # ── 성공 안내 (D-3, D-4 처리시간 강조) ──
    n_mats = len(by_material)
    total_rt = nest_all.get("total_runtime_sec", 0)
    n_unplaced_total = sum(len(r.get("unplaced", [])) for r in by_material.values())
    is_multi_top = any(r.get("total_garments", 0) > 1 for r in summary_rows)
    if is_multi_top and summary_rows:
        mode_label = f"다중사이즈 마카 ({summary_rows[0].get('total_garments', 1)}벌)"
    else:
        mode_label = "단일사이즈 마카"
    if n_unplaced_total == 0:
        st.success(
            f"✅ **자동 마카 배치 완료** — {n_mats}개 재질 / {mode_label} / "
            f"전체 처리 시간 **{total_rt:.0f}초**"
        )
    else:
        st.warning(
            f"⚠️ {n_mats}개 재질 처리 — 배치 실패 {n_unplaced_total}개 발견. 아래 결과에서 상세 확인."
        )

    # ── 본사 매칭 비교 박스 (Phase 2-B-5 — expander 안에 숨김, 검증/테스트 용도) ──
    if hq_match and any(safe_float(hq_match.get(k)) > 0 for k in ("효율_pct", "벌당_요척_yd")):
      with st.expander(f"🔍 본사 검증 데이터 비교 ({hq_match.get('품번', '')})", expanded=False):
        main_row = next((r for r in summary_rows if r["material"] == "주원단"), None)
        if main_row is None and summary_rows:
            main_row = summary_rows[0]
        if main_row:
            hq_eff = safe_float(hq_match.get("효율_pct"))
            our_eff = main_row["efficiency_pct"]
            hq_yd = safe_float(hq_match.get("벌당_요척_yd"))
            our_yd = main_row.get("yards_per_garment") or main_row["marker_length_yd"]
            code = hq_match.get("품번", "")

            # 본사 마카 구성 추정 — 우선순위: 벌수 필드 > 사이즈비율 X
            hq_garments = safe_float(hq_match.get("벌수"))  # PDF 수동 입력만 보유
            hq_ratio_str = hq_match.get("사이즈비율", "")
            hq_config_str = ""
            if hq_garments > 0:
                hq_config_str = f"{int(hq_garments)}벌 구성"
            elif hq_ratio_str:
                # "X:Y-Z" 또는 "X:Y" — X 가 사이즈 종류 수 추정
                try:
                    n_sizes = int(hq_ratio_str.split(":")[0].strip())
                    hq_config_str = f"{n_sizes}사이즈 마카"
                except (ValueError, IndexError):
                    hq_config_str = "마카 구성 정보 없음"
            else:
                hq_config_str = "마카 구성 정보 없음"
            if hq_ratio_str:
                hq_config_str += f" (사이즈비율 `{hq_ratio_str}`)"

            # 우리 마카 구성
            mc = marker_config or {}
            our_total = mc.get("total_garments", main_row.get("total_garments", 1))
            our_mode = mc.get("marker_mode_label", "2WAY")
            our_base = mc.get("base_size", "")
            our_summary = mc.get("summary_text", "")
            our_config_str = our_summary or f"{our_total}벌 ({our_mode})"

            st.markdown(f"#### 🏢 본사 비교 ({code})")
            # 두 줄 비교 (본사 / 우리)
            hq_eff_part = f"효율 **{hq_eff:.2f}%**" if hq_eff > 0 else "효율 데이터 없음"
            hq_yd_part = f"1벌당 **{hq_yd:.3f} yd**" if hq_yd > 0 else "1벌 요척 데이터 없음"
            st.markdown(f"- **본사 마카**: {hq_config_str} · {hq_yd_part} · {hq_eff_part}")
            st.markdown(
                f"- **우리 마카**: {our_config_str} · "
                f"1벌당 **{our_yd:.3f} yd** · 효율 **{our_eff:.2f}%**"
            )

            # 마카 구성 차이 안내 + 추천
            mismatch = False
            if hq_garments > 0 and our_total != int(hq_garments):
                mismatch = True
            elif hq_ratio_str and our_total == 1:
                # 본사가 multi 인데 우리는 single → 명백한 불일치
                mismatch = True

            if mismatch:
                # 추천 옵션 자동 결정
                hq_n = int(hq_garments) if hq_garments > 0 else None
                if hq_n is None and hq_ratio_str:
                    try:
                        hq_n = int(hq_ratio_str.split(":")[0].strip())
                    except (ValueError, IndexError):
                        hq_n = None
                rec = ""
                if hq_n == 1:
                    rec = "옵션 ① (기준사이즈 1벌, 1WAY)"
                elif hq_n == 2:
                    rec = "옵션 ② (기준사이즈 좌우 페어, 2WAY) 또는 ④ (2사이즈 조합)"
                elif hq_n is not None and hq_n >= 3:
                    rec = f"옵션 ③ (전 사이즈 1벌씩, {hq_n}사이즈 마카)"
                if rec:
                    st.info(
                        f"ⓘ 마카 구성이 달라 1벌당 요척 직접 비교는 부정확합니다.  \n"
                        f"**{rec}**으로 다시 돌리면 본사와 같은 구성에서 fair 비교 가능."
                    )
                else:
                    st.caption(
                        "ⓘ 본사 마카 구성 정보가 부족 — 1벌당 비교는 참고용. "
                        "효율(%)은 마카 구성 무관하므로 직접 비교 가능."
                    )
            elif hq_eff > 0:
                eff_gap = our_eff - hq_eff
                verdict = "✓ 본사 능가" if eff_gap >= 0 else "⚠️ 본사 미달"
                st.success(f"동일 마카 구성에서 효율 차이: `{eff_gap:+.2f}p` {verdict}")

    # ── PDF + Excel 다운로드 ──
    if pdf_context is not None:
        full_ctx = {**pdf_context, "nest_all": nest_all, "hq_match": hq_match}
        file_label = (pdf_context.get("style") or pdf_context.get("file_name") or "report").replace(" ", "_")
        dl_c1, dl_c2 = st.columns(2)
        with dl_c1:
            try:
                pdf_bytes = generate_pdf_report_v33(full_ctx)
                st.download_button(
                    "📥 PDF 보고서",
                    data=pdf_bytes,
                    file_name=f"{file_label}_요척보고서.pdf",
                    mime="application/pdf",
                    type="primary",
                    key="dl_pdf_v33",
                )
            except Exception as pdf_err:
                st.warning(f"PDF 생성 실패: {pdf_err}")
        with dl_c2:
            try:
                xlsx_bytes = generate_excel_report_v33(full_ctx)
                st.download_button(
                    "📊 Excel 다운로드",
                    data=xlsx_bytes,
                    file_name=f"{file_label}_요척보고서.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_xlsx_v33",
                )
            except Exception as xl_err:
                st.warning(f"Excel 생성 실패: {xl_err}")

    # ── 미분류 경고 ──
    if unclassified:
        n = len(unclassified)
        names = ", ".join(u["piece_name"] for u in unclassified[:5])
        if n > 5:
            names += f" 외 {n - 5}개"
        st.warning(
            f"⚠️ {n}개 피스의 재질이 미지정 — 우선 **주원단**으로 묶어 계산합니다. "
            f"({names})  \n"
            f"패턴 파일에 `Material:` 또는 `Annotation:` 으로 재질 표기를 추가하세요."
        )

    # ── 총합 표 (가장 위) ──
    st.markdown("#### 📊 재질별 요척 종합")
    is_multi = any(r.get("total_garments", 0) > 1 for r in summary_rows)
    if is_multi:
        # multi-size: 1벌당 요척 합계
        total_yd = sum(r["yards_per_garment"] for r in summary_rows)
        total_label = "1벌당 총 요척"
    else:
        total_yd = sum(r["marker_length_yd"] for r in summary_rows)
        total_label = "총 요척 합계"

    table_rows = []
    for r in summary_rows:
        n_pat = r["pieces_count"]
        n_mir = r["mirror_count"]
        tg = r.get("total_garments", 1)
        per_garment = n_pat + n_mir
        n_total = per_garment * (tg if tg > 1 else 1)
        row_dict = {
            "재질": r["material"],
            "원단 폭": f"{r['fabric_width_cm']:.0f} cm",
            "마카 길이": f"{r['marker_length_cm']:.1f} cm",
            "마카 요척": f"{r['marker_length_yd']:.2f} yd",
            "패턴 갯수": f"{n_pat}",
            "마카 갯수": f"{n_total}",
            "효율": f"{r['efficiency_pct']:.1f} %",
            "처리 시간": f"{r['runtime_actual_sec']:.0f}s",
        }
        if is_multi:
            row_dict["1벌당 요척"] = f"{r['yards_per_garment']:.2f} yd ({tg}벌 ÷)"
        table_rows.append(row_dict)
    df = pd.DataFrame(table_rows)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(f"**{total_label}: {total_yd:.2f} yd** "
               f"({total_yd * 0.9144:.2f} m)  ·  "
               f"전체 처리 시간 {nest_all.get('total_runtime_sec', 0):.0f}초")

    st.divider()

    # ── 재질별 상세 카드 ──
    for mat in materials_ordered:
        res = by_material.get(mat)
        if not res:
            continue
        row = next((r for r in summary_rows if r["material"] == mat), None)
        if row is None:
            continue

        st.markdown(f"### {mat}")

        if res.get("error"):
            st.error(f"❌ {mat} 마카 배치 실패: {res['error']}")
            continue

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("원단 폭", f"{row['fabric_width_cm']:.0f} cm")

        # multi-size 모드면 1벌당 요척 표시, 아니면 마카 길이 그대로
        is_multi = row.get("total_garments", 0) > 1
        with c2:
            if is_multi:
                st.metric("1벌당 요척",
                          f"{row['yards_per_garment']:.2f} yd",
                          f"마카 {row['marker_length_yd']:.2f} yd ÷ {row['total_garments']}벌")
            else:
                st.metric("마카 길이",
                          f"{row['marker_length_yd']:.2f} yd",
                          f"{row['marker_length_cm']:.1f} cm")
        with c3:
            st.metric("효율", f"{row['efficiency_pct']:.1f} %")
        with c4:
            # 새 라벨 통일 (사장님 명시):
            #   "마카 갯수" = 마카에 실제 깔린 모든 피스 수 (= n_total × tg)
            n_pat = row["pieces_count"]
            n_mir = row["mirror_count"]
            tg = row.get("total_garments", 1)
            per_garment_pieces = n_pat + n_mir  # 1벌당 마카에 깔리는 피스 수
            n_total = per_garment_pieces * (tg if tg > 1 else 1)
            sub = f"패턴 {n_pat} × {tg}벌" if tg > 1 else None
            st.metric("마카 갯수", f"{n_total} 개", sub)
        # 통일된 caption — 기준사이즈 / 패턴 갯수 / 마카 갯수
        st.caption(
            f"📦 패턴 갯수: **{n_pat} 개** (1벌당 unique 패턴)  ·  "
            f"마카 벌수: **{tg} 벌**" + (f"  ·  1벌당 마카 길이 {row['cm_per_garment']:.1f} cm" if is_multi else "")
        )

        # SVG 시각화 (한글 라벨) — 화면에만 표시. 다운로드는 PDF 한 가지로 통합 (작업 5).
        svg = res.get("svg_content_humanized") or res.get("svg_content", "")
        if svg:
            mlen = row["marker_length_cm"]
            fw = row["fabric_width_cm"]
            ratio = mlen / fw if fw > 0 else 1.0
            h_px = max(300, min(900, int(420 * (1.0 + ratio * 0.5))))
            st.components.v1.html(svg, height=h_px, scrolling=True)
        else:
            st.caption("(시각화 SVG 없음)")

        if res.get("unplaced"):
            st.warning(f"⚠️ 배치 실패 {len(res['unplaced'])}개 — 원단 폭이 너무 좁거나 피스가 너무 큼")

        if res.get("warnings"):
            with st.expander(f"⚠️ {mat} 경고 {len(res['warnings'])}건"):
                for w in res["warnings"]:
                    st.write(f"- {w}")

        st.divider()


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
# ║ v3.3 PDF 생성 (재질별 마카 결과 → 보고서)                   ║
# ╚════════════════════════════════════════════════════════════╝
def generate_pdf_report_v33(context: dict) -> bytes:
    """
    v3.3 자동 마카 배치 결과 PDF.

    context:
      file_name        : str
      style            : str
      sample_size      : str
      selected_sizes   : list[str]
      nest_all         : nest_by_material 결과 dict
      generated_at     : str
      runtime_seconds_used : int
    """
    nest_all = context["nest_all"]
    hq_match = context.get("hq_match")
    summary_rows = nest_all.get("summary_rows", [])
    by_material = nest_all.get("by_material", {})
    materials_ordered = nest_all.get("materials_ordered", [])

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
    small_caption = ParagraphStyle(
        "Caption", parent=styles["Normal"], fontName=KR_FONT,
        fontSize=8, textColor=colors.HexColor("#64748b"),
    )

    elements = []

    # 타이틀
    style_label = context.get("style") or context.get("file_name", "STYLE")
    elements.append(Paragraph(f"원단 요척 보고서 — {style_label}", title_style))

    # 메타 요약
    elements.append(Paragraph("스타일 요약", section_style))
    summary = [
        ["스타일", context.get("style") or "-"],
        ["샘플사이즈", context.get("sample_size") or "-"],
        ["계산 사이즈", ", ".join(context.get("selected_sizes", []))],
        ["파일", context.get("file_name") or "-"],
        ["엔진", f"jagua-rs sparrow ({context.get('runtime_seconds_used', 30)}s)"],
        ["작성일", context.get("generated_at") or "-"],
    ]
    elements.append(_pdf_kv_table(summary, KR_FONT))

    # 종합 표 (재질별)
    elements.append(Paragraph("재질별 요척 (자동 마카 배치)", section_style))
    total_yd = sum(r["marker_length_yd"] for r in summary_rows)
    total_m = total_yd * 0.9144

    header = ["원단 종류", "원단 폭", "마카 길이", "효율", "패턴 갯수", "마카 갯수", "요척"]
    rows = [header]
    for r in summary_rows:
        n_pat = r["pieces_count"]
        n_mir = r["mirror_count"]
        tg = r.get("total_garments", 1)
        per_garment = n_pat + n_mir
        n_total = per_garment * (tg if tg > 1 else 1)
        rows.append([
            r["material"],
            f"{r['fabric_width_cm']:.0f} cm",
            f"{r['marker_length_cm']:.1f} cm",
            f"{r['efficiency_pct']:.1f} %",
            f"{n_pat}",
            f"{n_total}",
            f"{r['marker_length_yd']:.2f} yd",
        ])
    # 합계 행
    rows.append([
        "합계", "—", "—", "—", "—", "—",
        f"{total_yd:.2f} yd",
    ])
    t = Table(rows, colWidths=[70, 55, 65, 50, 60, 60, 60])
    last_row = len(rows) - 1
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), KR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (0, last_row), (-1, last_row), colors.HexColor("#fef2f2")),
        ("FONTNAME", (0, last_row), (-1, last_row), KR_FONT),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        f"총 요척 합계: <b>{total_yd:.2f} yd ({total_m:.2f} m)</b>",
        body_style,
    ))
    elements.append(Spacer(1, 12))

    # 재질별 상세 (메트릭만)
    elements.append(Paragraph("재질별 상세", section_style))
    for mat in materials_ordered:
        res = by_material.get(mat)
        row = next((r for r in summary_rows if r["material"] == mat), None)
        if res is None or row is None:
            continue
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<b>● {mat}</b>", body_style))
        if res.get("error"):
            elements.append(Paragraph(f"❌ 마카 배치 실패: {res['error']}", body_style))
            continue
        n_pat = row["pieces_count"]
        n_mir = row["mirror_count"]
        tg = row.get("total_garments", 1)
        per_garment = n_pat + n_mir
        n_total = per_garment * (tg if tg > 1 else 1)
        detail = [
            ["원단 폭", f"{row['fabric_width_cm']:.0f} cm"],
            ["마카 길이", f"{row['marker_length_cm']:.1f} cm  ({row['marker_length_yd']:.2f} yd)"],
            ["효율", f"{row['efficiency_pct']:.2f} %"],
            ["패턴 갯수 (1벌당)", f"{n_pat} 개"],
            ["마카 갯수 (전체)", f"{n_total} 개"],
            ["마카 벌수", f"{tg} 벌 (다중 사이즈)" if tg > 1 else "1 벌 (단일 사이즈)"],
        ]
        if tg > 1:
            detail.append(["1벌당 마카 길이",
                           f"{row.get('cm_per_garment', 0):.1f} cm  ({row.get('yards_per_garment', 0):.3f} yd)"])
        detail.extend([
            ["배치 실패", str(len(res.get("unplaced", [])))],
            ["처리 시간", f"{row['runtime_actual_sec']:.1f} 초"],
        ])
        elements.append(_pdf_kv_table(detail, KR_FONT, col_widths=(110, 330)))

    # 본사 매칭 비교 (Phase 2-B-5 — 마카 구성 차이 명시)
    if hq_match:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("🏢 본사 데이터 비교", section_style))
        main_row = next((r for r in summary_rows if r["material"] == "주원단"), None)
        if main_row is None and summary_rows:
            main_row = summary_rows[0]
        if main_row:
            hq_eff = safe_float(hq_match.get("효율_pct"))
            our_eff = main_row["efficiency_pct"]
            hq_yd = safe_float(hq_match.get("벌당_요척_yd"))
            our_yd = main_row.get("yards_per_garment") or main_row["marker_length_yd"]
            hq_garments = safe_float(hq_match.get("벌수"))
            hq_ratio_str = hq_match.get("사이즈비율", "")
            mc = context.get("marker_config", {}) or {}
            our_total = mc.get("total_garments", main_row.get("total_garments", 1))
            our_summary = mc.get("summary_text", f"{our_total}벌")
            # 본사 마카 구성 문자열
            if hq_garments > 0:
                hq_cfg = f"{int(hq_garments)}벌 구성"
            elif hq_ratio_str:
                try:
                    n = int(hq_ratio_str.split(":")[0].strip())
                    hq_cfg = f"{n}사이즈 마카"
                except (ValueError, IndexError):
                    hq_cfg = "구성 정보 없음"
            else:
                hq_cfg = "구성 정보 없음"
            if hq_ratio_str:
                hq_cfg += f" (사이즈비율 {hq_ratio_str})"

            comp = [["품번", str(hq_match.get("품번", "—"))]]
            comp.append(["본사 마카 구성", hq_cfg])
            comp.append(["우리 마카 구성", our_summary])
            if hq_eff > 0:
                eff_gap = our_eff - hq_eff
                comp.append(["효율 (본사 / 우리)",
                             f"{hq_eff:.2f} % / {our_eff:.2f} % "
                             f"(차이 {eff_gap:+.2f}p, "
                             f"{'능가' if eff_gap >= 0 else '미달'})"])
            else:
                comp.append(["효율 (우리)", f"{our_eff:.2f} % (본사 효율 데이터 없음)"])
            if hq_yd > 0:
                yd_gap = our_yd - hq_yd
                comp.append(["1벌당 요척 (본사 / 우리)",
                             f"{hq_yd:.3f} yd / {our_yd:.3f} yd "
                             f"(차이 {yd_gap:+.3f} yd) ⚠️ 마카 구성 다르면 부정확"])
            else:
                comp.append(["1벌당 요척 (우리)",
                             f"{our_yd:.3f} yd (본사 요척 데이터 없음)"])
            if hq_match.get("LOSS여부"):
                comp.append(["본사 LOSS 기준", str(hq_match.get("LOSS여부"))])
            elements.append(_pdf_kv_table(comp, KR_FONT, col_widths=(140, 300)))

    # 미분류 경고
    unclassified = nest_all.get("unclassified_warnings", [])
    if unclassified:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("⚠️ 재질 미지정 피스", section_style))
        names = ", ".join(u["piece_name"] for u in unclassified[:10])
        if len(unclassified) > 10:
            names += f" 외 {len(unclassified) - 10}개"
        elements.append(Paragraph(
            f"{len(unclassified)}개 피스의 재질 표기가 누락 — 우선 주원단으로 묶어 계산함. ({names})",
            body_style,
        ))

    # 푸터
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(
        f"엔진: jagua-rs sparrow  ·  생성일: {context.get('generated_at')}  ·  "
        f"파일: {context.get('file_name')}",
        small_caption,
    ))

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
# ║ v3.3 Excel 생성 (재질별 마카 결과 → 다중 시트)              ║
# ╚════════════════════════════════════════════════════════════╝
def generate_excel_report_v33(context: dict) -> bytes:
    """
    v3.3 자동 마카 배치 결과 → Excel (.xlsx).

    시트 구성:
      ① 종합요약 — 메타 + 재질별 1행 + 합계
      ② 본사비교 — hq_match 있을 때만 (생략 가능)
      ③ {재질명}_상세 — 재질별 placements + 메트릭
    """
    nest_all = context["nest_all"]
    hq_match = context.get("hq_match")
    summary_rows = nest_all.get("summary_rows", [])
    by_material = nest_all.get("by_material", {})
    materials_ordered = nest_all.get("materials_ordered", [])

    wb = Workbook()

    # ── 공통 스타일 ──
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="0F172A")
    sub_font = Font(bold=True)
    sub_fill = PatternFill("solid", fgColor="F8FAFC")
    total_fill = PatternFill("solid", fgColor="FEF2F2")
    thin = Side(style="thin", color="CBD5E1")
    border = Border(top=thin, bottom=thin, left=thin, right=thin)

    def _style_header(ws, row_idx):
        for cell in ws[row_idx]:
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")

    def _autosize(ws, max_width=42):
        for col in ws.columns:
            letter = col[0].column_letter
            maxw = 0
            for cell in col:
                v = "" if cell.value is None else str(cell.value)
                disp = sum(2 if ord(c) > 127 else 1 for c in v)
                if disp > maxw:
                    maxw = disp
            ws.column_dimensions[letter].width = min(maxw + 2, max_width)

    # ─────────── 시트 1: 종합요약 ───────────
    ws1 = wb.active
    ws1.title = "종합요약"
    # 메타
    meta = [
        ["스타일", context.get("style") or "-"],
        ["샘플사이즈", context.get("sample_size") or "-"],
        ["계산 사이즈", ", ".join(context.get("selected_sizes", []))],
        ["파일", context.get("file_name") or "-"],
        ["엔진", f"jagua-rs sparrow ({context.get('runtime_seconds_used', 30)}s)"],
        ["작성일", context.get("generated_at") or "-"],
    ]
    for row in meta:
        ws1.append(row)
        ws1.cell(ws1.max_row, 1).font = sub_font
    ws1.append([])

    # 재질별 표 (라벨 통일: 패턴 갯수 / 마카 갯수)
    headers = ["원단 종류", "원단 폭(cm)", "마카 길이(cm)", "마카 길이(yd)",
               "효율(%)", "패턴 갯수", "마카 갯수", "마카 벌수", "1벌당 요척(yd)", "처리시간(s)"]
    ws1.append(headers)
    hdr_row = ws1.max_row
    total_yd = 0
    total_yd_per = 0
    is_multi = any(r.get("total_garments", 0) > 1 for r in summary_rows)
    for r in summary_rows:
        n_pat = r["pieces_count"]
        n_mir = r["mirror_count"]
        tg = r.get("total_garments", 1)
        per_garment = n_pat + n_mir
        n_total = per_garment * (tg if tg > 1 else 1)
        yd_per = r.get("yards_per_garment") or r["marker_length_yd"]
        ws1.append([
            r["material"], round(r["fabric_width_cm"], 0),
            round(r["marker_length_cm"], 1), round(r["marker_length_yd"], 3),
            round(r["efficiency_pct"], 2),
            n_pat, n_total, tg, round(yd_per, 3),
            round(r.get("runtime_actual_sec", 0), 1),
        ])
        total_yd += r["marker_length_yd"]
        total_yd_per += yd_per

    # 합계 행
    ws1.append([
        "합계", "—", "—", round(total_yd, 3), "—",
        "—", "—", "—", round(total_yd_per, 3) if is_multi else "—", "—",
    ])
    total_row = ws1.max_row
    for cell in ws1[total_row]:
        cell.font = sub_font
        cell.fill = total_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
    _style_header(ws1, hdr_row)
    for row_idx in range(hdr_row + 1, total_row):
        for cell in ws1[row_idx]:
            cell.border = border
            cell.alignment = Alignment(horizontal="center")
    _autosize(ws1)

    # ─────────── 시트 2: 본사 비교 (있을 때만) ───────────
    if hq_match:
        ws_hq = wb.create_sheet("본사비교")
        main_row = next((r for r in summary_rows if r["material"] == "주원단"), None)
        if main_row is None and summary_rows:
            main_row = summary_rows[0]
        if main_row:
            hq_eff = safe_float(hq_match.get("효율_pct"))
            our_eff = main_row["efficiency_pct"]
            hq_yd = safe_float(hq_match.get("벌당_요척_yd"))
            our_yd = main_row.get("yards_per_garment") or main_row["marker_length_yd"]
            hq_w_in = safe_float(hq_match.get("원단폭_in"))
            hq_w_cm = safe_float(hq_match.get("원단폭_cm"))

            rows_hq = [["항목", "본사", "앱(sparrow)", "차이"]]
            rows_hq.append(["품번", str(hq_match.get("품번", "—")), context.get("style") or "—", "—"])
            if hq_eff > 0:
                rows_hq.append(["효율(%)", round(hq_eff, 2), round(our_eff, 2),
                                f"{our_eff - hq_eff:+.2f}p" + (" ✓" if our_eff >= hq_eff else " ⚠️")])
            else:
                rows_hq.append(["효율(%)", "—", round(our_eff, 2), "—"])
            if hq_yd > 0:
                rows_hq.append(["1벌당 요척(yd)", round(hq_yd, 3), round(our_yd, 3),
                                f"{our_yd - hq_yd:+.3f}"])
            else:
                rows_hq.append(["1벌당 요척(yd)", "—", round(our_yd, 3), "—"])
            rows_hq.append(["원단폭(in)", round(hq_w_in, 0) if hq_w_in > 0 else "—", "—", "—"])
            rows_hq.append(["원단폭(cm)", round(hq_w_cm, 0) if hq_w_cm > 0 else "—", "—", "—"])
            rows_hq.append(["사이즈비율", str(hq_match.get("사이즈비율") or "—"), "—", "—"])
            rows_hq.append(["LOSS여부", str(hq_match.get("LOSS여부") or "—"), "—", "—"])
            rows_hq.append(["출처", str(hq_match.get("출처") or "—"), "—", "—"])

            for row in rows_hq:
                ws_hq.append(row)
            _style_header(ws_hq, 1)
            for row_idx in range(2, ws_hq.max_row + 1):
                for cell in ws_hq[row_idx]:
                    cell.border = border
                    cell.alignment = Alignment(horizontal="center")
        _autosize(ws_hq)

    # ─────────── 시트 3+: 재질별 상세 ───────────
    for mat in materials_ordered:
        res = by_material.get(mat)
        row_meta = next((r for r in summary_rows if r["material"] == mat), None)
        if res is None or row_meta is None:
            continue
        ws_mat = wb.create_sheet(mat[:30])  # 시트명 31자 제한
        # 메타 영역 (라벨 통일)
        n_pat = row_meta["pieces_count"]; n_mir = row_meta["mirror_count"]
        tg = row_meta.get("total_garments", 1)
        per_garment = n_pat + n_mir
        n_total = per_garment * (tg if tg > 1 else 1)
        meta_rows = [
            ["원단 폭", f"{row_meta['fabric_width_cm']:.0f} cm"],
            ["마카 길이", f"{row_meta['marker_length_cm']:.1f} cm  ({row_meta['marker_length_yd']:.3f} yd)"],
            ["효율", f"{row_meta['efficiency_pct']:.2f} %"],
            ["패턴 갯수 (1벌당)", f"{n_pat} 개"],
            ["마카 갯수 (전체)", f"{n_total} 개"],
            ["마카 벌수", f"{tg} 벌 (다중)" if tg > 1 else "1 벌 (단일)"],
        ]
        if tg > 1:
            meta_rows.append(["1벌당 마카 길이",
                              f"{row_meta.get('cm_per_garment', 0):.1f} cm  ({row_meta.get('yards_per_garment', 0):.3f} yd)"])
        meta_rows.extend([
            ["배치 실패", str(len(res.get("unplaced", [])))],
            ["처리 시간", f"{row_meta.get('runtime_actual_sec', 0):.1f} 초"],
            ["엔진 경고", str(len(res.get("warnings", [])))],
        ])
        for k, v in meta_rows:
            ws_mat.append([k, v])
            ws_mat.cell(ws_mat.max_row, 1).font = sub_font
            ws_mat.cell(ws_mat.max_row, 1).fill = sub_fill
        ws_mat.append([])

        # placements 표
        ws_mat.append(["피스 ID", "이름", "kind", "x_cm", "y_cm",
                       "bbox_w_cm", "bbox_h_cm", "회전(deg)"])
        plc_hdr = ws_mat.max_row
        _style_header(ws_mat, plc_hdr)
        for pl in res.get("placements", []):
            ws_mat.append([
                pl.get("piece_id", ""), pl.get("piece_name", ""),
                pl.get("kind", ""), round(pl.get("x_cm", 0), 2),
                round(pl.get("y_cm", 0), 2), round(pl.get("bbox_w_cm", 0), 2),
                round(pl.get("bbox_h_cm", 0), 2), round(pl.get("rotation_applied_deg", 0), 1),
            ])
        for row_idx in range(plc_hdr + 1, ws_mat.max_row + 1):
            for cell in ws_mat[row_idx]:
                cell.border = border
        _autosize(ws_mat)

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
        st.session_state.pop("nesting_v1", None)
        st.session_state.pop("nest_all_v33", None)
        st.session_state["accessory_fabrics"] = []
        st.session_state["last_file"] = parsed["file_name"]

    pieces_all = parsed["pieces"]

    st.divider()
    selected_sizes = size_selection_section(parsed)

    # 사장님 절대 원칙 (2026-05-01): DXF Material 코드 누락 시 사용자 수동 매핑 필수.
    # parsed["pieces"][*]["material_inferred"] 가 이 안에서 직접 override 됨.
    st.divider()
    material_mapping_section(parsed)

    st.divider()
    widths = width_section(pieces_all, selected_sizes)

    # ── 본사 매칭 자동 감지 (메인 흐름에는 노출 X — 결과 화면 비교용으로만) ──
    style_code_auto = extract_style_code(parsed.get("file_name", "")) or parsed.get("style", "")
    hq_match = find_hq_match(style_code_auto) if style_code_auto else None
    # 일반 사용자는 본사 데이터 자체가 없음. 인포 박스 노출 안 함.
    # nesting_section 도 hq_match 기반 prefill 없음 (DXF 사이즈 그대로 default).

    st.divider()
    opts = nesting_section(parsed.get("sizes", []))

    st.divider()

    # ── v3.3: 일직선 흐름 — 항상 sparrow 재질별 자동 마카 ─────
    if st.button("▶️ 마카 + 요척 산출", type="primary"):
        if not selected_sizes:
            st.error("계산할 사이즈를 1개 이상 선택해주세요.")
        else:
            # Bug 3 — 사용자 입력 → 알고리즘 처리 일치 명시 확인 (2026-05-01)
            sr_dbg = opts.get("size_ratio")
            tg_dbg = opts.get("total_garments", 1)
            if sr_dbg:
                _ratio_str = ", ".join(f"{sz}×{n}벌" for sz, n in sr_dbg.items())
                st.info(
                    f"🎯 **알고리즘 처리 확인** — 사이즈 비율: `{_ratio_str}` "
                    f"· 총 {tg_dbg}벌 · grain={opts.get('marker_mode_label', '2WAY')}"
                )
            else:
                st.info(
                    f"🎯 **알고리즘 처리 확인** — 단일사이즈 단일벌 "
                    f"· {opts.get('base_size', '?')} × 1벌 "
                    f"· grain={opts.get('marker_mode_label', '2WAY')}"
                )

            pieces_calc = apply_accessory_overrides(
                pieces_all, st.session_state.get("accessory_fabrics", []),
            )
            polygons = {
                p["piece_id"]: ShapelyPolygon(p["coords_cm"])
                for p in pieces_calc
                if p.get("coords_cm")
            }

            # 재질별 마카: 진행 표시 (재질당 1개)
            mat_set = {p.get("material_inferred") or "주원단" for p in pieces_calc
                       if p.get("size") in selected_sizes}
            n_mats = max(1, len(mat_set))
            est_total = opts["runtime_seconds"] * n_mats

            progress_bar = st.progress(0.0, text=f"마카 배치 준비 중... (재질 {n_mats}개, 최대 {est_total}초)")

            def _on_progress(idx, total, mat_name):
                progress_bar.progress(
                    idx / total,
                    text=f"[{idx}/{total}] {mat_name} 마카 배치 중... (수렴 시 조기 종료)",
                )

            # 사장님 절대 원칙 (2026-04-30):
            #   1WAY/2WAY 는 sparrow allowed_orientations 로 처리 (mirror_each 폐기)
            #   마카 갯수 = Σ(piece.quantity) × n_lay
            grain_mode = opts.get("marker_mode_label", "2WAY")
            if "혼합" in grain_mode:
                grain_mode = "2WAY"  # 혼합은 2WAY 통일
            try:
                with st.spinner(f"sparrow 재질별 마카 배치 중 (최대 약 {est_total}초)..."):
                    if opts.get("size_ratio"):
                        nest_all = nest_by_material_multisize(
                            pieces=pieces_calc,
                            fabric_widths_per_material=widths,
                            size_ratio=opts["size_ratio"],
                            polygons=polygons,
                            mirror_each=False,  # 폐기됨
                            grain_mode=grain_mode,
                            runtime_seconds=opts["runtime_seconds"],
                            early_termination=True,
                            progress_callback=_on_progress,
                        )
                    else:
                        # 단일 사이즈 모드 — n_lay 적용 (벌수)
                        nest_all = nest_by_material(
                            pieces=pieces_calc,
                            fabric_widths_per_material=widths,
                            sizes_to_nest=selected_sizes,
                            polygons=polygons,
                            mirror_each=False,  # 폐기됨
                            grain_mode=grain_mode,
                            n_lay=opts.get("total_garments", 1),
                            runtime_seconds=opts["runtime_seconds"],
                            early_termination=True,
                            progress_callback=_on_progress,
                        )
                progress_bar.progress(1.0, text="✓ 완료")
            except Exception as e:
                progress_bar.empty()
                st.error(f"마카 배치 실패: {e}")
                nest_all = None

            if nest_all:
                st.session_state["nest_all_v33"] = {
                    "result": nest_all,
                    "widths": widths,
                    "selected_sizes": selected_sizes,
                    "timestamp": datetime.now(),
                    "opts": opts,  # 본사 비교 박스에서 우리 마카 구성 표시용
                }
                # 구버전 세션 키 정리
                st.session_state.pop("calc_v3", None)
                st.session_state.pop("nesting_v1", None)

    if "nest_all_v33" in st.session_state:
        st.divider()
        nv = st.session_state["nest_all_v33"]
        # 우리 마카 구성 (본사 비교에서 차이 안내용)
        opts_used = nv.get("opts", opts)
        marker_config = {
            "config_id": opts_used.get("config_id", ""),
            "base_size": opts_used.get("base_size", ""),
            "marker_mode_label": opts_used.get("marker_mode_label", "2WAY"),
            "total_garments": opts_used.get("total_garments", 1),
            "summary_text": opts_used.get("summary_text", ""),
            "size_ratio": opts_used.get("size_ratio"),
        }
        pdf_context = {
            "file_name": parsed.get("file_name") or "(unknown)",
            "style": parsed.get("style") or style_code_auto,
            "sample_size": parsed.get("sample_size"),
            "selected_sizes": nv["selected_sizes"],
            "generated_at": nv["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "runtime_seconds_used": opts["runtime_seconds"],
            "marker_config": marker_config,
        }
        material_results_section(nv["result"], pdf_context=pdf_context, hq_match=hq_match,
                                 marker_config=marker_config)
    return  # v3.3 일직선 흐름 — efficiency_section 경로 폐기

    # ── [보존, 호출 안 됨] 구 v3.1 효율 슬라이더 경로 — regression_test 가 직접 호출 ──
    if st.button("▶️ 요척 계산하기", type="primary"):
        pieces_calc = apply_accessory_overrides(
            pieces_all, st.session_state.get("accessory_fabrics", []),
        )
        efficiency = 0.85  # 보존 코드 호환용 placeholder
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
        st.session_state.pop("nesting_v1", None)

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
