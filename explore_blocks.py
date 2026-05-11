# -*- coding: utf-8 -*-
"""
explore_blocks.py
-----------------
옵션 B 구현: 모델스페이스의 INSERT 엔티티를 virtual_entities()로 '펼쳐서'
각 블록이 실제로 어떤 기하(선·폴리라인·원호·스플라인 등)로 구성되어
도면 어느 위치에 놓여 있는지 본격적으로 살펴본다.

[왜 virtual_entities() 인가?]
  - INSERT 는 블록을 특정 위치·회전·스케일로 '참조 배치'한 것.
  - 블록 정의 내부 좌표는 '로컬 좌표'(블록 원점 기준)라 그대로는 실측에 못 씀.
  - virtual_entities() 는 그 배치 변환을 '이미 적용한' 엔티티 복사본을
    하나씩 돌려준다 → 월드 좌표에서 바로 쓸 수 있다.
  - 원본 블록 정의는 건드리지 않기 때문에 "가상(virtual)"이라는 이름.

이 스크립트가 출력하는 것:
  1) INSERT 기본 정보 표 (블록명, 삽입점, 회전, 스케일)
  2) 각 INSERT 내부 엔티티 타입 집계 (virtual_entities 기반)
  3) 각 INSERT 의 bounding box (실좌표)
  4) TEXT 엔티티의 실제 문자열 내용과 위치
  5) 도면 전체 bounding box + 단위 추정 힌트
"""

# ── 표준 라이브러리 ────────────────────────────────────────────
from collections import Counter  # 타입별 개수 집계용

# ── 외부 라이브러리 ────────────────────────────────────────────
# ezdxf.bbox 는 엔티티의 bounding box(경계 상자)를 계산해주는 헬퍼 모듈.
# INSERT 를 그대로 넘기면 내부 엔티티까지 자동으로 펼쳐 계산해준다.
from ezdxf import bbox

# ── 같은 폴더 안의 이전 스크립트에서 함수/상수 재사용 ─────────────
# 파이썬은 "같은 디렉터리의 .py 파일" 을 모듈처럼 import 할 수 있다.
# → 공통 로직(파일 열기, 경로 상수)을 중복 정의하지 않는다 (DRY 원칙).
from explore_dxf import open_dxf, DXF_FILE


# ╔════════════════════════════════════════════════════════════╗
# ║ 1. INSERT 정보 수집                                        ║
# ╚════════════════════════════════════════════════════════════╝
def inspect_inserts(doc) -> list[dict]:
    """
    모델스페이스 안의 INSERT 엔티티를 전부 찾아 기본 속성을 dict 로 수집한다.

    반환 형식:
      [
        {"name": "1", "x": ..., "y": ..., "rotation": ..., "xscale": ..., "yscale": ..., "entity": <INSERT>},
        ...
      ]

    entity 필드를 같이 담아두면, 이후 함수에서 또 쿼리하지 않고
    이 리스트만으로 모든 작업을 이어서 할 수 있어 효율적이다.
    """
    msp = doc.modelspace()

    # msp.query("INSERT") 는 지정한 DXF 타입만 필터링해서 돌려준다 (ezdxf 편의 기능).
    # for 루프에 그대로 쓸 수 있는 이터러블이다.
    inserts: list[dict] = []
    for ins in msp.query("INSERT"):
        inserts.append(
            {
                # dxf.name : 참조하는 블록의 이름 (예: "1", "2", ...)
                "name": ins.dxf.name,
                # dxf.insert : 삽입점 좌표 (Vec3 객체 → .x, .y, .z)
                "x": ins.dxf.insert.x,
                "y": ins.dxf.insert.y,
                # dxf.rotation : 회전각(도 단위, degree)
                "rotation": ins.dxf.rotation,
                # dxf.xscale / yscale : X/Y 방향 확대 배율 (보통 1.0)
                "xscale": ins.dxf.xscale,
                "yscale": ins.dxf.yscale,
                # 원본 엔티티 자체도 보관 → virtual_entities() / bbox 계산에 재사용
                "entity": ins,
            }
        )
    return inserts


def print_insert_table(inserts: list[dict]) -> None:
    """수집한 INSERT 정보를 정렬된 표로 출력한다."""
    print(f"\n── 모델스페이스 INSERT 목록 (총 {len(inserts)}개) ──")

    # 표 헤더 (폭 지정자로 칸 정렬)
    header = f"  {'#':>3} | {'블록':<4} | {'X':>12} | {'Y':>12} | {'Rot°':>6} | {'Sx':>5} | {'Sy':>5}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    # 블록 이름이 숫자 문자열이므로, 보기 좋게 int 변환 후 정렬해서 출력.
    # 정렬 실패(숫자 아님) 시 원래 순서 유지.
    try:
        inserts_sorted = sorted(inserts, key=lambda r: int(r["name"]))
    except ValueError:
        inserts_sorted = inserts

    for i, r in enumerate(inserts_sorted, start=1):
        print(
            f"  {i:>3} | {r['name']:<4} | {r['x']:>12.2f} | {r['y']:>12.2f} | "
            f"{r['rotation']:>6.1f} | {r['xscale']:>5.2f} | {r['yscale']:>5.2f}"
        )


