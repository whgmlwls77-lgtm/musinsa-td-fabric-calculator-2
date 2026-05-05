# 원단 요척 산출 시스템 — 패턴 파일(DXF) 준비 가이드

> **대상**: 패턴사 / 협력 업체
> **목적**: 요척 산출 시스템이 패턴을 정확히 인식하도록 DXF 파일을 작성하는 최소 규칙

---

## 1. 왜 이 규칙이 중요한가

본 시스템은 DXF 내부의 **메타데이터(Piece Name / Size / Quantity / Material)를 읽어 자동 계산**합니다.
이 정보가 누락되거나 잘못 표기되면:

- 재질 분류가 "미지정"으로 떨어져 주원단에 잘못 합산됨
- 사이즈별 요척 계산이 틀어짐
- 요척 값이 비정상적으로 나옴

아래 규칙을 지켜주시면 시스템이 정상 인식합니다.

---

## 2. 파일 기본 요구사항

| 항목 | 요구 조건 |
|------|----------|
| 포맷 | **DXF** |
| 단위 | **cm** (또는 mm — 자동 감지) |
| 지원 CAD | **Yuka, Optitex, Gerber, StyleCAD, PAD System** 등 주요 의류 CAD |

---

## 3. 피스(조각) 구성 규칙

### 3.1. 각 피스는 블록(Block)으로 묶기 — 이름은 명확하게

**블록 이름은 "부위명 + 번호"** 형식으로 작성해주세요. 숫자 맨끝에 없으면 1 생략 가능.

**권장 예시**:
```
FRONT BODY 1          (앞판 좌)
FRONT BODY 2          (앞판 우)
BACK BODY             (뒷판)
BACK YOKE             (뒷요크)
SLEEVE 1              (소매 좌)
SLEEVE 2              (소매 우)
SIDE BODY 1           (사이바 좌)
SIDE BODY 2           (사이바 우)
COLLAR                (칼라)
COLLAR BAND           (넥밴드)
CUFF 1                (커프스 좌)
CUFF 2                (커프스 우)
POCKET 1              (주머니 좌)
POCKET 2              (주머니 우)
PLACKET               (플래킷)
WAISTBAND             (허리밴드)
```

> ❌ 피해주세요: `1`, `2`, `BLK_001`, `블록1` 같이 부위 명시 없는 이름

### 3.2. 외곽선은 시접 포함해서 작성

각 피스 외곽선은 **시접을 포함한 재단선**으로 그려주세요.
(시접 제외된 완성선만 있으면 요척이 실제보다 적게 산출됩니다.)

- 외곽선은 반드시 **닫힌 POLYLINE** (closed)
- 한 블록에 재단선 + 완성선 둘 다 있어도 OK — 시스템이 큰 쪽(재단선)을 자동 선택

---

## 4. 피스 메타정보 (필수 4가지)

각 피스(블록) 내부에 **아래 4개 TEXT 엔티티를 반드시** 포함:

```
Piece Name: [부위명 — 영문]
Size: [사이즈]
Quantity: [1벌당 개수]
Material: [재질 코드]
```

**예시** (앞판 좌):
```
Piece Name: FRONT BODY 1
Size: S
Quantity: 1
Material: SELF
```

---

## 5. 부위명 표기 (Piece Name — 영문)

**의류 패턴은 영문 명칭이 업계 표준**입니다. 한글·한자 표기는 피해주세요.

| 부위 | 표기 (권장) | 약어 |
|------|-----------|------|
| 앞판 | FRONT BODY | FR |
| 뒷판 | BACK BODY | BK |
| 뒷요크 | BACK YOKE | BK YK |
| 사이바 | SIDE BODY | SD |
| 소매 | SLEEVE | SLV |
| 칼라 | COLLAR | CLR |
| 넥밴드 | COLLAR BAND | CB |
| 커프스 | CUFF | CFF |
| 허리밴드 | WAISTBAND | WB |
| 주머니 | POCKET | PKT |
| 플래킷 | PLACKET | PLKT |
| 바인딩 | BINDING | BD |
| 스트랩 | STRAP | STR |
| 벨트 | BELT | BLT |

좌/우·다중 피스가 있으면 뒤에 숫자: `FRONT BODY 1`, `FRONT BODY 2`.

---

## 6. 재질 구분 (가장 중요!) ⭐

재질 정보가 잘못되면 원단 요척이 틀어집니다.

### 6.1. 재질 코드

