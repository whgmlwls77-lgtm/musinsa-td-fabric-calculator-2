"""
validate_against_reference.py
=============================

앱이 계산한 요척값을 본사 실제 요척서와 비교해 정확도를 검증.

사용법:
    python validate_against_reference.py                         # 전체 비교
    python validate_against_reference.py --style MWDPS901        # 단일 품번
    python validate_against_reference.py --tolerance 0.05        # 허용 오차 5%
    python validate_against_reference.py --report html           # HTML 리포트 출력

검증 데이터: 요척자료데이터/요척_검증데이터.csv

작성: 2026-04-27 (스켈레톤)
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ============================================================
# 상수
# ============================================================
PROJECT_ROOT = Path(__file__).parent
REFERENCE_CSV = PROJECT_ROOT / "요척자료데이터" / "요척_검증데이터.csv"
DXF_DIR = PROJECT_ROOT  # 현재 프로젝트 루트에 DXF 두는 구조
OUTPUT_DIR = PROJECT_ROOT / "output"

YD_TO_M = 0.9144
IN_TO_CM = 2.54

# 허용 오차 기본값 (5%)
DEFAULT_TOLERANCE = 0.05


# ============================================================
# 데이터 모델
# ============================================================
@dataclass
class ReferenceRow:
    """본사 요척서 1건"""
    style_code: str          # 품번 (예: MWDPS901)
    material: str            # 재질 (SELF, FUSE, ...)
    fabric_width_in: Optional[float]
    consumption_yd: Optional[float]   # 벌당 요척 (yd)
    efficiency_pct: Optional[float]
    loss_included: bool      # LOSS 포함 여부
    direction: str           # 1WAY / 2WAY / 미상
    source_file: str
    note: str = ""

    @property
    def consumption_m(self) -> Optional[float]:
        return self.consumption_yd * YD_TO_M if self.consumption_yd else None

    @property
    def fabric_width_cm(self) -> Optional[float]:
        return self.fabric_width_in * IN_TO_CM if self.fabric_width_in else None


@dataclass
class AppCalculation:
    """앱이 계산한 결과 1건"""
    style_code: str
    material: str
    fabric_width_cm: float
    consumption_m: float
    size: Optional[str] = None
    direction: str = "2WAY"

    @property
    def consumption_yd(self) -> float:
        return self.consumption_m / YD_TO_M


@dataclass
class Comparison:
    """검증 결과 1건"""
    reference: ReferenceRow
    app: Optional[AppCalculation]
    delta_yd: Optional[float] = None
    delta_pct: Optional[float] = None
    status: str = "pending"   # pass / fail / no_app_data / no_ref_data
    notes: list[str] = field(default_factory=list)


# ============================================================
# 1. 검증 데이터 로드
# ============================================================
def load_reference(csv_path: Path = REFERENCE_CSV) -> list[ReferenceRow]:
    """본사 요척 CSV → ReferenceRow 리스트"""
    rows: list[ReferenceRow] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            try:
                width = float(r["원단폭_in"]) if r["원단폭_in"] and r["원단폭_in"].replace(".", "").isdigit() else None
                cons = float(r["벌당_요척_yd"]) if r["벌당_요척_yd"] and r["벌당_요척_yd"].replace(".", "").isdigit() else None
                eff = float(r["효율_pct"]) if r["효율_pct"] and r["효율_pct"].replace(".", "").isdigit() else None
            except ValueError:
                width = cons = eff = None

            rows.append(ReferenceRow(
                style_code=r["품번"] or "",
                material=r["재질"] or "",
                fabric_width_in=width,
                consumption_yd=cons,
                efficiency_pct=eff,
                loss_included=("미포함" not in r["LOSS여부"] and "NET" not in r["LOSS여부"]),
                direction=r["방향"] or "미상",
                source_file=r["파일명"],
                note=r["비고"] or "",
            ))
    return rows


# ============================================================
# 2. 앱 계산 호출 (TODO — 클로드 코드가 채울 부분)
# ============================================================
def calculate_with_app(style_code: str, dxf_dir: Path = DXF_DIR) -> list[AppCalculation]:
    """
    품번에 해당하는 DXF를 찾아서 앱 로직(fabric_calculator)으로 요척 계산.

    TODO:
    - [ ] dxf_dir에서 {style_code}*.dxf 파일 검색
    - [ ] fabric_calculator.calculate_consumption() 호출
    - [ ] 결과를 AppCalculation 리스트로 변환 (재질별/사이즈별)
    - [ ] 본사 요척과 비교 가능한 단위(yd, in)로 정규화

    힌트:
    >>> from fabric_calculator import calculate_consumption
    >>> result = calculate_consumption(dxf_path, fabric_width_cm=137)
    >>> # result 형식 확인 후 AppCalculation으로 매핑
    """
    raise NotImplementedError("클로드 코드 세션에서 구현 필요")


# ============================================================
# 3. 비교 로직
# ============================================================
def compare_one(ref: ReferenceRow, apps: list[AppCalculation], tolerance: float) -> Comparison:
    """본사 요척 1건 vs 앱 계산 결과들 — 가장 가까운 매칭 찾아 비교"""
    if not apps:
        return Comparison(reference=ref, app=None, status="no_app_data",
                          notes=["앱 계산 결과 없음"])
    if ref.consumption_yd is None:
        return Comparison(reference=ref, app=apps[0], status="no_ref_data",
                          notes=["본사 요척값 없음 (수동 입력 필요)"])

    # 재질 매칭 우선 (같은 SELF끼리), 없으면 첫 번째
    matched = next((a for a in apps if a.material.upper() == ref.material.upper()), apps[0])

    delta_yd = matched.consumption_yd - ref.consumption_yd
    delta_pct = delta_yd / ref.consumption_yd

    notes = []
    if not ref.loss_included:
        notes.append("⚠ 본사값은 LOSS 미포함 — 앱 계산에도 LOSS 빼야 정확 비교")
    if matched.material.upper() != ref.material.upper():
        notes.append(f"⚠ 재질 불일치: 본사={ref.material}, 앱={matched.material}")

    status = "pass" if abs(delta_pct) <= tolerance else "fail"
    return Comparison(
        reference=ref, app=matched,
        delta_yd=round(delta_yd, 4), delta_pct=round(delta_pct * 100, 2),
        status=status, notes=notes,
    )


# ============================================================
# 4. 리포트
# ============================================================
def print_report(comparisons: list[Comparison]) -> None:
    """콘솔 표 출력"""
    print(f"\n{'='*100}")
    print(f"{'품번':<14} {'재질':<10} {'본사(yd)':>10} {'앱(yd)':>10} {'오차(yd)':>10} {'오차(%)':>8} {'상태':<8} 비고")
    print(f"{'='*100}")

    for c in comparisons:
        ref_yd = f"{c.reference.consumption_yd:.4f}" if c.reference.consumption_yd else "-"
        app_yd = f"{c.app.consumption_yd:.4f}" if c.app else "-"
        d_yd = f"{c.delta_yd:+.4f}" if c.delta_yd is not None else "-"
        d_pct = f"{c.delta_pct:+.2f}" if c.delta_pct is not None else "-"
        notes = "; ".join(c.notes)
        print(f"{c.reference.style_code:<14} {c.reference.material:<10} {ref_yd:>10} {app_yd:>10} {d_yd:>10} {d_pct:>8} {c.status:<8} {notes}")

    # 통계
    total = len(comparisons)
    passed = sum(1 for c in comparisons if c.status == "pass")
    failed = sum(1 for c in comparisons if c.status == "fail")
    nodata = sum(1 for c in comparisons if c.status in ("no_app_data", "no_ref_data"))
    print(f"\n{'='*100}")
    print(f"총 {total}건 | 통과 {passed} | 실패 {failed} | 데이터 없음 {nodata}")
    if total - nodata > 0:
        print(f"통과율: {passed / (total - nodata) * 100:.1f}%")


def save_report_json(comparisons: list[Comparison], path: Path) -> None:
    """JSON 리포트 저장"""
    data = []
    for c in comparisons:
        data.append({
            "style_code": c.reference.style_code,
            "material": c.reference.material,
            "reference_yd": c.reference.consumption_yd,
            "app_yd": c.app.consumption_yd if c.app else None,
            "delta_yd": c.delta_yd,
            "delta_pct": c.delta_pct,
            "status": c.status,
            "notes": c.notes,
            "source_file": c.reference.source_file,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


# ============================================================
# CLI
# ============================================================
def main():
    p = argparse.ArgumentParser(description="앱 vs 본사 요척 검증")
    p.add_argument("--style", help="단일 품번만 검증 (예: MWDPS901)")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                   help=f"허용 오차 비율 (기본 {DEFAULT_TOLERANCE})")
    p.add_argument("--report", choices=["console", "json"], default="console")
    p.add_argument("--output", default=str(OUTPUT_DIR / "validation_report.json"))
    args = p.parse_args()

    print(f"검증 데이터 로드: {REFERENCE_CSV}")
    refs = load_reference()
    if args.style:
        refs = [r for r in refs if r.style_code == args.style]
        print(f"  → {args.style} 필터: {len(refs)}건")
    else:
        print(f"  → 총 {len(refs)}건")

    comparisons = []
    for ref in refs:
        try:
            apps = calculate_with_app(ref.style_code)
        except NotImplementedError as e:
            comparisons.append(Comparison(reference=ref, app=None, status="no_app_data",
                                           notes=[str(e)]))
            continue
        except FileNotFoundError:
            comparisons.append(Comparison(reference=ref, app=None, status="no_app_data",
                                           notes=["DXF 파일 없음"]))
            continue
        comparisons.append(compare_one(ref, apps, args.tolerance))

    if args.report == "console":
        print_report(comparisons)
    elif args.report == "json":
        save_report_json(comparisons, Path(args.output))
        print(f"리포트 저장: {args.output}")


if __name__ == "__main__":
    main()
