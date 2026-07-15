"""
DXF 진단 — 카테고리 (결방향 / 원단 / 텍스트 인코딩 / 수량 / 스케일) 자동 진단 + 협력사 메시지.

부위명(패널) 카테고리는 사장님 확정 결정(2026-07-14)으로 폐기 — PIECE NAME 필수 아님.
대신 텍스트 인코딩(영문/숫자만) 카테고리 신설 (비ASCII 표기 = 인코딩 오류 위험).

사장님 절대 원칙: 알고리즘 읽기 실패 vs 협력사 정보 누락 구분.
이 모듈은 그 구분을 raw 데이터로 입증한다 — 추측 금지.

호출자: app.py 가 parse_dxf_v3 결과 + ezdxf doc 을 넘긴다.

검증 스크립트: /tmp/dxf_diagnosis_audit.py
"""
from __future__ import annotations

import re

# 진단 결과 상태값.
OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

STATUS_LABEL: dict[str, str] = {OK: "✅ 정상", WARN: "⚠️ 부족", FAIL: "❌ 누락"}
STATUS_EMOJI: dict[str, str] = {OK: "✅", WARN: "⚠️", FAIL: "❌"}


# ──────────────────────────────────────────────
# [1] 결방향
# ──────────────────────────────────────────────
def diagnose_grain(parsed: dict, doc=None, grain_layer: str | None = None) -> dict:
    """식서 LAYER 인식 + piece 별 grain 추출 결과.

    raw 메트릭 우선순위:
      1) parsed['diagnosis_raw']  — parse_dxf_v3 가 미리 계산해 넣어둠 (선호)
      2) doc 인자                 — fallback (검증/audit 스크립트용)
    """
    pieces = parsed["pieces"]
    n = len(pieces)

    raw = parsed.get("diagnosis_raw") or {}
    if grain_layer is None:
        grain_layer = raw.get("grain_layer")

    if "total_grain_lines" in raw:
        total_lines = int(raw["total_grain_lines"])
    elif doc is not None:
        total_lines = 0
        for blk in doc.blocks:
            for e in blk:
                if e.dxftype() == "LINE":
                    if grain_layer is None or e.dxf.layer == grain_layer:
                        total_lines += 1
    else:
        total_lines = 0

    by_kind: dict[str, int] = {}
    via_layer = 0
    via_bbox = 0
    via_unknown = 0
    for p in pieces:
        g = p.get("grain") or {}
        kind = g.get("kind", "UNKNOWN")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if g.get("estimated"):
            via_bbox += 1
        elif g.get("raw_layer"):
            via_layer += 1
        else:
            via_unknown += 1

    if n == 0:
        return _empty("결방향")

    if grain_layer and via_layer == n:
        status = OK
        summary = f"식서 LAYER '{grain_layer}' 인식, {n}/{n} piece 직접 추출."
    elif grain_layer and via_layer > 0:
        status = WARN
        summary = (
            f"식서 LAYER '{grain_layer}' 부분 인식 ({via_layer}/{n}). "
            f"{via_bbox}개 piece 는 bbox 비율로 자동 추정 (정확도 낮음)."
        )
    else:
        status = FAIL
        summary = "식서 LAYER 미인식 — 모든 piece bbox 비율 추정."

    return {
        "status": status,
        "summary": summary,
        "dxf_state": (
            f"식서 LAYER: {grain_layer or '(미인식)'} · "
            f"식서 LINE 총 {total_lines}개"
        ),
        "algo_state": (
            f"직접 추출 {via_layer} / bbox 추정 {via_bbox} / 분류 불가 {via_unknown}  "
            f"(분포: " + ", ".join(f"{k}:{v}" for k, v in sorted(by_kind.items())) + ")"
        ),
        "raw": {
            "grain_layer": grain_layer,
            "total_grain_lines": total_lines,
            "via_layer": via_layer,
            "via_bbox": via_bbox,
            "via_unknown": via_unknown,
            "by_kind": by_kind,
        },
    }


# ──────────────────────────────────────────────
# [2] 원단 표기
# ──────────────────────────────────────────────
# 사장님 표준 5종 (2026-05-06): 주원단 / 안감 / 포켓팅 / 배색 / 논. "심지" 폐기.
_MATERIAL_KEYWORDS = [
    "주원단", "메인", "MAIN", "SELF",
    "안감", "LINING",
    "포켓팅", "포켓", "주머니", "POCKETING", "POCKET",
    "배색", "CONTRAST",
    "논", "NON",
]