# ╔════════════════════════════════════════════════════════════╗
# ║ 2. 블록 내부 엔티티 집계 (virtual_entities)                ║
# ╚════════════════════════════════════════════════════════════╝
def expand_entities(inserts: list[dict]) -> Counter:
    """
    각 INSERT 에 대해 virtual_entities() 로 내부를 펼쳐
    블록별 엔티티 타입 개수를 보여주고, 전체 합계도 같이 돌려준다.

    반환값: 전체 합계 Counter (이후 분석에 재사용 가능)
    """
    print("\n── 각 INSERT 내부 엔티티 (virtual_entities 로 펼침) ──")

    # 전체 합계를 누적할 Counter.
    # Counter 는 update() 로 다른 Counter 를 더할 수 있다 — 편리.
    global_counter: Counter = Counter()

    # 이름이 숫자 문자열이니 정수 정렬로 보기 좋게.
    try:
        ordered = sorted(inserts, key=lambda r: int(r["name"]))
    except ValueError:
        ordered = inserts

    for r in ordered:
        ins = r["entity"]

        # 핵심 호출: INSERT 가 참조하는 블록을 펼쳐 각 엔티티를 순회한다.
        # 이 때 나오는 엔티티들은 '가상 복제'라서 INSERT 의 위치·회전·스케일이
        # 반영된 좌표를 가진다. 필요하면 여기서 곧바로 bbox 나 길이 계산 가능.
        local_counter = Counter(e.dxftype() for e in ins.virtual_entities())
        global_counter.update(local_counter)

        # "LINE:12, ARC:3" 처럼 짧게 한 줄로 요약.
        summary = ", ".join(f"{t}:{c}" for t, c in local_counter.most_common())
        total = sum(local_counter.values())
        print(f"  블록 '{r['name']:<3}' → {total:>4}개  [{summary}]")

    # 전체 합계 출력
    print(f"\n  [모든 블록 합계] {sum(global_counter.values())}개")
    for t, c in global_counter.most_common():
        print(f"    {t:<15}: {c}")

    return global_counter


