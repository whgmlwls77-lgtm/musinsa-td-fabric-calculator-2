"""조각 4코너 / 원형 지름 기반 치수 추출 (Task #38-g — 사장님 확정 2026-07-24).

배경 (Task #38-f/38-g Step 1.5):
  raw bbox 는 곡선·사선 조각의 단일 극점에 민감해 실제 축율과 부호가 뒤집힘
  (BLK_5_1: bbox 가로 +0.19%/세로 -3.34% → 4코너 실측 +0.12%/-0.13%).
  Step 1.5 검증: 코너 정점은 동일 index 의 실제 좌표 이동 (샘플링 아티팩트 아님).
  → 조각 유형별로 식서 축 정렬 후 4코너(또는 원형 지름) 실측 = 사장님 본질 #1
    "식서 = 요척 핵심" 정렬.

순수 계산 (streamlit 의존성 없음 — 단위 테스트 가능). 식서 정렬은 grain_extractor 재사용.
결과 좌표는 raw (회전은 축 감지·정렬용, 치수는 실좌표 유클리드 거리).
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon as ShapelyPolygon

from grain_extractor import get_alignment_rotation, rotate_polygon

# ── 유형 감지 임계 (튜닝 가능 · 명시 상수) ──────────────────────
CORNER_ANGLE_THRESHOLD_DEG = 25.0   # 지배적 코너 = 정점 턴 각도 이 값 이상
CIRCLE_COMPACTNESS_MIN = 0.80       # 원형/타원 = 지배 코너 0 + 4πA/P² 이 값 이상
                                    # (완전원 0.997 / 2:1 타원 0.842 통과 · 라운드 사각 ~0.75 제외)
EDGE_STRAIGHT_TOL_RATIO = 0.02      # 변 직선성: 중간 정점 편차 / 조각 대각 이 값 이하 = 직선
CURVED_TOP_RATIO = 0.10             # 곡선 상단(소매산 등): (G.y - max(A.y,B.y))/(G.y-F.y) 이 값 초과
                                    # (Task #38-h — 소매산 꼭대기 G 가 상단 코너보다 충분히 높음)

# 조각 유형 상수.
TYPE_RECTANGLE = "rectangle"
TYPE_CURVED_RECTANGLE = "curved_rectangle"
TYPE_N_POLYGON = "n_polygon"
TYPE_TRIANGLE = "triangle"
TYPE_CIRCLE = "circle"
TYPE_UNKNOWN = "unknown"


def _as_xy(coords) -> list[tuple[float, float]]:
    if not coords:
        return []
    return [(float(p[0]), float(p[1])) for p in coords]


def _polygon(coords):
    """(N,2) → shapely 폴리곤 (자기교차 buffer(0) 정리). 미성립 시 None."""
    xy = _as_xy(coords)
    if len(xy) < 3:
        return None
    try:
        poly = ShapelyPolygon(xy)
    except Exception:
        return None
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    return poly


def _turn_angle_deg(a, b, c) -> float:
    """정점 b 에서의 턴 각도(도) — 진입(a→b)·진출(b→c) 방향 사이 각. 0=직진."""
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 <= 0 or n2 <= 0:
        return 0.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def dominant_corner_count(coords) -> int:
    """지배적 코너 수 — 턴 각도가 CORNER_ANGLE_THRESHOLD_DEG 이상인 정점 개수.

    곡선(촘촘한 정점)은 스텝당 턴이 작아 코너로 안 잡힘. 사각형=4, 삼각형=3,
    원형=0 (모든 스텝 미세). 사선 curved_rectangle 은 코너 4 + 곡선변 다수.
    """
    xy = _as_xy(coords)
    n = len(xy)
    if n < 3:
        return 0
    cnt = 0
    for i in range(n):
        a, b, c = xy[(i - 1) % n], xy[i], xy[(i + 1) % n]
        if _turn_angle_deg(a, b, c) >= CORNER_ANGLE_THRESHOLD_DEG:
            cnt += 1
    return cnt


def _compactness(poly) -> float:
    """4πA/P² — 완전 원=1.0, 정사각형=0.785, 길쭉할수록 낮음."""
    p = poly.length
    return (4.0 * math.pi * poly.area / (p * p)) if p > 0 else 0.0


def detect_piece_type(coords_cm) -> str:
    """조각 외곽선 raw 좌표 → 유형.

    rectangle / curved_rectangle / n_polygon / triangle / circle / unknown.

    판정 순서 (지배 코너 턴각 + 4사분면 극점 distinctness + 둘레비):
      1. 지배 코너 ≤1 & compactness ≥ 0.90 → circle (원형/타원)
      2. 지배 코너 ≥5 → n_polygon
      3. 4사분면 극점 distinct 3개 (한 쌍 겹침) → triangle
      4. distinct 4개 → 둘레비로 rectangle(직선) / curved_rectangle(곡선)
    """
    poly = _polygon(coords_cm)
    if poly is None:
        return TYPE_UNKNOWN
    n_dom = dominant_corner_count(coords_cm)
    comp = _compactness(poly)

    if n_dom <= 1 and comp >= CIRCLE_COMPACTNESS_MIN:
        return TYPE_CIRCLE
    if n_dom >= 5:
        return TYPE_N_POLYGON
    if _distinct_quadrant_corners(coords_cm) <= 3:
        return TYPE_TRIANGLE
    return TYPE_RECTANGLE if _edges_straight(coords_cm) else TYPE_CURVED_RECTANGLE


def _distinct_quadrant_corners(coords) -> int:
    """4사분면 극점(LT/RT/RB/LB) 중 서로 다른 정점 수 (겹침=삼각형 신호)."""
    rc = _as_xy(coords)
    if len(rc) < 3:
        return 0
    c = _four_corners(rc)
    pts = [c["LT"], c["RT"], c["RB"], c["LB"]]
    diag = max((_dist(a, b) for a in pts for b in pts), default=1.0) or 1.0
    tol = diag * 0.02
    uniq: list = []
    for p in pts:
        if not any(_dist(p, q) < tol for q in uniq):
            uniq.append(p)
    return len(uniq)


def _grain_align_vertical(coords_cm, grain) -> list[tuple[float, float]]:
    """식서를 세로(Y축)로 정렬한 좌표 (get_alignment_rotation=X정렬 + 90°).

    좌변/우변 = 식서 방향(세로 장변), 상변/하변 = 식서 직각(가로 단변).
    """
    rot = get_alignment_rotation(grain) + 90.0
    return rotate_polygon(_as_xy(coords_cm), rot)


def _four_corners(rc) -> dict:
    """정렬 좌표 → 4 사분면 극단 정점 (표준 회전-사각 코너 검출)."""
    LT = min(rc, key=lambda p: p[0] - p[1])   # 좌상: min(x-y)
    RB = max(rc, key=lambda p: p[0] - p[1])   # 우하: max(x-y)
    LB = min(rc, key=lambda p: p[0] + p[1])   # 좌하: min(x+y)
    RT = max(rc, key=lambda p: p[0] + p[1])   # 우상: max(x+y)
    return {"LT": LT, "RT": RT, "LB": LB, "RB": RB}


def _four_corner_indices(rc) -> dict:
    """4 사분면 극단 정점의 인덱스 (정렬·raw 좌표 동일 순서 → raw 매핑용).

    Task #38-g 지적 4 — 오버랩 이미지에 측정 변 라인 표시 (raw 방향 좌표에 매핑).
    """
    n = range(len(rc))
    return {
        "LT": min(n, key=lambda k: rc[k][0] - rc[k][1]),
        "RB": max(n, key=lambda k: rc[k][0] - rc[k][1]),
        "LB": min(n, key=lambda k: rc[k][0] + rc[k][1]),
        "RT": max(n, key=lambda k: rc[k][0] + rc[k][1]),
    }


def find_4_corners_by_angle(rc) -> dict | None:
    """각도 기반 4코너 인덱스 (Task #38-h) — 지배적 코너(턴 각도 큰 정점)로 사분면 분류.

    곡선 상단 조각(소매 등)의 코너를 정점 샘플링 밀도와 무관하게 안정 검출.
    지배 코너가 4개 미만이면 전체 정점으로 fallback (= 사분면 극점, 기존 동작).
    반환: {A(좌상), B(우상), c(좌하), d(우하)} 인덱스.
    """
    n = len(rc)
    if n < 4:
        return None
    doms = [i for i in range(n)
            if _turn_angle_deg(rc[(i - 1) % n], rc[i], rc[(i + 1) % n]) >= CORNER_ANGLE_THRESHOLD_DEG]
    pool = doms if len(doms) >= 4 else list(range(n))
    return {
        "A": min(pool, key=lambda k: rc[k][0] - rc[k][1]),   # 좌상
        "B": max(pool, key=lambda k: rc[k][0] + rc[k][1]),   # 우상
        "c": min(pool, key=lambda k: rc[k][0] + rc[k][1]),   # 좌하
        "d": max(pool, key=lambda k: rc[k][0] - rc[k][1]),   # 우하
    }


def detect_curved_top(rc, corner_idx) -> dict:
    """곡선 상단 조각 판정 + G(소매산 꼭대기)·F(커프 하단 중앙) 산출 (식서=세로 정렬 좌표).

    G = y_max 정점 (조각 최상단) · F = 하단 코너 c·d 중점.
    curved_top = (G.y - max(A.y, B.y)) / (G.y - F.y) > CURVED_TOP_RATIO.
    G-F = 조각 실제 세로 길이 (식서 방향).
    반환: {curved_top, g, f, g_index, gf_length, ratio}.
    """
    n = len(rc)
    g_index = max(range(n), key=lambda k: rc[k][1])
    G = rc[g_index]
    A, B = rc[corner_idx["A"]], rc[corner_idx["B"]]
    c, d = rc[corner_idx["c"]], rc[corner_idx["d"]]
    F = ((c[0] + d[0]) / 2.0, (c[1] + d[1]) / 2.0)
    denom = G[1] - F[1]
    ratio = ((G[1] - max(A[1], B[1])) / denom) if denom > 0 else 0.0
    return {
        "curved_top": ratio > CURVED_TOP_RATIO,
        "g": G, "f": F, "g_index": g_index,
        "gf_length": _dist(G, F), "ratio": ratio,
    }


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_line_dist(p, a, b) -> float:
    """점 p 와 무한 직선 a-b 수직 거리. a==b 면 점거리."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg = math.hypot(dx, dy)
    if seg <= 0:
        return _dist(p, a)
    return abs(dx * (a[1] - p[1]) - dy * (a[0] - p[0])) / seg


def _nearest_index(rc, pt) -> int:
    return min(range(len(rc)), key=lambda k: _dist(rc[k], pt))


def edge_max_deviation(coords_cm) -> float:
    """4코너 사이 각 변(호)의 중간 정점 최대 수직 편차 (조각 좌표 단위 cm).

    코너 순서대로 폴리곤을 4 호로 나눠, 각 호의 중간 정점이 코너-코너 직선에서
    벗어난 최대 거리. 직선 변이면 ≈0, 곡선 변이면 bow 만큼 커짐.
    """
    rc = _as_xy(coords_cm)
    n = len(rc)
    if n < 4:
        return 0.0
    c = _four_corners(rc)
    order = sorted({_nearest_index(rc, c[k]) for k in ("LT", "RT", "RB", "LB")})
    if len(order) < 4:
        return 0.0
    max_dev = 0.0
    for i in range(len(order)):
        i0, i1 = order[i], order[(i + 1) % len(order)]
        a, b = rc[i0], rc[i1]
        j = (i0 + 1) % n
        while j != i1:
            max_dev = max(max_dev, _point_line_dist(rc[j], a, b))
            j = (j + 1) % n
    return max_dev


def _edges_straight(coords_cm) -> bool:
    """4코너 변이 직선이면 True — 최대 수직 편차 / 조각 대각 ≤ 임계."""
    rc = _as_xy(coords_cm)
    if len(rc) < 4:
        return True
    c = _four_corners(rc)
    diag = max(_dist(c["LT"], c["RB"]), _dist(c["RT"], c["LB"]), 1e-9)
    return (edge_max_deviation(coords_cm) / diag) <= EDGE_STRAIGHT_TOL_RATIO


def extract_corners(coords_cm, grain) -> dict:
    """식서 정렬 후 4코너 + 4변 길이 (사각형/N각형/삼각형).

    반환:
      {corners:{LT,RT,LB,RB}, edges:{left,right,top,bottom}, warnings:[...]}
      좌변/우변 = 식서 방향(세로), 상변/하변 = 식서 직각(가로).
    """
    rc = _grain_align_vertical(coords_cm, grain)
    warnings: list[str] = []
    if len(rc) < 3:
        return {"corners": None, "corner_indices": None, "edges": None,
                "curved_top": False, "gf": None, "warnings": ["좌표 부족 (폴리곤 미성립)"]}
    # 각도 기반 4코너 (Task #38-h) — A/B/c/d → LT/RT/LB/RB 매핑.
    ai = find_4_corners_by_angle(rc) or {}
    idx = {"LT": ai.get("A"), "RT": ai.get("B"), "LB": ai.get("c"), "RB": ai.get("d")}
    if any(v is None for v in idx.values()):   # 각도 감지 실패 → 사분면 극점 fallback.
        idx = _four_corner_indices(rc)
        warnings.append("각도 기반 코너 감지 실패 — 사분면 극점 fallback")
    c = {k: rc[idx[k]] for k in ("LT", "RT", "LB", "RB")}
    # 코너 중복 감지 (삼각형·퇴화) — 경고만.
    pts = [c["LT"], c["RT"], c["RB"], c["LB"]]
    for i in range(4):
        if _dist(pts[i], pts[(i + 1) % 4]) < 1e-6:
            warnings.append("코너 2개 이상 겹침 (삼각형/퇴화 가능) — 상세 확인 필요")
            break
    edges = {
        "left": _dist(c["LT"], c["LB"]),
        "right": _dist(c["RT"], c["RB"]),
        "top": _dist(c["LT"], c["RT"]),
        "bottom": _dist(c["LB"], c["RB"]),
    }
    # G-F/곡선 상단 로직 폐기 (사장님 지시 2026-07-27 — 정중앙 세로/가로가 대체).
    # 세로 축율 = 좌우 평균 (각도 기반 4코너로 왜곡 없음 · 28_Small 검증 -0.15%).
    return {"corners": c, "corner_indices": idx, "edges": edges, "warnings": warnings}


def measure_center_axes(coords_cm, grain) -> dict:
    """조각 정중앙 세로/가로 span (shapely — 사장님 지시 2026-07-27).

    식서 정렬(세로) 후 centroid 통과 세로선·가로선과 조각 교차 길이 = 실제 중심 폭.
    center_vertical  = centroid x 통과 세로선 ∩ 조각 (식서 방향 중심 길이)
    center_horizontal = centroid y 통과 가로선 ∩ 조각 (식서 직각 중심 폭)
    측정 불가 시 {vertical:None, horizontal:None}.
    """
    rc = _grain_align_vertical(coords_cm, grain)
    poly = _polygon(rc)
    if poly is None:
        return {"centroid": None, "vertical": None, "horizontal": None}
    cx, cy = poly.centroid.x, poly.centroid.y
    minx, miny, maxx, maxy = poly.bounds
    v_line = LineString([(cx, miny - 1.0), (cx, maxy + 1.0)])
    h_line = LineString([(minx - 1.0, cy), (maxx + 1.0, cy)])
    try:
        v = poly.intersection(v_line).length
        h = poly.intersection(h_line).length
    except Exception:
        return {"centroid": (cx, cy), "vertical": None, "horizontal": None}
    return {"centroid": (cx, cy), "vertical": v, "horizontal": h}


def extract_circle(coords_cm, grain) -> dict:
    """식서 정렬 후 중심점 + 식서 축 지름 (원형/타원 — 사장님 정의 2026-07-24).

    세로 지름 = 식서 방향(세로) 상·하 극점 거리 (y-extent).
    가로 지름 = 식서 직각(가로) 좌·우 극점 거리 (x-extent).
    """
    rc = _grain_align_vertical(coords_cm, grain)
    if len(rc) < 3:
        return {"centroid": None, "v_diameter": None, "h_diameter": None,
                "warnings": ["좌표 부족 (폴리곤 미성립)"]}
    xs = [p[0] for p in rc]
    ys = [p[1] for p in rc]
    poly = _polygon(rc)
    ctr = (poly.centroid.x, poly.centroid.y) if poly is not None else \
        (sum(xs) / len(xs), sum(ys) / len(ys))
    return {
        "centroid": ctr,
        "v_diameter": max(ys) - min(ys),
        "h_diameter": max(xs) - min(xs),
        "warnings": [],
    }


def measure_piece(coords_cm, grain) -> dict:
    """조각 유형 자동 감지 후 유형별 치수 측정 (통합 진입점).

    반환:
      {
        "piece_type": str,
        "corners": {LT,RT,LB,RB} | None,
        "edges": {left,right,top,bottom} | None,      # 사각형/N각형/삼각형
        "circle": {centroid,v_diameter,h_diameter} | None,  # 원형/타원
        "warnings": [str, ...],
      }
    """
    ptype = detect_piece_type(coords_cm)
    aligned = _grain_align_vertical(coords_cm, grain)   # 오버랩 시각화용 (식서=세로 정렬)
    center = measure_center_axes(coords_cm, grain)      # 정중앙 세로/가로 (모든 조각)
    if ptype == TYPE_CIRCLE:
        circ = extract_circle(coords_cm, grain)
        return {"piece_type": ptype, "corners": None, "corner_indices": None, "edges": None,
                "circle": {k: circ[k] for k in ("centroid", "v_diameter", "h_diameter")},
                "center_axes": center,
                "aligned_coords": aligned, "warnings": circ["warnings"]}
    if ptype == TYPE_UNKNOWN:
        return {"piece_type": ptype, "corners": None, "corner_indices": None, "edges": None,
                "circle": None, "center_axes": center,
                "aligned_coords": aligned,
                "warnings": ["조각 유형 감지 실패 — 4코너/원형 판정 불가 (raw 좌표 확인 필요)"]}
    corn = extract_corners(coords_cm, grain)
    return {"piece_type": ptype, "corners": corn["corners"],
            "corner_indices": corn.get("corner_indices"), "edges": corn["edges"],
            "circle": None, "center_axes": center,
            "aligned_coords": aligned, "warnings": corn["warnings"]}
