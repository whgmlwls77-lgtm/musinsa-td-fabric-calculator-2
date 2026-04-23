# -*- coding: utf-8 -*-
"""
explore_dxf.py
--------------
DXF 파일 탐색 스크립트.
의류 패턴 DXF를 열어서 다음 정보를 콘솔에 출력합니다.
  1) 도면 단위 ($INSUNITS)
  2) 레이어 이름 목록
  3) 모델스페이스 엔티티 타입별 개수
  4) 블록(Block) 이름 목록

사용 라이브러리:
  - ezdxf : DXF 파싱용 (pip install ezdxf)

실행:
  python explore_dxf.py
"""

# ── 표준 라이브러리 ────────────────────────────────────────────
# Path : 파일 경로를 문자열보다 안전하게 다루는 객체
from pathlib import Path
# Counter : 항목별 개수를 세는 데 특화된 딕셔너리 (collections 모듈 제공)
from collections import Counter

# ── 외부 라이브러리 ────────────────────────────────────────────
# ezdxf 본체와, 예외 타입 두 개(파일 없음 / DXF 구조 오류)를 함께 가져온다.
import ezdxf
from ezdxf import DXFStructureError


# ╔════════════════════════════════════════════════════════════╗
# ║ 1. 설정 값 (파일 경로는 여기서만 관리한다 — 하드코딩 금지) ║
# ╚════════════════════════════════════════════════════════════╝
# Path.home() 은 ~ (홈 디렉터리)를 반환한다.
# OS마다 홈 경로가 달라도 이 한 줄이면 안전하게 절대경로가 만들어진다.
DXF_FILE: Path = (
    Path.home()
    / "Desktop"
    / "Claude"
    / "fit-prog"
    / "dxf_test"
    / "MWESL4Z03_우먼즈 릴렉스드 멀티 스트라이프 셔츠_삼원.dxf"
)

# $INSUNITS 코드 → 사람이 읽을 수 있는 단위명 매핑.
# DXF 스펙(AutoCAD)에 정의된 숫자 코드이며, 0은 "단위 지정 없음"을 의미한다.
INSUNITS_MAP: dict[int, str] = {
    0: "Unitless (단위 없음)",
    1: "Inches (인치)",
    2: "Feet (피트)",
    3: "Miles (마일)",
    4: "Millimeters (mm)",
    5: "Centimeters (cm)",
    6: "Meters (m)",
    7: "Kilometers (km)",
    8: "Microinches",
    9: "Mils",
    10: "Yards (야드)",
    11: "Angstroms",
    12: "Nanometers",
    13: "Microns",
    14: "Decimeters",
    15: "Decameters",
    16: "Hectometers",
    17: "Gigameters",
    18: "Astronomical units",
    19: "Light years",
    20: "Parsecs",
}


# ╔════════════════════════════════════════════════════════════╗
# ║ 2. 함수 정의                                               ║
# ╚════════════════════════════════════════════════════════════╝
def open_dxf(path: Path):
    """
    DXF 파일을 읽어 Drawing 객체를 돌려준다.

    - 파일이 없으면 FileNotFoundError,
    - DXF 구조가 깨져 있으면 DXFStructureError 발생 가능.
    - 두 경우 모두 친절한 한글 메시지를 출력하고 None 을 반환한다.

    ezdxf.readfile() 은 엄격 모드이고,
    구조 오류 시 ezdxf.recover.readfile() 로 한 번 더 시도한다 (복구 모드).
    """
    # 파일 존재 여부를 먼저 확인하면, 실제 파싱 에러와 혼동하지 않게 된다.
    if not path.exists():
        print(f"[에러] 파일을 찾을 수 없습니다: {path}")
        return None

    try:
        # 1차 시도: 엄격 파싱.
        doc = ezdxf.readfile(str(path))
        print(f"[OK] DXF 파일 열기 성공 (엄격 모드): {path.name}")
        return doc

    except DXFStructureError as e:
        # 파일 구조가 깨졌을 때는 recover 모듈로 관대하게 읽어본다.
        print(f"[경고] 구조 오류 감지 — 복구 모드로 재시도합니다. ({e})")
        try:
            # ezdxf.recover.readfile 은 (Drawing, auditor) 튜플을 돌려준다.
            import ezdxf.recover as recover

            doc, auditor = recover.readfile(str(path))
            if auditor.has_errors:
                print(f"[경고] 복구 후에도 {len(auditor.errors)}건의 문제가 남아 있음")
            print(f"[OK] DXF 파일 열기 성공 (복구 모드): {path.name}")
            return doc
        except Exception as inner:
            print(f"[에러] 복구 모드도 실패했습니다: {inner}")
            return None

    except IOError as e:
        # 권한 문제, 파일이 잠긴 경우 등 OS 수준 IO 에러.
        print(f"[에러] 파일을 열 수 없습니다 (IO 오류): {e}")
        return None


def print_insunits(doc) -> None:
    """
    도면 단위($INSUNITS)를 조회해서 코드와 의미를 함께 출력한다.

    $INSUNITS 는 DXF HEADER 섹션에 저장된 변수이며,
    '이 도면의 길이 값이 어떤 단위로 기록되어 있는지'를 나타낸다.
    """
    # doc.header 는 딕셔너리처럼 접근 가능한 HEADER 변수 컨테이너다.
    # .get(key, default) 를 쓰면 변수가 없어도 KeyError 가 안 난다.
    code: int = doc.header.get("$INSUNITS", 0)

    # INSUNITS_MAP 에 없는 코드가 나와도 안전하게 처리하기 위해 .get 사용.
    meaning: str = INSUNITS_MAP.get(code, "Unknown (정의되지 않은 코드)")

    print("\n── 도면 단위 ($INSUNITS) ──")
    print(f"  코드: {code}")
    print(f"  의미: {meaning}")