def diagnose_material(parsed: dict) -> dict:
    pieces = parsed["pieces"]
    n = len(pieces)
    if n == 0:
        return _empty("원단 표기")

    n_with_mat = sum(1 for p in pieces if (p.get("material_raw") or "").strip())
    cov_mat = n_with_mat / n

    n_with_anno = 0
    for p in pieces:
        annos = " ".join(p.get("annotations") or [])
        if any(k in annos for k in _MATERIAL_KEYWORDS):
            n_with_anno += 1
    cov_anno = n_with_anno / n

    by_inferred: dict[str, int] = {}
    for p in pieces:
        m = p["material_inferred"]
        by_inferred[m] = by_inferred.get(m, 0) + 1

    raw_codes: dict[str, int] = {}
    for p in pieces:
        c = (p.get("material_raw") or "").strip().upper()
        if c:
            raw_codes[c] = raw_codes.get(c, 0) + 1

    if cov_mat >= 1.0:
        status = OK
        summary = f"모든 piece 에 Material 코드 표기 ({n}/{n})."
    elif cov_mat == 0 and cov_anno == 0:
        status = FAIL
        summary = (
            "Material 코드 0% + annotation 한글 키워드 0%. "
            "알고리즘이 모든 piece 를 '주원단'으로 fallback — 사용자 수동 매핑 필수."
        )
    elif cov_mat == 0 and cov_anno > 0:
        status = WARN
        summary = (
            f"Material 코드 0% / annotation 한글 키워드 {n_with_anno}/{n} "
            f"({cov_anno*100:.0f}%). annotation 추정만으로는 부정확."
        )
    else:
        status = WARN
        summary = (
            f"Material 코드 부분 보유 {n_with_mat}/{n} ({cov_mat*100:.0f}%). "
            f"누락분은 사용자 매핑 필요."
        )

    if raw_codes:
        codes_disp = ", ".join(f"{c}:{v}" for c, v in sorted(raw_codes.items()))
    else:
        codes_disp = "(없음)"

    return {
        "status": status,
        "summary": summary,
        "dxf_state": (
            f"Material 코드 {n_with_mat}/{n} ({cov_mat*100:.0f}%) · "
            f"한글 annotation {n_with_anno}/{n} ({cov_anno*100:.0f}%) · "
            f"raw 코드: {codes_disp}"
        ),
        "algo_state": (
            "분류 결과: " + ", ".join(f"{k} {v}개" for k, v in sorted(by_inferred.items()))
            + (" → 사용자 매핑 UI 호출" if status != OK else "")
        ),
        "raw": {
            "material_coverage": cov_mat,
            "annotation_coverage": cov_anno,
            "raw_codes": raw_codes,
            "by_inferred": by_inferred,
        },
    }


# ──────────────────────────────────────────────
# [3] 텍스트 인코딩 (영문/숫자만 — 비ASCII 감지)
# 사장님 확정 결정 (2026-07-14): PIECE NAME 부위명 카테고리화 폐기.
#   "국제표준어 영어로만 쓰면 크게 문제 없음. 중국어 등으로 쓰면 오류 날 수 있음."
#   → 영문/숫자만 사용해야 인코딩 오류(CP949/EUC-KR 등) 방지 가능.
#   → 한글/중국어/일본어 등 비ASCII 문자 감지 시 위반 알림.
#   본질 #6 "정상은 침묵, 위반만 알림" 준수.
# ──────────────────────────────────────────────
def diagnose_text_encoding(parsed: dict) -> dict:
    """각 조각의 텍스트 필드에 비ASCII 문자(한글/중국어/일본어 등) 감지.

    사장님 확정 원리 (2026-07-14):
      영문/숫자만 사용해야 인코딩 오류(CP949/EUC-KR 등) 방지 가능.
      비ASCII 문자(ord > 127) 감지 시 위반.
    """
    pieces = parsed.get("pieces") or []
    if not pieces:
        return _empty("텍스트 인코딩")

    violations: list[dict] = []
    for p in pieces:
        for field in ("material_raw", "piece_name", "size"):
            val = p.get(field)
            val = val if isinstance(val, str) else ("" if val is None else str(val))
            non_ascii = [c for c in val if ord(c) > 127]
            if non_ascii:
                violations.append({
                    "piece_id": p.get("piece_id"),
                    "field": field,
                    "value": val,
                    "non_ascii": non_ascii[:5],  # 처음 5글자만
                })
        # annotations 리스트도 검사
        for anno in (p.get("annotations") or []):
            anno = anno if isinstance(anno, str) else str(anno)
            non_ascii = [c for c in anno if ord(c) > 127]
            if non_ascii:
                violations.append({
                    "piece_id": p.get("piece_id"),
                    "field": "annotation",
                    "value": anno,
                    "non_ascii": non_ascii[:5],
                })

    n_total = len(pieces)
    if not violations:
        return {
            "status": OK,
            "summary": f"모든 텍스트 영문/숫자 표기 ({n_total} piece) — 인코딩 오류 위험 없음.",
            "dxf_state": f"비ASCII 문자 0건 / {n_total} piece",
            "algo_state": "영문/숫자 표기 — CP949/EUC-KR 인코딩 안전",
            "raw": {"total": n_total, "violation_count": 0, "violations": []},
        }

    n_pieces_affected = len({v["piece_id"] for v in violations})
    sample_disp = " · ".join(
        f'{v["field"]}="{v["value"]}"' for v in violations[:5]
    )
    return {
        "status": WARN,
        "summary": (
            f"{n_pieces_affected}개 조각에서 한글/중국어 등 비ASCII 문자 감지됨 "
            f"({len(violations)}건) → 협력사에 영문/숫자로 재저장 요청 필요."
        ),
        "dxf_state": f"비ASCII 감지: {sample_disp}",
        "algo_state": "영문/숫자만 표기 요청 — 한글/중국어/일본어 표기는 CP949/EUC-KR 깨짐 유발",
        "raw": {
            "total": n_total,
            "violation_count": len(violations),
            "violations": violations,
        },
    }


# ──────────────────────────────────────────────
# [4] 수량/대칭
# 사장님 본질 (2026-05-06): PAIRED 처리 후 1벌당 마카 piece 명시.
#   raw 14 unique → PAIRED 처리 후 17 (사장님 raw 정답) 같은 변환 표시.
# ──────────────────────────────────────────────
def per_garment_marker_pieces(p: dict) -> int:
    """piece 1개의 1벌당 마카 piece 수 (옵션 A 정책 + 마카제외 반영).

    옵션 A 정책 (auto_nesting_v2._split_mirrored_pieces 와 동치):
      - mirror=True + q==1       → 2  (PAIRED:DOUBLE, orig+M split)
      - mirror=True + q 짝수(≥2) → q  (q/2 + q/2 split, 합 보존)
      - mirror=True + q 홀수(≥3) → q  (split skip, 원본만)
      - mirror=False/None        → q
      - Material:NON / 마카제외   → 0  (nesting skip)
    """
    if (p.get("material_inferred") or "").strip() == "마카제외":
        return 0
    raw_mat = (p.get("material_raw") or p.get("material") or "").strip().upper()
    if raw_mat in {"NON", "NONE"}:
        return 0
    q = p.get("quantity") or 1
    if p.get("mirror") is True and q == 1:
        return 2
    return q


