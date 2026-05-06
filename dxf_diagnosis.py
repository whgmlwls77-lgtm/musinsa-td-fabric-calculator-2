"""
DXF 진단 — 4대 카테고리 (결방향 / 원단 / 패널 / 수량) 자동 진단 + 협력사 메시지.

사장님 절대 원칙: 알고리즘 읽기 실패 vs 협력사 정보 누락 구분.
이 모듈은 그 구분을 raw 데이터로 입증한다 — 추측 금지.

호출자: app.py 가 parse_dxf_v3 결과 + ezdxf doc 을 넘긴다.

검증 스크립트: /tmp/dxf_diagnosis_audit.py
"""
from __future__ import annotations

import re

from piece_name_normalize import normalize_piece_name

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
# [3] 패널 정보 (piece_name)
# 사장님 본질 (2026-05-06): "표준만 인식 → 표준 외 위반 알림"
#   panel_mapping.json 의 standard_names + 약자 매칭 = 표준
#   미매칭 = 표준 외 (위반)
#   Material:NON 마카제외 piece 는 패널 분류 대상에서 제외.
# ──────────────────────────────────────────────
def diagnose_panel(parsed: dict) -> dict:
    pieces = parsed["pieces"]
    if not pieces:
        return _empty("패널 정보")

    style = (parsed.get("style") or "").upper()
    seen_keys: set[str] = set()
    by_class: dict[str, int] = {"standard": 0, "non_standard": 0, "empty": 0}
    samples: dict[str, list[str]] = {k: [] for k in by_class}
    n_excluded = 0

    for p in pieces:
        pk = p.get("piece_key") or p.get("piece_id") or ""
        if pk in seen_keys:
            continue
        seen_keys.add(pk)

        # 마카제외 (Material=NON) → 패널 표준 분류 대상 외.
        raw_mat = (p.get("material_raw") or p.get("material") or "").strip().upper()
        inferred_mat = (p.get("material_inferred") or "").strip()
        if inferred_mat == "마카제외" or raw_mat in {"NON", "NONE"}:
            n_excluded += 1
            continue

        nm = (p.get("piece_name") or "").strip()
        # 스타일 prefix 제거 (예: 'MMAPS003 FRONT_BODY' → 'FRONT_BODY')
        if style and nm.upper().startswith(style):
            nm = nm[len(style):].lstrip(" -_")

        if not nm:
            cls = "empty"
            disp = "(empty)"
        else:
            std_name, is_standard = normalize_piece_name(nm)
            if is_standard:
                cls = "standard"
                disp = std_name if std_name == nm.upper() else f"{nm} → {std_name}"
            else:
                cls = "non_standard"
                disp = nm

        by_class[cls] += 1
        if len(samples[cls]) < 5:
            samples[cls].append(disp)

    n_total = len(seen_keys)
    n_classified = sum(by_class.values())
    n_std = by_class["standard"]
    n_non = by_class["non_standard"]
    n_empty = by_class["empty"]

    # 마카제외만 있고 분류 대상 0개 → 정상 (마카 nesting skip).
    if n_classified == 0:
        if n_excluded > 0:
            return {
                "status": OK,
                "summary": f"마카제외 piece 만 {n_excluded}/{n_total} (전부 nesting skip).",
                "dxf_state": f"unique 부위 {n_total}개 (전부 마카제외)",
                "algo_state": "마카 nesting skip",
                "raw": {
                    "n_unique_pieces": n_total,
                    "by_class": by_class,
                    "samples": samples,
                    "n_excluded": n_excluded,
                },
            }
        return _empty("패널 정보")

    excluded_disp = f" + 마카제외 {n_excluded}개" if n_excluded > 0 else ""

    if n_std == n_classified:
        status = OK
        summary = f"모든 piece 표준 부위명 ({n_std}/{n_classified}){excluded_disp}."
    elif n_empty > 0 and n_non == 0:
        status = FAIL
        summary = f"이름 누락 piece {n_empty}/{n_classified}{excluded_disp}."
    elif n_non > 0:
        status = WARN
        summary = (
            f"표준 외 명칭 {n_non}/{n_classified}개{excluded_disp} — "
            f"panel_mapping.json 표준 어휘집 등재 또는 영문 표준 부위명 사용 요청 필요."
        )
    else:
        status = WARN
        summary = f"혼재 — 표준:{n_std} 표준외:{n_non} 누락:{n_empty}{excluded_disp}"

    # 샘플 표시.
    sample_disp_parts = []
    for cls, label in [("standard", "표준"), ("non_standard", "표준외"), ("empty", "누락")]:
        if samples[cls]:
            sample_disp_parts.append(f"{label}: " + ", ".join(samples[cls]))
    sample_disp = " · ".join(sample_disp_parts)

    return {
        "status": status,
        "summary": summary,
        "dxf_state": f"unique 부위 {n_total}개 (마카 분류 {n_classified}, 마카제외 {n_excluded}) — {sample_disp}",
        "algo_state": (
            "표준 외/누락 → 매핑 사전 또는 영문 표준 표기 요청"
            if (n_non > 0 or n_empty > 0)
            else "표준 표기 그대로 사용"
        ),
        "raw": {
            "n_unique_pieces": n_total,
            "by_class": by_class,
            "samples": samples,
            "n_excluded": n_excluded,
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

    # unique piece 단위 집계 — diagnose_panel 과 일관.
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
# [6] DXF 스케일 검증 — 50x50 비율 박스 (사장님 본질 2026-05-07)
#
# 사장님 명시: 50cm × 50cm 정사각형 박스 piece 추가 (Material:NON, 마카 제외).
# DXF 좌표가 cm 단위로 정확한지 raw 검증 도구.
#   측정 ≈ 50 cm        → 스케일 정상 ✅
#   측정 ≈ 19.685 cm    → DXF inch 단위 (×2.54 = 50cm)
#   측정 ≈ 5 cm         → DXF mm 단위 (×10 = 50cm)
#   기타                → 사장님 직접 측정 + 보정 결정
# ──────────────────────────────────────────────
SCALE_BOX_NAME_KEYWORDS = ("50X50", "50_X_50", "50CM", "SCALE_BOX", "비율박스")
SCALE_BOX_TARGET_CM = 50.0
SCALE_BOX_TOLERANCE_CM = 0.5  # ±0.5cm 이내 → 정상으로 판정


def detect_scale_box(pieces: list[dict]) -> dict | None:
    """50x50 비율 박스 piece 검출.

    검출 조건 (모두 충족):
      1) Material:NON (마카 제외)
      2) piece_name 에 SCALE_BOX_NAME_KEYWORDS 중 하나 포함
         OR 정사각형 (|w - h| < 0.5)
    검출 불가 시 None.
    """
    candidates = []
    for p in pieces:
        # 마카 제외 piece 만 후보
        raw = (p.get("material_raw") or p.get("material") or "").strip().upper()
        inferred = (p.get("material_inferred") or "").strip()
        is_non = inferred == "마카제외" or raw in {"NON", "NONE"}
        if not is_non:
            continue

        nm = (p.get("piece_name") or "").upper()
        w = float(p.get("width_cm") or 0)
        h = float(p.get("height_cm") or 0)
        is_square = w > 0 and abs(w - h) < 0.5
        name_match = any(kw in nm for kw in SCALE_BOX_NAME_KEYWORDS)

        if name_match or is_square:
            candidates.append({
                "piece_id": p.get("piece_id", "?"),
                "piece_name": p.get("piece_name") or "(empty)",
                "measured_w_cm": w,
                "measured_h_cm": h,
                "name_match": name_match,
                "is_square": is_square,
            })

    if not candidates:
        return None

    # 이름 매칭이 있으면 우선, 없으면 정사각형 중 가장 큰 것
    name_matched = [c for c in candidates if c["name_match"]]
    if name_matched:
        return name_matched[0]
    candidates.sort(key=lambda c: c["measured_w_cm"], reverse=True)
    return candidates[0]


def compute_scale_correction(measured_cm: float) -> tuple[float, str]:
    """50cm 박스 측정값 → 보정 비율 + 단위 가설 반환.

    Returns:
      (correction_ratio, unit_hypothesis)
      correction_ratio = 1.0 → 보정 불필요 (cm)
      correction_ratio = 2.54 → DXF 좌표 inch 의심
      correction_ratio = 10.0 → DXF 좌표 mm 의심
      etc.
    """
    if measured_cm <= 0:
        return 1.0, "측정 불가"
    ratio = SCALE_BOX_TARGET_CM / measured_cm
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


def diagnose_scale(parsed: dict) -> dict:
    """50x50 비율 박스로 DXF 스케일 검증 (사장님 본질 2026-05-07).

    박스 검출 시:
      - 측정 50.0 ± 0.5 cm → ✅ 스케일 정상
      - 그 외 → ⚠️ 보정 비율 + 단위 가설 안내 (자동 적용 X)
    검출 불가 시: ✅ "검증 도구 박스 없음 (협력사 표준 가이드 §X 참고)" — 정보성.
    """
    pieces = parsed.get("pieces") or []
    box = detect_scale_box(pieces)

    if box is None:
        return {
            "status": OK,
            "summary": "스케일 검증 박스 없음 — 50x50cm Material:NON 박스 추가 시 자동 검증 가능.",
            "dxf_state": "검증 도구 미사용",
            "algo_state": "스케일 검증 skip",
            "raw": {"detected": False},
        }

    w = box["measured_w_cm"]
    h = box["measured_h_cm"]
    delta_w = w - SCALE_BOX_TARGET_CM
    delta_h = h - SCALE_BOX_TARGET_CM

    # 정상 (±0.5cm)
    if abs(delta_w) <= SCALE_BOX_TOLERANCE_CM and abs(delta_h) <= SCALE_BOX_TOLERANCE_CM:
        return {
            "status": OK,
            "summary": (
                f"스케일 검증 박스 ({box['piece_name']}) 측정 "
                f"{w:.3f} × {h:.3f} cm — 50cm 기준 정상 ✅"
            ),
            "dxf_state": f"박스 측정: {w:.3f} × {h:.3f} cm (목표 50.0)",
            "algo_state": "DXF 좌표 cm 단위 정상 — 보정 불필요",
            "raw": {
                "detected": True,
                "piece_name": box["piece_name"],
                "measured_w_cm": w,
                "measured_h_cm": h,
                "delta_w": delta_w,
                "delta_h": delta_h,
                "correction_ratio": 1.0,
                "unit_hypothesis": "cm (정상)",
            },
        }

    # 보정 필요 (단위 미스매치 의심)
    correction, hypothesis = compute_scale_correction(w)
    return {
        "status": WARN,
        "summary": (
            f"스케일 검증 박스 ({box['piece_name']}) 측정 "
            f"{w:.3f} × {h:.3f} cm — 50cm 기준 {delta_w:+.3f}cm 갭 ⚠️  "
            f"단위 의심: {hypothesis}"
        ),
        "dxf_state": (
            f"박스 측정: {w:.3f} × {h:.3f} cm  ·  목표: 50.0 cm  ·  "
            f"갭: w {delta_w:+.3f} / h {delta_h:+.3f}"
        ),
        "algo_state": (
            f"보정 비율 {correction:.4f}배 — 자동 적용 X (사장님 결정 대기). "
            f"옵션: ① 코드 자동 보정 / ② 사장님 export 옵션 변경"
        ),
        "raw": {
            "detected": True,
            "piece_name": box["piece_name"],
            "measured_w_cm": w,
            "measured_h_cm": h,
            "delta_w": delta_w,
            "delta_h": delta_h,
            "correction_ratio": correction,
            "unit_hypothesis": hypothesis,
        },
    }


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
      - pattern_name_invalid: 표준 어휘집 외 명칭
      - quantity_missing: 갯수 메타 부재
      - material_missing: 원단 종류 미표기
      - grain_missing: 식서 LINE 부재 (Y kind 가 estimated 인 경우)

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
        is_std = bool(p.get("is_standard_name"))

        # 1) 패턴 명칭 표준 외 — piece_name_raw 가 있을 때만 검증
        if raw_pn and not is_std:
            violations.append({
                "type": "pattern_name_invalid",
                "piece_name": pn,
                "raw_name": raw_pn,
                "detail": f"'{raw_pn}' 표준 어휘집 외 명칭",
            })

        # 2) 갯수 메타 부재
        if p.get("quantity") is None:
            violations.append({
                "type": "quantity_missing",
                "piece_name": pn,
                "raw_name": raw_pn,
                "detail": "갯수 메타 없음",
            })

        # 3) 원단 종류 미표기 — material_raw 비어있고 inferred 도 fallback
        raw_mat = (p.get("material_raw") or p.get("material") or "").strip()
        if not raw_mat:
            violations.append({
                "type": "material_missing",
                "piece_name": pn,
                "raw_name": raw_pn,
                "detail": "원단 종류 표기 없음",
            })

        # 4) 식서 부재 — grain.estimated == True (LINE 못 찾고 bbox 추정 사용)
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
        "panel":    diagnose_panel(parsed),
        "quantity": diagnose_quantity(parsed),
        "excluded": diagnose_excluded(parsed),
        # 사장님 본질 (2026-05-07) — DXF 스케일 검증 (50x50 비율 박스)
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
    if diag["panel"]["status"] in (WARN, FAIL):
        d = diag["panel"]["raw"]
        sub = []
        if d.get("by_class", {}).get("non_standard", 0) > 0:
            sub.append(
                "표준 외 부위명 발견 → 표준 영문 부위명 (panel_mapping.json) 사용 또는 약자 매핑 추가 필요."
            )
        if d.get("by_class", {}).get("empty", 0) > 0:
            sub.append("이름 누락 piece 발견 → 전 piece 에 Piece Name 부여.")
        if sub:
            items.append(
                f"{len(items)+1}. **piece_name 부위명** — " + " ".join(sub)
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

    if not items or all(diag[k]["status"] == OK for k in ("material", "panel", "quantity", "grain")):
        # 4가지 모두 OK 라도 시접은 항상 안내. 그래도 메시지 자체는 전달.
        pass

    body = "\n".join(items)
    return (
        f"안녕하세요. 패턴 파일({style}) 검토 결과 다음 정보가 누락/부족하여 "
        f"정확한 요척 산출이 어렵습니다:\n\n"
        f"{body}\n\n"
        f"`PATTERN_PREP_GUIDE.md` v1.4 §15.0 협력사 패턴 제출 6 필수사항 참조 부탁드립니다.\n"
        f"감사합니다."
    )