# ╔════════════════════════════════════════════════════════════╗
# ║ 3. 각 INSERT 의 bounding box (실좌표)                      ║
# ╚════════════════════════════════════════════════════════════╝
def compute_bboxes(inserts: list[dict]) -> list[dict]:
    """
    각 INSERT 의 실좌표 경계 상자(bounding box)를 계산하여 표로 출력하고,
    bbox 정보를 보강한 리스트를 돌려준다.
    """
    print("\n── 각 INSERT 의 Bounding Box (월드 좌표) ──")
    header = (
        f"  {'#':>3} | {'블록':<4} | "
        f"{'Xmin':>10} {'Ymin':>10} → {'Xmax':>10} {'Ymax':>10} | "
        f"{'너비':>9} × {'높이':>9}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    try:
        ordered = sorted(inserts, key=lambda r: int(r["name"]))
    except ValueError:
        ordered = inserts

    enriched: list[dict] = []
    for i, r in enumerate(ordered, start=1):
        ins = r["entity"]

        # ezdxf.bbox.extents(iterable) : 엔티티들의 합집합 bbox.
        # 단일 엔티티도 리스트로 감싸서 넘겨야 한다 → [ins].
        extents = bbox.extents([ins])

        if extents.has_data:
            mn = extents.extmin  # Vec3 (최솟값 점)
            mx = extents.extmax  # Vec3 (최댓값 점)
            width = mx.x - mn.x
            height = mx.y - mn.y
            print(
                f"  {i:>3} | {r['name']:<4} | "
                f"{mn.x:>10.1f} {mn.y:>10.1f} → {mx.x:>10.1f} {mx.y:>10.1f} | "
                f"{width:>9.1f} × {height:>9.1f}"
            )
            # 이후 전체 통계/정렬에 쓰기 위해 bbox 정보를 추가한 레코드를 따로 보관.
            enriched.append({**r, "bbox_min": mn, "bbox_max": mx, "w": width, "h": height})
        else:
            # 빈 블록이거나 기하가 없는 경우 — 거의 드물지만 방어적으로 처리.
            print(f"  {i:>3} | {r['name']:<4} | (bbox 계산 불가 — 내부 기하 없음)")
            enriched.append({**r, "bbox_min": None, "bbox_max": None, "w": 0, "h": 0})

    return enriched


# ╔════════════════════════════════════════════════════════════╗
# ║ 4. TEXT 내용 조회                                          ║
# ╚════════════════════════════════════════════════════════════╝
def list_texts(doc) -> None:
    """
    모델스페이스의 TEXT 엔티티를 순회하며 실제 글자 내용과 위치를 보여준다.
    의류 DXF 에서는 보통 피스 라벨(FRONT, BACK, 사이즈 등)이 여기에 있다.
    """
    msp = doc.modelspace()
    texts = list(msp.query("TEXT"))

    print(f"\n── TEXT 엔티티 내용 ({len(texts)}개) ──")
    # 텍스트가 하나도 없으면 친절히 알려주고 끝.
    if not texts:
        print("  (TEXT 엔티티가 없음)")
        return

    # 위치 기준으로 정렬해서 보여주면 라벨 배치 감각이 잡힌다.
    texts_sorted = sorted(texts, key=lambda t: (t.dxf.insert.y, t.dxf.insert.x))

    for i, t in enumerate(texts_sorted, start=1):
        content = t.dxf.text          # 실제 글자 내용
        ip = t.dxf.insert              # 삽입점 (Vec3)
        height = t.dxf.height          # 글자 높이
        rotation = t.dxf.rotation      # 회전각
        print(
            f"  {i:>2}. '{content}'  @ ({ip.x:>9.1f}, {ip.y:>9.1f}) "
            f"[h={height:.1f}, rot={rotation:.1f}°]"
        )


# ╔════════════════════════════════════════════════════════════╗
# ║ 5. 전체 도면 bbox + 단위 추정                              ║
# ╚════════════════════════════════════════════════════════════╝
def guess_real_unit(width: float, height: float) -> str:
    """
    도면 전체의 가로·세로 길이(좌표값 기준)를 보고 실제 단위를 추정한다.

    힌트:
      - 셔츠 패턴 전체 크기 현실값은 대략 1m × 1.5m 수준.
      - 그 값이 어떤 단위로 표현됐느냐에 따라 좌표 스케일이 달라진다:
          mm  → 수백~수천 (예: 600 × 1500)
          cm  → 수십~수백  (예: 60 × 150)
          m   → 한 자리~두 자리 (예: 0.6 × 1.5)
      - $INSUNITS 값이 실제와 다른 경우가 흔하므로, 좌표 스케일로 역추론한다.
    """
    # 가장 큰 차원을 기준으로 판단 — 둘 다 보다 보수적.
    longest = max(abs(width), abs(height))

    if longest >= 300:
        # 수백 이상 → mm 일 확률이 압도적 (한국 패턴업체 표준)
        return "mm (추정: 좌표 크기가 수백 단위 → 밀리미터)"
    elif longest >= 30:
        return "cm (추정: 좌표가 수십~수백 단위)"
    elif longest >= 0.3:
        return "m  (추정: 좌표가 소수점 자리수)"
    else:
        return "판별 불가 (좌표 크기가 너무 작거나 비어있음)"


def overall_bbox(doc) -> None:
    """도면 전체의 bounding box 를 계산하고, 실제 단위를 좌표 스케일로 추정한다."""
    msp = doc.modelspace()
    # 모델스페이스의 모든 엔티티를 리스트로 모아서 bbox 계산.
    all_entities = list(msp)
    extents = bbox.extents(all_entities)

    print("\n── 도면 전체 Bounding Box ──")
    if not extents.has_data:
        print("  (도면에 기하가 없어 bbox 를 계산할 수 없음)")
        return

    mn, mx = extents.extmin, extents.extmax
    width = mx.x - mn.x
    height = mx.y - mn.y

    print(f"  Min  : ({mn.x:>12.2f}, {mn.y:>12.2f})")
    print(f"  Max  : ({mx.x:>12.2f}, {mx.y:>12.2f})")
    print(f"  크기 : {width:.2f} × {height:.2f}")
    print(f"  단위 추정 (좌표 스케일 기반): {guess_real_unit(width, height)}")


# ╔════════════════════════════════════════════════════════════╗
# ║ 6. 메인 진입점                                             ║
# ╚════════════════════════════════════════════════════════════╝
def main() -> None:
    print("=" * 70)
    print(f"블록 내부 탐색 시작: {DXF_FILE.name}")
    print("=" * 70)

    # 이전 스크립트에서 만든 open_dxf 를 그대로 재사용.
    doc = open_dxf(DXF_FILE)
    if doc is None:
        print("\n[중단] DXF 문서를 열 수 없어 탐색을 종료합니다.")
        return

    # 순서:
    #   1) INSERT 기본 정보 수집 → 한 번만 쿼리하고 여러 단계에서 재사용
    #   2) 표 출력
    #   3) virtual_entities 로 내부 엔티티 집계
    #   4) 각 INSERT bbox
    #   5) TEXT 내용
    #   6) 전체 bbox + 단위 추정
    inserts = inspect_inserts(doc)
    print_insert_table(inserts)
    expand_entities(inserts)
    compute_bboxes(inserts)
    list_texts(doc)
    overall_bbox(doc)

    print("\n" + "=" * 70)
    print("블록 내부 탐색 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