def diagnose_quantity(parsed: dict) -> dict:
    pieces = parsed["pieces"]
    n = len(pieces)
    if n == 0:
        return _empty("수량/대칭")

    # unique piece 단위 집계 (piece_key/piece_id 기준 중복 제거).
    seen_keys: set[str] = set()
    n_unique = 0
    n_excluded = 0
    n_with_qty = 0
    n_unique_pair = 0
    n_unique_mirror = 0
    qty_dist: dict[str, int] = {}
    per_garment_total = 0
    # 사장님 본질 (2026-05-07): 재질별 piece 수 분리 — SELF/LINING/합계 명시.
    per_garment_by_material: dict[str, int] = {}

    for p in pieces:
        pk = p.get("piece_key") or p.get("piece_id") or ""
        if pk in seen_keys:
            continue
        seen_keys.add(pk)
        n_unique += 1

        # 마카제외 카운트
        raw_mat = (p.get("material_raw") or p.get("material") or "").strip().upper()
        inferred_mat = (p.get("material_inferred") or "").strip()
        if inferred_mat == "마카제외" or raw_mat in {"NON", "NONE"}:
            n_excluded += 1

        if p.get("quantity") is not None:
            n_with_qty += 1
        if p.get("quantity") == 2:
            n_unique_pair += 1
        if p.get("mirror") is True:
            n_unique_mirror += 1

        q = p.get("quantity")
        key = str(q) if q is not None else "None"
        qty_dist[key] = qty_dist.get(key, 0) + 1

        pg = per_garment_marker_pieces(p)
        per_garment_total += pg
        if pg > 0:
            mat_label = inferred_mat or "미지정"
            per_garment_by_material[mat_label] = (
                per_garment_by_material.get(mat_label, 0) + pg
            )

    cov = n_with_qty / n_unique if n_unique > 0 else 0.0
    n_classified = n_unique - n_excluded

    # 재질별 분해 라벨 — 표준 5종 우선 정렬 (사장님 본질 2026-05-07).
    standard_order = ["주원단", "안감", "포켓팅", "배색", "논"]
    materials_sorted = (
        [m for m in standard_order if m in per_garment_by_material]
        + sorted(m for m in per_garment_by_material if m not in standard_order)
    )
    by_mat_disp = ", ".join(
        f"{m} {per_garment_by_material[m]}개" for m in materials_sorted
    )

    if cov >= 1.0:
        status = OK
        summary = (
            f"Quantity 메타 100% ({n_unique}/{n_unique}). "
            f"PAIRED 처리 후 1벌당 마카 piece: 합계 {per_garment_total}개"
            + (f" ({by_mat_disp})" if by_mat_disp else "")
            + (f" · 마카제외 {n_excluded}개" if n_excluded > 0 else "")
            + "."
        )
    elif cov >= 0.8:
        status = WARN
        summary = (
            f"Quantity 메타 {n_with_qty}/{n_unique} ({cov*100:.0f}%). "
            f"누락 piece 는 1로 fallback (좌우 페어 누수 위험). "
            f"1벌당 마카 piece (추정): 합계 {per_garment_total}개"
            + (f" ({by_mat_disp})" if by_mat_disp else "")
            + "."
        )
    else:
        status = FAIL
        summary = (
            f"Quantity 메타 {n_with_qty}/{n_unique} ({cov*100:.0f}%) — 좌우 페어 처리 불가. "
            f"사용자 입력 또는 협력사 표기 요청 필수."
        )

    qty_disp = ", ".join(f"{k}:{v}" for k, v in sorted(qty_dist.items()))
    excluded_disp = f" · 마카제외 {n_excluded}개" if n_excluded > 0 else ""
    return {
        "status": status,
        "summary": summary,
        "dxf_state": (
            f"DXF unique piece {n_unique}개 (마카 분류 {n_classified}{excluded_disp}) · "
            f"Quantity 보유 {n_with_qty}/{n_unique} · 분포: {qty_disp}"
        ),
        "algo_state": (
            f"PAIRED 처리 후 1벌당 마카 piece — 합계 {per_garment_total}개"
            + (f"  ({by_mat_disp})" if by_mat_disp else "")
            + f"  ·  mirror=True {n_unique_mirror}개 / Q=2 페어 {n_unique_pair}개 / "
            f"None→1 fallback {n_unique - n_with_qty}개"
        ),
        "raw": {
            "qty_coverage": cov,
            "qty_distribution": qty_dist,
            "pair_pieces": n_unique_pair,
            "fallback_to_1": n_unique - n_with_qty,
            "n_unique_pieces": n_unique,
            "n_excluded": n_excluded,
            "n_mirror_true": n_unique_mirror,
            "per_garment_marker_pieces": per_garment_total,
            # 재질별 분해 (SELF/LINING/etc) — 사장님 본질 2026-05-07.
            "per_garment_by_material": per_garment_by_material,
        },
    }


