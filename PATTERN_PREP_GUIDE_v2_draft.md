# 원단 요척 산출 시스템 — DXF 표기 규칙 사양서 (v2 draft)

> **대상**: 협력사 패턴사 / 사내 소싱팀
> **목적**: 본 시스템이 DXF 를 정확히 인식하도록 **표기 형식**을 사양 수준으로 명시
> **상태**: v2 초안. 검토 후 v2 정식 승격 결정 (`PATTERN_PREP_GUIDE.md` 덮어쓰기)
> **작성일**: 2026-05-04

---

## 0. 이 문서의 역할

v1.x 가이드는 "권장 사항"으로 작성됐으나 v2 는 **사양서(specification)** 입니다.
시스템 동작과 표기 규칙을 1:1 대응시켜, 협력사가 "이렇게 표기하면 시스템이 어떻게 읽는가"를
코드 수준에서 예측할 수 있게 합니다.

### 0.1. 사장님 절대 원칙 (협력사 필독)

> **"원리·개념·분석·근거로만 일해야 한다. 추측이나 임의 처리는 금지."**

본 시스템은 **DXF 데이터에 명시된 정보만 사용**하며, 누락 시 알고리즘이 추측하지 않습니다.
누락된 정보는 사용자(소싱팀)에게 명시 입력을 요구하거나, 부득이한 fallback 시 ⚠️ 경고를 표시합니다.

### 0.2. 요척 산출 4대 핵심 요소

| # | 요소 | 본 사양서 § |
|---|------|------------|
| 1 | 재질별 분리 마카 (SELF/FUSE/LINING/CONTRAST/POCKET 별도 계산) | §2 |
| 2 | 결방향 (식서/푸서/바이어스) 정확 인식 | §4 |
| 3 | 벌수 + 1WAY/2WAY (`마카 갯수 = Σ(piece.quantity) × n_lay`) | §3, §6 |
| 4 | 본사 검증 데이터는 사용자에게 노출 X (소싱팀은 본사 데이터 미보유) | (UI 정책) |

### 0.3. v2 가 인용하는 raw audit 사례 — MMAPS003.dxf

본 사양서의 ❌ 예시는 **실제 발견된 케이스** 입니다.
근거 파일: [`output/mmaps003_raw_audit_2026-05-04.md`](output/mmaps003_raw_audit_2026-05-04.md)

**MMAPS003 raw audit 요약 (2026-05-04 측정)**:

| 메타 항목 | 보유율 | 결과 |
|---------|--------|------|
| `Piece Name` | 100% (104/104) | ⚠️ 모두 회사 약자 (TS, TT, CAPS, CTT, DM, DTC, LTC, LTH) — 영문 부위명 부재 |
| `Material` | **0%** (0/104) | ❌ 알고리즘 100% fallback "주원단" 강제 |
| `Quantity` | **0%** (0/104) | ❌ 모두 None — Σ(quantity) 계산 불능 |
| 식서 LAYER `"7"` | **100%** (104/104) | ✅ 식서 인식 정상 |

→ MMAPS003 은 "DXF 자체에 정보가 없어 협력사 누락"의 대표 사례. 알고리즘이 잘 동작해도 raw 데이터가 비어있으면 결과 무의미.

---

## §1. 피스명 (Piece Name) — 영문 부위명 표준 어휘집

### 1.1. 표기 형식

```
Piece Name: [영문 부위명] [번호 또는 LEFT/RIGHT 접미사]
```

- 모든 피스(블록) 내부에 `Piece Name:` 으로 시작하는 TEXT 엔티티 1개
- 값은 **공백 구분 영문 단어** + 선택적 번호/방향 접미사
- 한글 부위명 / 한자 / 회사 약자 (TS, TT 등) 는 v2 부터 ❌

### 1.2. 카테고리별 표준 어휘집

#### 상의 (Tops / Shirts)

| 부위 | 표준 표기 | 약어 (허용) |
|------|----------|------------|
| 앞판 | `FRONT_BODY` | `FB` |
| 뒷판 | `BACK_BODY` | `BB` |
| 사이바 (옆판) | `SIDE_BODY` | `SB` |
| 앞요크 | `FRONT_YOKE` | `FY` |
| 뒷요크 | `BACK_YOKE` | `BY` |
| 칼라 (외측) | `COLLAR_OUTER` | `CLR_O` |
| 칼라 (내측, 심지) | `COLLAR_INNER` | `CLR_I` |
| 넥밴드 | `COLLAR_BAND` | `CB` |
| 소매 | `SLEEVE` | `SLV` |
| 커프스 | `CUFF` | `CFF` |
| 플래킷 | `PLACKET` | `PLKT` |
| 주머니 (겉면) | `POCKET_OUTER` | `PKT_O` |
| 주머니 (안감) | `POCKET_BAG` | `PKT_B` |