def print_layers(doc) -> None:
    """
    도면에 정의된 모든 레이어 이름을 정렬해서 출력한다.

    doc.layers 는 Layer 객체들을 순회할 수 있는 테이블이다.
    각 Layer 에는 이름(dxf.name), 색상, 선종류 등의 속성이 있다.
    여기서는 이름만 간단히 모아서 보여준다.
    """
    # 리스트 컴프리헨션: "모든 layer 객체에서 layer.dxf.name 만 꺼내라"
    names = [layer.dxf.name for layer in doc.layers]
    # sorted() 로 알파벳(유니코드) 순서 정렬 — 일관된 출력을 위해.
    names.sort()

    print(f"\n── 레이어 목록 (총 {len(names)}개) ──")
    for i, name in enumerate(names, start=1):
        # f-string의 정렬 지정자 {:>3} : 오른쪽 정렬 3칸
        print(f"  {i:>3}. {name}")


def count_entities(doc) -> Counter:
    """
    모델스페이스에 있는 엔티티를 DXF 타입별로 집계하여 표 형태로 출력한다.
    집계 결과(Counter)는 호출한 쪽에서 더 쓸 수 있도록 반환한다.

    모델스페이스(modelspace):
      - DXF 의 실제 도형(도면)이 그려지는 메인 공간.
      - doc.modelspace() 로 접근하면 이터레이션이 가능한 레이아웃 객체가 나온다.
      - 각 엔티티는 LINE, LWPOLYLINE, CIRCLE, ARC, SPLINE, INSERT, TEXT ... 등
        문자열로 된 DXF 타입을 가진다 — entity.dxftype() 으로 얻는다.
    """
    msp = doc.modelspace()

    # 제너레이터 표현식으로 타입 문자열만 흘려보내서 Counter 로 바로 집계.
    # (리스트를 먼저 만들지 않으므로 메모리 절약에 유리하다.)
    counter: Counter = Counter(entity.dxftype() for entity in msp)
    total = sum(counter.values())

    print(f"\n── 모델스페이스 엔티티 집계 (총 {total}개) ──")
    # 표 헤더
    print(f"  {'엔티티 타입':<15} | {'개수':>8}")
    print(f"  {'-' * 15}-+-{'-' * 8}")

    # most_common() 은 개수 많은 순으로 정렬된 (타입, 개수) 튜플 리스트.
    for dxftype, count in counter.most_common():
        print(f"  {dxftype:<15} | {count:>8}")

    return counter


def print_blocks(doc) -> None:
    """
    도면에 정의된 블록(Block) 이름 목록을 출력한다.

    블록(Block) 이란?
      - 여러 엔티티를 하나의 '도장(스탬프)'처럼 묶어 재사용 가능하게 만든 것.
      - 모델스페이스에 INSERT 엔티티로 참조되어 반복적으로 배치된다.
      - DXF 내부에는 '*Model_Space', '*Paper_Space' 같은
        시스템 자동 생성 블록도 포함되어 있다 — 별(*)로 시작하는 것이 특징.
    """
    # 사용자 블록과 시스템 블록을 나누어서 보여주면 이해가 쉽다.
    user_blocks: list[str] = []
    system_blocks: list[str] = []

    # doc.blocks 를 순회하면 BlockLayout 객체가 나오고,
    # .name 속성에서 블록 이름을 얻을 수 있다.
    for block in doc.blocks:
        if block.name.startswith("*"):
            system_blocks.append(block.name)
        else:
            user_blocks.append(block.name)

    user_blocks.sort()
    system_blocks.sort()

    print(f"\n── 블록 목록 (사용자 {len(user_blocks)}개 / 시스템 {len(system_blocks)}개) ──")

    print("  [사용자 정의 블록]")
    if user_blocks:
        for i, name in enumerate(user_blocks, start=1):
            print(f"    {i:>3}. {name}")
    else:
        print("    (없음)")

    print("  [시스템 블록]")
    if system_blocks:
        for i, name in enumerate(system_blocks, start=1):
            print(f"    {i:>3}. {name}")
    else:
        print("    (없음)")


# ╔════════════════════════════════════════════════════════════╗
# ║ 3. 메인 실행부                                             ║
# ╚════════════════════════════════════════════════════════════╝
def main() -> None:
    """각 함수를 순서대로 호출하는 진입점."""
    print("=" * 60)
    print(f"DXF 탐색 시작: {DXF_FILE.name}")
    print("=" * 60)

    doc = open_dxf(DXF_FILE)
    # 파일 열기 실패 시 나머지 단계는 건너뛴다.
    if doc is None:
        print("\n[중단] DXF 문서를 열 수 없어 탐색을 종료합니다.")
        return

    print_insunits(doc)
    print_layers(doc)
    count_entities(doc)
    print_blocks(doc)

    print("\n" + "=" * 60)
    print("DXF 탐색 완료")
    print("=" * 60)


# 이 파일이 `python explore_dxf.py` 로 직접 실행될 때만 main() 이 돌도록 한다.
# (다른 파일에서 import 해서 함수만 가져다 쓰고 싶을 때도 안전하게 동작.)
if __name__ == "__main__":
    main()