# ──────────────────────────────────────────────
# [6] DXF 스케일 검증 — 50cm × 50cm 비율 박스 (사장님 본질 2026-05-07)
#
# 사장님 명시: 50cm × 50cm 정사각형 박스 piece 추가 (Material:NON, 마카 제외).
# 단위 명시 — mm/inch 아님. DXF 좌표가 cm 단위로 정확한지 raw 검증 도구.
#   측정 ≈ 50 cm        → 스케일 정상 ✅
#   측정 ≈ 19.685 cm    → DXF inch 단위 (×2.54 = 50cm)
#   측정 ≈ 5 cm         → DXF mm 단위 (×10 = 50cm)
#   기타                → 사장님 직접 측정 + 보정 결정
#
# 사장님 명시 (2026-05-07 정정): 협력사 혼선 방지 — 모든 표기 "50cm × 50cm".
# ──────────────────────────────────────────────
# 실무에서 실제 사용되는 다양한 표기 (사장님 실증 2026-07-14: "50x50_32").
# 대소문자 무시 + 사이즈 접미사 무관 substring 매칭 (기존 로직 유지).
SCALE_BOX_NAME_KEYWORDS = (
    "SCALE_BOX",
    "50CM_X_50CM",
    "50CMX50CM",
    "50CM",
    "50X50",       # 사장님 실증 케이스 (2026-07-14 — "50x50_32")
    "50_X_50",
    "50 X 50",
    "SCALE",
    "BOX",
    "비율박스",     # 기존 유지
    "비율_박스",    # 기존 유지
)
SCALE_BOX_SIZE_CM = 50.0  # 사장님 명시 표준 (단위 명시 — mm/inch 아님)
SCALE_BOX_TARGET_CM = SCALE_BOX_SIZE_CM  # 후방 호환 alias
SCALE_BOX_TOLERANCE_CM = 0.5  # ±0.5cm 이내 → 정상으로 판정

# 50cm 정사각형이 각 단위 좌표계에서 갖는 변 길이(cm) + 허용오차 (사장님 지시 2026-07-14).
#   inch/mm = "off-unit" — 자연스러운 조각 치수 아님 → Material 무관 감지 (정확 매칭, 추측 X).
#   cm      = 자연 치수 가능 → Material:NON 확인 필요 (일반 정사각 조각 오검출 방지).
SCALE_BOX_KNOWN_OFF_UNIT_CM = ((19.685, 0.5), (500.0, 5.0))  # (inch 좌표, mm 좌표)
SCALE_BOX_KNOWN_CM = (50.0, 0.5)                             # cm 좌표 (기존)
SCALE_BOX_SQUARE_RATIO_TOL = 0.05  # 정사각형 판정 — 변 길이 ±5%


def _scale_box_is_square(w: float, h: float) -> bool:
    """정사각형 판정 — 변 길이 ±5% (사장님 지시 2026-07-14). 스케일 박스는 정사각형."""
    if w <= 0 or h <= 0:
        return False
    return abs(w - h) <= SCALE_BOX_SQUARE_RATIO_TOL * max(w, h)


def _scale_box_known_off_unit(w: float, h: float) -> bool:
    """정사각형 변 길이가 off-unit 표준값(inch 19.685 / mm 500)에 정확 매칭."""
    for target, tol in SCALE_BOX_KNOWN_OFF_UNIT_CM:
        if abs(w - target) <= tol and abs(h - target) <= tol:
            return True
    return False


def _scale_box_known_cm(w: float, h: float) -> bool:
    """정사각형 변 길이가 cm 표준값(50)에 정확 매칭."""
    target, tol = SCALE_BOX_KNOWN_CM
    return abs(w - target) <= tol and abs(h - target) <= tol


def detect_scale_box_50cm(pieces: list[dict]) -> dict | None:
    """50cm × 50cm 비율 박스 piece 검출 (사장님 견고성 증진 2026-07-14).

    사장님 실증 (2026-07-14): PP 파일 스케일 박스가 이름 "50x50_32" + Material:SELF
      (NON 아님) → 기존 is_non 게이트에서 제외되어 단위 보정 미실행. 견고화 필요.

    검출 조건 (모두 정사각형 ±5% 필수 — 스케일 박스는 정사각형):
      A) 이름 키워드 매칭 (piece_name/block_name) → Material 무관 (명시적 raw 증거)
      B) off-unit 표준값 정사각형 (inch 19.685 / mm 500) → Material 무관
         (자연 조각 치수 아님 = 명확한 스케일 박스 증거, 추측 X)
      C) cm 표준값(50) 정사각형 → Material:NON 필요 (자연 치수 가능 → 오검출 방지)

    검출 불가 시 None.
    """
    candidates = []
    for p in pieces:
        w = float(p.get("width_cm") or 0)
        h = float(p.get("height_cm") or 0)
        if not _scale_box_is_square(w, h):
            continue  # 비정사각형 = 스케일 박스 아님 (추측 금지 — 배제)

        nm = (p.get("piece_name") or "").upper()
        bn = (p.get("block_name") or "").upper()  # 사장님 "50x50_32" 는 block_name
        name_match = any((kw in nm) or (kw in bn) for kw in SCALE_BOX_NAME_KEYWORDS)

        raw = (p.get("material_raw") or p.get("material") or "").strip().upper()
        inferred = (p.get("material_inferred") or "").strip()
        is_non = inferred == "마카제외" or raw in {"NON", "NONE"}

        off_unit = _scale_box_known_off_unit(w, h)
        cm_size = _scale_box_known_cm(w, h)

        # A) 이름 매칭 or B) off-unit → Material 무관. C) cm 표준값 → NON 필요.
        qualifies = name_match or off_unit or (cm_size and is_non)
        if qualifies:
            candidates.append({
                "piece_id": p.get("piece_id", "?"),
                "piece_name": p.get("piece_name") or "(empty)",
                "measured_w_cm": w,
                "measured_h_cm": h,
                "name_match": name_match,
                "is_square": True,
            })

    if not candidates:
        return None

    # 우선순위: 이름 매칭 우선. 없으면 보정 필요한(off-unit) 후보 우선
    #   (50cm 자연 정사각 조각이 실제 off-unit 스케일 박스를 가리는 것 방지).
    name_matched = [c for c in candidates if c["name_match"]]
    if name_matched:
        name_matched.sort(key=lambda c: c["measured_w_cm"], reverse=True)
        return name_matched[0]

    needs_correction = [
        c for c in candidates
        if abs(c["measured_w_cm"] - SCALE_BOX_SIZE_CM) > SCALE_BOX_TOLERANCE_CM
    ]
    pool = needs_correction if needs_correction else candidates
    pool.sort(key=lambda c: c["measured_w_cm"], reverse=True)
    return pool[0]