#### 하의 (Bottoms / Pants) — 슬랙스 13개 부위 (MMAPS003 정리, 2026-05-05 사장님 명시)

| 한국어 | 영문 표준 | 재질 | 비고 |
|--------|----------|------|------|
| 앞판 | `FRONT_BODY` | SELF | |
| 뒤판 | `BACK_BODY` | SELF | |
| 허리단 앞 | `WAISTBAND_FRONT` | SELF | |
| 허리단 뒤 | `WAISTBAND_BACK` | SELF | |
| 앞주머니 손등 묵가데 | `FRONT_POCKET_FACING_UPPER` | SELF | 손등 닿는 면 (몸판 안쪽 덧댐) |
| 앞주머니 손바닥 묵가데 | `FRONT_POCKET_FACING_BOTTOM` | SELF | 손바닥 닿는 면 (주머니감 쪽 덧댐) |
| 마이다데 | `FLY_UNDERLAY` | SELF | 일본어 まえだち, FLY 안쪽 보강 |
| 뎅고제감 | `FLY` | SELF | FLY 본체 (지퍼 덮개) |
| 뒤주머니 손등 묵가데 | `BACK_POCKET_FACING_UPPER` | SELF | |
| 뒤주머니 손바닥 묵가데 | `BACK_POCKET_FACING_BOTTOM` | SELF | |
| 앞주머니감 | `FRONT_POCKET_BAG` | POCKET | |
| 뒤주머니감 | `BACK_POCKET_BAG` | POCKET | |
| 뎅고 시다 | `FLY_FACING` | LINING 또는 POCKET | ❓ 사장님 재질 결정 보류 |

**명명 컨벤션 (사장님 결정, 2026-05-05)**:
- 손등 = `UPPER` / 손바닥 = `BOTTOM`
- 마이다데 = `FLY_UNDERLAY` (FLY 안쪽 보강)
- 뎅고제감 = `FLY` (FLY 본체)
- 뎅고시다 = `FLY_FACING` (FLY 안감)

**기타 하의 부위** (슬랙스 외 / 청바지 / 카고 등 확장 시):

| 부위 | 표준 표기 | 약어 (허용) |
|------|----------|------------|
| 벨트 루프 | `BELT_LOOP` | `BLP` |
| 무릎 안감 | `KNEE_LINING` | `KL` |
| 단 (Hem) | `HEM_TAB` | `HT` |

#### 자켓 / 아우터

| 부위 | 표준 표기 | 약어 (허용) |
|------|----------|------------|
| 앞판 | `FRONT_BODY` | `FB` |
| 뒷판 | `BACK_BODY` | `BB` |
| 라펠 | `LAPEL` | `LPL` |
| 칼라 (재킷) | `JACKET_COLLAR` | `JC` |
| 안주머니 | `INTERNAL_POCKET` | `IPKT` |
| 안감 앞판 | `LINING_FRONT` | `LF` |
| 안감 뒷판 | `LINING_BACK` | `LB` |
| 어깨심 | `SHOULDER_PAD_FUSE` | `SPF` |
| 가슴심 | `CHEST_FUSE` | `CF` |

#### 부속물 (Accessories)

| 부위 | 표준 표기 |
|------|----------|
| 벨트 | `BELT` |
| 스트랩 | `STRAP` |
| 바인딩 | `BINDING` |
| 라벨 자리 | `LABEL_PATCH` |

### 1.3. 좌우 / 다중 피스 접미사

좌우 비대칭이거나 같은 부위가 여러 개인 경우:

- **좌우 페어**: `_LEFT` / `_RIGHT` (영문) — 비대칭일 때만
- **단순 다수**: `_1`, `_2` (좌우 대칭이지만 별도 piece 로 표현할 때)

### 1.4. ✅ 올바른 예시 (실제 DXF TEXT 형태)

```
Piece Name: FRONT_BODY_LEFT
Piece Name: FRONT_BODY_RIGHT
Piece Name: SLEEVE_1
Piece Name: COLLAR_OUTER
Piece Name: POCKET_BAG
Piece Name: WAISTBAND
```

### 1.5. ❌ 틀린 예시 (MMAPS003 에서 실제 발견)