| 재질 | 코드 (권장) | 설명 |
|------|-----------|------|
| **제감/주원단** | `SELF` 또는 `1` | 메인 원단 (겉면) |
| **심지** | `FUSE` 또는 `FN` | 접착심 (칼라·커프스·플래킷 보강용) |
| **안감** | `LINING` 또는 `IL` | 안쪽 라이닝 |
| **배색** | `CONTRAST` 또는 `CT` | 콘트라스트 원단 (다른 색·재질) |
| **주머니감** | `POCKET` 또는 `PK` | 포켓 안감 전용 |
| **마카 제외** | `NON` 또는 `NONE` | 마카에 포함하지 않을 piece (검수용 표시·부자재 등) |

#### 마카 제외 표기 (사장님 명시 2026-05-05)

마카에 포함하지 않을 piece (정합 표시·부자재·라벨 등)는 Material 값을 **`NON`** 으로 표기.

- **이유**: StyleCAD 등 패턴 프로그램의 "마커 제외" 기능을 DXF export 로 직접 전달할 수 없음
  (StyleCAD 마커 제외 ✅ 시 갯수 0 → DXF Quantity:1 로 강제 변환되어 시스템에서 인식 불가)
- **우회**: 기존 Material 키 재사용 + 6번째 코드 `NON` 신설 → 시스템이 자동 마카 제외 처리

예시:
```
Piece Name: DIA30
Material: NON
Quantity: 1
```

시스템 처리:
- 재질 분류: "마카제외"
- 자동 마카 nesting 에서 자동 제외 + `excluded_pieces` 리스트 기록
- 진단 리포트 [5] "마카 제외 piece" 카테고리에 명시

### 6.2. 표기 방법

**방법 A** — Material 메타 TEXT에 코드 직접 기재 (권장)
```
Material: SELF
Material: FUSE
Material: LINING
```

**방법 B** — Piece Name에 접미사로 표기 (Optitex 관행)
```
Piece Name: COLLAR FUSE
Piece Name: CUFF LINING
Piece Name: FRONT CONTRAST
```

### 6.3. ⚠️ 주의

- **심지/배색/안감은 각각 다른 블록**으로 만들어야 함
- 칼라 3겹 (COLLAR + COLLAR FUSE + COLLAR LINING) → 3개 블록으로
- 커프스도 마찬가지 (CUFF + CUFF FUSE + CUFF LINING)

---

## 7. 수량 (Quantity)

**1벌당 실제 재단되는 개수**를 기재.

| 피스 | Quantity |
|------|---------|
| 뒷판 (cut on fold) | 1 |
| 앞판 좌·우 (비대칭) | 1 각각 |
| 소매 | 2 (또는 좌·우 별도 블록 × 1) |
| 커프스 | 2 |
| 칼라 | 1 |
| 주머니 | 좌·우 있으면 2, 하나면 1 |

---

## 8. 사이즈 (Size) — 풀 그레이딩 파일

각 사이즈 피스마다 Size 메타 필수:
```
Size: XS
Size: S
Size: M
Size: L
Size: XL
```

숫자 사이즈(하의)도 지원: `Size: 26`, `Size: 28`, `Size: 30`...

---

## 9. 스케일 박스 (선택)

**50cm × 50cm 정사각형**을 도면 빈 곳에 넣어두면 시스템이 자동 감지해서 계산에서 제외합니다. 없어도 무관.

---

## 10. 체크리스트 (파일 납품 전)

```
[ ] DXF 포맷
[ ] 단위 cm (또는 mm)
[ ] 모든 피스가 블록으로 묶여있음
[ ] 블록 이름이 부위명 + 번호 (예: FRONT BODY 1)
[ ] 외곽선은 시접 포함 (재단선)
[ ] Piece Name (영문) 기재
[ ] Size 기재
[ ] Quantity 기재 (1벌당 실 재단 개수)
[ ] Material 코드 기재 (SELF / FUSE / LINING / CONTRAST / POCKET)
[ ] 블록 이름 중복 없음
```

---

## 11. 샘플 — 피스 1개 구조

```
블록 이름: FRONT BODY 1
  ├─ TEXT: "Piece Name: FRONT BODY 1"
  ├─ TEXT: "Size: S"
  ├─ TEXT: "Quantity: 1"
  ├─ TEXT: "Material: SELF"
  ├─ POLYLINE (closed) — 재단선 (시접 포함)
  └─ POLYLINE (open) — 그레인 라인 / 내부 마크 (선택)
```

---

## 12. 문의

- **담당**: [TD 담당자명 / 이메일]
- **시스템**: https://musinsa-td-fabric-calc.streamlit.app/
- **피드백**: [슬랙 채널 / 이슈 트래커]

---

**버전**: 1.1 · **작성일**: 2026-04-24