# 후방 호환 alias — 기존 호출자 보호 (deprecate 후 제거 예정)
detect_scale_box = detect_scale_box_50cm


def compute_unit_correction_50cm_box(measured_cm: float) -> tuple[float, str]:
    """50cm × 50cm 박스 측정값 → 보정 비율 + 단위 가설 반환 (사장님 명시 2026-05-07).

    Returns:
      (correction_ratio, unit_hypothesis)
      correction_ratio = 1.0 → 보정 불필요 (cm)
      correction_ratio = 2.54 → DXF 좌표 inch 의심
      correction_ratio = 10.0 → DXF 좌표 mm 의심
    """
    if measured_cm <= 0:
        return 1.0, "측정 불가"
    ratio = SCALE_BOX_SIZE_CM / measured_cm
    # 알려진 단위 비율 매칭 (±5% 허용)
    if abs(ratio - 1.0) <= 0.01:
        return 1.0, "cm (정상)"
    if 2.4 <= ratio <= 2.7:
        return 2.54, "inch (DXF 좌표 inch — ×2.54 보정 필요)"
    if 9.5 <= ratio <= 10.5:
        return 10.0, "mm (DXF 좌표 mm — ×10 보정 필요)"
    if 90 <= ratio <= 92:
        return 91.44, "yd (DXF 좌표 yd — 비표준)"
    return ratio, f"비표준 (×{ratio:.4f} 보정)"


# 후방 호환 alias
compute_scale_correction = compute_unit_correction_50cm_box


def diagnose_scale(parsed: dict) -> dict:
    """50cm × 50cm 비율 박스로 DXF 스케일 검증 (사장님 본질 2026-05-07).

    parsed 에 'scale_correction_applied' / 'scale_correction_ratio' 키가 있으면
    parse_dxf_v3 가 이미 자동 보정 적용한 상태 → 보정 적용 안내 메시지.
    그 외에는 raw 박스 검출 + 단위 가설 + 안내.

    박스 검출 시:
      - 측정 50.0 ± 0.5 cm (보정 후) → ✅ 스케일 정상
      - 보정 적용됨               → ✅ "자동 보정 ×N.NN 적용"
      - 박스 측정 비정상 + 보정 미적용 → ⚠️
    검출 불가 시: ✅ "박스 없음 — 협력사 가이드 §비율 검증 박스 참고" — 정보성.
    """
    pieces = parsed.get("pieces") or []
    # scale_box_info 우선 (move_scale_box_to_excluded 로 박스가 pieces 에서 빠져도
    # 진단 정상 유지 — 2026-07-15). 없으면 pieces 에서 재감지 (기존 경로).
    box = parsed.get("scale_box_info") or detect_scale_box_50cm(pieces)
    correction_applied = bool(parsed.get("scale_correction_applied"))
    correction_ratio = float(parsed.get("scale_correction_ratio") or 1.0)
    original_w = parsed.get("scale_correction_original_w_cm")

    if box is None:
        return {
            "status": OK,
            "summary": (
                "50cm × 50cm 비율 검증 박스 없음 — "
                "협력사 가이드 §비율 검증 박스 (Piece Name: SCALE_BOX, Material: NON) 추가 시 자동 인식."
            ),
            "dxf_state": "비율 검증 박스 미사용",
            "algo_state": "박스 추가 권장",
            "raw": {"detected": False},
        }

    w = box["measured_w_cm"]
    h = box["measured_h_cm"]
    delta_w = w - SCALE_BOX_SIZE_CM
    delta_h = h - SCALE_BOX_SIZE_CM

    # 자동 보정 적용된 경우 — parse_dxf_v3 가 모든 piece 좌표/사이즈 보정 완료.
    # 사장님 본질 정정 (2026-05-07): 사용자 노출 메시지에 raw 수치/비율/단위 명시 X.
    if correction_applied and abs(delta_w) <= SCALE_BOX_TOLERANCE_CM:
        return {
            "status": OK,
            "summary": "✅ 50cm × 50cm 박스 인식 → 자동 보정 완료",
            "dxf_state": "비율 검증 박스 정상 인식",
            "algo_state": "자동 보정 완료 — 모든 piece 좌표/사이즈 정합",
            "raw": {
                # 내부 변수 (디버그/audit 용 — 사용자 노출 X)
                "detected": True,
                "piece_name": box["piece_name"],
                "measured_w_cm": w,
                "measured_h_cm": h,
                "delta_w": delta_w,
                "delta_h": delta_h,
                "correction_ratio": correction_ratio,
                "correction_applied": True,
                "original_measured_w_cm": original_w,
            },
        }

    # 정상 (±0.5cm) 보정 미적용 — 박스가 처음부터 50cm 인 케이스
    if abs(delta_w) <= SCALE_BOX_TOLERANCE_CM and abs(delta_h) <= SCALE_BOX_TOLERANCE_CM:
        return {
            "status": OK,
            "summary": "✅ 50cm × 50cm 박스 정상 인식",
            "dxf_state": "비율 검증 박스 정상",
            "algo_state": "보정 불필요",
            "raw": {
                "detected": True,
                "piece_name": box["piece_name"],
                "measured_w_cm": w,
                "measured_h_cm": h,
                "delta_w": delta_w,
                "delta_h": delta_h,
                "correction_ratio": 1.0,
                "correction_applied": False,
            },
        }

    # 보정 필요한 경우 — parse_dxf_v3 가 자동 보정 미수행 (드문 케이스).
    # 사용자 노출 메시지에 raw 수치/단위/비율 명시 X (사장님 본질 정정 2026-05-07).
    correction, hypothesis = compute_unit_correction_50cm_box(w)
    return {
        "status": WARN,
        "summary": "⚠️ 50cm × 50cm 박스 측정 비정상 — 자동 보정 미적용",
        "dxf_state": "비율 검증 박스 인식 실패",
        "algo_state": "박스 표기 또는 도면 재확인 필요",
        "raw": {
            # 내부 변수 (디버그/audit 용)
            "detected": True,
            "piece_name": box["piece_name"],
            "measured_w_cm": w,
            "measured_h_cm": h,
            "delta_w": delta_w,
            "delta_h": delta_h,
            "correction_ratio": correction,
            "correction_applied": False,
            "unit_hypothesis": hypothesis,
        },
    }