```
Piece Name: MMAPS003 TS        ← 회사 약자, 부위 식별 불가
Piece Name: MMAPS003 TT        ← 동일
Piece Name: MMAPS003 CAPS      ← 동일
Piece Name: MMAPS003 LTC       ← 동일 (총 8개 약자 모두 부위 미상)
Piece Name: 1                   ← 숫자만
Piece Name: 앞판                ← 한글
```

→ MMAPS003 의 8개 unique 피스명(`TS / TT / CAPS / CTT / DM / DTC / LTC / LTH`)은 시스템이 부위를 식별할 수 없어, 시각화·재질 자동 추론·매핑 사전 모두 실패합니다.

### 1.6. 시스템 동작 (한 줄)

`parse_block_metadata_v3()` 가 블록 내 `Piece Name:` TEXT 를 `partition(":")` 으로 분리, CP949 자동 복원 시도 후 `meta["piece_name"]` 에 저장 — 영문 부위명만 §2 재질 자동 추론과 §5 사이즈 그룹핑에 사용 가능.

---

## §2. 재질 (Material) — DXF 어디에 어떻게 적나

### 2.1. 표기 위치 — 블록 내부 TEXT 엔티티

**필수**: 각 블록(피스) 내부에 다음 형식의 TEXT 엔티티 **반드시 1개** 포함.

```
Material: [표준 코드]
```

- TEXT 엔티티 1개 (LAYER 무관 — 모델스페이스/임의 LAYER 모두 OK)
- `Material:` 키 (대소문자 구분 X) + 공백 + 값
- 값은 **영문 표준 코드** 권장 (한글·레거시 코드도 인식하지만 표준 권장)

### 2.2. 표준 코드 (5종)

| 재질 | 표준 코드 | 레거시 허용 코드 |
|------|----------|----------------|
| 주원단 (Self / Main) | `SELF` | `1`, `MAIN`, `FABRIC`, `주원단` |
| 심지 (Fusing / Interfacing) | `FUSE` | `FN`, `FUSING`, `INTERFACING`, `INTERLINING` |
| 안감 (Lining) | `LINING` | `IL`, `INNER LINING`, `LIN` |
| 배색 (Contrast) | `CONTRAST` | `CT`, `CONT` |
| 주머니감 (Pocket fabric) | `POCKET` | `PK`, `PKT` |

### 2.3. ✅ 올바른 예시

```
Material: SELF              ← 주원단 (가장 흔함)
Material: FUSE              ← 심지
Material: LINING            ← 안감
Material: CONTRAST          ← 배색
Material: POCKET            ← 주머니감
```

### 2.4. ❌ 틀린 예시 (MMAPS003 에서 실제 발견)

```
(Material TEXT 자체가 없음)        ← MMAPS003: 104/104 = 100% 누락
Material:                           ← 빈 값
Material: 심지부착 (2겹)            ← 모호 — annotation 메모이지 코드 아님
Material: 안감(주머니용)            ← 괄호 안 정보는 토큰 매칭에서 제외됨
```

→ MMAPS003 은 `material_raw` 보유율 0% (0/104). 결과: **알고리즘이 104 piece 모두 fallback 분기로 강제 "주원단" 분류**. 실제로 안감/심지/주머니감일 가능성이 높지만 시스템은 알 수 없음.

### 2.5. 시스템 동작 (한 줄)

`infer_material_v3()` 가 4단계 우선순위로 분류: **(0) `material_raw` 가 SELF/1/MAIN 명시 → (1) `annotations` 토큰 매칭 (괄호 제외) → (2) `piece_name` 토큰 매칭 → (3) DXF 표준/레거시 코드 매칭 → (4) ⚠️ FALLBACK "주원단"** — Material 표기가 없으면 마지막 분기로 떨어져 잘못된 합산 위험.

### 2.6. 분기 동작 추적 — 협력사 자가 검증

DXF 납품 후 사내 시스템에서 다음을 확인:
- 결과 화면 → 진단 리포트 → "재질 분류 분기 통계"
- `4_FALLBACK_default` 건수 = 0 이어야 정상
- `1` 건이라도 있으면 해당 piece 의 Material 표기 추가 후 재납품

---

## §3. 수량 (Quantity) — 좌우 대칭 / 비대칭 처리

### 3.1. 표기 형식

```
Quantity: [정수]
```

- TEXT 엔티티 1개
- 값은 **1벌당 실제 재단되는 개수** (정수)
- "2 pcs" 같은 단위 부착도 첫 토큰만 정수 변환 시도 (안전)

### 3.2. 좌우 대칭 처리 — 두 가지 방식 (둘 다 허용)

#### 방식 A — 단일 piece + Quantity = 2 (Optitex 관행)

```
Block 이름: SLEEVE
  TEXT: Piece Name: SLEEVE
  TEXT: Quantity: 2          ← 좌우 한 쌍을 2 로 표현
  TEXT: Material: SELF
```

#### 방식 B — 좌우 별도 piece + Quantity = 1 each

```
Block 이름: SLEEVE_LEFT
  TEXT: Piece Name: SLEEVE_LEFT
  TEXT: Quantity: 1

Block 이름: SLEEVE_RIGHT
  TEXT: Piece Name: SLEEVE_RIGHT
  TEXT: Quantity: 1          ← 비대칭이거나 명시적 분리 시 권장
```

### 3.3. 비대칭 piece — **반드시 별도 piece + LEFT/RIGHT 접미사**

좌우 형상이 다른 경우 (예: 사선 도련, 비대칭 칼라):
- ❌ 단일 piece + Quantity=2 + 자동 미러 → **사장님 절대 원칙 위반 (자동 미러 폐기)**
- ✅ 좌우 각각 별도 piece + 각 Quantity=1

### 3.4. ✅ 올바른 예시

```
# 좌우 대칭 — 방식 A
Piece Name: SLEEVE
Quantity: 2

# 좌우 비대칭 — 방식 B 의무
Piece Name: FRONT_BODY_LEFT
Quantity: 1
(다른 블록)
Piece Name: FRONT_BODY_RIGHT
Quantity: 1
```

### 3.5. ❌ 틀린 예시 (MMAPS003 에서 실제 발견)

```
(Quantity TEXT 자체가 없음)        ← MMAPS003: 104/104 = 100% 누락
Quantity:                           ← 빈 값
Quantity: 좌우 한쌍                 ← 정수 아님, 파싱 실패
Quantity: 2 pcs                     ← "2" 만 인식 (다행히 안전 동작)
```

→ MMAPS003 은 Quantity 메타 100% 누락. 결과: `Σ(quantity) = 0` — **마카 갯수 공식 `Σ(quantity) × n_lay` 가 계산 불능**. 시스템은 None 그대로 보존하며 fallback 추측을 하지 않음.

### 3.6. 시스템 동작 (한 줄)

`parse_block_metadata_v3()` 가 `Quantity:` 값을 `int(value)` → 실패 시 `int(value.split()[0])` 순으로 시도하며, 모두 실패하면 `None` 으로 보존(fallback 금지) — 마카 갯수 공식 `Σ(piece.quantity) × n_lay` 에서 None 은 0 으로 처리되어 결과 무의미.

### 3.7. StyleCAD ↔ 시스템 매핑 가설 (❓ 검증 대기, 2026-05-05)

StyleCAD 의 패턴 입력 시 **갯수** + **대칭** 두 필드 조합이 DXF export 로 어떻게 박히는지 가설:

| StyleCAD 입력 | 의미 | 시스템 매핑 (가설) |
|--------------|------|------------------|
| 갯수 1 + 대칭 ✅ | 1개 그렸지만 좌우 미러 2장 | `Quantity: 2`, `Mirror: True` |
| 갯수 2 + 대칭 ❌ | 같은 모양 2장 (미러 X) | `Quantity: 2`, `Mirror: False` |
| 갯수 1 + 대칭 ❌ | 1장 단독 | `Quantity: 1`, `Mirror: False` |
| 갯수 N + 대칭 ❌ | 동일 모양 N장 | `Quantity: N`, `Mirror: False` |

⚠️ **라벨: 가설 (❓)** — StyleCAD DXF export 시 갯수/대칭 메타가 어떤 형태(`Quantity:` TEXT? 별도 키? 블록 복제?)로 박히는지 미검증.
**검증 절차**: 사장님이 MMAPS003 (StyleCAD 표기 완료본) 을 export → 우리 앱에 업로드 → 진단 리포트의 raw 메타로 ✅/❌ 확정.

→ 검증 완료 후 본 §3.7 의 "(가설)" 라벨 제거 + `data/panel_mapping.json` 의 `verification_status` 갱신.

---

## §4. 식서 LAYER — 표준 LAYER명과 LINE 형식

### 4.1. 표기 위치 — 전용 LAYER + LINE 엔티티

**원칙**: 각 피스(블록) 내부에 식서 방향을 나타내는 **LINE 엔티티 1개**.

- 전용 LAYER 에 배치 (해당 LAYER 에는 LINE 만, POLYLINE/TEXT 없음)
- LINE 길이는 최소 **30 mm 이상** 권장 (각도 정확도 확보)
- 한 블록당 LINE 1개 (2개 이상이면 첫 번째 사용)

### 4.2. 표준 LAYER 명 — **둘 다 허용**