# ──────────────────────────────────────────────
# 자동 보정 적용 (옵션 A — 사장님 결정 2026-05-07)
# parse_dxf_v3 끝에서 호출. 50cm 박스 검출 → 측정값과 50.0 비교 → 비율 적용.
# ──────────────────────────────────────────────
def apply_unit_correction_50cm_box(parsed: dict) -> dict:
    """50cm × 50cm 비율 박스 측정값으로 모든 piece 좌표/사이즈/polygon 보정.

    호출 흐름 (parse_dxf_v3 내부):
      1. 박스 검출 (detect_scale_box_50cm)
      2. 측정값 vs 50cm 비교
      3. 측정 정상 (±0.5cm) → no-op
      4. 미스매치 → 모든 piece 의 width/height/area/coords/bbox/centroid × ratio
         (polygons 는 별도 — caller 가 ShapelyPolygon 재생성)

    단위 가설별 비율 (compute_unit_correction_50cm_box 사용):
      - 19.685 cm → ×2.54 (inch)
      - 5.0 cm   → ×10.0 (mm)

    Returns:
      parsed dict with 추가 키:
        scale_correction_applied : bool
        scale_correction_ratio   : float (1.0 if no-op)
        scale_correction_original_w_cm : float (보정 전 박스 측정값, 보정 시에만)
        scale_box_info           : dict (검출 박스 info)
    """
    pieces = parsed.get("pieces") or []
    box = detect_scale_box_50cm(pieces)
    if box is None:
        parsed["scale_correction_applied"] = False
        parsed["scale_correction_ratio"] = 1.0
        return parsed

    measured_w = box["measured_w_cm"]
    if abs(measured_w - SCALE_BOX_SIZE_CM) <= SCALE_BOX_TOLERANCE_CM:
        # 측정 정상 — 보정 불필요
        parsed["scale_correction_applied"] = False
        parsed["scale_correction_ratio"] = 1.0
        parsed["scale_box_info"] = box
        return parsed

    correction, _hypothesis = compute_unit_correction_50cm_box(measured_w)

    # 모든 piece 좌표/사이즈/면적 비율 적용
    r2 = correction * correction
    for p in pieces:
        if p.get("width_cm") is not None:
            p["width_cm"] = float(p["width_cm"]) * correction
        if p.get("height_cm") is not None:
            p["height_cm"] = float(p["height_cm"]) * correction
        if p.get("area_cm2") is not None:
            p["area_cm2"] = float(p["area_cm2"]) * r2
        if p.get("bbox_cm") is not None:
            p["bbox_cm"] = tuple(float(v) * correction for v in p["bbox_cm"])
        if p.get("centroid_cm") is not None:
            p["centroid_cm"] = tuple(float(v) * correction for v in p["centroid_cm"])
        if p.get("coords_cm") is not None:
            p["coords_cm"] = [
                (float(x) * correction, float(y) * correction)
                for x, y in p["coords_cm"]
            ]

    # excluded 박스도 보정 (시각화 일관성)
    for e in parsed.get("excluded") or []:
        if "bbox_cm" in e and e["bbox_cm"] is not None:
            e["bbox_cm"] = tuple(float(v) * correction for v in e["bbox_cm"])

    parsed["scale_correction_applied"] = True
    parsed["scale_correction_ratio"] = correction
    parsed["scale_correction_original_w_cm"] = measured_w
    # scale_box_info 는 보정 후 측정값 반영 (박스도 ×correction 됨) — diagnose_scale
    # delta 계산이 pieces 재감지 없이도 정확하도록 (박스 excluded 이동 대비 2026-07-15).
    box = dict(box)
    box["measured_w_cm"] = float(box["measured_w_cm"]) * correction
    box["measured_h_cm"] = float(box["measured_h_cm"]) * correction
    parsed["scale_box_info"] = box
    return parsed