| LAYER 명 | 비고 |
|---------|------|
| `"7"` | **현재 협력사 관행** (Yuka/Optitex 28 DXF 모두 LAYER "7" 또는 "5" 사용 — 그대로 허용) |
| `"GRAIN"` / `"STRAIGHT"` / `"GR"` / `"SG"` / `"GL"` | 의미 LAYER 명 (선호) |

→ 둘 중 하나만 일관되게 사용. 한 DXF 안에 LAYER "7" 과 "GRAIN" 혼용 금지.

### 4.3. 식서 / 푸서 / 바이어스 각도 분류

LINE 의 X 축 대비 각도 (mod 180°) 로 자동 분류:

| 각도 범위 | 분류 | 의미 |
|----------|------|------|
| 0~10° 또는 170~180° | `STRAIGHT_GRAIN_X` | 가로 결방향 |
| 80~100° | `STRAIGHT_GRAIN_Y` | 세로 결방향 (의류 표준) |
| 35~55° 또는 125~145° | `BIAS` | 바이어스 (45° 사선) |
| 그 외 | `NONSTANDARD` | ⚠️ 비표준 — 알고리즘 경고 |

(허용 오차: 식서 ±10°, 바이어스 ±10°)

### 4.4. ✅ 올바른 예시

```
LAYER 7 (또는 GRAIN) 에 다음 LINE:
  start = (100, 50)
  end   = (100, 200)        ← 세로 LINE = STRAIGHT_GRAIN_Y (정상 식서)
  length = 150 mm           ← 30 mm 이상 OK
```

### 4.5. ❌ 틀린 예시

```
(식서 LINE 자체가 없음)              ← 협력사 1차 export 누락 빈번
LAYER "0" 의 LINE                     ← 외곽선과 같은 LAYER → 점수제 인식 실패
LAYER "7" 에 POLYLINE 또는 TEXT 혼재  ← "LINE only" +5점 손실 → LAYER 식별 실패
LINE length = 5 mm                    ← 너무 짧아 각도 정확도 저하
LINE 각도 = 23°                       ← NONSTANDARD 분류 (식서/푸서/바이어스 어디에도 안 맞음)
```

### 4.6. 시스템 동작 (한 줄)

`detect_grain_layer()` 가 doc 단위로 LAYER 별 점수 합산 (LINE only +5 / 50% 블록 커버리지 +3 / 각도 anchor 90% 몰림 +2 / 이름 "7"·GRAIN 등 +1) 후 최고점 LAYER 선택, `extract_grain()` 가 해당 LAYER 의 LINE 각도로 STRAIGHT_GRAIN_X/Y/BIAS 분류 — LAYER 인식 실패 또는 LINE 미존재 시 ⚠️ `estimate_grain_from_bbox()` fallback (UI 경고).

---

## §5. 사이즈 (Size) — 그레이딩 케이스 표기

### 5.1. 표기 방식 — 두 가지 (둘 다 허용)

#### 방식 A — `Size:` 메타 TEXT (권장)

각 블록 내부에 다음 TEXT:
```
Size: [사이즈명]
```

#### 방식 B — 블록명 패턴 `BLOCK_X_Y` (Yuka SuperALPHA_Plus 관행)

블록명 끝에 `_사이즈인덱스` 접미사:
```
Block 이름: FRONT_BODY_26     ← 사이즈 26 (인치)
Block 이름: FRONT_BODY_27
Block 이름: FRONT_BODY_28
```

→ 시스템은 동일 prefix 그룹화 후 사이즈 별 piece 매핑.

### 5.2. 사이즈 표기 표준

#### 상의 (영문 알파벳)
```
Size: XS / S / M / L / XL / 2XL / 3XL
```

#### 하의 (인치 — 무신사 스탠다드)
- 남자 (12종): `27 28 29 30 31 32 33 34 35 36 40 42`
- 여자 (11종): `23 24 25 26 27 28 29 30 31 32 34`

```
Size: 32        ← 인치 (단위 표기 X)
```

#### 한국 사이즈 (선택)
```
Size: 90 / 95 / 100 / 105   ← 한국 cm 사이즈
```

### 5.3. 같은 부위 여러 사이즈 구분 — 그레이딩 DXF

#### ✅ 올바른 예시

```
Block 이름: FRONT_BODY_26
  TEXT: Piece Name: FRONT_BODY
  TEXT: Size: 26
  TEXT: Quantity: 1
  TEXT: Material: SELF

Block 이름: FRONT_BODY_27
  TEXT: Piece Name: FRONT_BODY        ← 같은 부위명
  TEXT: Size: 27                       ← 사이즈만 다름
  TEXT: Quantity: 1
  TEXT: Material: SELF

(전 사이즈 반복)
```