def move_scale_box_to_excluded(parsed: dict) -> dict:
    """감지된 스케일 박스를 material 무관하게 pieces → excluded 이동 (사장님 확정 2026-07-15).

    사장님 실증 (2026-07-15): PP 파일 스케일 박스가 Material:SELF 로 저장 → 마카제외
      필터(Material=NON)에 안 걸려 pieces 에 잔존. 메인 파일은 Material:NON 이라 제외됨
      → 두 파일 조각 개수 비대칭 → PP vs 메인 크기 순 매칭 어긋남.

    사장님 원칙: "스케일 박스로 감지되면 material 무관 자동 제외."

    apply_unit_correction_50cm_box 가 세팅한 scale_box_info(piece_id 포함)를 사용해
    해당 piece 를 pieces 에서 제거하고 excluded 로 이동. 감지 조건은 변경하지 않음
    (이미 감지된 박스를 이동만).
    """
    box = parsed.get("scale_box_info")
    if not box:
        return parsed  # 감지된 박스 없음 (또는 이미 파싱 단계 excluded 처리)
    box_pid = box.get("piece_id")
    if not box_pid:
        return parsed

    pieces = parsed.get("pieces") or []
    kept: list[dict] = []
    moved: dict | None = None
    for p in pieces:
        if moved is None and p.get("piece_id") == box_pid:
            moved = p
            continue
        kept.append(p)

    if moved is None:
        return parsed  # 이미 pieces 에 없음 (파싱 단계 is_scale_box 로 제외됨)

    parsed["pieces"] = kept
    excluded = parsed.get("excluded")
    if excluded is None:
        excluded = []
        parsed["excluded"] = excluded
    excluded.append({
        "block_name": moved.get("block_name"),
        "piece_name": moved.get("piece_name") or "(empty)",
        "size": moved.get("size"),
        "bbox_cm": moved.get("bbox_cm"),
        "material_raw": moved.get("material_raw") or moved.get("material") or "",
        "reason": "scale_box",  # material 무관 스케일 박스 자동 제외 (사장님 2026-07-15)
    })
    return parsed


# ──────────────────────────────────────────────
# [5] 마카 제외 piece (Material=NON, 사장님 결정 2026-05-05)
# ──────────────────────────────────────────────
def diagnose_excluded(parsed: dict) -> dict:
    """Material=NON / "마카제외" 분류된 piece 를 명시.

    StyleCAD "마커 제외" export 우회 솔루션 — Material 값 "NON" 표기.
    excluded 가 0개면 None 반환 (진단 출력 생략 — run_full_diagnosis 가 처리).
    """
    pieces = parsed.get("pieces", [])
    excluded = []
    for p in pieces:
        raw = (p.get("material_raw") or p.get("material") or "").strip().upper()
        inferred = (p.get("material_inferred") or "").strip()
        if inferred == "마카제외" or raw in {"NON", "NONE"}:
            excluded.append({
                "piece_id": p.get("piece_id", "?"),
                "piece_name": (p.get("piece_name") or p.get("piece_id") or "?"),
                "material_raw": p.get("material_raw") or p.get("material") or "",
            })

    if not excluded:
        return {
            "status": OK,
            "summary": "Material=NON 표기 piece 없음 (전체 마카 포함)",
            "dxf_state": "-",
            "algo_state": "-",
            "raw": {"excluded_count": 0, "excluded": []},
        }

    names = ", ".join(e["piece_name"] for e in excluded)
    return {
        "status": OK,
        "summary": f"{len(excluded)}개 piece 마카 제외 — Material=NON 인식 ({names})",
        "dxf_state": f"Material=NON: {len(excluded)}개",
        "algo_state": "자동 마카 제외 + excluded_pieces 리스트 기록",
        "raw": {"excluded_count": len(excluded), "excluded": excluded},
    }


# ──────────────────────────────────────────────
# 통합
# ──────────────────────────────────────────────
def _empty(label: str) -> dict:
    return {
        "status": FAIL,
        "summary": f"{label} 진단 불가 — piece 0개",
        "dxf_state": "-",
        "algo_state": "-",
        "raw": {},
    }


def build_raw_table(parsed: dict) -> list[dict]:
    """raw 정보 표 — 항상 표시 (사장님 본질 2026-05-05).

    각 piece 의 핵심 메타 raw 그대로 노출. 추측 X.

    Returns:
      [
        {
          "패턴 명칭": piece_name (정규화된 표준명 또는 raw),
          "원본 표기": piece_name_raw (raw 그대로),
          "갯수": quantity (int 또는 "(미표기)"),
          "좌우 대칭": "✅ 페어" / "단독" / "(미표기)",
          "원단": material_inferred,
          "_is_standard_name": bool,
        },
        ...
      ]
    """
    rows: list[dict] = []
    for p in parsed.get("pieces", []):
        q = p.get("quantity")
        m = p.get("mirror")
        rows.append({
            "패턴 명칭": p.get("piece_name") or "(이름 없음)",
            "원본 표기": p.get("piece_name_raw") or p.get("piece_name") or "",
            "갯수": q if q is not None else "(미표기)",
            "좌우 대칭": ("✅ 페어" if m is True else ("단독" if m is False else "(미표기)")),
            "원단": p.get("material_inferred") or "(미분류)",
            "_is_standard_name": bool(p.get("is_standard_name")),
        })
    return rows