→ `Piece Name` 동일 + `Size` 만 다름 → 시스템이 그레이딩 그룹으로 자동 인식.

### 5.4. ❌ 틀린 예시

```
Block 이름: FRONT_BODY_1, FRONT_BODY_2, FRONT_BODY_3
                                  ← 1/2/3 이 사이즈 인덱스인지 좌우 번호인지 모호
                                  ← Size 메타 부재 시 그룹핑 실패
Block 이름: FB26, FB27          ← 약어 + 사이즈 → 부위 식별 불가
Size: 인치 32                    ← 단위 표기 (정수 아님)
```

### 5.5. 시스템 동작 (한 줄)

`detect_sizes()` 가 두 가지 방법으로 사이즈 식별: **(1) `Size:` TEXT 메타 → `SIZE_META` 분기 / (2) 블록명 끝 숫자 패턴 → `BLK_PATTERN` 분기 / (3) 둘 다 없으면 `SINGLE`** — 같은 `piece_name` + 다른 `size` 를 그레이딩 그룹으로 묶어 multi-size 마카에 사용.

---

## §6. 대칭 처리 — 절대 원칙 (자동 미러 X)

### 6.1. 핵심 원칙 — 데이터로만 표현

> **알고리즘은 좌우 자동 미러를 수행하지 않습니다.** 대칭 정보는 반드시 DXF 데이터로 표현해야 합니다.
> (사장님 절대 원칙 — 2026-04-30 명시)

### 6.2. 대칭 표현 방법

#### 방식 A — 좌우 대칭 (형상 동일)

```
Piece Name: SLEEVE
Quantity: 2          ← Quantity = 2 가 곧 "좌우 한 쌍" 의미
Material: SELF
```

→ 시스템: `Σ(quantity)` 에 2 누적, 마카에 같은 polygon 2개 배치.

#### 방식 B — 좌우 비대칭 (형상 다름)

```
# 좌측 piece
Piece Name: FRONT_BODY_LEFT
Quantity: 1

# 우측 piece (별도 블록)
Piece Name: FRONT_BODY_RIGHT
Quantity: 1          ← 형상이 미러가 아닌 별도 폴리곤
```

→ 시스템: 각 폴리곤 그대로 사용, 미러 변환 X.

### 6.3. ❌ 금지 — 자동 미러 의존

```
# 협력사가 좌측만 그리고 "시스템이 알아서 미러" 가정
Piece Name: SLEEVE_LEFT
Quantity: 1                          ← 우측 piece 부재
(주석: "우측은 미러로 처리")           ← ❌ 시스템이 읽지 않음
```

→ v2 시스템은 미러를 추가하지 않으므로, 우측이 마카에서 누락됩니다.

### 6.4. ✅ 올바른 예시

```
# 좌우 대칭 (방식 A)
Block 이름: SLEEVE
  Piece Name: SLEEVE
  Quantity: 2

# 좌우 비대칭 (방식 B)
Block 이름: COLLAR_LEFT
  Piece Name: COLLAR_LEFT
  Quantity: 1
Block 이름: COLLAR_RIGHT
  Piece Name: COLLAR_RIGHT
  Quantity: 1
```

### 6.5. ❌ 틀린 예시 (MMAPS003 에서 실제 발견)

```
Block 이름: MMAPS003 TS_26
  Quantity: (없음)         ← Σ(quantity) = 0
  주석/메모도 없음          ← 좌우 페어 의도 표현 부재
```

→ MMAPS003 은 Quantity 100% 누락이라 좌우 대칭 정보를 알 길이 전혀 없습니다. 시스템은 추측하지 않고 None 보존.

### 6.6. 시스템 동작 (한 줄)

이전 버전의 `mirror_pieces.py` 자동 미러는 **2026-04-30 폐기**됨 — 시스템은 DXF 의 `Quantity` 값과 별도 piece 분리만으로 좌우 정보를 인식하며, `마카 갯수 = Σ(piece.quantity) × n_lay` 공식에 따라 좌우 처리.

---

## §7. 금지 사항 (Anti-patterns)

### 7.1. 모호한 annotation 사용

❌ `Annotation: 심지부착 (2겹)` — 메모성 텍스트는 토큰 매칭에서 괄호 내용 제거되고 substring 매칭 안 됨 → 분류 실패.

✅ `Material: FUSE` — 코드로 명시.

### 7.2. 한글 부위명

❌ `Piece Name: 앞판`, `Piece Name: 뒷요크`