def detect_violations(parsed: dict) -> list[dict]:
    """위반 알림 — 위반 시만 (사장님 본질 2026-05-05).

    위반 케이스 (협력사 메시지 자동 생성용):
      - quantity_missing: 갯수 메타 부재
      - material_missing: 원단 종류 미표기
      - grain_missing: 식서 LINE 부재 (Y kind 가 estimated 인 경우)

    부위명(pattern_name_invalid) 위반은 사장님 확정 결정(2026-07-14)으로 폐기 —
    PIECE NAME 필수 아님. 텍스트 표기 검증은 diagnose_text_encoding 이 담당.

    Material:NON 은 위반 X — 정보성 표시 (마카 제외 처리됨).

    Returns:
      [
        {"type": str, "piece_name": str, "raw_name": str, "detail": str},
        ...
      ]
    """
    violations: list[dict] = []
    for p in parsed.get("pieces", []):
        pn = p.get("piece_name") or "(이름 없음)"
        raw_pn = p.get("piece_name_raw") or pn

        # 1) 갯수 메타 부재
        if p.get("quantity") is None:
            violations.append({
                "type": "quantity_missing",
                "piece_name": pn,
                "raw_name": raw_pn,
                "detail": "갯수 메타 없음",
            })

        # 2) 원단 종류 미표기 — material_raw 비어있고 inferred 도 fallback
        raw_mat = (p.get("material_raw") or p.get("material") or "").strip()
        if not raw_mat:
            violations.append({
                "type": "material_missing",
                "piece_name": pn,
                "raw_name": raw_pn,
                "detail": "원단 종류 표기 없음",
            })

        # 3) 식서 부재 — grain.estimated == True (LINE 못 찾고 bbox 추정 사용)
        grain = p.get("grain") or {}
        if grain.get("estimated"):
            violations.append({
                "type": "grain_missing",
                "piece_name": pn,
                "raw_name": raw_pn,
                "detail": "식서 LINE 없음 (bbox 비율 추정)",
            })

    return violations


def run_full_diagnosis(parsed: dict, doc=None, grain_layer: str | None = None) -> dict:
    """app.py 호출 진입점 (사장님 본질 갱신 2026-05-05).

    기존 5 카테고리 진단 + 새 raw 정보 표 + 위반 알림 통합.
    parsed['diagnosis_raw'] 가 있으면 doc 없이도 동작.
    """
    return {
        "grain":    diagnose_grain(parsed, doc=doc, grain_layer=grain_layer),
        "material": diagnose_material(parsed),
        "encoding": diagnose_text_encoding(parsed),
        "quantity": diagnose_quantity(parsed),
        "excluded": diagnose_excluded(parsed),
        # 사장님 본질 (2026-05-07) — DXF 스케일 검증 (50cm × 50cm 비율 박스)
        "scale":    diagnose_scale(parsed),
        # 사장님 본질 (2026-05-05) — raw 표 + 위반 알림만
        "raw_table":  build_raw_table(parsed),
        "violations": detect_violations(parsed),
    }


# ──────────────────────────────────────────────
# 협력사 피드백 메시지
# ──────────────────────────────────────────────
def build_coop_message(parsed: dict, diag: dict) -> str:
    """진단 결과의 ❌/⚠️ 항목 → 협력사 요청 메시지 자동 생성. 이슈 없으면 빈 문자열."""
    style = parsed.get("style") or "(스타일 미지정)"
    items: list[str] = []

    if diag["material"]["status"] in (WARN, FAIL):
        items.append(
            "1. **Material 코드** (SELF / LINING / POCKETING / CONTRAST / NON) — "
            "모든 piece 의 Block ATTDEF 에 `Material:` 키로 표준 코드 표기 필요. "
            "NON 은 마카 제외 piece (예: 표시·도식)."
        )
    if diag.get("encoding", {}).get("status") in (WARN, FAIL):
        items.append(
            f"{len(items)+1}. **텍스트 표기 (영문/숫자만)** — 조각 이름·원단·사이즈·주석에 "
            "한글/중국어/일본어 등 비ASCII 문자가 있으면 인코딩 오류(글자 깨짐)가 발생할 수 있습니다. "
            "국제 표준어(영문)와 숫자로만 표기하여 재저장 부탁드립니다."
        )
    if diag["quantity"]["status"] in (WARN, FAIL):
        items.append(
            f"{len(items)+1}. **Quantity 메타** — 좌우 대칭 piece 는 2 로, 단일 piece 는 1 로 명시. "
            "현재 누락된 piece 는 시스템이 1 로 fallback 처리합니다."
        )
    if diag["grain"]["status"] in (WARN, FAIL):
        items.append(
            f"{len(items)+1}. **식서 방향 LINE** — 식서/푸서/바이어스 표시 LINE 을 일관된 LAYER 에 배치. "
            "누락 piece 는 시스템이 bbox 비율로 자동 추정하므로 정확도가 떨어집니다."
        )

    # 시접은 DXF 만으로 검증 불가 → 항상 안내.
    items.append(
        f"{len(items)+1}. **시접 포함 여부 명시** — 외곽선(POLYLINE) 은 재단선(시접 포함) 이어야 합니다. "
        "Net(완성선) 만 포함된 경우 요척이 부족하게 산출됩니다."
    )

    if not items or all(diag[k]["status"] == OK for k in ("material", "quantity", "grain")):
        # 모두 OK 라도 시접은 항상 안내. 그래도 메시지 자체는 전달.
        pass

    body = "\n".join(items)
    return (
        f"안녕하세요. 패턴 파일({style}) 검토 결과 다음 정보가 누락/부족하여 "
        f"정확한 요척 산출이 어렵습니다:\n\n"
        f"{body}\n\n"
        f"`PATTERN_PREP_GUIDE.md` v1.4 §15.0 협력사 패턴 제출 6 필수사항 참조 부탁드립니다.\n"
        f"감사합니다."
    )