✅ `Piece Name: FRONT_BODY`, `Piece Name: BACK_YOKE`

→ 사유: 영문 표준 어휘집(§1.2)에서만 카테고리 자동 추론 가능. 한글은 매핑 사전 의존.

### 7.3. 회사 약자 (TS, TT, CAPS 등)

❌ MMAPS003 의 8개 약자 (`TS / TT / CAPS / CTT / DM / DTC / LTC / LTH`)

→ 시스템이 약자에서 부위 추정 X. §1 표준 어휘집의 영문 부위명만 사용.

### 7.4. 자동 미러 의존

❌ "좌측만 그리고 우측은 미러" 가정 (주석으로만 표현)

✅ Quantity=2 (방식 A) 또는 LEFT/RIGHT 별도 piece (방식 B) — §6 참조.

### 7.5. 식서 LINE 누락 / LAYER 혼란

❌ 식서 LINE 자체가 없음, 외곽선과 같은 LAYER 의 LINE, 너무 짧은 LINE (< 30 mm), 비표준 각도 (23°, 67°)

✅ 전용 LAYER ("7" 또는 "GRAIN") 의 LINE 1개, 30 mm 이상, 0°/45°/90°/135° 부근 — §4 참조.

### 7.6. Material 표기 누락 (가장 심각)

❌ `Material:` TEXT 자체가 없음 → MMAPS003 처럼 100% fallback "주원단" 강제

✅ 모든 piece 에 `Material: [표준 코드]` 명시 (§2.2 표 참조)

### 7.7. Quantity 표기 누락

❌ `Quantity:` TEXT 자체가 없음 → Σ(quantity) = 0, 마카 갯수 공식 무의미

✅ 모든 piece 에 `Quantity: [정수]` 명시 (§3 참조)

### 7.8. 같은 piece_name 중복

❌ 좌우 비대칭인데 둘 다 `Piece Name: FRONT_BODY` (구분 불능)

✅ `FRONT_BODY_LEFT` / `FRONT_BODY_RIGHT` 또는 `FRONT_BODY_1` / `FRONT_BODY_2`

### 7.9. 본사 검증 데이터 사용자 노출 (UI 정책)

❌ 결과 화면 / PDF / Excel 에 본사 비교 % 또는 갭 표시

✅ 협력사·소싱팀은 본사 데이터 미보유. 비교는 내부 검증용 만 (코드/CSV 산출물).

---

## §7.5. 비율 검증 박스 (필수) — v2 신설 (사장님 본질 2026-05-07)

### 7.5.1. 협력사 디폴트 항목

**모든 DXF 파일에 50cm × 50cm 정사각형 박스 piece 1개 필수 포함.**

| 메타 | 값 | 설명 |
|------|------|------|
| **Piece Name** | `SCALE_BOX` ⭐ | 권장 (자동 검출 우선순위 1) |
|  | `50CM_X_50CM` / `50CM` / `비율박스` | 대안 키워드 |
| **Material** | `NON` | 마카 제외 (필수 — §2.2 5종 + NON) |
| **bbox** | **50 cm × 50 cm 정사각형** ⭐ | **단위 cm 명시** (mm/inch 아님) |

### 7.5.2. 의도

DXF 좌표 단위가 cm/mm/inch 어느 것이든 박스 측정값으로 시스템이 자동 비율 도출 +
모든 piece 좌표/사이즈/면적 보정.

| 박스 측정 | 단위 가설 | 자동 보정 |
|---|---|---|
| **50.0 ± 0.5 cm** | cm (정상) | 보정 불필요 ✅ |
| **19.685 cm** | inch DXF (50/2.54) | × 2.54 자동 적용 |
| **5.0 cm** | mm DXF (50/10) | × 10.0 자동 적용 |

### 7.5.3. ✅ 올바른 예시

```
블록: SCALE_BOX_REF
├─ TEXT: "Piece Name: SCALE_BOX"
├─ TEXT: "Material: NON"
└─ POLYLINE: 4 vertex 닫힌 정사각형, 50cm × 50cm
```

### 7.5.4. ❌ 틀린 예시

- 박스 누락 → 시스템 휴리스틱 단위 추정 (정확도 ↓)
- 사이즈 50 inch → 26.42 cm (의도와 다름) — **사장님이 cm 명시했어도 export 옵션이 inch면 좌표값이 다름**
- Material:NON 누락 → 일반 piece 로 마카에 포함됨 (요척 오류)

→ **사용자 입력은 cm 의도, DXF 좌표는 inch** 인 케이스가 가장 흔한 적발 사례 (MMAPS003 raw 검증 2026-05-07).

---

## §8. 협력사 자가 검증 체크리스트

DXF 납품 전 다음을 확인:

```
[ ] 모든 piece 가 블록(Block) 으로 묶여있다
[ ] 모든 piece 에 Piece Name TEXT — 영문 부위명 (§1.2 표준 어휘집)
[ ] 모든 piece 에 Material TEXT — 표준 코드 (§2.2 5종)
[ ] 모든 piece 에 Quantity TEXT — 정수
[ ] 그레이딩이면 모든 piece 에 Size TEXT 또는 블록명 _사이즈 접미사
[ ] 모든 piece 에 식서 LINE — 전용 LAYER ("7" 또는 "GRAIN") + 30 mm 이상
[ ] 외곽선은 닫힌 POLYLINE — 시접 포함된 재단선
[ ] 좌우 비대칭은 LEFT/RIGHT 별도 piece (자동 미러 의존 X)
[ ] 한글 부위명 X / 회사 약자 (TS, TT 등) X
[ ] 같은 piece_name 중복 X
[ ] **50cm × 50cm 비율 검증 박스 (Piece Name: SCALE_BOX, Material: NON) 1개** ⭐ v2 필수
```

→ 사내 시스템 업로드 후 **DXF 진단 리포트** (`dxf_diagnosis.py` 자동 생성) 의 4대 카테고리가 모두 ✅ 인지 확인. ⚠️/❌ 항목이 있으면 표기 보강 후 재납품.

---

## §9. 부록 — 시스템이 보는 piece 1개의 raw 구조

```
Block 이름: FRONT_BODY_LEFT
├─ TEXT (LAYER 무관): "Piece Name: FRONT_BODY_LEFT"
├─ TEXT (LAYER 무관): "Size: 32"
├─ TEXT (LAYER 무관): "Quantity: 1"
├─ TEXT (LAYER 무관): "Material: SELF"
├─ LWPOLYLINE (closed, LAYER "0" 등): 외곽선 — 시접 포함 재단선
└─ LINE (LAYER "7" 또는 "GRAIN"): 식서 방향 표시 — 30 mm 이상
```

각 엔티티 타입은:
- TEXT 1개씩 4종 → `parse_block_metadata_v3()` 가 `partition(":")` 으로 키:값 추출
- LWPOLYLINE → `find_outline()` 가 면적 큰 닫힌 polygon 선택, `polyline_to_shapely()` 로 변환
- LINE → `extract_grain()` 가 각도 mod 180° 로 STRAIGHT_GRAIN_X/Y/BIAS 분류

---

## §10. v1.x → v2 변경 요약

| 항목 | v1.4 | v2 (이 문서) |
|------|------|--------------|
| 톤 | 권장 사항 | 사양서 (코드 동작과 1:1 대응) |
| 부위명 어휘집 | 14개 (단순 표) | 카테고리별 (상의/하의/자켓/부속) 분류 + 약어 |
| Material 표기 | 5종 코드 | 5종 코드 + 분기 동작 추적 (§2.5) |
| Quantity 처리 | 단순 안내 | 좌우 대칭 방식 A/B 명시 + 자동 미러 폐기 §6 |
| 식서 LAYER | "7" 권장 | "7" / "GRAIN" 둘 다 허용 (점수제 인식) |
| 사이즈 | 표기 종류만 안내 | `SIZE_META` / `BLK_PATTERN` 두 분기 명시 |
| 대칭 처리 | 미명시 | §6 단독 섹션 — 절대 원칙 명시 |
| 금지 사항 | 분산 | §7 단독 섹션 (9개 anti-pattern) |
| MMAPS003 인용 | 없음 | 모든 ❌ 예시에 raw audit 인용 |

---

## §11. 검토 / 승격 절차

1. **검토자**: 사장님 (사양 채택 결정)
2. **검증 대상**: 사내 28 DXF 중 매핑 사전 누적 데이터로 시범 적용
3. **승격 조건**:
   - 본 v2 draft 의 § 1~7 표기 규칙에 이의 없음
   - 카테고리별 어휘집 (§1.2) 의 부위명이 실무 명칭과 일치
   - 협력사 배포 전 PPT 갱신 (`패턴_준비_가이드.pptx`)
4. **승격 시**: `PATTERN_PREP_GUIDE.md` 덮어쓰기 + git 커밋 메시지에 "v2 승격" 명시

---

**버전**: 2.0 draft · **작성일**: 2026-05-04
**근거 데이터**: `output/mmaps003_raw_audit_2026-05-04.md`
**상위 문서**: `PROJECT_STATUS.md` (§4대 핵심 요소, §절대 원칙)
